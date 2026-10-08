import httpx
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from config import settings
from services.gemini_ai import safe_print

BOT_HEADERS = {"X-Auth-Token": settings.SECRET_KEY}

def consultar_disponibilidad(fecha: str) -> str:
    """Consulta la disponibilidad de turnos en la clínica Soldent para una fecha determinada (formato YYYY-MM-DD)."""
    tz_bolivia = ZoneInfo(settings.TZ_CONSULTORIO)
    try:
        f_clean = fecha.strip()
        dt_target = datetime.strptime(f_clean, "%Y-%m-%d").date()
    except Exception:
        dt_target = datetime.now(tz_bolivia).date()

    dias_esp = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    dia_nombre = dias_esp[dt_target.weekday()]
    fecha_fmt = dt_target.strftime("%d/%m/%Y")

    if dt_target.weekday() == 6:  # Domingo
        return f"DOMINGO_CERRADO: El {dia_nombre} {fecha_fmt} la clínica permanece cerrada todo el día. Atendemos de Lunes a Viernes de 09:00 a 12:00 y de 15:30 a 19:30, y Sábados de 09:00 a 12:00."

    if dt_target.weekday() in (1, 3):  # Martes y Jueves
        return f"MARTES_JUEVES_DIRECTO_DRA: Los días {dia_nombre} la agenda se coordina de manera directa y personalizada con la {settings.DOCTORA_NOMBRE} al {settings.DOCTORA_TELEFONO}. No se puede agendar por este bot para los días martes o jueves."

    citas_dia = []
    try:
        r = httpx.get(f"{settings.API_BACKEND_URL}/api/citas", headers=BOT_HEADERS, timeout=6.0)
        if r.status_code == 200:
            for c in r.json():
                if (c.get("estado") or "").lower() in ("pendiente", "confirmada", "atendida"):
                    c_ini_str = c.get("inicio", "")
                    c_fin_str = c.get("fin", "")
                    if c_ini_str and c_fin_str:
                        c_ini = datetime.fromisoformat(c_ini_str.replace("Z", "+00:00")).astimezone(tz_bolivia)
                        c_fin = datetime.fromisoformat(c_fin_str.replace("Z", "+00:00")).astimezone(tz_bolivia)
                        if c_ini.date() == dt_target:
                            citas_dia.append((c_ini.time(), c_fin.time()))
    except Exception as e:
        safe_print(f"[Aviso Disponibilidad Backend]: {e}")

    citas_dia.sort(key=lambda x: x[0])

    if dt_target.weekday() == 5:
        horario_texto = "Sábados: turno mañana de 09:00 a 12:00 (tardes cerrado)"
    else:
        horario_texto = "Lunes a Viernes: mañana de 09:00 a 12:00 y tarde de 15:30 a 19:30 (receso de mediodía de 12:00 a 15:30)"

    if not citas_dia:
        return f"DISPONIBILIDAD_TOTAL: Para el {dia_nombre} {fecha_fmt} ({horario_texto}), todos los turnos están 100% libres."

    ocupados = [f"{ini.strftime('%H:%M')} a {fin.strftime('%H:%M')}" for ini, fin in citas_dia]
    ocupados_str = ", ".join(ocupados)
    siguiente_hora = citas_dia[-1][1].strftime("%H:%M")

    return (
        f"DISPONIBILIDAD: Para el {dia_nombre} {fecha_fmt} ({horario_texto}): "
        f"HORARIOS YA OCUPADOS: {ocupados_str}. "
        f"HORARIOS LIBRES: Disponibilidad a partir de las {siguiente_hora} o en los espacios libres oficiales."
    )

