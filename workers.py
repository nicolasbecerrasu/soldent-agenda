import os
import re
import uuid
import json
import random
import time as time_mod
from datetime import datetime, timedelta, timezone, time
from typing import Optional
from zoneinfo import ZoneInfo
import httpx
from sqlalchemy import func, select, text
from sqlalchemy.exc import (
    DatabaseError,
    DataError,
    IntegrityError,
    InternalError,
    OperationalError,
    ProgrammingError
)
from sqlalchemy.orm import Session

from config import settings
from database import (
    AuditoriaCita,
    Cita,
    NotificacionEnviada,
    Paciente,
    SyncOutbox,
    Tratamiento,
    WhatsAppSession,
    WorkerHeartbeat
)
from routers.ortodoncia import _obtener_pacientes_ortodoncia_calculados
from security import (
    es_telefono_bolivia_valido,
    hash_token,
    normalizar_telefono
)
from services.google_calendar import (
    generar_token_respuesta,
    get_calendar_service,
    registrar_auditoria
)

from types import MappingProxyType

ultimo_resumen_manana: Optional[str] = None
ultimo_resumen_tarde: Optional[str] = None

# Lista blanca inmutable de tipos de excepción autorizados para telemetría
SAFE_ALLOWED_EXCEPTION_TYPES = frozenset({
    "ConnectTimeout",
    "ConnectError",
    "ReadTimeout",
    "WriteTimeout",
    "PoolTimeout",
    "TimeoutException",
    "HTTPStatusError",
    "HttpError",
    "IntegrityError",
    "OperationalError",
    "DatabaseError",
    "ProgrammingError",
    "DataError",
    "InternalError",
    "RuntimeError",
    "ValueError",
    "TypeError",
    "KeyError",
    "AttributeError",
    "NoneType",
    "ControlledOperationalException"
})

# Catálogo inmutable de solo lectura garantizado por MappingProxyType
SAFE_ERROR_CATALOG = MappingProxyType({
    "TIMEOUT_EXCEEDED": "Tiempo de espera agotado en comunicacion de red",
    "CONNECTION_TIMEOUT": "Tiempo de espera agotado al intentar conectar con el servicio",
    "CONNECTION_ERROR": "Error de conexion o resolucion de red con el servicio externo",
    "CONNECTION_REFUSED": "Servicio de destino no disponible o conexion rechazada activamente",
    "HTTP_API_ERROR": "Error en respuesta de API de servicio externo",
    "DATABASE_UNAVAILABLE": "Base de datos temporalmente no disponible por conectividad",
    "DATABASE_OPERATIONAL_ERROR": "Fallo operativo en ejecucion de base de datos o contencion de recursos",
    "DATABASE_GENERIC_ERROR": "Fallo reportado por el motor de base de datos",
    "DATA_INTEGRITY_ERROR": "Violacion de restriccion de integridad de datos en almacenamiento",
    "DATABASE_SCHEMA_OR_QUERY_ERROR": "Error en sentencia SQL o esquema de base de datos",
    "DATA_TYPE_MISMATCH_ERROR": "Datos incompatibles con el tipo de columna en base de datos",
    "DATABASE_INTERNAL_ERROR": "Fallo interno reportado por el motor de base de datos",
    "PERSISTENCE_ERROR": "Error de persistencia de estado de infraestructura",
    "GATEWAY_ERROR": "Error reportado por pasarela de mensajeria",
    "GENERIC_ERROR": "Fallo operativo interno controlado"
})

def sanitizar_error(e) -> dict:
    """
    Extrae metadatos seguros de diagnóstico sin exponer URLs privadas, tokens ni datos personales.
    Contrato garantizado: Siempre devuelve un dict con 'error_type', 'error_code' y 'message'.
    """
    if e is None:
        return {
            "error_type": "NoneType",
            "error_code": "GENERIC_ERROR",
            "message": f"{SAFE_ERROR_CATALOG['GENERIC_ERROR']} (NoneType)"
        }
    if not isinstance(e, BaseException):
        return {
            "error_type": "ControlledOperationalException",
            "error_code": "GENERIC_ERROR",
            "message": f"{SAFE_ERROR_CATALOG['GENERIC_ERROR']} (ControlledOperationalException)"
        }
    try:
        raw_type = e.__class__.__name__
        # Validación estricta contra lista blanca de tipos de excepción permitidos
        err_type = raw_type if raw_type in SAFE_ALLOWED_EXCEPTION_TYPES else "ControlledOperationalException"
        err_code = "GENERIC_ERROR"

        # 1. Fallos de conexión previos al socket/despacho: ConnectTimeout vs ConnectError
        if isinstance(e, httpx.ConnectTimeout) or raw_type == "ConnectTimeout":
            err_code = "CONNECTION_TIMEOUT"
        elif isinstance(e, httpx.ConnectError) or raw_type == "ConnectError":
            err_code = "CONNECTION_ERROR"
        # 2. Timeouts en tránsito o en espera de respuesta (ReadTimeout, WriteTimeout, PoolTimeout)
        elif isinstance(e, (httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout, httpx.TimeoutException)) or raw_type in ("ReadTimeout", "WriteTimeout", "PoolTimeout", "TimeoutException"):
            err_code = "TIMEOUT_EXCEEDED"
        # 3. Errores HTTP de respuesta de APIs externas (httpx.HTTPStatusError, googleapiclient.errors.HttpError)
        elif isinstance(e, httpx.HTTPStatusError) or raw_type in ("HTTPStatusError", "HttpError"):
            err_code = "HTTP_API_ERROR"
        # 4. Violaciones de integridad de base de datos (claves únicas, foráneas, check constraints)
        elif isinstance(e, IntegrityError) or raw_type == "IntegrityError":
            err_code = "DATA_INTEGRITY_ERROR"
        # 5. Errores de sintaxis SQL o discrepancias de esquema (ProgrammingError)
        elif isinstance(e, ProgrammingError) or raw_type == "ProgrammingError":
            err_code = "DATABASE_SCHEMA_OR_QUERY_ERROR"
        # 6. Datos incompatibles con el tipo esperado de columna (DataError)
        elif isinstance(e, DataError) or raw_type == "DataError":
            err_code = "DATA_TYPE_MISMATCH_ERROR"
        # 7. Fallo interno reportado por el motor de base de datos (InternalError)
        elif isinstance(e, InternalError) or raw_type == "InternalError":
            err_code = "DATABASE_INTERNAL_ERROR"
        # 8. Fallos de OperationalError: distinguir fallo de conectividad vs contención de recursos / operativo
        elif isinstance(e, OperationalError) or raw_type == "OperationalError":
            e_str = str(e).lower()
            if any(term in e_str for term in (
                "could not connect", "connection refused", "connection closed",
                "connection reset", "broken pipe", "server closed",
                "timeout expired", "is not accepting connections", "network is unreachable"
            )):
                err_code = "DATABASE_UNAVAILABLE"
            else:
                err_code = "DATABASE_OPERATIONAL_ERROR"
        # 9. Fallos genéricos de DatabaseError no clasificados en sub-clases previas
        elif isinstance(e, DatabaseError) or raw_type == "DatabaseError":
            err_code = "DATABASE_GENERIC_ERROR"

        safe_msg = f"{SAFE_ERROR_CATALOG.get(err_code, SAFE_ERROR_CATALOG['GENERIC_ERROR'])} ({err_type})"
        return {"error_type": err_type, "error_code": err_code, "message": safe_msg}
    except Exception:
        return {
            "error_type": "ControlledOperationalException",
            "error_code": "GENERIC_ERROR",
            "message": f"{SAFE_ERROR_CATALOG['GENERIC_ERROR']} (ControlledOperationalException)"
        }

