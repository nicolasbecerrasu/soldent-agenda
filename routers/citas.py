import uuid
from datetime import datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import settings
from database import Cita, NotificacionEnviada, Paciente, Tratamiento, get_db
from schemas import ESTADOS_VALIDOS, CitaIn, CitaUpdateIn
from security import hash_token, verificar_autenticacion
from services.google_calendar import (
    encolar_outbox,
    generar_token_respuesta,
    get_calendar_service,
    registrar_auditoria
)

router = APIRouter(tags=["Citas y Agenda"])

def validar_horario_soldent(dt_inicio: datetime, dt_fin: datetime):
    """
    Valida las restricciones oficiales de horarios de atención en Soldent:
    - Lunes a Viernes: Mañana 09:00 a 12:00 | Tarde 15:30 a 19:30
    - Sábados: Mañana 09:00 a 12:00 (Tardes y domingos cerrado)
    """
    tz_bol = ZoneInfo(settings.TZ_CONSULTORIO)
    dt_ini_bol = dt_inicio.astimezone(tz_bol) if dt_inicio.tzinfo else dt_inicio.replace(tzinfo=timezone.utc).astimezone(tz_bol)
    dt_fin_bol = dt_fin.astimezone(tz_bol) if dt_fin.tzinfo else dt_fin.replace(tzinfo=timezone.utc).astimezone(tz_bol)

    weekday = dt_ini_bol.weekday()  # 0 = Lunes, 5 = Sábado, 6 = Domingo
    t_ini = dt_ini_bol.time()
    t_fin = dt_fin_bol.time()

    t_0900 = time(9, 0)
    t_1200 = time(12, 0)
    t_1530 = time(15, 30)
    t_1930 = time(19, 30)

    if weekday == 6:
        raise HTTPException(
            status_code=422,
            detail="Soldent permanece cerrado los domingos. Por favor seleccione un turno de Lunes a Sábado."
        )

    if weekday == 5:  # Sábado
        if not (t_ini >= t_0900 and t_fin <= t_1200):
            raise HTTPException(
                status_code=422,
                detail="Los sábados la clínica atiende únicamente en el turno de la mañana (09:00 a 12:00). Las tardes de sábado y domingos estamos cerrados."
            )
        return

    # Lunes a Viernes (0 a 4)
    en_manana = (t_ini >= t_0900 and t_fin <= t_1200)
    en_tarde = (t_ini >= t_1530 and t_fin <= t_1930)

    if not (en_manana or en_tarde):
        if t_ini >= t_1200 and t_ini < t_1530:
            raise HTTPException(
                status_code=422,
                detail="El horario solicitado coincide con el receso del mediodía (12:00 a 15:30). Los turnos disponibles son en la mañana (09:00 a 12:00) o en la tarde (15:30 a 19:30)."
            )
        raise HTTPException(
            status_code=422,
            detail="El horario solicitado está fuera del horario de atención de Soldent. Horarios oficiales: Lunes a Viernes de 09:00 a 12:00 y de 15:30 a 19:30; Sábados de 09:00 a 12:00."
        )

@router.get("/api/citas")
def listar_citas(
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    estado: Optional[str] = None,
    db: Session = Depends(get_db),
    _auth: bool = Depends(verificar_autenticacion)
):
    stmt = (
        select(Cita, Paciente, Tratamiento)
        .join(Paciente, Cita.paciente_id == Paciente.id)
        .join(Tratamiento, Cita.tratamiento_id == Tratamiento.id)
        .order_by(Cita.inicio.asc())
    )
    if desde:
        stmt = stmt.where(Cita.inicio >= desde)
    if hasta:
        stmt = stmt.where(Cita.inicio <= hasta)
    if estado:
        stmt = stmt.where(Cita.estado == estado)
    
    rows = db.execute(stmt).all()
    resultado = []
    for cita, pac, trat in rows:
        resultado.append({
            "id": str(cita.id),
            "paciente_id": str(cita.paciente_id),
            "tratamiento_id": str(cita.tratamiento_id),
            "inicio": cita.inicio.isoformat() if cita.inicio else None,
            "fin": cita.fin.isoformat() if cita.fin else None,
            "estado": cita.estado,
            "motivo": cita.motivo,
            "notas": cita.notas,
            "google_event_id": cita.google_event_id,
            "version": cita.version,
            "paciente": {
                "id": str(pac.id),
                "nombre": pac.nombre,
                "apellidos": pac.apellidos,
                "telefono": pac.telefono,
                "email": pac.email,
            },
            "tratamiento": {
                "id": str(trat.id),
                "nombre": trat.nombre,
                "color": trat.color,
                "duracion_min": trat.duracion_min,
                "precio": float(trat.precio) if trat.precio is not None else None,
            }
        })
    return resultado

