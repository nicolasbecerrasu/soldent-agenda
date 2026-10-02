import asyncio, os, sys
from datetime import datetime, timezone, timedelta, time
from zoneinfo import ZoneInfo
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request
import uvicorn
from google import genai
from google.genai import types
from main import SessionLocal, worker_sync_outbox, worker_recordatorios

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

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
DEFAULT_COUNTRY_CODE = os.getenv("DEFAULT_COUNTRY_CODE", "+591")
CLINICA_DIRECCION = os.getenv("CLINICA_DIRECCION", "Calle Lemoine 407 esquina Vallegrande, Santa Cruz de la Sierra, Bolivia")
DOCTORA_NOMBRE = os.getenv("DOCTORA_NOMBRE", "Dra. Pamela Pinto Suárez")
API_BACKEND_URL = os.getenv("API_BACKEND_URL", "http://127.0.0.1:8000")

# Inicializar cliente Gemini oficial
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

# Diccionario de sesiones de chat activas por remitente
sesiones_chat = {}
mensajes_procesados_recientes = {}

def consultar_disponibilidad(fecha: str) -> str:
    """Consulta la disponibilidad de turnos en la clínica Soldent para una fecha determinada (formato YYYY-MM-DD), retornando qué horarios ya están ocupados y a partir de qué hora hay turnos libres.

    Args:
        fecha: Fecha a consultar en formato YYYY-MM-DD (ej: '2026-10-03'). Si el paciente menciona 'hoy', 'mañana' o un día como 'sábado', calcula la fecha exacta en formato YYYY-MM-DD.
    """
    safe_print(f"\n[TOOL CALL: consultar_disponibilidad] Fecha: {fecha}")
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
        return f"DOMINGO_CERRADO: El {dia_nombre} {fecha_fmt} la clínica Soldent permanece cerrada todo el día. Atendemos de Lunes a Viernes de 09:00 a 12:00 y de 15:30 a 19:30, y Sábados de 09:00 a 12:00."

    # Obtener citas existentes activas
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
        safe_print(f"[Tool Error Disponibilidad]: {e}")

    citas_dia.sort(key=lambda x: x[0])

    if dt_target.weekday() == 5:  # Sábado
        horario_texto = "Sábados: turno mañana de 09:00 a 12:00 (tardes cerrado)"
    else:  # Lunes a Viernes
        horario_texto = "Lunes a Viernes: mañana de 09:00 a 12:00 y tarde de 15:30 a 19:30 (receso de mediodía de 12:00 a 15:30)"

    if not citas_dia:
        return f"DISPONIBILIDAD_TOTAL: Para el {dia_nombre} {fecha_fmt} ({horario_texto}), todos los turnos están 100% libres y disponibles."

    ocupados = [f"{ini.strftime('%H:%M')} a {fin.strftime('%H:%M')}" for ini, fin in citas_dia]
    ocupados_str = ", ".join(ocupados)

    # Identificar la hora a partir de la cual queda libre
    ultima_fin = citas_dia[-1][1]
    siguiente_hora = ultima_fin.strftime("%H:%M")

    return (
        f"DISPONIBILIDAD_HORARIOS: Para el {dia_nombre} {fecha_fmt} ({horario_texto}): "
        f"HORARIOS YA OCUPADOS: {ocupados_str}. "
        f"HORARIOS LIBRES: Con gusto hay disponibilidad a partir de las {siguiente_hora} am o en los demás espacios disponibles dentro de los turnos oficiales."
    )