def enmascarar_telefono(tel: Optional[str]) -> str:
    """Enmascara el teléfono para logs operativos, p. ej. +59178472875 -> +591***2875."""
    if not tel:
        return "[sin-telefono]"
    tel_str = str(tel).strip()
    if len(tel_str) <= 4:
        return "***"
    return f"{tel_str[:4]}***{tel_str[-4:]}"

def enmascarar_nombre(nom: Optional[str]) -> str:
    """Enmascara el nombre para logs operativos, p. ej. 'Juan Perez' -> 'J*** P***'."""
    if not nom:
        return "[anonimo]"
    partes = str(nom).strip().split()
    enmascaradas = [f"{p[0]}***" if len(p) > 1 else p for p in partes]
    return " ".join(enmascaradas)

def worker_control_mensual_ortodoncia(db: Session):
    tz_bol = ZoneInfo(getattr(settings, "TZ_CONSULTORIO", "America/La_Paz"))
    ahora_bol = datetime.now(tz_bol)
    if ahora_bol.weekday() <= 4 and ahora_bol.hour == 10 and 12 <= ahora_bol.minute <= 18:
        try:
            res = _obtener_pacientes_ortodoncia_calculados(db)
            vencidos = [p for p in res["pacientes"] if p["estado_control"] == "vencido" and p["puede_recordar"]]
            if vencidos:
                print(f"🦷 [Worker Ortodoncia] Detectados {len(vencidos)} pacientes con control mensual vencido.")
        except Exception as err:
            safe_err = sanitizar_error(err)["message"]
            print(f"⚠️ [Worker Ortodoncia Error]: {safe_err}")

def worker_sync_outbox(db: Session):
    ahora = datetime.now(timezone.utc)
    pendientes = db.execute(
        select(SyncOutbox)
        .where(SyncOutbox.estado == "pendiente", SyncOutbox.proximo_intento <= ahora)
        .order_by(SyncOutbox.created_at)
        .limit(50)
    ).scalars().all()
    for outbox in pendientes:
        try:
            service = get_calendar_service()
            event_id = outbox.payload.get("google_event_id")

            # 1. Eliminación de eventos en Google Calendar
            if outbox.accion == "delete":
                if event_id:
                    try:
                        service.events().delete(calendarId=settings.CALENDAR_ID, eventId=event_id).execute()
                    except Exception as del_err:
                        if "404" not in str(del_err) and "410" not in str(del_err):
                            raise del_err
                outbox.estado, outbox.procesado_en = "completado", ahora
                db.commit()
                continue

            # 2. Creación o Actualización de eventos
            inicio_iso = outbox.payload.get("inicio")
            fin_iso = outbox.payload.get("fin")
            if not event_id or not inicio_iso or not fin_iso:
                cita_db = db.get(Cita, outbox.entidad_id)
                if cita_db:
                    if not event_id and cita_db.google_event_id:
                        event_id = cita_db.google_event_id
                    if not inicio_iso and cita_db.inicio:
                        inicio_iso = cita_db.inicio.isoformat()
                    if not fin_iso and cita_db.fin:
                        fin_iso = cita_db.fin.isoformat()

            if not inicio_iso or not fin_iso:
                outbox.estado, outbox.ultimo_error = "fallido", "Falta fecha de inicio o fin en payload"
                outbox.procesado_en = ahora
                db.commit()
                continue

            event_body = {
                "summary": f"Cita: {outbox.payload.get('paciente_nombre', 'Paciente')}",
                "start": {"dateTime": inicio_iso, "timeZone": settings.TZ_CONSULTORIO},
                "end": {"dateTime": fin_iso, "timeZone": settings.TZ_CONSULTORIO}
            }
            
            if outbox.accion == "create":
                res = service.events().insert(calendarId=settings.CALENDAR_ID, body=event_body).execute()
                db.execute(text("UPDATE agenda.citas SET google_event_id=:gid WHERE id=:cid"), {"gid": res["id"], "cid": outbox.entidad_id})
                outbox.estado, outbox.procesado_en = "completado", ahora
            elif outbox.accion == "update" and event_id:
                service.events().update(calendarId=settings.CALENDAR_ID, eventId=event_id, body=event_body).execute()
                outbox.estado, outbox.procesado_en = "completado", ahora
            db.commit()
        except Exception as e:
            outbox.intentos += 1
            outbox.ultimo_error = str(e)
            if outbox.intentos >= outbox.max_intentos:
                outbox.estado, outbox.procesado_en = "fallido", ahora
            else:
                outbox.proximo_intento = ahora + timedelta(minutes=2 ** outbox.intentos)
            db.commit()