@router.post("/api/citas", status_code=status.HTTP_201_CREATED)
def crear_cita(
    data: CitaIn,
    db: Session = Depends(get_db),
    _auth: bool = Depends(verificar_autenticacion)
):
    trat = db.get(Tratamiento, data.tratamiento_id)
    if not trat:
        raise HTTPException(404, "Tratamiento no encontrado")
    duracion = data.duracion_min if (data.duracion_min and data.duracion_min > 0) else trat.duracion_min
    fin = data.fin if data.fin else (data.inicio + timedelta(minutes=duracion))
    validar_horario_soldent(data.inicio, fin)
    paciente = db.get(Paciente, data.paciente_id)
    if not paciente:
        raise HTTPException(404, "Paciente no encontrado")

    # Validación estricta anti-traslapes
    solapada = db.execute(
        select(Cita)
        .where(
            Cita.estado.notin_(["cancelada", "no_asistio"]),
            Cita.inicio < fin,
            Cita.fin > data.inicio
        )
    ).scalars().first()
    if solapada:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El horario solicitado ya se encuentra ocupado por otra cita en el consultorio."
        )

    ahora_utc = datetime.now(timezone.utc)
    inicio_utc = data.inicio.astimezone(timezone.utc) if data.inicio.tzinfo else data.inicio.replace(tzinfo=timezone.utc)

    # Citas que inician en menos de 3 horas se guardan como confirmadas directamente
    es_inmediata = (inicio_utc - ahora_utc) < timedelta(hours=3)
    estado_inicial = "confirmada" if es_inmediata else "pendiente"

    cita = Cita(
        paciente_id=data.paciente_id,
        tratamiento_id=data.tratamiento_id,
        inicio=data.inicio,
        fin=fin,
        motivo=data.motivo,
        notas=data.notas,
        estado=estado_inicial,
        recordatorio_enviado=(inicio_utc <= ahora_utc)
    )
    token = generar_token_respuesta(db, cita)
    try:
        db.add(cita)
        db.flush()

        if es_inmediata and paciente and paciente.telefono:
            ya = NotificacionEnviada(
                cita_id=cita.id,
                tipo="recordatorio",
                destino=paciente.telefono,
                estado="enviado",
                enviado_at=ahora_utc
            )
            db.add(ya)

        encolar_outbox(
            db, cita.id, "create",
            {
                "inicio": cita.inicio.isoformat(),
                "fin": fin.isoformat(),
                "paciente_nombre": paciente.nombre if paciente else "Paciente",
                "notas": data.notas
            }
        )
        registrar_auditoria(db, cita.id, "doctora", "crear", despues={"inicio": str(cita.inicio), "estado": estado_inicial})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ese hueco ya está ocupado o el paciente ya tiene cita en ese horario")
    return {
        "id": str(cita.id),
        "fin": fin.isoformat(),
        "estado": cita.estado,
        "es_inmediata": es_inmediata,
        "version": cita.version,
        "token_respuesta": token,
        "link_respuesta": f"{settings.PUBLIC_BASE_URL}/r/{token}"
    }

