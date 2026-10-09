"""Monitor de conexión de WhatsApp con alertas por correo electrónico (SMTP).

Variables de entorno requeridas para enviar correos (ej. Gmail con contraseña de aplicación):
  SMTP_USER       -> cuenta emisora (ej. nicbs1985@gmail.com)
  SMTP_PASSWORD   -> contraseña de aplicación de 16 caracteres
Opcionales:
  ALERT_EMAIL_TO  -> destinatario (por defecto nicbs1985@gmail.com)
  SMTP_HOST / SMTP_PORT -> por defecto smtp.gmail.com / 465 (SSL)
  ALERTA_MINUTOS_CAIDA -> minutos desconectado antes de avisar (por defecto 5)
"""
import os
import smtplib
import time
from email.message import EmailMessage

import httpx

from services.gemini_ai import safe_print

ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO", "nicbs1985@gmail.com")
MINUTOS_CAIDA = int(os.getenv("ALERTA_MINUTOS_CAIDA", "5"))

_estado = {"desconectado_desde": None, "alerta_enviada": False}


def _enviar_correo(asunto: str, cuerpo: str) -> bool:
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    if not user or not password:
        safe_print("⚠️ [Alertas] SMTP_USER/SMTP_PASSWORD no configurados: no se puede enviar el correo.")
        return False
    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = user
    msg["To"] = ALERT_EMAIL_TO
    msg.set_content(cuerpo)
    try:
        host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        port = int(os.getenv("SMTP_PORT", "465"))
        with smtplib.SMTP_SSL(host, port, timeout=20) as smtp:
            smtp.login(user, password)
            smtp.send_message(msg)
        safe_print(f"📧 [Alertas] Correo enviado a {ALERT_EMAIL_TO}: {asunto}")
        return True
    except Exception as e:
        safe_print(f"⚠️ [Alertas] Error enviando correo: {e}")
        return False


async def vigilar_conexion_whatsapp():
    """Se llama cada minuto. Avisa por correo si WhatsApp lleva desconectado varios minutos y cuando se recupera."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get("http://127.0.0.1:8000/api/whatsapp/estado")
            conectado = bool(r.json().get("conectado")) if r.status_code == 200 else False
    except Exception:
        conectado = False

    ahora = time.time()
    if conectado:
        if _estado["alerta_enviada"]:
            _enviar_correo(
                "✅ SOLDENT: WhatsApp reconectado",
                "El bot de WhatsApp de SOLDENT volvió a conectarse y funciona con normalidad.",
            )
        _estado["desconectado_desde"] = None
        _estado["alerta_enviada"] = False
        return

    if _estado["desconectado_desde"] is None:
        _estado["desconectado_desde"] = ahora
        return

    minutos = (ahora - _estado["desconectado_desde"]) / 60
    if minutos >= MINUTOS_CAIDA and not _estado["alerta_enviada"]:
        enviado = _enviar_correo(
            "🚨 SOLDENT: el bot de WhatsApp está desconectado",
            f"El bot de WhatsApp lleva {int(minutos)} minutos desconectado.\n\n"
            "Si la sesión fue revocada, escanea un nuevo QR en: http://146.181.38.79/qr?pin=1104\n"
            "Mientras esté caído NO se envían recordatorios a los pacientes.",
        )
        # Si el correo no está configurado, no marcar como enviada para reintentar cuando se configure
        _estado["alerta_enviada"] = enviado