def worker_sync_inverso_google(db: Session):
    """
    Sondeo periódico de Google Calendar (iPhone / Google Calendar -> App Web)
    """
    try:
        service = get_calendar_service()
    except Exception as e:
        safe_err = sanitizar_error(e)["message"]
        print(f"[Sync Inverso Google] Error al obtener credenciales de Google Calendar: {safe_err}")
        return

    ahora_utc = datetime.now(timezone.utc)
    time_min = (ahora_utc - timedelta(days=30)).isoformat()
    time_max = (ahora_utc + timedelta(days=60)).isoformat()

    try:
        try:
            res = service.events().list(
                calendarId=settings.CALENDAR_ID,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
                maxResults=250
            ).execute()
        except Exception:
            res = service.events().list(
                calendarId=settings.CALENDAR_ID,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                maxResults=250
            ).execute()

        eventos = res.get("items", [])
        if not eventos:
            return

        tz_bol = ZoneInfo(settings.TZ_CONSULTORIO)

        for evento in eventos:
            gid = evento.get("id")
            if not gid:
                continue

            status = evento.get("status")
            cita = db.execute(select(Cita).where(Cita.google_event_id == gid)).scalar_one_or_none()

            # 1. Evento eliminado o cancelado en Google Calendar
            if status == "cancelled":
                if cita and cita.estado != "cancelada":
                    print(f"🗑️ [Sync Inverso Google] Cita cancelada en Google Calendar detectada: ID {cita.id}")
                    cita.estado = "cancelada"
                    cita.updated_at = ahora_utc
                    registrar_auditoria(db, cita.id, "doctora_iphone", "cancelar_google", antes={"estado": cita.estado}, despues={"estado": "cancelada"})
                    db.commit()
                continue

            # 2. Extraer horarios de inicio y fin
            start_data = evento.get("start", {})
            end_data = evento.get("end", {})
            inicio_raw = start_data.get("dateTime") or start_data.get("date")
            fin_raw = end_data.get("dateTime") or end_data.get("date")

            if not inicio_raw or len(inicio_raw) == 10:
                continue

            try:
                dt_inicio = datetime.fromisoformat(inicio_raw.replace("Z", "+00:00"))
                if dt_inicio.tzinfo is None:
                    dt_inicio = dt_inicio.replace(tzinfo=tz_bol)
            except Exception:
                continue

            if fin_raw and len(fin_raw) > 10:
                try:
                    dt_fin = datetime.fromisoformat(fin_raw.replace("Z", "+00:00"))
                    if dt_fin.tzinfo is None:
                        dt_fin = dt_fin.replace(tzinfo=tz_bol)
                except Exception:
                    dt_fin = dt_inicio + timedelta(minutes=30)
            else:
                dt_fin = dt_inicio + timedelta(minutes=30)

            summary = (evento.get("summary") or "Consulta Dra. Pamela").strip()
            if summary in ("9⁹99999", "Día del Trabajo", "FERIADO") or "cumpleaño" in summary.lower():
                continue

            # 3. Cita existente: Actualizar horario si fue reprogramada en el iPhone
            if cita:
                c_ini_utc = cita.inicio.astimezone(timezone.utc) if cita.inicio.tzinfo else cita.inicio.replace(tzinfo=timezone.utc)
                dt_ini_utc = dt_inicio.astimezone(timezone.utc)
                if abs((c_ini_utc - dt_ini_utc).total_seconds()) > 60:
                    print(f"🔄 [Sync Inverso Google] Reprogramando cita {cita.id} desde iPhone a {dt_inicio}")
                    cita.inicio = dt_inicio
                    cita.fin = dt_fin
                    cita.updated_at = ahora_utc
                    registrar_auditoria(db, cita.id, "doctora_iphone", "reprogramar_google", despues={"inicio": str(dt_inicio), "fin": str(dt_fin)})
                    db.commit()
                continue

            # 3.5. Comprobar si esta cita fue eliminada explícitamente en el sistema
            ya_eliminado = db.execute(
                select(AuditoriaCita).where(
                    AuditoriaCita.accion == "eliminar",
                    text("antes->>'google_event_id' = :gid").params(gid=gid)
                )
            ).scalars().first()

            if not ya_eliminado:
                ya_eliminado = db.execute(
                    select(SyncOutbox).where(
                        SyncOutbox.accion == "delete",
                        text("payload->>'google_event_id' = :gid").params(gid=gid)
                    )
                ).scalars().first()

            if ya_eliminado:
                print(f"🛑 [Sync Inverso Google] Evento {gid} fue eliminado voluntariamente de la agenda. Ignorando re-importación.")
                if status != "cancelled":
                    try:
                        service.events().delete(calendarId=settings.CALENDAR_ID, eventId=gid).execute()
                        print(f"🗑️ [Sync Inverso Google] Evento huérfano {gid} purgado de Google Calendar.")
                    except Exception:
                        pass
                continue

            # 4. Nueva cita creada manualmente en el iPhone: Importar a agenda.citas
            nombre_paciente = summary
            if summary.lower().startswith("cita:"):
                nombre_paciente = summary[5:].strip()
            elif summary.lower().startswith("cita "):
                nombre_paciente = summary[5:].strip()
            elif summary.lower().startswith("consulta "):
                nombre_paciente = summary[9:].strip()

            descripcion = evento.get("description", "") or ""
            texto_busqueda = f"{summary} {descripcion}"
            m_tel = re.search(r"(?:(?:\+?591\s*)?([67]\d{7}))", texto_busqueda)
            tel_extraido = normalizar_telefono(m_tel.group(0)) if m_tel else None

            if m_tel and m_tel.group(0) in nombre_paciente:
                nombre_paciente = nombre_paciente.replace(m_tel.group(0), "").strip()
            if not nombre_paciente:
                nombre_paciente = "Paciente iPhone"

            paciente = None
            if tel_extraido:
                paciente = db.execute(select(Paciente).where(Paciente.telefono == tel_extraido)).scalar_one_or_none()
            if not paciente:
                paciente = db.execute(
                    select(Paciente).where(func.lower(Paciente.nombre) == nombre_paciente.lower())
                ).scalars().first()

            if not paciente:
                nombre_limpio = re.sub(r"(?i)\s+(ort|ortodoncia|control|15d|profi|profilaxis|rest|restauracion|impresion|placa|inferior|superior)\b", "", nombre_paciente).strip()
                if nombre_limpio:
                    paciente = db.execute(
                        select(Paciente).where(func.lower(Paciente.nombre) == nombre_limpio.lower())
                    ).scalars().first()

            if not paciente:
                paciente = Paciente(
                    nombre=nombre_paciente,
                    telefono=tel_extraido,
                    notas="Registrado automáticamente desde Google Calendar (iPhone de la Doctora)"
                )
                db.add(paciente)
                db.flush()

            if not paciente.telefono:
                nom_base = re.sub(r"(?i)\s+(ort|ortodoncia|control|15d|profi|profilaxis|rest|restauracion|impresion|placa|inferior|superior)\b", "", paciente.nombre).strip().lower()
                candidato = db.execute(
                    select(Paciente).where(
                        Paciente.telefono.isnot(None),
                        func.lower(Paciente.nombre).like(f"%{nom_base}%")
                    )
                ).scalars().first()
                if candidato and candidato.telefono:
                    paciente.telefono = candidato.telefono
                    print(f"📞 [Sync Inverso Google] Teléfono {enmascarar_telefono(candidato.telefono)} vinculado a paciente '{enmascarar_nombre(paciente.nombre)}'")
                    db.flush()

            texto_eval = f"{summary} {descripcion}".lower()
            trat = None
            if any(k in texto_eval for k in ["tercer molar", "tercel molar", "molar", "cordal", "muela del juicio"]):
                trat = db.execute(select(Tratamiento).where(Tratamiento.nombre.ilike("%tercer molar%"))).scalars().first()
            elif any(k in texto_eval for k in ["implante", "implan"]):
                trat = db.execute(select(Tratamiento).where(Tratamiento.nombre.ilike("%implante%"))).scalars().first()
            elif any(k in texto_eval for k in ["ortodoncia", "bracket", "control ort", " ort ", "ajuste"]) or texto_eval.endswith(" ort"):
                trat = db.execute(select(Tratamiento).where(Tratamiento.nombre.ilike("%ortodoncia%"))).scalars().first()
            elif any(k in texto_eval for k in ["limpieza", "profilaxis", "destartraje", "sarro"]):
                trat = db.execute(select(Tratamiento).where(Tratamiento.nombre.ilike("%limpieza%"))).scalars().first()
            elif any(k in texto_eval for k in ["obturacion", "obturación", "resina", "curacion", "curación"]):
                trat = db.execute(select(Tratamiento).where(Tratamiento.nombre.ilike("%resina%"))).scalars().first()
            elif any(k in texto_eval for k in ["extraccion", "extracción"]):
                trat = db.execute(select(Tratamiento).where(Tratamiento.nombre.ilike("%extracción%"))).scalars().first()
            elif any(k in texto_eval for k in ["endodoncia", "conducto"]):
                trat = db.execute(select(Tratamiento).where(Tratamiento.nombre.ilike("%endodoncia%"))).scalars().first()
            elif any(k in texto_eval for k in ["blanqueamiento", "aclaramiento"]):
                trat = db.execute(select(Tratamiento).where(Tratamiento.nombre.ilike("%blanqueamiento%"))).scalars().first()

            if not trat:
                trat = db.execute(
                    select(Tratamiento).where(Tratamiento.nombre.ilike("%Consulta y Diagnóstico%"))
                ).scalars().first()
            if not trat:
                trat = db.execute(
                    select(Tratamiento).where(Tratamiento.activo == True).order_by(Tratamiento.id)
                ).scalars().first()
            if not trat:
                trat = Tratamiento(nombre="Consulta y Diagnóstico", duracion_min=30, precio=100.0)
                db.add(trat)
                db.flush()

            nueva_cita = Cita(
                paciente_id=paciente.id,
                tratamiento_id=trat.id,
                inicio=dt_inicio,
                fin=dt_fin,
                estado="confirmada",
                motivo=summary,
                notas="Sincronizado automáticamente desde iPhone (Google Calendar)",
                google_event_id=gid,
                recordatorio_enviado=(dt_inicio <= ahora_utc)
            )
            generar_token_respuesta(db, nueva_cita)

            try:
                db.add(nueva_cita)
                db.flush()
                registrar_auditoria(db, nueva_cita.id, "doctora_iphone", "crear_desde_google", despues={"inicio": str(dt_inicio), "estado": "confirmada"})
                db.commit()
                print(f"✅ [Sync Inverso Google] Cita de iPhone importada con éxito: '{enmascarar_nombre(nombre_paciente)}' ({dt_inicio.strftime('%d/%m/%Y %H:%M')})")
            except IntegrityError as err_int:
                db.rollback()
                print(f"⚠️ [Sync Inverso Google] Aviso de colisión al importar cita de iPhone: {err_int.__class__.__name__}")
            except Exception as err_ins:
                db.rollback()
                print(f"⚠️ [Sync Inverso Google] Error al guardar cita de iPhone: {err_ins.__class__.__name__}")

    except Exception as e:
        safe_err = sanitizar_error(e)["message"]
        print(f"[Sync Inverso Google] Error en el ciclo de sondeo: {safe_err}")

