import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    TZ_CONSULTORIO: str = os.getenv("TZ_CONSULTORIO", "America/La_Paz")
    WHATSAPP_TOKEN: str = os.getenv("WHATSAPP_TOKEN", "")
    WHATSAPP_PHONE_ID: str = os.getenv("WHATSAPP_PHONE_ID", "")
    GOOGLE_REFRESH_TOKEN: str = os.getenv("GOOGLE_REFRESH_TOKEN", "")
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    CALENDAR_ID: str = os.getenv("CALENDAR_ID", "primary")
    PUBLIC_BASE_URL: str = os.getenv("PUBLIC_BASE_URL", "https://soldent-agenda.onrender.com")
    RECORDATORIO_HORAS: int = int(os.getenv("RECORDATORIO_HORAS", "3"))
    RECORDATORIO_MIN: int = int(os.getenv("RECORDATORIO_MIN", "175"))
    RECORDATORIO_MAX: int = int(os.getenv("RECORDATORIO_MAX", "185"))
    DOCTORA_PIN: str = os.getenv("DOCTORA_PIN", "1104")
    DOCTORA_NOMBRE: str = os.getenv("DOCTORA_NOMBRE", "Dra. Pamela Pinto Suárez")
    DOCTORA_TELEFONO: str = os.getenv("DOCTORA_TELEFONO", "+59178472875")
    ADMIN_TELEFONO: str = os.getenv("ADMIN_TELEFONO", "+59170277520")
    BOT_PHONE_NUMBER: str = os.getenv("WHATSAPP_PHONE_NUMBER", "+59175825272")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "soldent_secret_key_pamela_2026")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    EVOLUTION_API_URL: str = os.getenv("EVOLUTION_API_URL", "http://127.0.0.1:8080")
    DEFAULT_COUNTRY_CODE: str = os.getenv("DEFAULT_COUNTRY_CODE", "+591")
    CLINICA_DIRECCION: str = os.getenv("CLINICA_DIRECCION", "Calle Lemoine 407 esquina Vallegrande, Santa Cruz de la Sierra, Bolivia")
    CLINICA_NOMBRE: str = os.getenv("CLINICA_NOMBRE", "Soldent - Soluciones Dentales")
    API_BACKEND_URL: str = os.getenv("API_BACKEND_URL", "https://soldent-agenda.onrender.com")

settings = Settings()

MENSAJE_OFICIAL_DEFAULT = (
    "¡Hola! 🦷✨ Bienvenido a *Soldent*.\n\n"
    f"👩‍⚕️ *{settings.DOCTORA_NOMBRE}* (Odontología Integral & Ortodoncia)\n"
    f"📍 {settings.CLINICA_DIRECCION}\n"
    "⏰ *Horarios:* Lun-Vie 09:00-12:00 y 15:30-19:30 | Sáb 09:00-12:00\n\n"
    "Para agendar una cita, indíquenos su nombre completo y el día y hora de su preferencia, "
    f"o escriba al WhatsApp de la doctora: {settings.DOCTORA_TELEFONO}."
)