@router.patch("/api/citas/{cid}")
def actualizar_cita(
    cid: uuid.UUID,
    data: CitaUpdateIn,
    db: Session = Depends(get_db),
    _auth: bool = Depends(verificar_autenticacion)
):
    cita = db.get(Cita, cid)
    if not cita:
        raise HTTPException(404, "Cita no encontrada")
    if data.estado and data.estado not in ESTADOS_VALIDOS:
        raise HTTPException(422, "Estado inválido")
    antes = {"estado": cita.estado, "inicio": str(cita.inicio), "version": cita.version, "tratamiento_id": str(cita.tratamiento_id)}
    cambios = data.model_dump(exclude_unset=True, exclude={"version"})
    if not cambios:
        raise HTTPException(422, "Nada que actualizar")

    ini_actual = cambios.get("inicio") or cita.inicio
    trat_id = cambios.get("tratamiento_id") or cita.tratamiento_id
    trat = db.get(Tratamiento, trat_id) if trat_id else None
    duracion = cambios.get("duracion_min") or (trat.duracion_min if trat else 30)
    fin_calc = ini_actual + timedelta(minutes=duracion)

    recalcula_tiempo = bool(data.inicio or data.tratamiento_id or data.duracion_min)
    if recalcula_tiempo:
        validar_horario_soldent(ini_actual, fin_calc)

        solapada = db.execute(
            select(Cita)
            .where(
                Cita.id != cid,
                Cita.estado.notin_(["cancelada", "no_asistio"]),
                Cita.inicio < fin_calc,
                Cita.fin > ini_actual
            )
        ).scalars().first()
        if solapada:
            raise HTTPException(409, "El nuevo horario o duración se traslapa con otra cita activa en el consultorio")
    else:
        fin_calc = cita.fin

    q = text("""UPDATE agenda.citas SET inicio = COALESCE(:inicio, inicio), tratamiento_id = COALESCE(:tratamiento_id, tratamiento_id), 
                fin = COALESCE(:fin, fin), estado = COALESCE(:estado, estado), motivo = COALESCE(:motivo, motivo), notas = COALESCE(:notas, notas), 
                version = version + 1, updated_at = now() 
                WHERE id = :cid AND version = :version RETURNING version, fin""")
    try:
        row = db.execute(q, {
            "cid": cid,
            "version": data.version,
            "inicio": cambios.get("inicio"), 
            "tratamiento_id": str(cambios["tratamiento_id"]) if cambios.get("tratamiento_id") else None,
            "fin": fin_calc if recalcula_tiempo else None,
            "estado": cambios.get("estado"),
            "motivo": cambios.get("motivo"),
            "notas": cambios.get("notas")
        }).mappings().first()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "El nuevo horario se traslapa con otra cita")
    if row is None:
        q_fallback = text("""UPDATE agenda.citas SET inicio = COALESCE(:inicio, inicio), tratamiento_id = COALESCE(:tratamiento_id, tratamiento_id), 
                    fin = COALESCE(:fin, fin), estado = COALESCE(:estado, estado), motivo = COALESCE(:motivo, motivo), notas = COALESCE(:notas, notas), 
                    version = version + 1, updated_at = now() 
                    WHERE id = :cid RETURNING version, fin""")
        try:
            row = db.execute(q_fallback, {
                "cid": cid,
                "inicio": cambios.get("inicio"), 
                "tratamiento_id": str(cambios["tratamiento_id"]) if cambios.get("tratamiento_id") else None,
                "fin": fin_calc if recalcula_tiempo else None,
                "estado": cambios.get("estado"),
                "motivo": cambios.get("motivo"),
                "notas": cambios.get("notas")
            }).mappings().first()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "El nuevo horario se traslapa con otra cita")
        if row is None:
            db.rollback()
            raise HTTPException(404, "Cita no encontrada.")
    
    pac = getattr(cita, "paciente", None) or db.get(Paciente, cita.paciente_id)
    pac_nombre = f"{pac.nombre} {pac.apellidos or ''}".strip() if pac else "Paciente"
    fin_val = row["fin"].isoformat() if hasattr(row["fin"], "isoformat") else str(row["fin"])
    ini_val = ini_actual.isoformat() if hasattr(ini_actual, "isoformat") else str(ini_actual)

    encolar_outbox(
        db, cid, "update",
        {
            "estado": cambios.get("estado", cita.estado),
            "inicio": ini_val,
            "fin": fin_val,
            "paciente_nombre": pac_nombre
        }
    )
    registrar_auditoria(db, cid, "doctora", "actualizar", antes=antes, despues={"estado": cambios.get("estado", cita.estado), "version": row["version"], "tratamiento_id": str(trat_id)})
    db.commit()
    return {"id": str(cid), "version": row["version"], "fin": fin_val}