def worker_recordatorios(
    db: Session,
    forzar: bool = False,
    filtro: Optional[str] = None,
    cita_id_especifica: Optional[uuid.UUID] = None
) -> list[dict]:
    """
    Envía recordatorios automáticos por WhatsApp con reglas oficiales de Soldent:
    1. BLOQUEO ESTRICTO DE MADRUGADA (22:00 a 07:29):
       En este horario el bot NUNCA envía mensajes automáticos.
       (Excepción: si forzar=True porque la Dra. Pamela o Nicolás lo solicitaron).
    2. VENTANA NOCTURNA (20:30 a 22:00):
       Citas tempranas de mañana (<= 10:30 AM) se envían con antelación tranquila
       para evitar molestar en la madrugada.
    3. RESCATE DE LAS 07:30 AM:
       Citas de la mañana de hoy no enviadas anoche se envían a partir de las 07:30 AM.
    4. VENTANA DIURNA ESTÁNDAR (07:30 a 22:00):
       Citas de media mañana y tarde se envían exactamente con 3 horas de anticipación.
    5. CONTROL MANUAL (forzar=True):
       Permite a la Dra. Pamela o Nicolás enviar recordatorios a cualquier hora.
    """
    # 0. RESTRICCIÓN DE SEGURIDAD ESTRICTA PARA FORZAR ENVÍO:
    # Se prohíbe terminantemente forzar=True sin especificar una cita_id_especifica puntual.
    # Esta verificación se ejecuta en la primera instrucción, antes de cualquier cálculo, consulta o efecto secundario.
    if forzar and not cita_id_especifica:
        raise ValueError("forzar=True requiere cita_id_especifica obligatoria para evitar reenvios masivos")

    import time as time_mod
    ahora_utc = datetime.now(timezone.utc)
    tz_bol = ZoneInfo(getattr(settings, "TZ_CONSULTORIO", "America/La_Paz"))
    ahora_bol = datetime.now(tz_bol)
    hoy_bol = ahora_bol.date()
    manana_bol = hoy_bol + timedelta(days=1)
    horas_anticipacion = int(getattr(settings, "RECORDATORIO_HORAS", 3))

    t_actual = ahora_bol.time()
    t_0730 = time(7, 30)
    t_1030 = time(10, 30)
    t_2030 = time(20, 30)
    t_2200 = time(22, 0)

    # 1. BLOQUEO ESTRICTO DE MADRUGADA (22:00 a 07:29) para envíos automáticos
    if not forzar:
        if t_actual < t_0730 or t_actual >= t_2200:
            return []

    # Sanar citas futuras bloqueadas indebidamente
    try:
        db.execute(text("""
            UPDATE agenda.citas c
            SET recordatorio_enviado = FALSE
            WHERE c.inicio > :ahora
              AND c.recordatorio_enviado = TRUE
              AND NOT EXISTS (
                  SELECT 1 FROM agenda.notificaciones_enviadas n
                  WHERE n.cita_id = c.id AND n.tipo = 'recordatorio' AND n.estado = 'enviado'
              )
        """), {"ahora": ahora_utc})
        db.commit()
    except Exception:
        db.rollback()

    # Vincular automáticamente teléfonos faltantes desde fichas coincidentes
    try:
        db.execute(text("""
            UPDATE agenda.pacientes p_sin
            SET telefono = p_con.telefono
            FROM agenda.pacientes p_con
            WHERE p_sin.telefono IS NULL
              AND p_con.telefono IS NOT NULL
              AND p_sin.id != p_con.id
              AND (
                  lower(p_sin.nombre) = lower(p_con.nombre)
                  OR lower(p_sin.nombre) LIKE lower(concat(p_con.nombre, '%'))
                  OR lower(p_con.nombre) LIKE lower(concat(p_sin.nombre, '%'))
              )
        """))
        db.commit()
    except Exception:
        db.rollback()

    # Consultar citas candidatas
    query = (
        select(Cita, Paciente)
        .join(Paciente, Cita.paciente_id == Paciente.id)
        .where(
            Cita.estado.in_(["pendiente", "confirmada"]),
            Cita.inicio > (ahora_utc - timedelta(hours=1))
        )
    )
    if cita_id_especifica:
        query = query.where(Cita.id == cita_id_especifica)
    elif not forzar:
        query = query.where(Cita.recordatorio_enviado == False, Cita.inicio > ahora_utc)

    rows = db.execute(query.order_by(Cita.inicio)).all()

    es_ventana_nocturna = (t_actual >= t_2030 and t_actual < t_2200)
    es_ventana_diurna = (t_actual >= t_0730 and t_actual < t_2200)

    enviados = []

    for cita, paciente in rows:
        dt_inicio_utc = cita.inicio if (cita.inicio and cita.inicio.tzinfo) else cita.inicio.replace(tzinfo=timezone.utc)
        dt_bol = dt_inicio_utc.astimezone(tz_bol)
        fecha_cita_bol = dt_bol.date()
        hora_cita_bol = dt_bol.time()

        # 1. COMPROBACIÓN PRIORITARIA DE OPT-OUT:
        # Si el paciente solicitó la baja ([OPTOUT_WHATSAPP]), se descarta de inmediato
        # ANTES de consultar, crear o modificar NotificacionEnviada y ANTES de cualquier db.flush()
        if paciente.notas and "[OPTOUT_WHATSAPP]" in paciente.notas:
            print(f"[WhatsApp Opt-out] Omitiendo recordatorio cita {cita.id}: paciente '{enmascarar_nombre(paciente.nombre)}' solicitó baja.")
            continue

        if forzar:
            if filtro and filtro.lower() not in ("todos", "todas", "todo"):
                f_clean = filtro.strip().lower()
                nom_p = (paciente.nombre or "").lower()
                h_p = dt_bol.strftime("%H:%M")
                if f_clean not in nom_p and f_clean not in h_p:
                    continue
            debe_enviar = True
        else:
            debe_enviar = False
            # REGLA A: Citas de mañana del primer turno (09:00 a 10:30 AM)
            # Se envían la noche anterior entre las 20:30 y 22:00
            if fecha_cita_bol == manana_bol and hora_cita_bol <= t_1030:
                if es_ventana_nocturna:
                    debe_enviar = True

            # REGLA B: Citas de hoy dentro de la ventana diurna (07:30 a 22:00)
            elif fecha_cita_bol == hoy_bol and es_ventana_diurna:
                # B1: Citas tempranas (<= 10:30 AM) no enviadas anoche -> enviar desde las 7:30 AM
                if hora_cita_bol <= t_1030:
                    debe_enviar = True
                # B2: Citas de media mañana y tarde (10:31 en adelante) -> enviar con 3 horas de anticipación
                elif dt_inicio_utc <= ahora_utc + timedelta(hours=horas_anticipacion):
                    debe_enviar = True

        if not debe_enviar:
            continue

        # Intentar rescatar teléfono si está vacío
        if not paciente.telefono:
            nom_base = re.sub(r"(?i)\s+(ort|ortodoncia|control|15d|profi|profilaxis|rest|restauracion|impresion|placa|inferior|superior|cirugia|cirugía)\b", "", paciente.nombre).strip().lower()
            candidato = db.execute(
                select(Paciente).where(
                    Paciente.telefono.isnot(None),
                    func.lower(Paciente.nombre).like(f"%{nom_base}%")
                )
            ).scalars().first()
            if candidato and candidato.telefono:
                paciente.telefono = candidato.telefono
                db.commit()

        if not paciente.telefono or not es_telefono_bolivia_valido(paciente.telefono):
            print(f"[WhatsApp] Pendiente recordatorio cita {cita.id}: paciente '{enmascarar_nombre(paciente.nombre)}' sin teléfono boliviano válido ({enmascarar_telefono(paciente.telefono)}).")
            continue

        ya = db.execute(
            select(NotificacionEnviada).where(
                NotificacionEnviada.cita_id == cita.id,
                NotificacionEnviada.tipo == "recordatorio"
            )
        ).scalar_one_or_none()

        if ya:
            if not forzar and ya.estado == "enviado":
                cita.recordatorio_enviado = True
                db.commit()
                continue
            elif not forzar and ya.estado == "incierto":
                # Timeout previo: protección estricta contra duplicados.
                # Para evitar duplicados en el paciente ante incertidumbre de entrega de la red,
                # NO se reintenta automáticamente. Requiere intervención manual (forzar=True) o reconciliación.
                print(f"[WhatsApp] Saltando recordatorio cita {cita.id}: estado incierto previo ({enmascarar_telefono(paciente.telefono)}). Protección contra duplicados activa.")
                continue
            elif not forzar and ya.estado == "error":
                # Fallo previo confirmado: reintento controlado (máx 3 intentos con 10 min de separación desde el último intento)
                if (ya.intentos or 0) >= 3:
                    print(f"[WhatsApp] Saltando recordatorio cita {cita.id}: superó límite de reintentos (3).")
                    continue
                ultimo_intento = ya.enviado_at or ya.created_at or ahora_utc
                tiempo_seg = (ahora_utc - ultimo_intento).total_seconds()
                if tiempo_seg < 600:
                    continue

        # Preservar el hash si ya existe; solo generar si es nulo.
        # Jamás altera cita.token_respuesta_hash (enlace de confirmación original).
        if not cita.token_recordatorio_hash:
            token = str(uuid.uuid4())
            cita.token_recordatorio_hash = hash_token(token)

        if not ya:
            ya = NotificacionEnviada(
                cita_id=cita.id,
                tipo="recordatorio",
                destino=paciente.telefono,
                estado="pendiente",
                intentos=0
            )
            db.add(ya)
        db.flush()

        try:
            hora_str = dt_bol.strftime("%H:%M")
            hora_12 = dt_bol.strftime("%I:%M %p").lstrip("0")
            dias_esp = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
            dia_str = dias_esp[dt_bol.weekday()]
            fecha_str = dt_bol.strftime("%d/%m")

            if fecha_cita_bol == hoy_bol:
                cuando_str = f"hoy *{dia_str} {fecha_str}*"
            elif fecha_cita_bol == manana_bol:
                cuando_str = f"mañana *{dia_str} {fecha_str}*"
            else:
                cuando_str = f"el *{dia_str} {fecha_str}*"

            estado_desc = "confirmada" if cita.estado == "confirmada" else "programada"

            encabezados = [
                "🦷 *SOLDENT - Recordatorio de Cita*",
                "🦷 *Recordatorio de Consulta - SOLDENT*",
            ]
            saludos = [
                f"Hola *{paciente.nombre}*",
                f"Estimado/a *{paciente.nombre}*",
            ]
            cuerpos = [
                f"le recordamos su cita con la *Dra. Pamela Pinto Suárez* para {cuando_str} a las *{hora_str}* ({hora_12}).",
                f"le recordamos su atención con la *Dra. Pamela Pinto Suárez* para {cuando_str} a las *{hora_str}* ({hora_12}).",
            ]
            llamados_accion = [
                "👉 *Responda \"Confirmo\" para asegurar su turno (o avísenos si necesita reprogramar).*",
                "👉 *Por favor responda \"Confirmo\" para validar su asistencia (o indíquenos si desea reprogramar).*",
            ]
            optouts = [
                "_(Para no recibir recordatorios responda SALIR)_",
            ]

            partes_mensaje = [
                random.choice(encabezados),
                "",
                f"{random.choice(saludos)}, {random.choice(cuerpos)}",
                "📍 *Lugar:* Calle Parapetí (o Lemoine) 407 esq. Vallegrande.",
                "",
                f"{random.choice(llamados_accion)} ¡Le esperamos! ✨",
                "",
                random.choice(optouts)
            ]

            mensaje = "\n".join(partes_mensaje).strip()

            gateway_url = os.getenv("WHATSAPP_GATEWAY_URL", os.getenv("EVOLUTION_API_URL", "http://127.0.0.1:8080")).rstrip("/")
            timeout_wa = httpx.Timeout(connect=3.0, read=15.0, write=5.0, pool=3.0)
            ya.intentos = (ya.intentos or 0) + 1
            try:
                resp = httpx.post(
                    f"{gateway_url}/send-message",
                    json={"number": paciente.telefono, "text": mensaje, "message": mensaje},
                    timeout=timeout_wa
                )
                if resp.status_code in (200, 201):
                    ya.estado = "enviado"
                    ya.enviado_at = ahora_utc
                    ya.error = None
                    cita.recordatorio_enviado = True
                    db.commit()
                    print(f"[WhatsApp] Recordatorio enviado con éxito a paciente activo '{enmascarar_nombre(paciente.nombre)}' ({enmascarar_telefono(paciente.telefono)}) para {cuando_str} a las {hora_str}")
                    enviados.append({
                        "paciente": paciente.nombre,
                        "telefono": paciente.telefono,
                        "fecha": dt_bol.strftime("%d/%m/%Y"),
                        "hora": hora_str
                    })
                elif resp.status_code in (400, 422):
                    # Fallos confirmados previos al despacho por validación de parámetros
                    ya.estado = "error"
                    ya.enviado_at = ahora_utc
                    ya.error = f"Gateway HTTP {resp.status_code} (Rechazo de parametros)"
                    db.commit()
                    print(f"[WhatsApp Error] Gateway rechazó mensaje ({resp.status_code}) para {enmascarar_telefono(paciente.telefono)}")
                else:
                    # HTTP 500, 502, 503, 504 u otros: Resultado incierto.
                    # Un 503 puede originarse en proxies intermedios o durante la desconexión del socket
                    # en pleno envío. Para evitar duplicados, se clasifica como 'incierto'.
                    ya.estado = "incierto"
                    ya.enviado_at = ahora_utc
                    ya.error = f"Gateway HTTP {resp.status_code} (Incierto)"
                    db.commit()
                    print(f"[WhatsApp Incierto] Gateway respondió {resp.status_code} para {enmascarar_telefono(paciente.telefono)}. Marcado 'incierto' para evitar duplicación.")
            except (httpx.ReadTimeout, httpx.WriteTimeout):
                ya.estado = "incierto"
                ya.enviado_at = ahora_utc
                ya.error = "Timeout en espera de respuesta (posible envío en tránsito)"
                db.commit()
                print(f"[WhatsApp Incierto] Timeout al enviar a {enmascarar_telefono(paciente.telefono)}. Marcado 'incierto' para evitar duplicación.")
            except (httpx.ConnectError, httpx.ConnectTimeout) as err_conn:
                safe_conn = sanitizar_error(err_conn)["message"]
                ya.estado = "error"
                ya.enviado_at = ahora_utc
                ya.error = safe_conn
                db.commit()
                print(f"[WhatsApp Error] Gateway inaccesible para {enmascarar_telefono(paciente.telefono)}: {safe_conn}")
            except Exception as err_w:
                safe_w = sanitizar_error(err_w)["message"]
                ya.estado = "incierto"
                ya.enviado_at = ahora_utc
                ya.error = safe_w
                db.commit()
                print(f"[WhatsApp Incierto] Error inesperado para {enmascarar_telefono(paciente.telefono)}: {safe_w}")

            time_mod.sleep(random.uniform(5.0, 10.0))
        except IntegrityError:
            db.rollback()

    return enviados

