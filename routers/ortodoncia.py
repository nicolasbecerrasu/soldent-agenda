import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import Cita, NotificacionEnviada, Paciente, Pago, Tratamiento, get_db
from security import verificar_autenticacion

router = APIRouter(prefix="/api/ortodoncia", tags=["Ortodoncia"])

def _obtener_pacientes_ortodoncia_calculados(db: Session):
    ahora_utc = datetime.now(timezone.utc)
    
    todos_pacientes = db.execute(select(Paciente)).scalars().all()
    todas_citas = db.execute(select(Cita)).scalars().all()
    todos_pagos = db.execute(select(Pago)).scalars().all()
    todos_tratamientos = {t.id: t for t in db.execute(select(Tratamiento)).scalars().all()}
    
    citas_por_paciente = {}
    for c in todas_citas:
        citas_por_paciente.setdefault(c.paciente_id, []).append(c)
        
    pagos_por_paciente = {}
    for p in todos_pagos:
        pagos_por_paciente.setdefault(p.paciente_id, []).append(p)

    notifs = db.execute(
        select(NotificacionEnviada)
        .where(NotificacionEnviada.tipo == "recordatorio_ortodoncia")
        .order_by(NotificacionEnviada.enviado_at.desc())
    ).scalars().all()
    ult_notif_por_tel = {}
    for n in notifs:
        if n.destino and n.destino not in ult_notif_por_tel:
            ult_notif_por_tel[n.destino] = n.enviado_at

    palabras_clave = ['orto', 'bracket', 'frenillo', 'ortopedia', 'control ort', 'ajuste']

    resultado = []
    for pac in todos_pacientes:
        c_list = citas_por_paciente.get(pac.id, [])
        p_list = pagos_por_paciente.get(pac.id, [])
        alertas = pac.alertas_medicas or {}

        # Determinar si es paciente de ortodoncia
        es_orto = alertas.get("es_ortodoncia") is True
        if not es_orto:
            txt_pac = f"{pac.notas or ''} {str(alertas)}".lower()
            if any(k in txt_pac for k in palabras_clave):
                es_orto = True
        if not es_orto:
            for c in c_list:
                t = todos_tratamientos.get(c.tratamiento_id)
                t_nom = (t.nombre or '').lower() if t else ''
                txt_c = f"{c.motivo or ''} {c.notas or ''} {t_nom}".lower()
                if any(k in txt_c for k in palabras_clave):
                    es_orto = True
                    break
        if not es_orto:
            for p in p_list:
                if any(k in (p.concepto or '').lower() for k in palabras_clave):
                    es_orto = True
                    break

        if not es_orto:
            continue

        citas_pasadas = [c for c in c_list if c.inicio and c.inicio <= ahora_utc and c.estado in ("confirmada", "atendida", "pendiente")]
        citas_futuras = [c for c in c_list if c.inicio and c.inicio > ahora_utc and c.estado in ("confirmada", "pendiente")]

        tiene_futura = len(citas_futuras) > 0
        proxima_cita = min(citas_futuras, key=lambda x: x.inicio) if tiene_futura else None
        ultima_cita = max(citas_pasadas, key=lambda x: x.inicio) if citas_pasadas else None

        if ultima_cita:
            dias_transcurridos = max(0, (ahora_utc - ultima_cita.inicio).days)
            f_ult_iso = ultima_cita.inicio.isoformat()
            t_ult = todos_tratamientos.get(ultima_cita.tratamiento_id)
            motivo_ult = ultima_cita.motivo or (t_ult.nombre if t_ult else "Control de Ortodoncia")
        else:
            dias_transcurridos = 30
            f_ult_iso = None
            motivo_ult = "Sin citas previas registradas"

        if tiene_futura:
            estado_control = "al_dia"
        else:
            if dias_transcurridos >= 30:
                estado_control = "vencido"
            elif dias_transcurridos >= 21:
                estado_control = "proximo"
            else:
                estado_control = "al_dia"

        f_notif = ult_notif_por_tel.get(pac.telefono)
        f_notif_iso = f_notif.isoformat() if f_notif else None
        
        es_dummy = not pac.telefono or pac.telefono.startswith("+59199")
        puede_recordar = not es_dummy and (not f_notif or (ahora_utc - f_notif).days >= 7)

        f_prox_iso = proxima_cita.inicio.isoformat() if proxima_cita else None

        resultado.append({
            "paciente_id": str(pac.id),
            "nombre": pac.nombre,
            "apellidos": pac.apellidos,
            "telefono": pac.telefono,
            "es_dummy_telefono": es_dummy,
            "alertas": alertas,
            "ultima_cita_inicio": f_ult_iso,
            "ultima_cita_motivo": motivo_ult,
            "dias_transcurridos": dias_transcurridos,
            "estado_control": estado_control,
            "tiene_cita_futura": tiene_futura,
            "proxima_cita_inicio": f_prox_iso,
            "ultimo_recordatorio_enviado": f_notif_iso,
            "puede_recordar": puede_recordar
        })

    prioridad = {"vencido": 0, "proximo": 1, "al_dia": 2}
    resultado.sort(key=lambda x: (prioridad.get(x["estado_control"], 3), -x["dias_transcurridos"]))

    tot_vencidos = sum(1 for x in resultado if x["estado_control"] == "vencido")
    tot_proximos = sum(1 for x in resultado if x["estado_control"] == "proximo")
    tot_al_dia = sum(1 for x in resultado if x["estado_control"] == "al_dia")

    return {
        "total_ortodoncia": len(resultado),
        "total_vencidos": tot_vencidos,
        "total_proximos": tot_proximos,
        "total_al_dia": tot_al_dia,
        "pacientes": resultado
    }

