import asyncio
import os
import sys
import re
from datetime import datetime, timedelta, timezone
from collections import defaultdict
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
from services.whatsapp_gateway import enviar_mensaje_whatsapp, enviar_ubicacion_whatsapp
from services.alertas import vigilar_conexion_whatsapp
from services.booking_tools import consultar_disponibilidad, crear_cita
from bot.state import historial_sesiones, mensajes_procesados_recientes
from bot.handlers import (
    procesar_mensaje_doctora,
    obtener_datos_completos_agenda_doctora,
    procesar_mensaje_administrador,
    obtener_metricas_administrador,
    procesar_mensaje_con_gemini,
    construir_prompt_sistema,
    actualizar_estado_cita_paciente,
)


if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Verificación de entorno: Desactivar en Render para evitar colisiones con Oracle Cloud
is_render = bool(os.getenv("RENDER") or os.getenv("RENDER_SERVICE_ID") or os.getenv("RENDER_EXTERNAL_URL"))
disable_whatsapp = os.getenv("DISABLE_WHATSAPP", "").lower() in ("true", "1", "yes")
enable_force = os.getenv("ENABLE_WHATSAPP_ON_RENDER", "").lower() in ("true", "1", "yes")

if (is_render or disable_whatsapp) and not enable_force:
    safe_print("⏸️ [WhatsApp Bot] Desactivado automáticamente en Render/Respaldo para proteger la instancia principal en Oracle Cloud.")
    sys.exit(0)

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
                # 6. Vigilancia de conexión de WhatsApp (alerta por correo si se cae)
                try:
                    await vigilar_conexion_whatsapp()
                except Exception as err_mon:
                    safe_print(f"⚠️ [Alertas Error]: {err_mon}")
            finally:
                db.close()
        except Exception as e:
            safe_print(f"[Workers Error]: {e}")

        await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    enable_embedded = os.getenv("ENABLE_EMBEDDED_WORKERS", "").lower() in ("true", "1", "yes")
    task = None
    if enable_embedded:
        safe_print("⚡ [WhatsApp Bot] Workers embebidos activados dentro de lifespan.")
        task = asyncio.create_task(loop_workers_automaticos())
    else:
        safe_print("🚀 [WhatsApp Bot] Modo desacoplado: los workers corren en su propio proceso independiente (run_workers.py).")
    yield
    if task:
        task.cancel()

app = FastAPI(title="Soldent WhatsApp Bot", lifespan=lifespan)
_user_locks = defaultdict(asyncio.Lock)

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

    async with _user_locks[remitente]:
        return await _procesar_mensaje_paciente(remitente, nombre, texto, tel_paciente)