def _resumen_registrado_hoy(db: Session, turno: str, hoy_str: str) -> Optional[str]:
    """
    Comprueba en WhatsAppSession o en WorkerHeartbeat.meta el estado del resumen del turno hoy.
    Retorna:
      - 'despachado': enviado exitosamente hoy.
      - 'incierto': falló con timeout o error 5xx/desconocido; protegido contra duplicados.
      - None: pendiente (no procesado hoy).
    Si la base de datos no responde, propaga la excepción para que el worker aborte el ciclo sin riesgo de duplicar.
    """
    sess = db.get(WhatsAppSession, f"resumen_doctora_{turno}")
    if sess and sess.value:
        try:
            val_data = json.loads(sess.value)
            if isinstance(val_data, dict) and val_data.get("fecha") == hoy_str:
                return val_data.get("estado", "despachado")
        except Exception:
            if sess.value == hoy_str:
                return "despachado"

    hb = db.get(WorkerHeartbeat, "worker_resumen_turnos_doctora")
    if hb and hb.meta and isinstance(hb.meta, dict):
        reg = hb.meta.get(f"resumen_{turno}")
        if isinstance(reg, dict) and reg.get("fecha") == hoy_str:
            return reg.get("estado", "despachado")
        elif hb.meta.get(f"ultimo_resumen_{turno}") == hoy_str:
            return "despachado"

    return None

