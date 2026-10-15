"""Estado y memoria persistente para sesiones de WhatsApp y deduplicación de mensajes."""

from datetime import datetime, timezone
from database import SessionLocal, BotSession

def cargar_historial_db(telefono: str) -> list:
    """Carga el historial de conversación desde la base de datos Supabase."""
    try:
        db = SessionLocal()
        try:
            sesion = db.query(BotSession).filter(BotSession.telefono == str(telefono)).first()
            if sesion and sesion.historial:
                return list(sesion.historial)
        finally:
            db.close()
    except Exception:
        pass
    return []

def guardar_historial_db(telefono: str, historial: list):
    """Guarda o actualiza el historial en la base de datos Supabase."""
    try:
        db = SessionLocal()
        try:
            sesion = db.query(BotSession).filter(BotSession.telefono == str(telefono)).first()
            if not sesion:
                sesion = BotSession(telefono=str(telefono), historial=historial, contexto={})
                db.add(sesion)
            else:
                sesion.historial = historial
                sesion.updated_at = datetime.now(timezone.utc)
            db.commit()
        finally:
            db.close()
    except Exception:
        pass

class PersistentSessionDict(dict):
    """Diccionario en memoria respaldado automáticamente en Supabase."""
    def __getitem__(self, key):
        if not super().__contains__(key):
            historial = cargar_historial_db(key)
            super().__setitem__(key, historial)
        return super().__getitem__(key)

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        guardar_historial_db(key, value)

    def get(self, key, default=None):
        if not super().__contains__(key):
            historial = cargar_historial_db(key)
            if historial:
                super().__setitem__(key, historial)
                return historial
            return default
        return super().get(key, default)

    def __contains__(self, key):
        if super().__contains__(key):
            return True
        historial = cargar_historial_db(key)
        if historial:
            super().__setitem__(key, historial)
            return True
        return False

# Instancias compartidas por el bot
historial_sesiones = PersistentSessionDict()
mensajes_procesados_recientes = {}
