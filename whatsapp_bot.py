import asyncio, os, sys, re
from datetime import datetime, timezone, timedelta, time
from zoneinfo import ZoneInfo
from contextlib import asynccontextmanager
from typing import Optional
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
import uvicorn
from main import (
    SessionLocal,
    worker_sync_outbox,
    worker_recordatorios,
    worker_sync_inverso_google,
    worker_resumen_turnos_doctora,
    worker_control_mensual_ortodoncia
)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def safe_print(msg: str):
    try:
        print(msg)
    except Exception:
        try:
            print(msg.encode("ascii", errors="replace").decode("ascii"))
        except Exception:
            pass

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
gemini_client = None  # Compatible con parches externos y llamadas ligeras
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://127.0.0.1:8080")
DEFAULT_COUNTRY_CODE = os.getenv("DEFAULT_COUNTRY_CODE", "+591")
CLINICA_DIRECCION = os.getenv("CLINICA_DIRECCION", "Calle Lemoine 407 esquina Vallegrande, Santa Cruz de la Sierra, Bolivia")
CLINICA_NOMBRE = os.getenv("CLINICA_NOMBRE", "Soldent - Soluciones Dentales")
DOCTORA_NOMBRE = os.getenv("DOCTORA_NOMBRE", "Dra. Pamela Pinto Suárez")
DOCTORA_TELEFONO = os.getenv("DOCTORA_TELEFONO", "+59178472875")
BOT_PHONE_NUMBER = os.getenv("WHATSAPP_PHONE_NUMBER", "+59162422577")
API_BACKEND_URL = os.getenv("API_BACKEND_URL", "https://soldent-agenda.onrender.com")
SECRET_KEY = os.getenv("SECRET_KEY", "soldent_secret_key_pamela_2026")
BOT_HEADERS = {"X-Auth-Token": SECRET_KEY}

# Mensaje oficial por defecto ante fallas o falta de API key
MENSAJE_OFICIAL_DEFAULT = (
    "¡Hola! 🦷✨ Gracias por comunicarte con *Soldent - Soluciones Dentales*.\n\n"
    f"👩‍⚕️ *Especialista:* {DOCTORA_NOMBRE} (Odontología Integral & Ortodoncia)\n"
    f"📍 *Ubicación:* {CLINICA_DIRECCION}\n"
    f"📞 *Contacto / Urgencias:* {DOCTORA_TELEFONO}\n\n"
    "⏰ *Horarios Oficiales de Atención:*\n"
    "• Lunes a Viernes: 09:00 a 12:00 y 15:30 a 19:30\n"
    "• Sábados: 09:00 a 12:00 (Tardes y domingos cerrado)\n\n"
    "Todas nuestras atenciones se realizan bajo *Consulta Odontológica* previa cita. "
    "Para agendar, por favor indícanos tu nombre completo y el día y hora de tu preferencia, "
    f"o comunícate directamente al {DOCTORA_TELEFONO}. ¡Será un gusto atenderte!"
)

# Diccionario de historial de mensajes recientes por remitente
historial_sesiones = {}
mensajes_procesados_recientes = {}