def _guardar_resumen_registrado(db: Session, turno: str, hoy_str: str, estado: str = "despachado") -> bool:
    """
    Persiste en WhatsAppSession y WorkerHeartbeat.meta el estado explícito del resumen del turno ('despachado' o 'incierto') para hoy.
    Si ocurre un error de base de datos, ejecuta rollback y propaga la excepción.
    """
    try:
        payload = json.dumps({
            "fecha": hoy_str,
            "estado": estado,
            "actualizado_at": datetime.now(timezone.utc).isoformat()
        })
        sess = db.get(WhatsAppSession, f"resumen_doctora_{turno}")
        if not sess:
            sess = WhatsAppSession(key=f"resumen_doctora_{turno}", value=payload)
            db.add(sess)
        else:
            sess.value = payload
            sess.updated_at = datetime.now(timezone.utc)

        hb = db.get(WorkerHeartbeat, "worker_resumen_turnos_doctora")
        if hb:
            meta_dict = dict(hb.meta or {})
            meta_dict[f"resumen_{turno}"] = {"fecha": hoy_str, "estado": estado}
            meta_dict[f"ultimo_resumen_{turno}"] = hoy_str
            hb.meta = meta_dict
        db.commit()
        return True
    except Exception as e_save:
        try:
            db.rollback()
        except Exception:
            pass
        safe_err = sanitizar_error(e_save)["message"]
        print(f"[ERROR] [Resumen Turno Error Critico] No se pudo persistir estado '{estado}' en BD: {safe_err}")
        raise e_save

