import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, status
import httpx
from sqlalchemy.orm import Session

from config import settings
from database import Paciente, Pago, get_db
from schemas import PagoIn
from security import verificar_autenticacion

router = APIRouter(tags=["Pagos y Facturación"])

@router.get("/api/pacientes/{paciente_id}/pagos")
def listar_pagos_paciente(
    paciente_id: uuid.UUID,
    db: Session = Depends(get_db),
    _auth: bool = Depends(verificar_autenticacion)
):
    pagos = db.query(Pago).filter(Pago.paciente_id == paciente_id).order_by(Pago.fecha_pago.desc()).all()
    total_tratamientos = sum(float(p.monto_total or 0) for p in pagos)
    total_pagado = sum(float(p.monto_pagado or 0) for p in pagos)
    saldo_pendiente = max(0.0, total_tratamientos - total_pagado)
    return {
        "paciente_id": str(paciente_id),
        "total_tratamientos": total_tratamientos,
        "total_pagado": total_pagado,
        "saldo_pendiente": saldo_pendiente,
        "pagos": [
            {
                "id": str(p.id),
                "paciente_id": str(p.paciente_id),
                "cita_id": str(p.cita_id) if p.cita_id else None,
                "monto_total": float(p.monto_total or 0),
                "monto_pagado": float(p.monto_pagado or 0),
                "saldo_pendiente": float(p.saldo_pendiente or 0),
                "metodo_pago": p.metodo_pago,
                "concepto": p.concepto,
                "notas": p.notas,
                "fecha_pago": p.fecha_pago.isoformat() if p.fecha_pago else None,
            }
            for p in pagos
        ]
    }

@router.post("/api/pagos", status_code=status.HTTP_201_CREATED)
def crear_pago(
    data: PagoIn,
    db: Session = Depends(get_db),
    _auth: bool = Depends(verificar_autenticacion)
):
    pac = db.get(Paciente, data.paciente_id)
    if not pac:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")
    
    saldo = max(0.0, float(data.monto_total) - float(data.monto_pagado))
    tz_bol = ZoneInfo(settings.TZ_CONSULTORIO)
    f_pago = data.fecha_pago if data.fecha_pago else datetime.now(tz_bol)

    pago = Pago(
        paciente_id=data.paciente_id,
        cita_id=data.cita_id,
        monto_total=data.monto_total,
        monto_pagado=data.monto_pagado,
        saldo_pendiente=saldo,
        metodo_pago=data.metodo_pago.lower(),
        concepto=data.concepto.strip(),
        notas=data.notas.strip() if data.notas else None,
        fecha_pago=f_pago
    )
    db.add(pago)
    db.commit()
    db.refresh(pago)
    return {"ok": True, "id": str(pago.id), "saldo_pendiente": float(pago.saldo_pendiente)}

@router.delete("/api/pagos/{pago_id}")
def eliminar_pago(
    pago_id: uuid.UUID,
    db: Session = Depends(get_db),
    _auth: bool = Depends(verificar_autenticacion)
):
    pago = db.get(Pago, pago_id)
    if not pago:
        raise HTTPException(status_code=404, detail="Pago no encontrado")
    db.delete(pago)
    db.commit()
    return {"ok": True, "mensaje": "Pago eliminado correctamente"}

@router.post("/api/pacientes/{paciente_id}/compartir-estado-cuenta")
async def compartir_estado_cuenta(
    paciente_id: uuid.UUID,
    db: Session = Depends(get_db),
    _auth: bool = Depends(verificar_autenticacion)
):
    pac = db.get(Paciente, paciente_id)
    if not pac or not pac.telefono:
        raise HTTPException(status_code=400, detail="El paciente no tiene un teléfono registrado")
    
    pagos = db.query(Pago).filter(Pago.paciente_id == paciente_id).order_by(Pago.fecha_pago.asc()).all()
    if not pagos:
        raise HTTPException(status_code=400, detail="El paciente no registra ningún pago o tratamiento")
    
    total_costo = sum(float(p.monto_total or 0) for p in pagos)
    total_pagado = sum(float(p.monto_pagado or 0) for p in pagos)
    saldo_restante = max(0.0, total_costo - total_pagado)

    detalles = []
    for p in pagos:
        f_str = p.fecha_pago.strftime('%d/%m/%Y') if p.fecha_pago else 'Reciente'
        detalles.append(f"• {f_str} | {p.concepto}: Abonó {float(p.monto_pagado):,.2f} Bs ({p.metodo_pago.upper()})")
    
    texto_detalles = "\n".join(detalles)

    msg = (
        f"🦷 *SOLDENT - Estado de Cuenta Odontológico*\n\n"
        f"Estimado/a *{pac.nombre}*, le compartimos el resumen de sus tratamientos y pagos:\n\n"
        f"{texto_detalles}\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📋 *Costo Total Tratamientos:* {total_costo:,.2f} Bs\n"
        f"💵 *Total Abonado / Pagado:* {total_pagado:,.2f} Bs\n"
        f"🔴 *Saldo Pendiente:* {saldo_restante:,.2f} Bs\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"Agradecemos su confianza en nuestro consultorio dental. "
        f"Cualquier consulta sobre su tratamiento o pagos, estamos a su servicio. ✨"
    )

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post("http://127.0.0.1:8080/send-message", json={"number": pac.telefono, "text": msg, "message": msg})
            return {"ok": True, "enviado": True, "mensaje": msg}
    except Exception as e:
        return {"ok": False, "error": str(e)}