def consultar_disponibilidad(fecha: str) -> str:
    """Consulta la disponibilidad de turnos en la clínica Soldent para una fecha determinada (formato YYYY-MM-DD)."""
    tz_bolivia = ZoneInfo("America/La_Paz")
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
        return f"MARTES_JUEVES_DIRECTO_DRA: Los días {dia_nombre} la agenda se coordina de manera directa y personalizada con la {DOCTORA_NOMBRE} al {DOCTORA_TELEFONO}. No se puede agendar por este bot para los días martes o jueves."

    citas_dia = []
    try:
        r = httpx.get(f"{API_BACKEND_URL}/api/citas", headers=BOT_HEADERS, timeout=6.0)
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
        r_pac = httpx.post(f"{API_BACKEND_URL}/api/pacientes", headers=BOT_HEADERS, json={
            "nombre": nombre_paciente.strip(),
            "telefono": tel_clean,
            "permitir_compartido": True
        }, timeout=6.0)

        if r_pac.status_code == 201:
            paciente_id = r_pac.json().get("id")
        else:
            digitos = "".join(c for c in tel_clean if c.isdigit())[-8:]
            sr = httpx.get(f"{API_BACKEND_URL}/api/pacientes?q={digitos}", headers=BOT_HEADERS, timeout=6.0)
            if sr.status_code == 200 and sr.json():
                paciente_id = sr.json()[0].get("id")
            else:
                primer_nombre = nombre_paciente.split()[0]
                sr2 = httpx.get(f"{API_BACKEND_URL}/api/pacientes?q={primer_nombre}", headers=BOT_HEADERS, timeout=6.0)
                if sr2.status_code == 200 and sr2.json():
                    paciente_id = sr2.json()[0].get("id")
    except Exception as e:
        safe_print(f"[Tool Error Paciente]: {e}")

    if not paciente_id:
        return "ERROR_PACIENTE: No se pudo registrar ni asociar al paciente en el sistema."

    tratamiento_id = None
    duracion_min = 30
    try:
        r_trat = httpx.get(f"{API_BACKEND_URL}/api/tratamientos", headers=BOT_HEADERS, timeout=6.0)
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

    tz_bolivia = ZoneInfo("America/La_Paz")
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
        return f"ERROR_MARTES_JUEVES_DIRECTO_DOCTORA: Las citas de los días martes y jueves se agendan de manera exclusiva y personalizada directamente con la {DOCTORA_NOMBRE} al {DOCTORA_TELEFONO}."

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
        r_citas_existentes = httpx.get(f"{API_BACKEND_URL}/api/citas", headers=BOT_HEADERS, timeout=6.0)
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
        r_cita = httpx.post(f"{API_BACKEND_URL}/api/citas", headers=BOT_HEADERS, json={
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

def construir_prompt_sistema(tel_paciente: str) -> str:
    tz_bolivia = ZoneInfo("America/La_Paz")
    ahora = datetime.now(tz_bolivia)
    dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    dia_nombre = dias[ahora.weekday()]
    fecha_actual_legible = f"{dia_nombre} {ahora.day}/{ahora.month}/{ahora.year}, hora actual: {ahora.strftime('%H:%M')} (Bolivia)"
    fecha_actual_iso = ahora.strftime("%Y-%m-%d")

    tel_limpio = re.sub(r"\D", "", str(tel_paciente or ""))
    tel_8 = tel_limpio[-8:] if len(tel_limpio) >= 8 else tel_limpio

    citas_este_paciente = []
    citas_ocupadas_otros = []

    try:
        from main import SessionLocal, Cita, Paciente
        db = SessionLocal()
        try:
            rows = db.query(Cita, Paciente).join(Paciente, Cita.paciente_id == Paciente.id).filter(
                Cita.estado.in_(["pendiente", "confirmada"])
            ).all()
            for cita, pac in rows:
                c_ini = cita.inicio.astimezone(tz_bolivia) if cita.inicio.tzinfo else cita.inicio.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz_bolivia)
                c_fin = cita.fin.astimezone(tz_bolivia) if cita.fin.tzinfo else cita.fin.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz_bolivia)
                pac_nom = pac.nombre or ""
                pac_tel_clean = re.sub(r"\D", "", str(pac.telefono or ""))

                d_nom = dias[c_ini.weekday()]
                fecha_fmt = f"{d_nom} {c_ini.day:02d}/{c_ini.month:02d}"
                hora_fmt = f"{c_ini.strftime('%H:%M')} a {c_fin.strftime('%H:%M')}"
                hora_12 = f"{c_ini.strftime('%I:%M %p').lstrip('0')}"
                estado_c = "Confirmada" if cita.estado == "confirmada" else "Pendiente de confirmación"

                es_de_este_paciente = False
                if pac_tel_clean and len(pac_tel_clean) >= 7 and tel_8:
                    pac_tel_8 = pac_tel_clean[-8:] if len(pac_tel_clean) >= 8 else pac_tel_clean
                    if tel_8 == pac_tel_8 or tel_8 in pac_tel_clean or pac_tel_8 in tel_limpio:
                        es_de_este_paciente = True

                if es_de_este_paciente:
                    citas_este_paciente.append(
                        f"• {fecha_fmt} a las {c_ini.strftime('%H:%M')} ({hora_12}) - Estado: {estado_c} (Paciente: {pac_nom})"
                    )
                else:
                    if ahora - timedelta(hours=2) <= c_ini <= ahora + timedelta(days=7):
                        citas_ocupadas_otros.append(f"{c_ini.strftime('%d/%m')} {c_ini.strftime('%H:%M')}-{c_fin.strftime('%H:%M')}")
        finally:
            db.close()
    except Exception as err_p:
        safe_print(f"[Prompt Citas Query Error]: {err_p}")

    if citas_este_paciente:
        texto_citas_paciente = "CITAS AGENDADAS A NOMBRE DE ESTE PACIENTE EN NUESTRO SISTEMA:\n" + "\n".join(citas_este_paciente)
    else:
        texto_citas_paciente = "El paciente NO registra citas agendadas con su número actual."

    ocupadas_texto = "; ".join(citas_ocupadas_otros[:14]) if citas_ocupadas_otros else "Sin turnos ocupados próximos"

    return f"""Eres el asistente virtual oficial de WhatsApp de 'SOLDENT - Clínica Odontológica', ubicada en {CLINICA_DIRECCION}.
Especialista a cargo: {DOCTORA_NOMBRE} (Especialista en Odontología Integral & Ortodoncia).
Teléfono de este bot (número automatizado): {BOT_PHONE_NUMBER}.
Teléfono directo de la Dra. Pamela (contacto personal / urgencias): {DOCTORA_TELEFONO}.
Teléfono del paciente que escribe: {tel_paciente}.

FECHA Y HORA ACTUAL: {fecha_actual_legible} (Fecha ISO: {fecha_actual_iso}).

{texto_citas_paciente}

TURNOS OCUPADOS EN CONSULTORIO POR OTROS PACIENTES:
{ocupadas_texto}.

HORARIOS OFICIALES DE ATENCIÓN DE SOLDENT (ESTRICTO):
• Lunes a Viernes: 09:00 a 12:00 y 15:30 a 19:30.
• Receso de Mediodía (CERRADO): 12:00 a 15:30 (NO atender ni ofrecer turnos).
• Sábados: 09:00 a 12:00 (Tardes de sábado cerrado).
• Domingos: CERRADO todo el día.

POLÍTICA DE SERVICIOS Y PRECIOS:
- ESPECIALIDADES DE LA DRA. PAMELA: La Dra. Pamela Pinto Suárez es especialista en Odontología Integral y Ortodoncia. Si el paciente pregunta qué tratamientos realiza o qué le puede hacer la doctora, explícale amablemente y con orgullo profesional: Ortodoncia (brackets y alineadores dentales), limpiezas profundas y profilaxis, curaciones y restauraciones estéticas en resina, evaluación general y diseño de sonrisas. Explícale que todo tratamiento inicia con una Evaluación Clínica / Consulta Odontológica para valorar su boca.
- PRECIOS: PROHIBIDO DAR PRECIOS O COTIZACIONES EXACTAS POR WHATSAPP. Si preguntan precios, indica amablemente que los costos se definen de manera personalizada tras la evaluación clínica presencial con la Dra. Pamela Pinto Suárez.
- PREGUNTAS CASUALES (ej. el clima, cómo estás, etc.): Responde con simpatía y calidez cruceña ("¡Por aquí todo excelente y con el consultorio listo para atenderte!", etc.) y conecta amablemente la conversación invitando a consultar dudas dentales o agendar su consulta.

REGLAS DE ATENCIÓN Y AGENDAMIENTO:
1. REGLA ESTRICTA - MARTES Y JUEVES (NO AGENDAR POR BOT, DERIVAR A LA DRA. PAMELA):
   - Los días MARTES y JUEVES este bot TIENE ESTRICTAMENTE PROHIBIDO agendar citas o confirmar turnos.
   - La atención de los días martes y jueves se coordina de manera EXCLUSIVA Y DIRECTA con la Dra. Pamela Pinto Suárez.
   - Si el paciente pide cita para un día MARTES o JUEVES, o pregunta por horarios de esos días:
     1. Explícale con amabilidad que la agenda de los días martes y jueves se coordina de forma personalizada y directa con la Dra. Pamela Pinto Suárez.
     2. Dale el número directo de la doctora: +591 78472875 para que le escriba o llame directamente.
     3. Indícale que si prefiere agendar por aquí mismo mediante el bot, con mucho gusto le puedes agendar para los días LUNES, MIÉRCOLES, VIERNES o SÁBADOS por la mañana.
     4. NUNCA generes la etiqueta [RESERVAR: ...] para un martes o jueves.

2. SI EL PACIENTE PREGUNTA SI TIENE CITA, CUÁNDO ES SU CITA O CONSULTA SU ESTADO:
   - Revisa la sección 'CITAS AGENDADAS A NOMBRE DE ESTE PACIENTE'.
   - Si tiene cita registrada, CONFÍRMASELO con total claridad y amabilidad, indicándole la fecha, la hora exacta (ej. "Lunes 05 de Octubre a las 19:00 (7:00 PM)") y su estado.
   - Si NO tiene ninguna cita registrada, dile con amabilidad que no figura ninguna cita a su nombre con este número y ofrécele con gusto los horarios disponibles para agendar.

2. SI EL PACIENTE PIDE AGENDAR EN UN HORARIO QUE ÉL MISMO YA TIENE AGENDADO (ej. a las 7:00 PM / 19:00 del lunes):
   - Aclárale con amabilidad que ese turno ya está reservado a su nombre en nuestro sistema:
     "¡Estimado/a! Justamente ese horario de las 7:00 PM (19:00) del lunes ya se encuentra reservado y agendado a su nombre en nuestro sistema. ¡Su espacio ya está asegurado!"
   - NO intentes reservarlo de nuevo ni digas que está ocupado por otra persona. Pregúntale si confirma su asistencia o si desea reprogramarlo a otro horario.

3. AGENDAR NUEVA CITA:
   - Para agendar necesitas: (1) Nombre completo del paciente, (2) Día y hora exacta dentro del horario de atención disponible.
   - Si el paciente CONFIRMA su nombre y un horario válido disponible (que no pertenezca a turnos ocupados), incluye al final de tu mensaje:
     [RESERVAR: Nombre Del Paciente | YYYY-MM-DDTHH:MM:SS]

4. TRATO Y TONO:
   - Sé cálido, educado y con trato amable típico de Santa Cruz de la Sierra ("¡Hola! Un gusto saludarte...", "Con todo gusto le ayudamos..."). Respuestas concisas para WhatsApp con emojis moderados.
"""