def worker_resumen_turnos_doctora(db: Session, forzar_turno: Optional[str] = None) -> Optional[dict]:
    global ultimo_resumen_manana, ultimo_resumen_tarde
    tz_bol = ZoneInfo(getattr(settings, "TZ_CONSULTORIO", "America/La_Paz"))
    ahora_bol = datetime.now(tz_bol)
    hoy = ahora_bol.date()
    hoy_str = hoy.strftime("%Y-%m-%d")
    weekday = hoy.weekday()
    hora = ahora_bol.hour
    minuto = ahora_bol.minute

    if not forzar_turno and weekday == 6:
        return None

    hay_cita_temprana_hoy = False
    try:
        inicio_temprano_utc = datetime(hoy.year, hoy.month, hoy.day, 8, 0, 0, tzinfo=tz_bol).astimezone(timezone.utc)
        fin_temprano_utc = datetime(hoy.year, hoy.month, hoy.day, 9, 0, 0, tzinfo=tz_bol).astimezone(timezone.utc)
        c_temp = db.execute(
            select(Cita.id).where(
                Cita.estado.in_(["pendiente", "confirmada"]),
                Cita.inicio >= inicio_temprano_utc,
                Cita.inicio < fin_temprano_utc
            )
        ).first()
        if c_temp:
            hay_cita_temprana_hoy = True
    except Exception:
        pass

    if forzar_turno:
        ft_clean = str(forzar_turno).strip().lower()
        if ft_clean not in ("manana", "mañana", "tarde"):
            raise ValueError(f"forzar_turno solo admite 'manana' o 'tarde', recibido: '{forzar_turno}'")
        es_turno_manana = (ft_clean in ("manana", "mañana"))
        es_turno_tarde = (ft_clean == "tarde")
    else:
        try:
            estado_manana_bd = _resumen_registrado_hoy(db, "manana", hoy_str)
            estado_tarde_bd = _resumen_registrado_hoy(db, "tarde", hoy_str)
            manana_ya_registrado = (ultimo_resumen_manana == hoy_str) or (estado_manana_bd in ("despachado", "incierto"))
            tarde_ya_registrado = (ultimo_resumen_tarde == hoy_str) or (estado_tarde_bd in ("despachado", "incierto"))
        except Exception as err_db:
            print(f"[BLOQUEO] [Resumen Turno] Abortando ciclo: BD inaccesible para verificar estado previo. Previniendo duplicados.")
            return {"ok": False, "error": "DATABASE_UNAVAILABLE_RESUMEN_ABORTED"}

        if manana_ya_registrado:
            ultimo_resumen_manana = hoy_str
        if tarde_ya_registrado:
            ultimo_resumen_tarde = hoy_str

        if hay_cita_temprana_hoy:
            # Si hay cita temprana (ej. 08:30 AM), el resumen se envía a las ~08:10 AM (20 min antes)
            es_turno_manana = (weekday <= 5) and (hora == 8 and 8 <= minuto <= 43) and not manana_ya_registrado
        else:
            es_turno_manana = (weekday <= 5) and (hora == 8 and 38 <= minuto <= 43) and not manana_ya_registrado

        es_turno_tarde = (weekday <= 4) and (hora == 15 and 8 <= minuto <= 13) and not tarde_ya_registrado

    if not (es_turno_manana or es_turno_tarde):
        return None

    turno_clave = "manana" if es_turno_manana else "tarde"
    turno_nombre = "Mañana" if es_turno_manana else "Tarde"
    tipo_notif = "resumen_doctora_manana" if es_turno_manana else "resumen_doctora_tarde"

    if es_turno_manana:
        dt_ini_turno = datetime(hoy.year, hoy.month, hoy.day, 8, 0, 0, tzinfo=tz_bol)
        dt_fin_turno = datetime(hoy.year, hoy.month, hoy.day, 12, 1, 0, tzinfo=tz_bol)
        horario_turno_texto = "08:30 a 12:00 (con Horario Especial)" if hay_cita_temprana_hoy else "09:00 a 12:00"
    else:
        dt_ini_turno = datetime(hoy.year, hoy.month, hoy.day, 15, 30, 0, tzinfo=tz_bol)
        dt_fin_turno = datetime(hoy.year, hoy.month, hoy.day, 19, 31, 0, tzinfo=tz_bol)
        horario_turno_texto = "15:30 a 19:30"

    dt_ini_utc = dt_ini_turno.astimezone(timezone.utc)
    dt_fin_utc = dt_fin_turno.astimezone(timezone.utc)

    citas = db.execute(
        select(Cita, Paciente, Tratamiento)
        .join(Paciente, Cita.paciente_id == Paciente.id)
        .outerjoin(Tratamiento, Cita.tratamiento_id == Tratamiento.id)
        .where(
            Cita.estado.in_(["pendiente", "confirmada"]),
            Cita.inicio >= dt_ini_utc,
            Cita.inicio < dt_fin_utc
        )
        .order_by(Cita.inicio)
    ).all()

    dias_esp = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    dia_nombre = dias_esp[weekday]
    fecha_fmt = hoy.strftime("%d/%m/%Y")
    saludo = "Buenos días" if es_turno_manana else "Buenas tardes"

    if not citas:
        mensaje = (
            f"🦷 *SOLDENT - Agenda del Turno {turno_nombre}*\n"
            f"📅 *{dia_nombre} {fecha_fmt}* • Turno de {horario_turno_texto}\n\n"
            f"{saludo} Dra. Pamela, le informamos que para este turno de la {turno_nombre.lower()} "
            f"no tiene pacientes agendados por el momento.\n\n"
            f"¡Que tenga una excelente jornada de descanso o atención! ✨"
        )
    else:
        lineas = []
        emojis_num = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        for idx, (cita, paciente, tratamiento) in enumerate(citas):
            c_ini = cita.inicio.astimezone(tz_bol) if cita.inicio.tzinfo else cita.inicio.replace(tzinfo=timezone.utc).astimezone(tz_bol)
            c_fin = cita.fin.astimezone(tz_bol) if cita.fin.tzinfo else cita.fin.replace(tzinfo=timezone.utc).astimezone(tz_bol)
            h_ini = c_ini.strftime("%H:%M")
            h_fin = c_fin.strftime("%H:%M")
            estado_badge = "✅ Confirmada" if cita.estado == "confirmada" else "⏳ Pendiente"
            trat_nom = tratamiento.nombre if tratamiento else "Consulta Odontológica"
            num_emoji = emojis_num[idx] if idx < len(emojis_num) else f"• {idx+1}."

            linea = (
                f"{num_emoji} *{h_ini} - {h_fin}* • {paciente.nombre}\n"
                f"   📱 {paciente.telefono or 'Sin teléfono registrado'} • {estado_badge}\n"
                f"   🩺 {trat_nom}"
            )
            if cita.notas and cita.notas.strip():
                linea += f"\n   📝 Nota: {cita.notas.strip()}"
            lineas.append(linea)

        citas_texto = "\n\n".join(lineas)
        mensaje = (
            f"🦷 *SOLDENT - Agenda del Turno {turno_nombre}*\n"
            f"📅 *{dia_nombre} {fecha_fmt}* • Turno de {horario_turno_texto}\n\n"
            f"{saludo} Dra. Pamela, este es el resumen de sus pacientes programados para este turno:\n\n"
            f"{citas_texto}\n\n"
            f"📊 Total de pacientes: *{len(citas)}*\n\n"
            f"¡Que tenga una exitosa jornada de atención! ✨"
        )

    doc_tel = getattr(settings, "DOCTORA_TELEFONO", "+59178472875")
    gateway_url = os.getenv("WHATSAPP_GATEWAY_URL", os.getenv("EVOLUTION_API_URL", "http://127.0.0.1:8080")).rstrip("/")
    timeout_resumen = httpx.Timeout(connect=3.0, read=15.0, write=5.0, pool=3.0)
    try:
        resp = httpx.post(
            f"{gateway_url}/send-message",
            json={"number": doc_tel, "text": mensaje, "message": mensaje},
            timeout=timeout_resumen
        )
        if resp.status_code in (200, 201):
            print(f"[OK] [Resumen Turno {turno_nombre}] Enviado exitosamente a la Dra. Pamela ({enmascarar_telefono(doc_tel)})")
            if not forzar_turno:
                if es_turno_manana:
                    ultimo_resumen_manana = hoy_str
                else:
                    ultimo_resumen_tarde = hoy_str
            try:
                _guardar_resumen_registrado(db, turno_clave, hoy_str, estado="despachado")
            except Exception as err_p:
                safe_err = sanitizar_error(err_p)["message"]
                print(f"[ALERTA] [Resumen Turno] Despacho exitoso pero falló persistencia en BD: {safe_err}")
                return {"ok": True, "turno": turno_nombre, "advertencia": "PERSISTENCIA_FALLIDA", "total_pacientes": len(citas)}
            # Retorno sanitizado: CERO exposición de nombres o citas de pacientes en respuestas API
            return {"ok": True, "turno": turno_nombre, "total_pacientes": len(citas)}
        elif resp.status_code in (400, 422):
            print(f"[ALERTA] [Resumen Turno Error] Gateway rechazó solicitud HTTP {resp.status_code}")
            return {"ok": False, "turno": turno_nombre, "error": f"Gateway HTTP {resp.status_code}"}
        else:
            # HTTP 500 u otros errores de servidor: resultado incierto
            print(f"[ALERTA] [Resumen Turno Incierto] Gateway respondió HTTP {resp.status_code}. Marcando turno como 'incierto' para evitar duplicados.")
            if not forzar_turno:
                if es_turno_manana:
                    ultimo_resumen_manana = hoy_str
                else:
                    ultimo_resumen_tarde = hoy_str
            try:
                _guardar_resumen_registrado(db, turno_clave, hoy_str, estado="incierto")
            except Exception:
                pass
            return {"ok": False, "turno": turno_nombre, "error": f"GATEWAY_{resp.status_code}_INCIERTO_EVITADO_DUPLICADO"}
    except (httpx.ReadTimeout, httpx.WriteTimeout):
        # Resultado incierto: el mensaje probablemente fue enviado pero la respuesta demoró >15s.
        print(f"[ALERTA] [Resumen Turno Incierto] Timeout de lectura (>15s). Marcando 'incierto' en BD para proteger a la Dra. Pamela contra duplicados.")
        if not forzar_turno:
            if es_turno_manana:
                ultimo_resumen_manana = hoy_str
            else:
                ultimo_resumen_tarde = hoy_str
        try:
            _guardar_resumen_registrado(db, turno_clave, hoy_str, estado="incierto")
        except Exception:
            pass
        return {"ok": False, "turno": turno_nombre, "error": "TIMEOUT_INCIERTO_EVITADO_DUPLICADO"}
    except (httpx.ConnectError, httpx.ConnectTimeout) as err_conn:
        safe_conn = sanitizar_error(err_conn)["message"]
        print(f"[ALERTA] [Resumen Turno Error] Gateway inaccesible: {safe_conn}")
        return {"ok": False, "turno": turno_nombre, "error": safe_conn}
    except Exception as err_envio:
        safe_envio = sanitizar_error(err_envio)["message"]
        print(f"[ALERTA] [Resumen Turno Incierto] Error inesperado en despacho: {safe_envio}. Marcando 'incierto' en BD para evitar duplicados.")
        if not forzar_turno:
            if es_turno_manana:
                ultimo_resumen_manana = hoy_str
            else:
                ultimo_resumen_tarde = hoy_str
        try:
            _guardar_resumen_registrado(db, turno_clave, hoy_str, estado="incierto")
        except Exception:
            pass
        return {"ok": False, "turno": turno_nombre, "error": safe_envio}
