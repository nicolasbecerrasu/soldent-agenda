from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import Tratamiento, get_db
from security import verificar_autenticacion

router = APIRouter(prefix="/api/tratamientos", tags=["Tratamientos"])

@router.get("")
def listar_tratamientos(db: Session = Depends(get_db), _auth: bool = Depends(verificar_autenticacion)):
    rows = db.execute(select(Tratamiento)).scalars().all()
    return [
        {
            "id": str(r.id),
            "nombre": r.nombre,
            "duracion_min": r.duracion_min,
            "color": r.color,
            "precio": float(r.precio) if r.precio else None
        }
        for r in rows
    ]