def llamar_gemini_http(prompt_sistema: str, historial: list) -> Optional[str]:
    """Invoca la API de Gemini mediante llamadas HTTP directas y ligeras (sin SDKs pesados)."""
    if not GEMINI_API_KEY:
        return None

    modelos = [
        "gemini-3.5-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-flash-latest",
        "gemini-3.8-flash"
    ]

    contents = []
    for item in historial:
        contents.append({
            "role": item["role"],
            "parts": [{"text": item["text"]}]
        })

    payload = {
        "system_instruction": {
            "parts": [{"text": prompt_sistema}]
        },
        "contents": contents,
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 600
        }
    }

    for modelo in modelos:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={GEMINI_API_KEY}"
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    cands = data.get("candidates", [])
                    if cands:
                        parts = cands[0].get("content", {}).get("parts", [])
                        if parts and "text" in parts[0]:
                            return parts[0]["text"].strip()
                elif resp.status_code in (404, 400):
                    continue
        except Exception as e:
            safe_print(f"[Gemini HTTP con {modelo}]: {e}")
            continue

    return None

def procesar_mensaje_con_gemini(remitente: str, nombre: str, texto: str, tel_paciente: str) -> str:
    """Procesa el mensaje del paciente con Gemini HTTP directo o devuelve respuesta oficial segura."""
    prompt_sistema = construir_prompt_sistema(tel_paciente)

    if remitente not in historial_sesiones:
        historial_sesiones[remitente] = []

    historial = historial_sesiones[remitente]
    historial.append({"role": "user", "text": f"Paciente ({nombre}): {texto}"})

    # Mantener últimos 6 mensajes para no sobrecargar el payload
    if len(historial) > 6:
        historial = historial[-6:]
        historial_sesiones[remitente] = historial

    respuesta_raw = llamar_gemini_http(prompt_sistema, historial)
    if not respuesta_raw:
        safe_print("⚠️ [Gemini HTTP] No hubo respuesta del modelo o API key ausente. Usando mensaje oficial por defecto.")
        return MENSAJE_OFICIAL_DEFAULT

    # Detectar si Gemini decidió ejecutar una reserva mediante la etiqueta [RESERVAR: Nombre | FechaHora]
    m_reserva = re.search(r"\[RESERVAR:\s*([^\|\]]+)\|\s*([^\]]+)\]", respuesta_raw)
    if m_reserva:
        nombre_cita = m_reserva.group(1).strip() or nombre
        fecha_cita = m_reserva.group(2).strip()
        safe_print(f"🎯 [Agendamiento Detectado]: {nombre_cita} para {fecha_cita}")

        resultado_reserva = crear_cita(nombre_cita, tel_paciente, fecha_cita)

        if "CITA_CONFIRMADA_201" in resultado_reserva:
            # Formato oficial estandarizado solicitado
            tz_bolivia = ZoneInfo("America/La_Paz")
            try:
                dt_c = datetime.fromisoformat(fecha_cita.replace(" ", "T"))
                dias_esp = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
                f_dia = f"{dias_esp[dt_c.weekday()]} {dt_c.strftime('%d/%m')}"
                f_hora = dt_c.strftime("%H:%M")
            except Exception:
                f_dia = "la fecha solicitada"
                f_hora = ""

            msg_confirmacion = (
                f"¡Perfecto, {nombre_cita}! 🦷✨\n"
                f"Su consulta odontológica ha quedado agendada y registrada en nuestro sistema con la {DOCTORA_NOMBRE} para el {f_dia} a las {f_hora}.\n\n"
                f"Le esperamos en nuestro consultorio ubicado en la {CLINICA_DIRECCION}.\n\n"
                f"Si tuviera alguna duda o inconveniente, puede escribirnos por aquí o llamar al {DOCTORA_TELEFONO}.\n"
                "¡Que tenga un excelente día!"
            )
            historial.append({"role": "model", "text": msg_confirmacion})

            # NOTIFICACIÓN INMEDIATA A LA DRA. PAMELA (+591 78472875)
            msg_alerta_doctora = (
                "🦷 *SOLDENT - Nueva Cita Agendada por Bot*\n\n"
                f"Estimada Dra. Pamela, un paciente acaba de agendar una consulta a través del asistente de WhatsApp:\n\n"
                f"👤 *Paciente:* {nombre_cita}\n"
                f"📱 *Teléfono:* {tel_paciente}\n"
                f"🗓️ *Fecha y Hora:* {f_dia} a las {f_hora}\n"
                f"🩺 *Servicio:* Consulta Odontológica\n\n"
                "✅ Ya se encuentra guardada en su agenda web y sincronizada con Google Calendar."
            )
            try:
                httpx.post(
                    f"{EVOLUTION_API_URL}/send-message",
                    json={"number": DOCTORA_TELEFONO, "text": msg_alerta_doctora, "message": msg_alerta_doctora},
                    timeout=5.0
                )
                safe_print(f"✅ [Alerta Doctora] Notificación enviada a la Dra. Pamela ({DOCTORA_TELEFONO}) por nueva cita de {nombre_cita}")
            except Exception as err_doc:
                safe_print(f"⚠️ [Alerta Doctora Error] No se pudo enviar notificación a la doctora: {err_doc}")

            return msg_confirmacion

        elif "ERROR_HORARIO_OCUPADO" in resultado_reserva:
            msg_ocupado = (
                "Ese horario ya se encuentra ocupado por otra cita en el consultorio. "
                "Con gusto le ofrezco agendar en el siguiente turno libre o en un horario diferente dentro de nuestros turnos oficiales."
            )
            historial.append({"role": "model", "text": msg_ocupado})
            return msg_ocupado

        elif "AVISO_CITA_EXISTENTE" in resultado_reserva:
            historial.append({"role": "model", "text": resultado_reserva})
            return (
                f"¡Estimado/a {nombre_cita}! Le recordamos que ya cuenta con una consulta odontológica activa "
                f"agendada en Soldent. Le esperamos en la {CLINICA_DIRECCION}."
            )

        elif "ERROR_MARTES_JUEVES_DIRECTO_DOCTORA" in resultado_reserva:
            msg_directo = (
                f"¡Estimado/a {nombre_cita}! Las citas para los días martes y jueves se coordinan de manera exclusiva y personalizada directamente con la {DOCTORA_NOMBRE}.\n\n"
                f"📲 Por favor comuníquese directamente a su WhatsApp o llámele al *{DOCTORA_TELEFONO}* para coordinar su espacio.\n\n"
                "Si prefiere agendar por aquí mismo mediante el asistente, con mucho gusto podemos ayudarle para los días Lunes, Miércoles, Viernes o Sábado."
            )
            historial.append({"role": "model", "text": msg_directo})
            return msg_directo

        elif any(err in resultado_reserva for err in ("ERROR_RECESO_MEDIODIA", "ERROR_SABADO_TARDE_CERRADO", "ERROR_DOMINGO_CERRADO", "ERROR_HORARIO_NO_PERMITIDO")):
            historial.append({"role": "model", "text": resultado_reserva})
            return (
                "El horario solicitado está fuera de nuestros turnos oficiales. "
                "Atendemos de Lunes a Viernes de 09:00 a 12:00 y de 15:30 a 19:30, y Sábados de 09:00 a 12:00. "
                "¿Qué turno de esos le quedaría más cómodo?"
            )

    # Si fue respuesta conversacional normal, limpiar posibles etiquetas internas y devolver
    texto_limpio = re.sub(r"\[RESERVAR:[^\]]*\]", "", respuesta_raw).strip()
    if not texto_limpio:
        texto_limpio = MENSAJE_OFICIAL_DEFAULT

    historial.append({"role": "model", "text": texto_limpio})
    return texto_limpio

