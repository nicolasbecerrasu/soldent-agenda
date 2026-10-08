import asyncio
import os
import sys
from datetime import datetime
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, Request
import uvicorn

from config import settings, MENSAJE_OFICIAL_DEFAULT
from database import SessionLocal, Paciente, Cita, NotificacionEnviada
from workers import (
    worker_sync_outbox,
    worker_recordatorios,
    worker_sync_inverso_google,
    worker_resumen_turnos_doctora,
    worker_control_mensual_ortodoncia,
)
from services.gemini_ai import safe_print, llamar_gemini_http
from services.whatsapp_gateway import enviar_mensaje_whatsapp
from services.booking_tools import consultar_disponibilidad, crear_cita
from bot.state import historial_sesiones, mensajes_procesados_recientes
from bot.handlers import (
    procesar_mensaje_doctora,
    obtener_datos_completos_agenda_doctora,
    procesar_mensaje_administrador,
    obtener_metricas_administrador,
    procesar_mensaje_con_gemini,
    construir_prompt_sistema,
)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Re-export variables para compatibilidad retrospectiva total
GEMINI_API_KEY = settings.GEMINI_API_KEY
EVOLUTION_API_URL = settings.EVOLUTION_API_URL
DEFAULT_COUNTRY_CODE = settings.DEFAULT_COUNTRY_CODE
CLINICA_DIRECCION = settings.CLINICA_DIRECCION
CLINICA_NOMBRE = settings.CLINICA_NOMBRE
DOCTORA_NOMBRE = settings.DOCTORA_NOMBRE
DOCTORA_TELEFONO = settings.DOCTORA_TELEFONO
BOT_PHONE_NUMBER = settings.BOT_PHONE_NUMBER
API_BACKEND_URL = settings.API_BACKEND_URL
SECRET_KEY = settings.SECRET_KEY
BOT_HEADERS = {"X-Auth-Token": SECRET_KEY}

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
                # 2. Enviar recordatorios automáticos a pacientes
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(loop_workers_automaticos())
    yield
    task.cancel()

app = FastAPI(title="Soldent WhatsApp Bot", lifespan=lifespan)

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

    # CANAL DE ATENCIÓN ADMINISTRATIVA - NICOLÁS (+591 70277520)
    is_admin = data.get("isAdmin", False) or ("70277520" in tel_paciente) or ("70277520" in (remitente or ""))
    if is_admin:
        safe_print(f"\n[WhatsApp IN] 👨‍💻 Administrador Nicolás ({tel_paciente}): {texto}")
        try:
            texto_respuesta = await asyncio.to_thread(
                procesar_mensaje_administrador,
                remitente, texto
            )
            safe_print(f"[Asistente Admin OUT]: {texto_respuesta}\n")
            await enviar_mensaje_whatsapp(remitente, texto_respuesta)
            return {"ok": True, "admin": True, "respuesta": texto_respuesta}
        except Exception as e:
            safe_print(f"[Error Asistente Admin]: {e}")
            fallback_adm = "Hola Nicolás 👨‍💻. Recibí tu consulta, el sistema y la base de datos están 100% operativos."
            await enviar_mensaje_whatsapp(remitente, fallback_adm)
            return {"ok": True, "admin": True, "respuesta": fallback_adm}

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
                f"👉 El bot le indicó que coordine directamente con usted a su WhatsApp ({settings.DOCTORA_TELEFONO})."
            )
            try:
                await enviar_mensaje_whatsapp(settings.DOCTORA_TELEFONO, msg_alerta_dra)
                safe_print(f"✅ [Alerta Martes/Jueves] Notificación enviada a la Dra. Pamela sobre {nombre}")
            except Exception as e_alerta:
                safe_print(f"⚠️ [Error Alerta Martes/Jueves]: {e_alerta}")

        return {"ok": True, "respuesta": texto_respuesta}

    except Exception as e:
        safe_print(f"[Error Procesando Webhook]: {e}")
        texto_respuesta = MENSAJE_OFICIAL_DEFAULT
        await enviar_mensaje_whatsapp(remitente, texto_respuesta)
        return {"ok": True, "respuesta": texto_respuesta}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5005)
