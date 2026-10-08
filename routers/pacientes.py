import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import settings
from database import Cita, Paciente, get_db
from schemas import PacienteIn, PacienteUpdateIn
from security import (
    es_telefono_bolivia_valido,
    normalizar_telefono,
    verificar_autenticacion
)
from services.google_calendar import (
    encolar_outbox,
    get_calendar_service,
    registrar_auditoria
)

router = APIRouter(prefix="/api/pacientes", tags=["Pacientes"])

@router.get("/verificar-telefono")
def verificar_telefono(
    telefono: str,
    paciente_id: Optional[uuid.UUID] = None,
    db: Session = Depends(get_db),
    _auth: bool = Depends(verificar_autenticacion)
):
    tel = normalizar_telefono(telefono)
    if not tel:
        return {
            "valido": False,
            "telefono_normalizado": None,
            "existe": False,
            "coincidencias": []
        }

    query = select(Paciente).where(Paciente.telefono == tel)
    if paciente_id:
        query = query.where(Paciente.id != paciente_id)

    encontrados = db.execute(query).scalars().all()
    coincidencias = [
        {
            "id": str(p.id),
            "nombre": f"{p.nombre} {p.apellidos or ''}".strip(),
            "telefono": p.telefono
        }
        for p in encontrados
    ]
    return {
        "valido": es_telefono_bolivia_valido(tel),
        "telefono_normalizado": tel,
        "existe": len(coincidencias) > 0,
        "coincidencias": coincidencias
    }

@router.post("", status_code=status.HTTP_201_CREATED)
def crear_paciente(
    data: PacienteIn,
    db: Session = Depends(get_db),
    _auth: bool = Depends(verificar_autenticacion)
):
    tel = normalizar_telefono(data.telefono) if (data.telefono and data.telefono.strip()) else None
    if tel:
        existentes = db.execute(select(Paciente).where(Paciente.telefono == tel)).scalars().all()
        if existentes:
            # 1. Si ya existe un paciente con el mismo nombre y mismo teléfono, devolverlo sin duplicar
            nombre_nuevo = data.nombre.strip().lower()
            mismo_paciente = None
            for ex in existentes:
                nombre_ex = f"{ex.nombre} {ex.apellidos or ''}".strip().lower()
                if ex.nombre.strip().lower() == nombre_nuevo or nombre_ex == nombre_nuevo:
                    mismo_paciente = ex
                    break

            if mismo_paciente:
                return {"id": str(mismo_paciente.id)}

            # 2. Si tiene distinto nombre pero NO se autorizó compartir el teléfono (caso familiar / tutor):
            if not data.permitir_compartido:
                ex0 = existentes[0]
                nombre_otro = f"{ex0.nombre} {ex0.apellidos or ''}".strip()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"El teléfono {tel} ya está asignado al paciente '{nombre_otro}'. Si es familiar o tutor, confirme el registro compartido."
                )
    elif data.nombre and data.nombre.strip():
        existente_nom = db.execute(select(Paciente).where(func.lower(Paciente.nombre) == data.nombre.strip().lower())).scalars().first()
        if existente_nom:
            return {"id": str(existente_nom.id)}

    p = Paciente(**data.model_dump(exclude={"telefono", "permitir_compartido"}), telefono=tel)
    db.add(p)
    try:
        db.commit()
        db.refresh(p)
    except IntegrityError:
        db.rollback()
        if tel:
            existente = db.execute(select(Paciente).where(Paciente.telefono == tel)).scalar_one_or_none()
            if existente:
                return {"id": str(existente.id)}
        raise HTTPException(409, "Paciente duplicado")
    return {"id": str(p.id)}

@router.patch("/{pid}")
def actualizar_paciente(
    pid: uuid.UUID,
    data: PacienteUpdateIn,
    db: Session = Depends(get_db),
    _auth: bool = Depends(verificar_autenticacion)
):
    p = db.get(Paciente, pid)
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    if data.telefono is not None:
        if data.telefono.strip() == "":
            p.telefono = None
        else:
            tel = normalizar_telefono(data.telefono)
            otro = db.execute(select(Paciente).where(Paciente.telefono == tel, Paciente.id != pid)).scalar_one_or_none()
            if otro and not data.permitir_compartido:
                nombre_otro = f"{otro.nombre} {otro.apellidos or ''}".strip()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Ya existe otro paciente con ese teléfono: '{nombre_otro}'. Si es familiar o tutor, confirme guardar."
                )
            p.telefono = tel
    if data.nombre is not None and data.nombre.strip():
        p.nombre = data.nombre.strip()
    if data.apellidos is not None:
        p.apellidos = data.apellidos.strip() or None
    if data.email is not None:
        p.email = data.email.strip() or None
    if data.notas is not None:
        p.notas = data.notas
    if data.alertas_medicas is not None:
        p.alertas_medicas = data.alertas_medicas
    db.commit()
    db.refresh(p)
    return {"id": str(p.id), "nombre": p.nombre, "telefono": p.telefono, "alertas": p.alertas_medicas}

@router.delete("/{pid}")
def eliminar_paciente(
    pid: uuid.UUID,
    db: Session = Depends(get_db),
    _auth: bool = Depends(verificar_autenticacion)
):
    paciente = db.get(Paciente, pid)
    if not paciente:
        raise HTTPException(404, "Paciente no encontrado")

    # Si tiene citas asociadas, asegurar borrado limpio en Google Calendar y lápidas en auditoría
    citas = db.execute(select(Cita).where(Cita.paciente_id == pid)).scalars().all()
    for cita in citas:
        gid = cita.google_event_id
        if gid:
            try:
                service = get_calendar_service()
                service.events().delete(calendarId=settings.CALENDAR_ID, eventId=gid).execute()
                print(f"🗑️ [Google Calendar] Cita vinculada {cita.id} (evento {gid}) eliminada.")
            except Exception:
                encolar_outbox(db, cita.id, "delete", {"google_event_id": gid})
        registrar_auditoria(db, cita.id, "doctora", "eliminar", antes={"estado": cita.estado, "inicio": str(cita.inicio), "google_event_id": gid})
        db.delete(cita)

    db.delete(paciente)
    db.commit()
    return {"ok": True, "id": str(pid)}

@router.get("")
def buscar_pacientes(
    q: str = "",
    db: Session = Depends(get_db),
    _auth: bool = Depends(verificar_autenticacion)
):
    stmt = select(Paciente)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            (Paciente.nombre.ilike(like)) | 
            (func.coalesce(Paciente.apellidos, "").ilike(like)) | 
            (func.coalesce(Paciente.telefono, "").ilike(like))
        )
    stmt = stmt.order_by(Paciente.nombre.asc())
    rows = db.execute(stmt).scalars().all()
    return [
        {
            "id": str(r.id),
            "nombre": r.nombre,
            "apellidos": r.apellidos,
            "telefono": r.telefono,
            "email": r.email,
            "notas": r.notas,
            "alertas": r.alertas_medicas
        }
        for r in rows
    ]