def crear_cita(nombre_paciente: str, telefono: str, fecha_hora_inicio: str) -> str:
    """Registra una consulta odontológica en la base de datos de Soldent y la encola para sincronizar con Google Calendar."""
    safe_print(f"\n[Tool crear_cita] Paciente: {nombre_paciente} | Tel: {telefono} | Inicio: {fecha_hora_inicio}")

    tel_clean = telefono.strip()
    if not tel_clean.startswith("+"):
        tel_clean = "+" + tel_clean

    paciente_id = None
    try:
        r_pac = httpx.post(f"{settings.API_BACKEND_URL}/api/pacientes", headers=BOT_HEADERS, json={
            "nombre": nombre_paciente.strip(),
            "telefono": tel_clean,
            "permitir_compartido": True
        }, timeout=6.0)

        if r_pac.status_code == 201:
            paciente_id = r_pac.json().get("id")
        else:
            digitos = "".join(c for c in tel_clean if c.isdigit())[-8:]
            sr = httpx.get(f"{settings.API_BACKEND_URL}/api/pacientes?q={digitos}", headers=BOT_HEADERS, timeout=6.0)
            if sr.status_code == 200 and sr.json():
                paciente_id = sr.json()[0].get("id")
            else:
                primer_nombre = nombre_paciente.split()[0]
                sr2 = httpx.get(f"{settings.API_BACKEND_URL}/api/pacientes?q={primer_nombre}", headers=BOT_HEADERS, timeout=6.0)
                if sr2.status_code == 200 and sr2.json():
                    paciente_id = sr2.json()[0].get("id")
    except Exception as e:
        safe_print(f"[Tool Error Paciente]: {e}")

    if not paciente_id:
        return "ERROR_PACIENTE: No se pudo registrar ni asociar al paciente en el sistema."

    tratamiento_id = None
    duracion_min = 30
    try:
        r_trat = httpx.get(f"{settings.API_BACKEND_URL}/api/tratamientos", headers=BOT_HEADERS, timeout=6.0)
        if r_trat.status_code == 200:
            trats = r_trat.json()
            for t in trats:
                t_nom = t.get("nombre", "").lower()
                if "consulta" in t_nom or "diagn" in t_nom:
                    tratamiento_id = t["id"]
                    duracion_min = t.get("duracion_min", 30)
                    break
            if not tratamiento_id and trats:
                tratamiento_id = trats[0]["id"]
                duracion_min = trats[0].get("duracion_min", 30)
    except Exception as e:
        safe_print(f"[Tool Error Tratamiento]: {e}")

    tz_bolivia = ZoneInfo(settings.TZ_CONSULTORIO)
    f_str = fecha_hora_inicio.strip().replace(" ", "T")
    try:
        dt = datetime.fromisoformat(f_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz_bolivia)
        inicio_iso = dt.isoformat()
    except Exception:
        dt = datetime.now(tz_bolivia)
        inicio_iso = dt.isoformat()

    fecha_solicitada = dt.date()
    weekday = dt.weekday()
    t_ini = dt.time()
    dt_fin = dt + timedelta(minutes=duracion_min)
    t_fin = dt_fin.time()

    t_0900 = time(9, 0)
    t_1200 = time(12, 0)
    t_1530 = time(15, 30)
    t_1930 = time(19, 30)

    if weekday == 6:
        return "ERROR_DOMINGO_CERRADO: Los domingos la clínica Soldent permanece cerrada todo el día. Atendemos de Lunes a Viernes de 09:00 a 12:00 o 15:30 a 19:30, y Sábados de 09:00 a 12:00."

    if weekday in (1, 3):
        return f"ERROR_MARTES_JUEVES_DIRECTO_DOCTORA: Las citas de los días martes y jueves se agendan de manera exclusiva y personalizada directamente con la {settings.DOCTORA_NOMBRE} al {settings.DOCTORA_TELEFONO}."

    if weekday == 5:
        if not (t_ini >= t_0900 and t_fin <= t_1200):
            return "ERROR_SABADO_TARDE_CERRADO: Los sábados la clínica atiende únicamente en el turno de la mañana de 09:00 a 12:00 (las tardes de sábado y domingos estamos cerrados)."
    else:
        en_manana = (t_ini >= t_0900 and t_fin <= t_1200)
        en_tarde = (t_ini >= t_1530 and t_fin <= t_1930)
        if not (en_manana or en_tarde):
            if t_ini >= t_1200 and t_ini < t_1530:
                return "ERROR_RECESO_MEDIODIA: El horario solicitado cae en el intervalo de receso del mediodía (12:00 a 15:30). La clínica no atiende al mediodía. Ofrecemos turnos en la mañana (09:00 a 12:00) o en la tarde (15:30 a 19:30)."
            return "ERROR_HORARIO_NO_PERMITIDO: El horario solicitado está fuera de nuestro horario oficial de atención (Lunes a Viernes de 09:00 a 12:00 y 15:30 a 19:30, Sábados de 09:00 a 12:00)."

    # Validación anti-solapamiento y anti-duplicados previa
    try:
        r_citas_existentes = httpx.get(f"{settings.API_BACKEND_URL}/api/citas", headers=BOT_HEADERS, timeout=6.0)
        if r_citas_existentes.status_code == 200:
            for c in r_citas_existentes.json():
                p_c_id = c.get("paciente_id") or (c.get("paciente") or {}).get("id")
                c_estado = (c.get("estado") or "").lower()
                c_inicio_str = c.get("inicio", "")
                c_fin_str = c.get("fin", "")
                if c_estado in ("pendiente", "confirmada") and c_inicio_str:
                    c_dt = datetime.fromisoformat(c_inicio_str.replace("Z", "+00:00")).astimezone(tz_bolivia)
                    if str(p_c_id) == str(paciente_id) and c_dt.date() == fecha_solicitada:
                        c_hora_existente = c_dt.strftime("%H:%M")
                        c_fecha_existente = c_dt.strftime("%d/%m/%Y")
                        return f"AVISO_CITA_EXISTENTE: El paciente {nombre_paciente} ya cuenta con una cita activa agendada para el día {c_fecha_existente} a las {c_hora_existente}."
                if c_estado in ("pendiente", "confirmada", "atendida") and c_inicio_str and c_fin_str:
                    c_ini = datetime.fromisoformat(c_inicio_str.replace("Z", "+00:00")).astimezone(tz_bolivia)
                    c_fin = datetime.fromisoformat(c_fin_str.replace("Z", "+00:00")).astimezone(tz_bolivia)
                    if dt < c_fin and dt_fin > c_ini:
                        c_ini_h = c_ini.strftime("%H:%M")
                        c_fin_h = c_fin.strftime("%H:%M")
                        return f"ERROR_HORARIO_OCUPADO: Ese horario ya se encuentra ocupado por otra cita en el consultorio (de {c_ini_h} a {c_fin_h}). Con gusto le ofrezco a partir de las {c_fin_h} o a la siguiente hora disponible."
    except Exception as e:
        safe_print(f"[Aviso Chequeo Citas]: {e}")

    try:
        r_cita = httpx.post(f"{settings.API_BACKEND_URL}/api/citas", headers=BOT_HEADERS, json={
            "paciente_id": paciente_id,
            "tratamiento_id": tratamiento_id,
            "inicio": inicio_iso,
            "motivo": "Agendado via WhatsApp Bot - Consulta Odontológica",
            "notas": f"Tel: {tel_clean}"
        }, timeout=8.0)

        if r_cita.status_code == 201:
            dias_esp = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
            f_dia = dias_esp[dt.weekday()] + " " + dt.strftime("%d/%m")
            f_hora = dt.strftime("%H:%M")
            safe_print(f"✅ [Éxito Cita] Creada para {nombre_paciente}: {f_dia} {f_hora}")
            return f"CITA_CONFIRMADA_201: Paciente: {nombre_paciente} | Día: {f_dia} | Hora: {f_hora}"
        elif r_cita.status_code == 409:
            return "ERROR_HORARIO_OCUPADO: Ese horario ya se encuentra ocupado por otra cita en la clínica. Por favor ofrece otro horario disponible."
        else:
            return f"ERROR_REGISTRO: El backend retornó código {r_cita.status_code}."
    except Exception as e:
        safe_print(f"[Error POST /api/citas]: {e}")
        return f"ERROR_CONEXION: No se pudo conectar con el servidor de la agenda ({e})."