def obtener_datos_completos_agenda_doctora() -> tuple[str, str]:
    """Obtiene la agenda estructurada y calcula los horarios libres de los próximos 7 días para la doctora."""
    tz_bol = ZoneInfo("America/La_Paz")
    ahora_bol = datetime.now(tz_bol)
    hoy = ahora_bol.date()

    citas_raw = []
    try:
        r = httpx.get(f"{API_BACKEND_URL}/api/citas", headers=BOT_HEADERS, timeout=6.0)
        if r.status_code == 200:
            citas_raw = r.json()
    except Exception as e:
        safe_print(f"[Agenda Doctora Backend Error]: {e}")

    dias_esp = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    resumen_citas_por_dia = {}
    citas_por_dia_times = {}

    for i in range(7):
        d_target = hoy + timedelta(days=i)
        resumen_citas_por_dia[d_target] = []
        citas_por_dia_times[d_target] = []

    for c in citas_raw:
        if (c.get("estado") or "").lower() in ("pendiente", "confirmada"):
            ini_str = c.get("inicio", "")
            fin_str = c.get("fin", "")
            if ini_str and fin_str:
                ini_dt = datetime.fromisoformat(ini_str.replace("Z", "+00:00")).astimezone(tz_bol)
                fin_dt = datetime.fromisoformat(fin_str.replace("Z", "+00:00")).astimezone(tz_bol)
                d_cita = ini_dt.date()
                if d_cita in resumen_citas_por_dia:
                    pac_obj = c.get("paciente") or {}
                    pac_nom = pac_obj.get("nombre") or c.get("paciente_nombre") or "Paciente"
                    pac_tel = pac_obj.get("telefono") or "Sin cel"
                    estado_str = "✅ Confirmada" if (c.get("estado") or "").lower() == "confirmada" else "⏳ Pendiente"
                    h_ini = ini_dt.strftime("%H:%M")
                    h_fin = fin_dt.strftime("%H:%M")
                    notas = f" (Nota: {c.get('notas')})" if c.get("notas") else ""
                    resumen_citas_por_dia[d_cita].append(
                        f"• {h_ini} - {h_fin}: {pac_nom} (Tel: {pac_tel}) [{estado_str}]{notas}"
                    )
                    citas_por_dia_times[d_cita].append((ini_dt.time(), fin_dt.time()))

    # Armar texto de citas
    lineas_citas = []
    for d_target, lista in resumen_citas_por_dia.items():
        nom_d = dias_esp[d_target.weekday()]
        f_str = d_target.strftime("%d/%m")
        etiqueta = "HOY" if d_target == hoy else ("MAÑANA" if d_target == hoy + timedelta(days=1) else nom_d)
        if not lista:
            lineas_citas.append(f"📅 {etiqueta} ({nom_d} {f_str}): Sin citas registradas.")
        else:
            lineas_citas.append(f"📅 {etiqueta} ({nom_d} {f_str}):\n" + "\n".join(lista))

    texto_citas = "\n\n".join(lineas_citas)

    # Armar texto de horarios libres listos para enviar a pacientes
    lineas_libres = []
    for d_target, lista_times in citas_por_dia_times.items():
        nom_d = dias_esp[d_target.weekday()]
        f_str = d_target.strftime("%d/%m")
        etiqueta = "HOY" if d_target == hoy else ("MAÑANA" if d_target == hoy + timedelta(days=1) else nom_d)

        weekday = d_target.weekday()
        if weekday == 6:
            lineas_libres.append(f"📅 {etiqueta} ({nom_d} {f_str}): Domingo cerrado todo el día.")
            continue

        lista_times.sort(key=lambda x: x[0])
        turnos = [(time(9, 0), time(12, 0))]
        if weekday <= 4:
            turnos.append((time(15, 30), time(19, 30)))

        bloques_dia = []
        for t_ini, t_fin in turnos:
            nom_t = "🌅 Turno Mañana (09:00 a 12:00)" if t_ini == time(9, 0) else "🌇 Turno Tarde (15:30 a 19:30)"
            libres_turno = []
            cursor = t_ini
            citas_turno = [c for c in lista_times if c[0] < t_fin and c[1] > t_ini]
            for c_ini, c_fin in citas_turno:
                c_ini_clamp = max(cursor, c_ini)
                if c_ini_clamp > cursor:
                    libres_turno.append(f"• {cursor.strftime('%H:%M')} a {c_ini_clamp.strftime('%H:%M')}")
                cursor = max(cursor, c_fin)
            if cursor < t_fin:
                libres_turno.append(f"• {cursor.strftime('%H:%M')} a {t_fin.strftime('%H:%M')}")

            if libres_turno:
                bloques_dia.append(f"{nom_t}:\n" + "\n".join(libres_turno))
            else:
                bloques_dia.append(f"{nom_t}: (Turno completo ocupado)")

        lineas_libres.append(f"📅 {etiqueta} ({nom_d} {f_str}):\n" + "\n".join(bloques_dia))

    texto_libres = "\n\n".join(lineas_libres)
    return texto_citas, texto_libres

