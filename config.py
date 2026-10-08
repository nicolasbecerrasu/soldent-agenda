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
    RECORDATORIO_HORAS: int = int(os.getenv("RECORDATORIO_HORAS", "4"))
    RECORDATORIO_MIN: int = int(os.getenv("RECORDATORIO_MIN", "175"))
    RECORDATORIO_MAX: int = int(os.getenv("RECORDATORIO_MAX", "185"))
    DOCTORA_PIN: str = os.getenv("DOCTORA_PIN", "1104")
    DOCTORA_TELEFONO: str = os.getenv("DOCTORA_TELEFONO", "+59178472875")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "soldent_secret_key_pamela_2026")

settings = Settings()