@router.delete("/api/citas/{cid}")
def eliminar_cita(
    cid: uuid.UUID,
    db: Session = Depends(get_db),
    _auth: bool = Depends(verificar_autenticacion)
):
    cita = db.get(Cita, cid)
    if not cita:
        raise HTTPException(404, "Cita no encontrada")
    
    gid = cita.google_event_id
    if gid:
        try:
            service = get_calendar_service()
            service.events().delete(calendarId=settings.CALENDAR_ID, eventId=gid).execute()
            print(f"🗑️ [Google Calendar] Evento {gid} eliminado de inmediato.")
        except Exception as err:
            print(f"⚠️ [Google Calendar] No se pudo borrar evento directo ({err}), encolando outbox.")
            encolar_outbox(db, cid, "delete", {"google_event_id": gid})
    
    registrar_auditoria(db, cid, "doctora", "eliminar", antes={"estado": cita.estado, "inicio": str(cita.inicio), "google_event_id": gid})
    db.delete(cita)
    db.commit()
    return {"ok": True, "id": str(cid)}

PAGE_HTML = """<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Confirmar Cita - Soldent</title>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;margin:0;background:#f8fafc;color:#1e293b;display:flex;justify-content:center;align-items:center;min-height:100vh;padding:16px;box-sizing:border-box}}
.card{{background:#fff;padding:32px 24px;border-radius:24px;box-shadow:0 10px 30px rgba(0,0,0,.06);max-width:400px;width:100%;text-align:center;border:1px solid #e2e8f0}}
.badge{{display:inline-flex;align-items:center;gap:6px;padding:6px 14px;background:#eff6ff;color:#2563eb;border-radius:999px;font-size:12px;font-weight:700;text-transform:uppercase;margin-bottom:16px}}
h1{{font-size:22px;margin:0 0 8px;color:#0f172a}}
.info-box{{background:#f8fafc;border-radius:14px;padding:16px;margin:16px 0 24px;text-align:left;font-size:14px;border:1px solid #edf2f7;line-height:1.6}}
.info-box p{{margin:6px 0;color:#475569}}
.info-box b{{color:#0f172a}}
button{{width:100%;padding:15px;border:none;border-radius:14px;font-size:15px;font-weight:700;cursor:pointer;margin-bottom:12px;transition:all .2s;display:flex;align-items:center;justify-content:center;gap:8px}}
button:active{{transform:scale(0.98)}}
.ok{{background:#16a34a;color:#fff;box-shadow:0 4px 12px rgba(22,163,74,.25)}}
.no{{background:#ef4444;color:#fff;box-shadow:0 4px 12px rgba(239,68,68,.25)}}
.msg{{display:none;padding:16px;border-radius:14px;font-weight:600;font-size:14px;margin-top:12px;line-height:1.4}}
.footer{{font-size:12px;color:#94a3b8;margin-top:20px;border-top:1px solid #f1f5f9;padding-top:14px}}
</style></head><body>
<div class="card">
  <div class="badge">🦷 Soldent • Clínica Odontológica</div>
  <h1>{titulo}</h1>
  <div class="info-box">{detalle}</div>
  <div id="ok" style="display:{show_btns}">
    <button class="ok" onclick="responder('confirmar')">✅ Confirmar Asistencia</button>
    <button class="no" onclick="responder('cancelar')">❌ Cancelar Cita</button>
  </div>
  <div id="msg" class="msg"></div>
  <div class="footer">Calle Lemoine 407 esq. Vallegrande<br>Santa Cruz de la Sierra, Bolivia</div>
</div>
<script>
async function responder(accion){{
  document.getElementById('ok').style.display='none';
  const msg=document.getElementById('msg');
  msg.style.display='block';
  msg.textContent='Procesando tu respuesta...';
  try {{
    const r=await fetch('/r/{token}/'+accion,{{method:'POST'}});
    const j=await r.json();
    msg.textContent=r.ok?j.mensaje:('Error: '+j.detail);
    msg.style.background=r.ok?'#dcfce7':'#fee2e2';
    msg.style.color=r.ok?'#15803d':'#b91c1c';
  }} catch(e){{
    msg.textContent='Error al conectar con la clínica.';
    msg.style.background='#fee2e2';
    msg.style.color='#b91c1c';
  }}
}}
</script></body></html>"""