def procesar_mensaje_doctora(remitente: str, texto: str) -> str:
    """Atiende a la Dra. Pamela como su Asistente Personal: citas, horarios libres, datos de pacientes y bloqueos."""
    global historial_sesiones
    if remitente not in historial_sesiones:
        historial_sesiones[remitente] = []

    historial = historial_sesiones[remitente]
    historial.append({"role": "user", "text": texto})
    if len(historial) > 10:
        historial = historial[-10:]
        historial_sesiones[remitente] = historial

    texto_citas, texto_libres = obtener_datos_completos_agenda_doctora()

    tz_bol = ZoneInfo("America/La_Paz")
    ahora_bol = datetime.now(tz_bol)
    dias_esp = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    dia_actual_nom = dias_esp[ahora_bol.weekday()]
    fecha_actual_legible = f"{dia_actual_nom} {ahora_bol.day}/{ahora_bol.month}/{ahora_bol.year}"
    hora_actual = ahora_bol.strftime("%H:%M")

    prompt_sistema = f"""Eres el Asistente Médico y Administrativo Personal de la Dra. Pamela Pinto Suárez, odontóloga y directora de 'SOLDENT - Soluciones Dentales'.
Estás hablando DIRECTAMENTE con la Dra. Pamela en su WhatsApp privado (+591 78472875).
NUNCA la trates como a un paciente ni le preguntes su nombre o motivo de consulta. Trátala como tu jefa y especialista de la clínica ("Dra. Pamela", "Con todo gusto, doctora").

HORA ACTUAL EN SANTA CRUZ: {fecha_actual_legible}, hora {hora_actual}.

HORARIOS OFICIALES DE SOLDENT:
• Lunes a Viernes: 09:00 a 12:00 y 15:30 a 19:30 (receso de mediodía de 12:00 a 15:30).
• Sábados: 09:00 a 12:00 (tardes cerrado).
• Domingos: Cerrado todo el día.

AGENDA ACTUALIZADA DE CITAS:
{texto_citas}

HORARIOS LIBRES CALCULADOS (Listos para enviar a pacientes):
{texto_libres}

TUS INSTRUCCIONES:
1. SI LA DOCTORA PIDE HORARIOS LIBRES O DISPONIBLES (ej: de hoy, mañana o un día específico):
   Entrégale la lista limpia de horarios disponibles para el día solicitado en un formato listo para copiar y reenviar a su paciente.
   Organízalo en:
   🌅 Turno Mañana (09:00 a 12:00)
   🌇 Turno Tarde (15:30 a 19:30)
   Añade al final: "📋 (Puede copiar este mensaje y reenviarlo directamente a su paciente)".

2. SI LA DOCTORA PREGUNTA POR SUS CITAS O AGENDA (ej: de hoy o mañana):
   Muéstrale los pacientes programados con sus horas, nombres, teléfonos, estado (✅ Confirmada / ⏳ Pendiente) y notas clínicas.

3. SI LA DOCTORA TE PIDE AGENDAR O BLOQUEAR UN HORARIO:
   - Para agendar: confirma amablemente y añade al final de tu mensaje [RESERVAR: Nombre | YYYY-MM-DDTHH:MM:SS]
   - Para bloquear un turno: confirma amablemente y añade al final de tu mensaje [BLOQUEAR: Motivo | YYYY-MM-DDTHH:MM:SS]

4. SI LA DOCTORA PREGUNTA QUIÉNES CONFIRMARON:
   Muéstrale quiénes ya confirmaron asistencia mediante WhatsApp y quiénes siguen pendientes.

5. TONO:
   Extremadamente servicial, rápido, organizado y respetuoso. Formato impecable con emojis moderados.
"""

    respuesta = llamar_gemini_http(prompt_sistema, historial)
    if not respuesta:
        texto_lower = texto.lower()
        if any(w in texto_lower for w in ("libre", "disponib", "espacio", "horario")):
            respuesta = (
                f"Dra. Pamela, estos son los horarios disponibles más próximos en su agenda:\n\n"
                f"{texto_libres[:1200]}\n\n"
                "📋 (Puede copiar este bloque y reenviarlo directamente a su paciente)."
            )
        elif any(w in texto_lower for w in ("cita", "agenda", "paciente", "quien", "programad")):
            respuesta = (
                f"Dra. Pamela, este es el detalle de sus citas registradas:\n\n"
                f"{texto_citas[:1200]}"
            )
        else:
            respuesta = (
                "Con todo gusto, Dra. Pamela. Estoy a su servicio. Puede consultarme:\n"
                "• '¿Qué citas tengo hoy (o mañana)?'\n"
                "• 'Horarios libres de mañana para pasarle a un paciente'\n"
                "• '¿Quiénes ya confirmaron para hoy?'\n"
                "• 'Agéndame a [Nombre] el [Día] a las [Hora]'\n"
                "• 'Bloquea el [Día] de [Hora] a [Hora] por cirugía/personal'"
            )

    # Si se solicitó reserva o bloqueo
    m_res = re.search(r"\[RESERVAR:\s*([^\|\]]+)\|\s*([^\]]+)\]", respuesta)
    if m_res:
        nom_c = m_res.group(1).strip()
        f_c = m_res.group(2).strip()
        crear_cita(nom_c, DOCTORA_TELEFONO, f_c)

    m_bloq = re.search(r"\[BLOQUEAR:\s*([^\|\]]+)\|\s*([^\]]+)\]", respuesta)
    if m_bloq:
        motivo_b = m_bloq.group(1).strip()
        f_b = m_bloq.group(2).strip()
        crear_cita(f"BLOQUEADO: {motivo_b}", DOCTORA_TELEFONO, f_b)

    respuesta_limpia = re.sub(r"\[RESERVAR:[^\]]*\]", "", respuesta)
    respuesta_limpia = re.sub(r"\[BLOQUEAR:[^\]]*\]", "", respuesta_limpia).strip()

    historial.append({"role": "model", "text": respuesta_limpia})
    return respuesta_limpia

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(loop_workers_automaticos())
    yield
    task.cancel()

