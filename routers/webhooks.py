from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Request
import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from config import settings
from database import Cita, get_db
from services.google_calendar import get_calendar_service, registrar_auditoria
from workers import worker_resumen_turnos_doctora

router = APIRouter(tags=["Webhooks y Utilidades"])

@router.post("/api/webhooks/google")
async def webhook_google(req: Request, db: Session = Depends(get_db)):
    if req.headers.get("X-Goog-Resource-State") not in ("exists", "not_exists", "sync"):
        return {"ok": True}
    try:
        service = get_calendar_service()
        tiempo_limite = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat() + "Z"
        result = service.events().list(calendarId=settings.CALENDAR_ID, updatedMin=tiempo_limite, singleEvents=True, orderBy="updated").execute()
        for evento in result.get("items", []):
            cita = db.execute(select(Cita).where(Cita.google_event_id == evento.get("id"))).scalar_one_or_none()
            if not cita:
                continue
            g_updated = datetime.fromisoformat(evento.get("updated").replace("Z", "+00:00"))
            if g_updated <= cita.updated_at.replace(tzinfo=timezone.utc):
                continue
            
            inicio_str = evento["start"].get("dateTime", evento["start"].get("date")).replace("Z", "+00:00")
            fin_str = evento["end"].get("dateTime", evento["end"].get("date")).replace("Z", "+00:00")
            cancelado = evento.get("status") == "cancelled"
            
            q = text("UPDATE agenda.citas SET inicio=:i, fin=:f, estado=:e, version=version+1, updated_at=now() WHERE id=:cid AND version=:v RETURNING version")
            row = db.execute(q, {"i": inicio_str, "f": fin_str, "e": "cancelada" if cancelado else cita.estado, "cid": cita.id, "v": cita.version}).mappings().first()
            if row:
                registrar_auditoria(db, cita.id, "sistema", "sync_google", antes={"inicio": str(cita.inicio)}, despues={"inicio": inicio_str})
        db.commit()
        return {"ok": True}
    except Exception as e:
        db.rollback()
        return {"ok": False, "error": str(e)}

@router.post("/api/test/resumen-doctora")
def test_resumen_doctora(turno: str = "manana", db: Session = Depends(get_db)):
    """Permite disparar el resumen de la mañana o tarde a la doctora para pruebas."""
    res = worker_resumen_turnos_doctora(db, forzar_turno=turno)
    return res or {"ok": False, "mensaje": "No se pudo generar el resumen"}

@router.get("/api/saludar-doctora")
@router.post("/api/saludar-doctora")
async def api_saludar_doctora():
    """Envía un saludo formal y bienvenida a la Dra. Pamela de parte de su bot asistente."""
    saludo = (
        "👋 ¡Buenas noches, Dra. Pamela!\n\n"
        "Soy su Asistente Virtual de *SOLDENT*. Ya me encuentro 100% activo y conectado a su servicio.\n\n"
        "Estoy a su total disposición para lo que necesite. Puede consultarme en cualquier momento:\n"
        "• 📅 *«¿Qué citas tengo hoy (o mañana)?»*\n"
        "• ⏰ *«Horarios libres de mañana»* (se los enviaré con el formato listo para reenviar a sus pacientes)\n"
        "• 👤 *«¿Quiénes ya confirmaron para mañana?»*\n"
        "• 📝 *«Agéndame a [Nombre] el [Día] a las [Hora]»*\n"
        "• 🔒 *«Bloquéame de [Hora] a [Hora] por cirugía o trámite»*\n\n"
        "¿En qué le puedo colaborar hoy, doctora? ✨"
    )
    doc_tel = getattr(settings, "DOCTORA_TELEFONO", "+59178472875")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post("http://127.0.0.1:8080/send-message", json={"number": doc_tel, "text": saludo, "message": saludo})
            return {"ok": True, "enviado": True, "respuesta_gateway": resp.json()}
    except Exception as e:
        return {"ok": False, "error": str(e)}