@router.get("/pacientes")
def listar_pacientes_ortodoncia(db: Session = Depends(get_db), _auth: bool = Depends(verificar_autenticacion)):
    return _obtener_pacientes_ortodoncia_calculados(db)

@router.post("/{paciente_id}/enviar-recordatorio")
async def enviar_recordatorio_control_ortodoncia(
    paciente_id: uuid.UUID,
    db: Session = Depends(get_db),
    _auth: bool = Depends(verificar_autenticacion)
):
    pac = db.get(Paciente, paciente_id)
    if not pac or not pac.telefono:
        raise HTTPException(status_code=400, detail="El paciente no tiene un número de teléfono válido")
    if pac.telefono.startswith("+59199"):
        raise HTTPException(status_code=400, detail="El paciente tiene un teléfono provisional o dummy")

    ahora_utc = datetime.now(timezone.utc)
    citas_pasadas = db.execute(
        select(Cita).where(
            Cita.paciente_id == paciente_id,
            Cita.inicio <= ahora_utc,
            Cita.estado.in_(["confirmada", "atendida", "pendiente"])
        ).order_by(Cita.inicio.desc())
    ).scalars().all()

    dias = max(0, (ahora_utc - citas_pasadas[0].inicio).days) if citas_pasadas else 25
    cita_asociada_id = citas_pasadas[0].id if citas_pasadas else None

    msg = (
        f"🦷 *SOLDENT - Control Mensual de Ortodoncia*\n\n"
        f"¡Hola, *{pac.nombre}*! ✨\n"
        f"Esperamos que te encuentres muy bien.\n\n"
        f"Te recordamos que ya han transcurrido *{dias} días* desde tu última atención odontológica "
        f"y es momento de tu *control y ajuste mensual de ortodoncia / brackets* con la *Dra. Pamela Pinto Suárez*.\n\n"
        f"El control periódico es indispensable para asegurar que tus dientes continúen alineándose correctamente "
        f"y evitar que tu tratamiento se extienda. 🎯\n\n"
        f"📅 *Horarios de atención en consultorio:*\n"
        f"• *Mañana:* 09:00 a 12:00\n"
        f"• *Tarde:* 15:30 a 19:30\n\n"
        f"¿Qué día y horario te queda más cómodo para visitarnos esta semana? "
        f"Escríbenos directamente aquí y te reservamos tu turno con mucho gusto. ¡Te esperamos! 💙"
    )

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                "http://127.0.0.1:8080/send-message",
                json={"number": pac.telefono, "text": msg, "message": msg}
            )
            
            notif = NotificacionEnviada(
                cita_id=cita_asociada_id,
                tipo="recordatorio_ortodoncia",
                destino=pac.telefono,
                estado="enviado",
                enviado_at=ahora_utc
            )
            db.add(notif)
            db.commit()

            return {"ok": True, "enviado": True, "mensaje": msg}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@router.post("/disparar-recordatorios-automaticos")
async def disparar_recordatorios_automaticos_ortodoncia(
    db: Session = Depends(get_db),
    _auth: bool = Depends(verificar_autenticacion)
):
    res = _obtener_pacientes_ortodoncia_calculados(db)
    pacientes_pendientes = [p for p in res["pacientes"] if p["estado_control"] == "vencido" and p["puede_recordar"]]
    enviados = 0
    errores = []

    for p in pacientes_pendientes:
        try:
            pid = uuid.UUID(p["paciente_id"])
            sub_res = await enviar_recordatorio_control_ortodoncia(pid, db, True)
            if sub_res.get("ok"):
                enviados += 1
            else:
                errores.append(f"{p['nombre']}: {sub_res.get('error')}")
        except Exception as e:
            errores.append(f"{p['nombre']}: {e}")

    return {"ok": True, "enviados": enviados, "total_vencidos": len(pacientes_pendientes), "errores": errores}