app = FastAPI(title="Soldent WhatsApp Bot", lifespan=lifespan)

async def enviar_mensaje_whatsapp(numero: str, texto: str):
    """Envía un mensaje de texto a través de la pasarela Baileys/Evolution asegurando texto válido."""
    url = f"{EVOLUTION_API_URL}/send-message"
    texto_seguro = str(texto or MENSAJE_OFICIAL_DEFAULT).strip()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json={
                "number": numero,
                "text": texto_seguro,
                "message": texto_seguro
            })
            if resp.status_code == 200:
                safe_print(f"[Bot OUT] Enviado con éxito a {numero}")
            else:
                safe_print(f"[Bot OUT Error] {resp.status_code}: {resp.text}")
    except Exception as e:
        safe_print(f"[Bot OUT Error] No se pudo conectar con la pasarela WhatsApp ({url}): {e}")

@app.post("/webhook")
async def recibir_mensaje(req: Request):
    try:
        data = await req.json()
    except Exception as err:
        return {"ok": False, "error": f"JSON invalido: {err}"}

    remitente = data.get("from")
    nombre = data.get("name", "Paciente")
    texto = data.get("text", "").strip()
    tel_paciente = data.get("phone", "") or (data.get("resolvedPhone") or "").replace("@s.whatsapp.net", "").replace("@lid", "") or (remitente or "").replace("@s.whatsapp.net", "").replace("@lid", "")

    if not tel_paciente.startswith("+"):
        tel_paciente = "+" + tel_paciente

    if not remitente or not texto:
        return {"ok": False}

    # CANAL DE ATENCIÓN A LA DRA. PAMELA (Modo Asistente Personal)
    is_doctor = data.get("isDoctor", False) or ("78472875" in tel_paciente) or ("78472875" in (remitente or ""))
    if is_doctor:
        safe_print(f"\n[WhatsApp IN] 👩‍⚕️ Dra. Pamela ({tel_paciente}): {texto}")
        try:
            texto_respuesta = await asyncio.to_thread(
                procesar_mensaje_doctora,
                remitente, texto
            )
            safe_print(f"[Asistente Doctora OUT]: {texto_respuesta}\n")
            await enviar_mensaje_whatsapp(remitente, texto_respuesta)
            return {"ok": True, "doctora": True, "respuesta": texto_respuesta}
        except Exception as e:
            safe_print(f"[Error Asistente Doctora]: {e}")
            fallback_doc = (
                "Dra. Pamela, recibí su consulta. Puede preguntarme:\n"
                "• '¿Qué citas tengo hoy (o mañana)?'\n"
                "• 'Horarios libres de mañana para pasarle a un paciente'\n"
                "• '¿Quiénes ya confirmaron para hoy?'"
            )
            await enviar_mensaje_whatsapp(remitente, fallback_doc)
            return {"ok": True, "doctora": True, "respuesta": fallback_doc}

    global mensajes_procesados_recientes
    ahora_ts = datetime.now().timestamp()
    mensajes_procesados_recientes = {k: v for k, v in mensajes_procesados_recientes.items() if ahora_ts - v < 60}
    clave_msg = (remitente, texto.lower())
    if clave_msg in mensajes_procesados_recientes and (ahora_ts - mensajes_procesados_recientes[clave_msg]) < 15:
        safe_print(f"[WhatsApp IN] Mensaje duplicado o reintento rápido ignorado (<15s): '{texto}'")
        return {"ok": True, "duplicado": True}
    mensajes_procesados_recientes[clave_msg] = ahora_ts

    safe_print(f"\n[WhatsApp IN] De: {nombre} ({remitente} | {tel_paciente}): {texto}")

    try:
        texto_respuesta = await asyncio.to_thread(
            procesar_mensaje_con_gemini,
            remitente, nombre, texto, tel_paciente
        )
        if not texto_respuesta:
            texto_respuesta = MENSAJE_OFICIAL_DEFAULT

        safe_print(f"[Gemini OUT]: {texto_respuesta}\n")
        await enviar_mensaje_whatsapp(remitente, texto_respuesta)

        # Si el paciente consultó por martes o jueves, notificar por cortesía a la Dra. Pamela
        texto_low = texto.lower()
        if any(d in texto_low for d in ("martes", "jueves")):
            msg_alerta_dra = (
                "🦷 *SOLDENT - Paciente Interesado en Martes/Jueves*\n\n"
                f"Dra. Pamela, el paciente *{nombre}* ({tel_paciente}) consultó por atención:\n"
                f"💬 *Mensaje:* \"{texto}\"\n\n"
                f"👉 El bot le indicó que coordine directamente con usted a su WhatsApp ({DOCTORA_TELEFONO})."
            )
            try:
                await enviar_mensaje_whatsapp(DOCTORA_TELEFONO, msg_alerta_dra)
                safe_print(f"✅ [Alerta Martes/Jueves] Notificación enviada a la Dra. Pamela sobre {nombre}")
            except Exception as e_alerta:
                safe_print(f"⚠️ [Error Alerta Martes/Jueves]: {e_alerta}")

        return {"ok": True, "respuesta": texto_respuesta}

    except Exception as e:
        safe_print(f"[Error Procesando Webhook]: {e}")
        texto_respuesta = MENSAJE_OFICIAL_DEFAULT
        await enviar_mensaje_whatsapp(remitente, texto_respuesta)
        return {"ok": True, "respuesta": texto_respuesta}