def crear_cita(nombre_paciente: str, telefono: str, fecha_hora_inicio: str, tratamiento_nombre: str = "Consulta y Diagnóstico") -> str:
    """Registra una consulta odontológica en la base de datos de Soldent y la encola para sincronizar con Google Calendar.

    Args:
        nombre_paciente: Nombre completo del paciente (ej: 'Nicolas Becerra').
        telefono: Número de teléfono o WhatsApp del paciente (ej: '+59170277520' o '70277520').
        fecha_hora_inicio: Fecha y hora de inicio de la cita en formato ISO (YYYY-MM-DDTHH:MM:SS) en hora de Bolivia (America/La_Paz, UTC-4).
        tratamiento_nombre: Por defecto 'Consulta y Diagnóstico'. Todas las atenciones se estandarizan como Consulta Odontológica.
    """
    safe_print(f"\n[TOOL CALL: crear_cita] Paciente: {nombre_paciente} | Tel: {telefono} | Inicio: {fecha_hora_inicio}")

    tel_clean = telefono.strip()
    if not tel_clean.startswith("+"):
        tel_clean = "+" + tel_clean

    # 1. Crear o asociar paciente en el backend
    paciente_id = None
    try:
        r_pac = httpx.post(f"{API_BACKEND_URL}/api/pacientes", json={
            "nombre": nombre_paciente.strip(),
            "telefono": tel_clean
        }, timeout=6.0)

        if r_pac.status_code == 201:
            paciente_id = r_pac.json().get("id")
            safe_print(f"[Tool] Paciente nuevo creado: {paciente_id}")
        else:
            # Si ya existe (409), buscarlo por los últimos dígitos de su teléfono o por nombre
            digitos = "".join(c for c in tel_clean if c.isdigit())[-8:]
            sr = httpx.get(f"{API_BACKEND_URL}/api/pacientes?q={digitos}", timeout=6.0)
            if sr.status_code == 200 and sr.json():
                paciente_id = sr.json()[0].get("id")
                safe_print(f"[Tool] Paciente existente encontrado por teléfono: {paciente_id}")
            else:
                primer_nombre = nombre_paciente.split()[0]
                sr2 = httpx.get(f"{API_BACKEND_URL}/api/pacientes?q={primer_nombre}", timeout=6.0)
                if sr2.status_code == 200 and sr2.json():
                    paciente_id = sr2.json()[0].get("id")
                    safe_print(f"[Tool] Paciente existente encontrado por nombre: {paciente_id}")
    except Exception as e:
        safe_print(f"[Tool Error Paciente]: {e}")

    if not paciente_id:
        return "ERROR: No se pudo registrar ni asociar al paciente en el sistema."

    # 2. Consultar tratamientos en el backend y asignar Consulta y Diagnóstico por defecto
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

    # 3. Formatear y validar fecha y hora en zona horaria America/La_Paz (-04:00)
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

    # 3.0. Validación de Horarios Oficiales de Soldent
    # Lunes a Viernes: 09:00 a 12:00 | 15:30 a 19:30 (Receso 12:00 a 15:30)
    # Sábados: 09:00 a 12:00 (Tardes y domingos cerrado)
    weekday = dt.weekday()
    t_ini = dt.time()
    dt_fin = dt + timedelta(minutes=duracion_min)
    t_fin = dt_fin.time()

    t_0900 = time(9, 0)
    t_1200 = time(12, 0)
    t_1530 = time(15, 30)
    t_1930 = time(19, 30)

    if weekday == 6:
        safe_print(f"⚠️ [Tool Validación] Intento de agendar en Domingo: {dt}")
        return "ERROR_DOMINGO_CERRADO: Los domingos la clínica Soldent permanece cerrada todo el día. Por favor ofrece al paciente un horario de Lunes a Viernes (09:00 a 12:00 o 15:30 a 19:30) o Sábado (09:00 a 12:00)."

    if weekday == 5:  # Sábado
        if not (t_ini >= t_0900 and t_fin <= t_1200):
            safe_print(f"⚠️ [Tool Validación] Intento de agendar fuera de horario sábado: {dt}")
            return "ERROR_SABADO_TARDE_CERRADO: Los sábados la clínica atiende únicamente en el turno de la mañana de 09:00 a 12:00 (las tardes de sábado y domingos estamos cerrados). Ofrece al paciente agendar en la mañana del sábado o de Lunes a Viernes."
    else:  # Lunes a Viernes
        en_manana = (t_ini >= t_0900 and t_fin <= t_1200)
        en_tarde = (t_ini >= t_1530 and t_fin <= t_1930)
        if not (en_manana or en_tarde):
            safe_print(f"⚠️ [Tool Validación] Intento de agendar fuera de turnos Lun-Vie: {dt}")
            if t_ini >= t_1200 and t_ini < t_1530:
                return "ERROR_RECESO_MEDIODIA: El horario solicitado cae en el intervalo de receso del mediodía (12:00 a 15:30). La clínica no atiende al mediodía. Por favor ofrece al paciente turnos en la mañana (09:00 a 12:00) o en la tarde (15:30 a 19:30)."
            return "ERROR_HORARIO_NO_PERMITIDO: El horario solicitado está fuera de nuestro horario oficial de atención. Atendemos de Lunes a Viernes de 09:00 a 12:00 y de 15:30 a 19:30, y Sábados de 09:00 a 12:00. Ofrece amablemente un turno válido dentro de estos rangos."

    # 3.1. Validación antiduplicados y anticolisión en la agenda de la clínica
    try:
        r_citas_existentes = httpx.get(f"{API_BACKEND_URL}/api/citas", timeout=6.0)
        if r_citas_existentes.status_code == 200:
            citas_data = r_citas_existentes.json()
            for c in citas_data:
                p_c_id = c.get("paciente_id") or (c.get("paciente") or {}).get("id")
                c_estado = (c.get("estado") or "").lower()
                c_inicio_str = c.get("inicio", "")
                c_fin_str = c.get("fin", "")
                if c_estado in ("pendiente", "confirmada") and c_inicio_str:
                    c_dt = datetime.fromisoformat(c_inicio_str.replace("Z", "+00:00")).astimezone(tz_bolivia)
                    # Chequeo antiduplicados del mismo paciente en el mismo día
                    if str(p_c_id) == str(paciente_id) and c_dt.date() == fecha_solicitada:
                        c_hora_existente = c_dt.strftime("%H:%M")
                        c_fecha_existente = c_dt.strftime("%d/%m/%Y")
                        safe_print(f"⚠️ [Tool Validación] Cita duplicada evitada: {nombre_paciente} ya tiene cita el {c_fecha_existente} a las {c_hora_existente}")
                        return (
                            f"AVISO_CITA_EXISTENTE: El paciente {nombre_paciente} ya cuenta con una cita activa agendada para el día {c_fecha_existente} "
                            f"a las {c_hora_existente}. No se ha creado un nuevo turno para evitar duplicados. "
                            f"Por favor recuérdale amablemente que su cita de las {c_hora_existente} ya está confirmada y registrada en el sistema de la clínica Soldent."
                        )
                # Chequeo estricto anti-traslapes en el consultorio/médico (Dra. Pamela Pinto Suárez)
                if c_estado in ("pendiente", "confirmada", "atendida") and c_inicio_str and c_fin_str:
                    c_ini = datetime.fromisoformat(c_inicio_str.replace("Z", "+00:00")).astimezone(tz_bolivia)
                    c_fin = datetime.fromisoformat(c_fin_str.replace("Z", "+00:00")).astimezone(tz_bolivia)
                    if dt < c_fin and dt_fin > c_ini:
                        c_ini_h = c_ini.strftime("%H:%M")
                        c_fin_h = c_fin.strftime("%H:%M")
                        safe_print(f"⚠️ [Tool Validación] Horario ocupado detectado: solapamiento con cita de {c_ini_h} a {c_fin_h}")
                        return (
                            f"ERROR_HORARIO_OCUPADO: Ese horario ya se encuentra ocupado por otra cita en el consultorio "
                            f"(de {c_ini_h} a {c_fin_h}). Con gusto le ofrezco a partir de las {c_fin_h} am o a la siguiente hora disponible."
                        )
    except Exception as e:
        safe_print(f"[Tool Advertencia Validación Citas]: {e}")

    # 4. Registrar la cita vía POST /api/citas
    try:
        r_cita = httpx.post(f"{API_BACKEND_URL}/api/citas", json={
            "paciente_id": paciente_id,
            "tratamiento_id": tratamiento_id,
            "inicio": inicio_iso,
            "motivo": "Agendado via WhatsApp Bot - Consulta Odontológica",
            "notas": f"Tel: {tel_clean}"
        }, timeout=8.0)

        safe_print(f"[Tool] Respuesta POST /api/citas: {r_cita.status_code}")

        if r_cita.status_code == 201:
            data = r_cita.json()
            cid = data.get("id")
            es_inmediata = data.get("es_inmediata", False)
            dias_esp = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
            f_dia = dias_esp[dt.weekday()] + " " + dt.strftime("%d/%m")
            f_hora = dt.strftime("%H:%M")
            safe_print(f"✅ [Tool Éxito] Cita creada con ID {cid} para {f_dia} a las {f_hora} (Inmediata: {es_inmediata})")
            if es_inmediata:
                return (
                    f"CITA_INMEDIATA_CONFIRMADA_201: Consulta odontológica agendada y confirmada de inmediato. "
                    f"Paciente: {nombre_paciente}. Día: {f_dia}. Hora: {f_hora}."
                )
            return (
                f"CITA_CONFIRMADA_201: Consulta odontológica agendada exitosamente. "
                f"Paciente: {nombre_paciente}. Día: {f_dia}. Hora: {f_hora}."
            )
        elif r_cita.status_code == 409:
            safe_print("[Tool Conflicto] Horario ocupado en agenda")
            return "ERROR_HORARIO_OCUPADO: Ese horario ya está ocupado por otra cita en la agenda de la clínica. Ofrece amablemente al paciente otro horario disponible (por ejemplo 30 o 60 minutos antes o después)."
        else:
            safe_print(f"[Tool Error API]: {r_cita.status_code} - {r_cita.text}")
            return f"ERROR_REGISTRO: El backend retornó código {r_cita.status_code}: {r_cita.text}"

    except Exception as e:
        safe_print(f"[Tool Excepción]: {e}")
        return f"ERROR_CONEXION: No se pudo conectar con el servidor de la agenda ({e})."