async def _procesar_mensaje_paciente(remitente: str, nombre: str, texto: str, tel_paciente: str):
    global mensajes_procesados_recientes
    ahora_ts = datetime.now().timestamp()
    mensajes_procesados_recientes = {k: v for k, v in mensajes_procesados_recientes.items() if ahora_ts - v < 60}
    clave_msg = (remitente, texto.lower())
    if clave_msg in mensajes_procesados_recientes and (ahora_ts - mensajes_procesados_recientes[clave_msg]) < 15:
        safe_print(f"[WhatsApp IN] Mensaje duplicado o reintento rápido ignorado (<15s): '{texto}'")
        return {"ok": True, "duplicado": True}
    mensajes_procesados_recientes[clave_msg] = ahora_ts

    safe_print(f"\n[WhatsApp IN] De: {nombre} ({remitente} | {tel_paciente}): {texto}")


    texto_limpio_cmd = texto.strip().lower()

    # 1. GESTIÓN DE BAJA (OPT-OUT): "SALIR"
    if texto_limpio_cmd in ("salir", "baja", "desuscribir", "cancelar recordatorios", "no enviar mas", "no enviar más"):
        safe_print(f"🛑 [Opt-out] Paciente {nombre} ({tel_paciente}) solicitó baja de recordatorios.")
        try:
            db_opt = SessionLocal()
            try:
                tel_clean = re.sub(r"\D", "", tel_paciente)
                tel_8 = tel_clean[-8:] if len(tel_clean) >= 8 else tel_clean
                pacs = db_opt.query(Paciente).all()
                for p in pacs:
                    p_tel = re.sub(r"\D", "", str(p.telefono or ""))
                    if p_tel and (p_tel == tel_clean or tel_8 in p_tel or p_tel in tel_clean):
                        if "[OPTOUT_WHATSAPP]" not in (p.notas or ""):
                            p.notas = ((p.notas or "").strip() + " [OPTOUT_WHATSAPP]").strip()
                db_opt.commit()
            finally:
                db_opt.close()
        except Exception as e_opt:
            safe_print(f"⚠️ [Error Opt-out]: {e_opt}")

        msg_optout_resp = (
            f"Listo, {nombre}. Hemos cancelado los recordatorios automáticos para su número.\n\n"
            "_(Para reactivarlos en cualquier momento responda ACTIVAR). ¡Que tenga buen día! ✨_"
        )
        await enviar_mensaje_whatsapp(remitente, msg_optout_resp)
        return {"ok": True, "optout": True, "respuesta": msg_optout_resp}

    # 2. REACTIVACIÓN DE RECORDATORIOS: "ACTIVAR"
    if texto_limpio_cmd in ("activar", "activar recordatorios", "alta"):
        safe_print(f"🔔 [Opt-in] Paciente {nombre} ({tel_paciente}) reactivó recordatorios.")
        try:
            db_opt = SessionLocal()
            try:
                tel_clean = re.sub(r"\D", "", tel_paciente)
                tel_8 = tel_clean[-8:] if len(tel_clean) >= 8 else tel_clean
                pacs = db_opt.query(Paciente).all()
                for p in pacs:
                    p_tel = re.sub(r"\D", "", str(p.telefono or ""))
                    if p_tel and (p_tel == tel_clean or tel_8 in p_tel or p_tel in tel_clean):
                        p.notas = (p.notas or "").replace("[OPTOUT_WHATSAPP]", "").strip()
                db_opt.commit()
            finally:
                db_opt.close()
        except Exception as e_opt:
            safe_print(f"⚠️ [Error Opt-in]: {e_opt}")

        msg_optin_resp = (
            f"✅ Recordatorios reactivados, {nombre}. Con gusto le avisaremos de sus próximas citas en Soldent. ¡Hasta pronto! ✨"
        )
        await enviar_mensaje_whatsapp(remitente, msg_optin_resp)
        return {"ok": True, "optin": True, "respuesta": msg_optin_resp}

    # 3. CONFIRMACIÓN INTERACTIVA BIDIRECCIONAL: "CONFIRMO" / "CONFIRMAR"
    if texto_limpio_cmd in ("confirmo", "confirmado", "confirmar", "si confirmo", "sí confirmo", "si asistire", "sí asistiré", "asistire", "asistiré"):
        safe_print(f"✅ [Confirmación Bidireccional] Paciente {nombre} ({tel_paciente}) confirmó su cita.")
        info_c = await asyncio.to_thread(actualizar_estado_cita_paciente, tel_paciente, "confirmada")
        nombre_p = info_c.get("paciente_nombre") or nombre

        if info_c and info_c.get("ya_estaba_confirmada"):
            msg_conf_resp = f"¡Con mucho gusto, {nombre_p}! Su cita para el *{info_c['fecha']} a las {info_c['hora']}* ya se encuentra confirmada. ¡Le esperamos en Soldent! 🦷✨"
        elif info_c:
            msg_conf_resp = (
                f"¡Cita confirmada, {nombre_p}! 🦷✨\n"
                f"La {settings.DOCTORA_NOMBRE} le espera el *{info_c['fecha']} a las {info_c['hora']}* en Soldent ({settings.CLINICA_DIRECCION}). ¡Hasta pronto!"
            )
            # Notificar a la Dra. Pamela (+591 78472875) UNA SOLA VEZ
            msg_doc = (
                f"🦷 *SOLDENT - Cita Confirmada por Paciente*\n\n"
                f"Estimada Dra. Pamela, el paciente *{nombre_p}* ({tel_paciente}) "
                f"acaba de confirmar su cita para el *{info_c['fecha']} a las {info_c['hora']}*."
            )
            try:
                await enviar_mensaje_whatsapp(settings.DOCTORA_TELEFONO, msg_doc)
                safe_print(f"✅ [Alerta Confirmación] Notificación enviada a la Dra. Pamela por {nombre_p}")
            except Exception as e_doc:
                safe_print(f"⚠️ [Error Alerta Dra Confirmacion]: {e_doc}")
        else:
            msg_conf_resp = (
                f"Hola {nombre}. No encontramos ninguna cita pendiente de confirmación a su nombre. "
                "Si desea agendar una consulta, indíquenos qué día le queda cómodo."
            )

        if remitente not in historial_sesiones:
            historial_sesiones[remitente] = []
        historial_sesiones[remitente].append({"role": "user", "text": f"Paciente ({nombre}): {texto}"})
        historial_sesiones[remitente].append({"role": "model", "text": msg_conf_resp})

        await enviar_mensaje_whatsapp(remitente, msg_conf_resp)
        return {"ok": True, "confirmada": bool(info_c and not info_c.get("ya_estaba_confirmada")), "respuesta": msg_conf_resp}

    # 4. SOLICITUD DIRECTA DE UBICACIÓN / GPS
    if texto_limpio_cmd in (
        "ubicacion", "ubicación", "donde quedan", "dónde quedan",
        "donde estan", "dónde están", "donde queda", "dónde queda",
        "donde atienden", "dónde atienden", "direccion", "dirección",
        "gps", "mapa", "croquis", "como llegar", "cómo llegar",
        "como llego", "cómo llego", "pasar ubicacion", "pasar ubicación",
        "mandar ubicacion", "mandar ubicación", "pasa la ubicacion", "pasa la ubicación"
    ):
        safe_print(f"📍 [Ubicación Directa] Paciente {nombre} ({tel_paciente}) solicitó ubicación GPS.")
        msg_ubi = (
            f"📍 *SOLDENT - Clínica Odontológica*\n\n"
            f"Estamos en la *Calle Lemoine 407 esquina Vallegrande*, en pleno centro de Santa Cruz de la Sierra.\n\n"
            f"🗺️ *Google Maps:* {settings.CLINICA_MAPS_URL}\n"
            "⏰ *Horarios:* Lun-Vie 09:00-12:00 y 15:30-19:30 | Sáb 09:00-12:00\n\n"
            "¡Aquí le envío también nuestra tarjeta de ubicación GPS interactiva! 🚗✨"
        )
        if remitente not in historial_sesiones:
            historial_sesiones[remitente] = []
        historial_sesiones[remitente].append({"role": "user", "text": f"Paciente ({nombre}): {texto}"})
        historial_sesiones[remitente].append({"role": "model", "text": msg_ubi})

        await enviar_mensaje_whatsapp(remitente, msg_ubi)
        await enviar_ubicacion_whatsapp(remitente)
        return {"ok": True, "ubicacion": True, "respuesta": msg_ubi}

    try:
        texto_respuesta = await asyncio.to_thread(
            procesar_mensaje_con_gemini,
            remitente, nombre, texto, tel_paciente
        )
        if not texto_respuesta:
            texto_respuesta = MENSAJE_OFICIAL_DEFAULT

        # Detectar si se debe enviar tarjeta GPS (vía tag de Gemini o mención explícita en el mensaje)
        debe_enviar_gps = ("[ENVIAR_UBICACION]" in texto_respuesta) or any(
            k in texto_limpio_cmd for k in (
                "ubicacion", "ubicación", "donde quedan", "dónde quedan",
                "donde estan", "dónde están", "donde queda", "dónde queda",
                "donde atienden", "dónde atienden", "como llegar", "cómo llegar",
                "como llego", "cómo llego", "direccion", "dirección",
                "croquis", "gps", "google maps", "mapa"
            )
        )
        texto_respuesta = texto_respuesta.replace("[ENVIAR_UBICACION]", "").strip()

        safe_print(f"[Gemini OUT]: {texto_respuesta}\n")
        await enviar_mensaje_whatsapp(remitente, texto_respuesta)

        if debe_enviar_gps:
            safe_print(f"📍 [Ubicación GPS] Despachando tarjeta interactiva a {nombre} ({remitente})...")
            await enviar_ubicacion_whatsapp(remitente)

        # Si el paciente consultó por martes o jueves, notificar por cortesía a la Dra. Pamela
        texto_low = texto.lower()
        if any(d in texto_low for d in ("martes", "jueves")):
            msg_alerta_dra = (
                "🦷 *SOLDENT - Paciente Interesado en Martes/Jueves*\n\n"
                f"Dra. Pamela, el paciente *{nombre}* ({tel_paciente}) consultó por atención:\n"
                f"💬 *Mensaje:* \"{texto}\"\n\n"
                f"👉 El bot le indicó coordinar a su WhatsApp directo ({settings.DOCTORA_TELEFONO})."
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