async def loop_workers_automaticos():
    """Ejecuta los workers periódicamente para recordatorios de 1h, outbox y sincronización inversa de Google Calendar."""
    safe_print("[Workers] Iniciando ciclo automático de recordatorios y sincronización con Google Calendar...")
    ciclo = 0
    while True:
        try:
            db = SessionLocal()
            try:
                # 0. Anti-Sleep Render Keep-Alive (evita que el servidor en la nube se duerma tras 15 min)
                if ciclo % 7 == 0:
                    try:
                        async with httpx.AsyncClient(timeout=10.0) as client_keepalive:
                            r_ping = await client_keepalive.get("https://soldent-agenda.onrender.com/api/salud")
                            if r_ping.status_code == 200:
                                safe_print("⚡ [Render Keep-Alive] Ping enviado a soldent-agenda.onrender.com (Servidor 24/7 activo)")
                    except Exception as err_ping:
                        safe_print(f"⚠️ [Render Keep-Alive Error]: {err_ping}")

                # 1. Sincronizar citas pendientes locales hacia Google Calendar (Outbox)
                worker_sync_outbox(db)
                # 2. Enviar recordatorios automáticos de 3 horas a pacientes
                worker_recordatorios(db)
                # 3. Resumen de turnos a la Dra. Pamela (20 min antes de abrir en la mañana y tarde)
                worker_resumen_turnos_doctora(db)
                # 4. Sincronización Inversa (iPhone / Google Calendar -> Base de Datos)
                if ciclo % 2 == 0:
                    worker_sync_inverso_google(db)
                # 5. Control Mensual de Ortodoncia (revisión diaria de pacientes vencidos)
                if ciclo % 10 == 0:
                    worker_control_mensual_ortodoncia(db)
                ciclo += 1
            finally:
                db.close()
        except Exception as e:
            safe_print(f"[Workers Error]: {e}")

        await asyncio.sleep(60)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5005)