def construir_instrucciones_sistema(telefono_paciente: str) -> str:
    tz_bolivia = ZoneInfo("America/La_Paz")
    ahora = datetime.now(tz_bolivia)
    
    dias = {"Monday": "Lunes", "Tuesday": "Martes", "Wednesday": "Miércoles", "Thursday": "Jueves", "Friday": "Viernes", "Saturday": "Sábado", "Sunday": "Domingo"}
    meses = {"January": "Enero", "February": "Febrero", "March": "Marzo", "April": "Abril", "May": "Mayo", "June": "Junio", "July": "Julio", "August": "Agosto", "September": "Septiembre", "October": "Octubre", "November": "Noviembre", "December": "Diciembre"}
    dia_nombre = dias.get(ahora.strftime("%A"), ahora.strftime("%A"))
    mes_nombre = meses.get(ahora.strftime("%B"), ahora.strftime("%B"))
    
    fecha_actual_legible = f"{dia_nombre} {ahora.day} de {mes_nombre} de {ahora.year}, hora actual: {ahora.strftime('%H:%M')} (hora local de Bolivia, UTC-4)"
    fecha_actual_iso = ahora.strftime("%Y-%m-%d")

    return f"""
Eres el asistente virtual oficial de WhatsApp de 'SOLDENT - Clínica Odontológica', ubicada en {CLINICA_DIRECCION}.
La especialista a cargo es la {DOCTORA_NOMBRE} (Especialista en Odontología Integral & Ortodoncia).

FECHA Y HORA ACTUAL: {fecha_actual_legible}.
Año actual: {ahora.year}. Fecha de hoy para cálculo de citas: {fecha_actual_iso}.

HORARIOS OFICIALES DE ATENCIÓN EN SOLDENT (ESTRICTO):
* Lunes a Viernes:
  - Turno Mañana: 09:00 a 12:00
  - Receso de Mediodía (CERRADO): 12:00 a 15:30 (NO atender ni ofrecer turnos en este intervalo)
  - Turno Tarde: 15:30 a 19:30
* Sábados:
  - Turno Mañana: 09:00 a 12:00
  - Sábados por la Tarde: CERRADO (NO agendar)
* Domingos: CERRADO todo el día (NO agendar)

Teléfono de contacto de la clínica: +59178472875.
Teléfono WhatsApp detectado del paciente: {telefono_paciente} (usa este teléfono automáticamente si el paciente no indica otro diferente).

POLÍTICA DE SERVICIOS Y PRECIOS (ESTRICTO):
- Todas las atenciones se estandarizan como "Consulta Odontológica" (o "su consulta"). No menciones nombres de tratamientos específicos (como limpieza, resina, endodoncia, etc.) al agendar o confirmar.
- ESTÁ TOTALMENTE PROHIBIDO DAR COTIZACIONES O LISTAS DE PRECIOS POR WHATSAPP.
- Si el paciente pregunta por costos de tratamientos complejos (resinas, endodoncias, extracciones, etc.), debes responder cordialmente que el presupuesto exacto se define de forma personalizada tras la evaluación en la consulta presencial con la Dra. Pamela Pinto Suárez.
- Al invocar la herramienta interna `crear_cita`, asigna por defecto el identificador de tratamiento correspondiente a 'Consulta y Diagnóstico'.

Tu personalidad:
- Eres cálido, empático, educado y con un trato amable típico de Santa Cruz de la Sierra ("¡Hola! Un gusto saludarte...", "Con todo gusto le ayudamos...").
- Mantén las respuestas concisas y fáciles de leer en WhatsApp (usa negritas con asteriscos, emojis dentales con moderación).

REGLAS DE DISPONIBILIDAD Y AGENDAMIENTO (MUY IMPORTANTE):
- ANTES de agendar o invocar `crear_cita`, cuando el paciente solicite un turno o consulte por un día o momento, debes verificar la disponibilidad llamando a la herramienta `consultar_disponibilidad` con la fecha en formato YYYY-MM-DD.
- Si el turno solicitado ya está ocupado (por ejemplo, Carlos Erick u otro paciente ya ocupa de 09:00 a 10:00), o si `crear_cita` retorna `ERROR_HORARIO_OCUPADO`, NO agendes ese horario. Debes advertirle de inmediato al paciente:
«Ese horario ya se encuentra ocupado. Con gusto le ofrezco a partir de las 10:00 am o a las [siguiente hora disponible]».
- El bot SOLO debe ofrecer y aceptar turnos dentro de los rangos oficiales permitidos:
  * Lun - Vie: 09:00 a 12:00 y 15:30 a 19:30.
  * Sáb: 09:00 a 12:00 (tardes de sábado y domingos cerrado).
- Si el paciente solicita un horario en el receso del mediodía (12:00 a 15:30), explícale cordialmente que el consultorio tiene receso al mediodía y ofrécele amablemente opciones en la mañana (09:00 a 12:00) o en la tarde (15:30 a 19:30).
- Si el paciente pide sábado por la tarde o domingo, indícale amablemente que en esos momentos nos encontramos cerrados y sugiérele el sábado por la mañana o un día entre semana.
- Para agendar únicamente necesitas saber:
  1. Nombre completo del paciente.
  2. Día y horario deseado dentro de los turnos oficiales permitidos y que se encuentre libre. Si dice "hoy" usa la fecha de hoy ({fecha_actual_iso}); si dice "mañana", calcula el día siguiente.
- En cuanto el paciente proporcione estos datos y se verifique la disponibilidad libre, invoca inmediatamente la función `crear_cita`.
- NUNCA inventes que una cita ha sido reservada o confirmada sin que la función `crear_cita` haya sido ejecutada y haya retornado `CITA_CONFIRMADA_201` o `CITA_INMEDIATA_CONFIRMADA_201`.
- Si la función retorna `CITA_CONFIRMADA_201` o `CITA_INMEDIATA_CONFIRMADA_201`, responde EXACTAMENTE siguiendo este formato cordial y profesional (sin mencionar precios ni tratamientos específicos):

¡Perfecto, [Nombre]! 🦷✨
Su consulta odontológica ha quedado agendada y registrada en nuestro sistema con la Dra. Pamela Pinto Suárez para el [Día] a las [Hora].

Le esperamos en nuestro consultorio ubicado en la Calle Lemoine 407, esquina Vallegrande.

Si tuviera alguna duda o inconveniente, puede escribirnos por aquí o llamar al +591 78472875.
¡Que tenga un excelente día!

- Si la función retorna `ERROR_RECESO_MEDIODIA`, `ERROR_SABADO_TARDE_CERRADO`, `ERROR_DOMINGO_CERRADO` o `ERROR_HORARIO_NO_PERMITIDO`, explícale amablemente la restricción de horario y recomiéndale las opciones válidas.
- Si la función retorna `AVISO_CITA_EXISTENTE`, explícaselo cordialmente indicando que ya tiene su consulta agendada y confirmada para ese mismo día en la clínica, y recuérdale su horario y dirección sin crear un nuevo turno duplicado.
"""

