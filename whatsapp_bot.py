import asyncio, os, sys, re
from datetime import datetime, timezone, timedelta, time
from zoneinfo import ZoneInfo
from contextlib import asynccontextmanager
from typing import Optional
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
import uvicorn
from main import SessionLocal, worker_sync_outbox, worker_recordatorios, worker_sync_inverso_google

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
API_BACKEND_URL = os.getenv("API_BACKEND_URL", "https://soldent-agenda.onrender.com")

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

    citas_dia = []
    try:
        r = httpx.get(f"{API_BACKEND_URL}/api/citas", timeout=6.0)
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
        r_pac = httpx.post(f"{API_BACKEND_URL}/api/pacientes", json={
            "nombre": nombre_paciente.strip(),
            "telefono": tel_clean
        }, timeout=6.0)

        if r_pac.status_code == 201:
            paciente_id = r_pac.json().get("id")
        else:
            digitos = "".join(c for c in tel_clean if c.isdigit())[-8:]
            sr = httpx.get(f"{API_BACKEND_URL}/api/pacientes?q={digitos}", timeout=6.0)
            if sr.status_code == 200 and sr.json():
                paciente_id = sr.json()[0].get("id")
            else:
                primer_nombre = nombre_paciente.split()[0]
                sr2 = httpx.get(f"{API_BACKEND_URL}/api/pacientes?q={primer_nombre}", timeout=6.0)
                if sr2.status_code == 200 and sr2.json():
                    paciente_id = sr2.json()[0].get("id")
    except Exception as e:
        safe_print(f"[Tool Error Paciente]: {e}")

    if not paciente_id:
        return "ERROR_PACIENTE: No se pudo registrar ni asociar al paciente en el sistema."

    tratamiento_id = None
    duracion_min = 30
    try:
        r_trat = httpx.get(f"{API_BACKEND_URL}/api/tratamientos", timeout=6.0)
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
        r_citas_existentes = httpx.get(f"{API_BACKEND_URL}/api/citas", timeout=6.0)
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
        r_cita = httpx.post(f"{API_BACKEND_URL}/api/citas", json={
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

    # Resumen de citas ocupadas próximas
    citas_proximas = []
    try:
        r = httpx.get(f"{API_BACKEND_URL}/api/citas", timeout=4.0)
        if r.status_code == 200:
            for c in r.json():
                if (c.get("estado") or "").lower() in ("pendiente", "confirmada"):
                    c_ini_str = c.get("inicio", "")
                    c_fin_str = c.get("fin", "")
                    if c_ini_str and c_fin_str:
                        c_ini = datetime.fromisoformat(c_ini_str.replace("Z", "+00:00")).astimezone(tz_bolivia)
                        c_fin = datetime.fromisoformat(c_fin_str.replace("Z", "+00:00")).astimezone(tz_bolivia)
                        if ahora - timedelta(hours=2) <= c_ini <= ahora + timedelta(days=5):
                            citas_proximas.append(f"{c_ini.strftime('%d/%m')} de {c_ini.strftime('%H:%M')} a {c_fin.strftime('%H:%M')}")
    except Exception:
        pass

    ocupadas_texto = "; ".join(citas_proximas[:8]) if citas_proximas else "Sin turnos ocupados próximos"

    return f"""Eres el asistente virtual oficial de WhatsApp de 'SOLDENT - Clínica Odontológica', ubicada en {CLINICA_DIRECCION}.
Especialista a cargo: {DOCTORA_NOMBRE} (Especialista en Odontología Integral & Ortodoncia).
Teléfono directo del consultorio: {DOCTORA_TELEFONO}.
Teléfono del paciente: {tel_paciente}.

FECHA Y HORA ACTUAL: {fecha_actual_legible} (Fecha ISO: {fecha_actual_iso}).
TURNOS YA OCUPADOS PRÓXIMOS EN CONSULTORIO: {ocupadas_texto}.

HORARIOS OFICIALES DE ATENCIÓN DE SOLDENT (ESTRICTO):
• Lunes a Viernes: 09:00 a 12:00 y 15:30 a 19:30.
• Receso de Mediodía (CERRADO): 12:00 a 15:30 (NO atender ni ofrecer turnos).
• Sábados: 09:00 a 12:00 (Tardes de sábado cerrado).
• Domingos: CERRADO todo el día.

POLÍTICA DE SERVICIOS Y PRECIOS:
- Todas las atenciones se estandarizan como "Consulta Odontológica" (o "su consulta"). No menciones nombres de tratamientos específicos (ej. limpieza, resina, ortodoncia, etc.).
- PROHIBIDO DAR PRECIOS O COTIZACIONES POR WHATSAPP. Si preguntan precios, indica amablemente que los costos se definen de manera personalizada tras la evaluación clínica con la Dra. Pamela Pinto Suárez.

REGLAS DE ATENCIÓN Y AGENDAMIENTO:
- Sé cálido, educado y con trato amable típico de Santa Cruz de la Sierra ("¡Hola! Un gusto saludarte...", "Con todo gusto le ayudamos..."). Respuestas concisas para WhatsApp con emojis moderados.
- Si el paciente pide un turno ocupado o fuera de horario, explícale amablemente y ofrece las opciones oficiales libres.
- Para agendar necesitas: (1) Nombre completo del paciente, (2) Día y hora exacta dentro del horario de atención.
- Si el paciente CONFIRMA su nombre y un horario válido disponible, incluye al final de tu mensaje la siguiente instrucción de reserva exacta:
[RESERVAR: Nombre Del Paciente | YYYY-MM-DDTHH:MM:SS]
Ejemplo: [RESERVAR: Carlos Perez | 2026-10-03T10:00:00]
"""

def llamar_gemini_http(prompt_sistema: str, historial: list) -> Optional[str]:
    """Invoca la API de Gemini mediante llamadas HTTP directas y ligeras (sin SDKs pesados)."""
    if not GEMINI_API_KEY:
        return None

    modelos = [
        "gemini-1.5-flash",
        "gemini-flash-latest",
        "gemini-2.5-flash",
        "gemini-3.1-flash-lite-preview"
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
        async with httpx.AsyncClient(timeout=10.0) as client:
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
                # 1. Sincronizar citas pendientes locales hacia Google Calendar (Outbox)
                worker_sync_outbox(db)
                # 2. Enviar recordatorios automáticos de 1 hora
                worker_recordatorios(db)
                # 3. Sincronización Inversa (iPhone / Google Calendar -> Base de Datos)
                if ciclo % 2 == 0:
                    worker_sync_inverso_google(db)
                ciclo += 1
            finally:
                db.close()
        except Exception as e:
            safe_print(f"[Workers Error]: {e}")

        await asyncio.sleep(60)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5005)
