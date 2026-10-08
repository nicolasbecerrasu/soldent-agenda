from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from database import WhatsAppSession, get_db
from schemas import SessionBatchIn, SessionItemIn

router = APIRouter(prefix="/api/internal/baileys-session", tags=["Baileys Session Sync"])

@router.get("")
def obtener_sesion_baileys(db: Session = Depends(get_db)):
    rows = db.execute(select(WhatsAppSession)).scalars().all()
    return {r.key: r.value for r in rows}

@router.post("")
def guardar_archivo_sesion(item: SessionItemIn, db: Session = Depends(get_db)):
    stmt = (
        pg_insert(WhatsAppSession)
        .values(key=item.key, value=item.value)
        .on_conflict_do_update(
            index_elements=["key"],
            set_={"value": item.value, "updated_at": func.now()}
        )
    )
    db.execute(stmt)
    db.commit()
    return {"ok": True, "key": item.key}

@router.post("/batch")
def guardar_archivos_sesion_batch(data: SessionBatchIn, db: Session = Depends(get_db)):
    if not data.items:
        return {"ok": True, "total": 0}
    values = [{"key": k, "value": v} for k, v in data.items.items()]
    insert_stmt = pg_insert(WhatsAppSession).values(values)
    stmt = insert_stmt.on_conflict_do_update(
        index_elements=["key"],
        set_={
            "value": insert_stmt.excluded.value,
            "updated_at": func.now()
        }
    )
    db.execute(stmt)
    db.commit()
    return {"ok": True, "total": len(data.items)}

@router.delete("")
def borrar_sesion_baileys(db: Session = Depends(get_db)):
    db.execute(text("DELETE FROM agenda.whatsapp_session"))
    db.commit()
    return {"ok": True, "mensaje": "Sesión eliminada de base de datos"}