def obtener_o_crear_chat(remitente: str, tel_paciente: str):
    """Devuelve o crea la sesión de chat con Function Calling configurado"""
    if remitente in sesiones_chat:
        return sesiones_chat[remitente]

    system_instruction = construir_instrucciones_sistema(tel_paciente)

    chat = gemini_client.chats.create(
        model="gemini-3.5-flash-lite",
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=[consultar_disponibilidad, crear_cita],
            temperature=0.2
        )
    )
    sesiones_chat[remitente] = chat
    return chat

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(loop_workers_automaticos())
    yield
    task.cancel()

app = FastAPI(title="Soldent WhatsApp Bot", lifespan=lifespan)

async def enviar_mensaje_whatsapp(numero: str, texto: str):
    """Envía un mensaje de texto a través de la pasarela Baileys/Evolution"""
    url = f"{EVOLUTION_API_URL}/send-message"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json={"number": numero, "text": texto})
            if resp.status_code == 200:
                safe_print(f"[Bot OUT] Enviado con éxito a {numero}")
            else:
                safe_print(f"[Bot OUT Error] {resp.status_code}: {resp.text}")
    except Exception as e:
        safe_print(f"[Bot OUT Error] No se pudo conectar con la pasarela WhatsApp: {e}")

def procesar_mensaje_con_gemini(remitente: str, nombre: str, texto: str, tel_paciente: str) -> str:
    """Envía el turno del mensaje a Gemini con Function Calling activo"""
    if not gemini_client:
        return "Hola! Gracias por comunicarte con Soldent. En este momento estamos configurando el bot. Por favor contactanos al +59178472875."

    chat = obtener_o_crear_chat(remitente, tel_paciente)

    try:
        # El paciente envía su mensaje en la conversación
        prompt_mensaje = f"Paciente ({nombre}): {texto}"
        resp = chat.send_message(prompt_mensaje)
        if resp and resp.text:
            return resp.text.strip()
    except Exception as e:
        safe_print(f"[Gemini Chat Error]: {e}. Reintentando con nueva sesión...")
        try:
            # Si la sesión falló (ej. timeout o token expirado), recrear sesión
            sesiones_chat.pop(remitente, None)
            nuevo_chat = obtener_o_crear_chat(remitente, tel_paciente)
            resp = nuevo_chat.send_message(f"Paciente ({nombre}): {texto}")
            if resp and resp.text:
                return resp.text.strip()
        except Exception as e2:
            safe_print(f"[Gemini Chat Fallback Error]: {e2}")

    return "¡Hola! Gracias por comunicarte con Soldent. En este momento tuvimos una pequeña demora técnica al procesar tu solicitud. Por favor escríbenos nuevamente o llámanos directamente al +59178472875."

