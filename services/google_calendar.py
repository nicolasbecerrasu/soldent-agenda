import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.orm import Session

from config import settings
from database import AuditoriaCita, Cita, SyncOutbox
from security import hash_token

try:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    import httplib2
    import google_auth_httplib2
except ImportError:
    Credentials = None
    build = None
    HttpError = Exception
    httplib2 = None
    google_auth_httplib2 = None

def get_google_creds():
    if not Credentials:
        raise RuntimeError("google-auth no está instalado en este entorno.")
    return Credentials(
        token=None,
        refresh_token=settings.GOOGLE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/calendar.events"]
    )

def get_calendar_service():
    if not build:
        raise RuntimeError("google-api-python-client no está instalado en este entorno.")
    if not (httplib2 and google_auth_httplib2):
        raise RuntimeError("google-auth-httplib2 y httplib2 son requeridos para garantizar timeout de red (15s) en Google Calendar.")
    creds = get_google_creds()
    # Timeout específico y aislado exclusivamente para el cliente HTTP de Google Calendar
    http_client = httplib2.Http(timeout=15.0)
    authorized_http = google_auth_httplib2.AuthorizedHttp(creds, http=http_client)
    return build("calendar", "v3", http=authorized_http)

def registrar_auditoria(db: Session, cita_id, actor: str, accion: str, antes: dict = None, despues: dict = None):
    db.add(AuditoriaCita(cita_id=cita_id, actor=actor, accion=accion, antes=antes, despues=despues))

def encolar_outbox(db: Session, cita_id, accion: str, payload: dict):
    db.add(SyncOutbox(entidad="cita", entidad_id=cita_id, accion=accion, payload=payload))

def generar_token_respuesta(db: Session, cita: Cita) -> str:
    token = str(uuid.uuid4())
    cita.token_respuesta_hash = hash_token(token)
    cita.token_expira_en = cita.fin + timedelta(hours=2)
    return token