def _buscar_por_token(db: Session, token: str) -> Optional[Cita]:
    h = hash_token(token)
    return db.execute(select(Cita).where((Cita.token_respuesta_hash == h) | (Cita.token_recordatorio_hash == h))).scalar_one_or_none()

@router.get("/r/{token}", response_class=HTMLResponse)
def pagina_respuesta(token: str, db: Session = Depends(get_db)):
    cita = _buscar_por_token(db, token)
    if not cita or (cita.token_expira_en and cita.token_expira_en < datetime.now(timezone.utc)):
        return HTMLResponse(PAGE_HTML.format(
            titulo="Enlace no válido o expirado",
            detalle="<p>El enlace de confirmación ha caducado o no se encuentra registrado en el sistema.</p><p>Por favor contáctate directamente con la clínica Soldent al <b>+591 78472875</b>.</p>",
            token=token,
            show_btns="none"
        ))
    p = db.get(Paciente, cita.paciente_id)
    tz_bol = ZoneInfo(settings.TZ_CONSULTORIO)
    dt_bol = cita.inicio.astimezone(tz_bol) if cita.inicio.tzinfo else cita.inicio.replace(tzinfo=timezone.utc).astimezone(tz_bol)
    f_fecha = dt_bol.strftime("%d/%m/%Y")
    f_hora = dt_bol.strftime("%H:%M")
    
    detalle_html = (
        f"<p><b>Paciente:</b> {p.nombre} {p.apellidos or ''}</p>"
        f"<p><b>Servicio:</b> Consulta Odontológica</p>"
        f"<p><b>Fecha:</b> {f_fecha}</p>"
        f"<p><b>Hora:</b> {f_hora} (hora de Santa Cruz)</p>"
        f"<p><b>Especialista:</b> Dra. Pamela Pinto Suárez</p>"
    )
    return HTMLResponse(PAGE_HTML.format(
        titulo=f"¡Hola, {p.nombre}!",
        detalle=detalle_html,
        token=token,
        show_btns="block" if cita.estado in ("pendiente", "confirmada") else "none"
    ))

@router.post("/r/{token}/{accion}")
def responder_cita(token: str, accion: str, db: Session = Depends(get_db)):
    if accion not in ("confirmar", "cancelar"):
        raise HTTPException(404, "Acción no válida")
    cita = _buscar_por_token(db, token)
    if not cita:
        raise HTTPException(404, "Enlace no válido")
    if cita.estado == "cancelada":
        return {"mensaje": "Esta cita ya fue cancelada previamente."}
    
    nuevo_estado = "confirmada" if accion == "confirmar" else "cancelada"
    q = text("UPDATE agenda.citas SET estado=:estado, version=version+1, updated_at=now() WHERE id=:cid AND version=:v RETURNING version")
    row = db.execute(q, {"estado": nuevo_estado, "cid": cita.id, "v": cita.version}).mappings().first()
    if row is None:
        db.rollback()
        raise HTTPException(409, "La cita cambió mientras respondías.")
    
    encolar_outbox(db, cita.id, "update", {"estado": nuevo_estado})
    registrar_auditoria(db, cita.id, "paciente", accion, antes={"estado": cita.estado}, despues={"estado": nuevo_estado})
    db.commit()
    if accion == "cancelar":
        db.add(NotificacionEnviada(cita_id=cita.id, tipo="cancelacion", destino="DOCTORA", estado="pendiente"))
        return {"mensaje": "Tu cita ha sido cancelada exitosamente."}
    return {"mensaje": "¡Cita confirmada! Te esperamos con mucho gusto en Soldent."}