@app.post("/webhook")
async def recibir_mensaje(req: Request):
    try:
        data = await req.json()
    except Exception as err:
        return {"ok": False, "error": f"JSON invalido: {err}"}

    remitente = data.get("from")
    nombre = data.get("name", "Paciente")
    texto = data.get("text", "").strip()
    tel_paciente = data.get("phone", "") or remitente.replace("@s.whatsapp.net", "").replace("@lid", "")

    if not tel_paciente.startswith("+"):
        tel_paciente = "+" + tel_paciente

    if not remitente or not texto:
        return {"ok": False}

    # Descartar mensajes duplicados idénticos en una ventana de 15 segundos
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
        # Procesar con Gemini y ejecutar Function Calling si corresponde
        texto_respuesta = await asyncio.to_thread(
            procesar_mensaje_con_gemini,
            remitente, nombre, texto, tel_paciente
        )

        safe_print(f"[Gemini OUT]: {texto_respuesta}\n")

        # Enviar respuesta al paciente por WhatsApp
        await enviar_mensaje_whatsapp(remitente, texto_respuesta)
        return {"ok": True, "respuesta": texto_respuesta}

    except Exception as e:
        safe_print(f"[Error Procesando Webhook]: {e}")
        error_msg = "¡Hola! Tuvimos un pequeño inconveniente al procesar tu mensaje. Puedes escribirnos directamente o llamarnos al +59178472875."
        await enviar_mensaje_whatsapp(remitente, error_msg)
        return {"ok": False, "error": str(e)}

async def loop_workers_automaticos():
    """Ejecuta los workers cada 60 segundos para recordatorios de 1h y sincronizacion de Google Calendar"""
    safe_print("[Workers] Iniciando ciclo automatico de recordatorios (cada 60 segundos)...")
    while True:
        try:
            db = SessionLocal()
            try:
                # 1. Sincronizar citas pendientes con Google Calendar
                worker_sync_outbox(db)
                # 2. Enviar recordatorios automaticos de 1 hora
                worker_recordatorios(db)
            finally:
                db.close()
        except Exception as e:
            safe_print(f"[Workers Error]: {e}")

        await asyncio.sleep(60)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5005)
