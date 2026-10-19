import os
import re
import json
from typing import Optional
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from datetime import datetime, timezone
from config import settings
from database import (
    AuditoriaCita,
    Base,
    Cita,
    NotificacionEnviada,
    Paciente,
    Pago,
    SessionLocal,
    SyncOutbox,
    Tratamiento,
    WhatsAppSession,
    WorkerHeartbeat,
    engine,
    get_db
)
from routers import (
    auth,
    baileys_sync,
    citas,
    ortodoncia,
    pacientes,
    pagos,
    tratamientos,
    webhooks,
    whatsapp
)
from security import generar_auth_token, verificar_autenticacion
from services.google_calendar import (
    encolar_outbox,
    generar_token_respuesta,
    get_calendar_service,
    registrar_auditoria
)
from workers import (
    worker_control_mensual_ortodoncia,
    worker_recordatorios,
    worker_resumen_turnos_doctora,
    worker_sync_inverso_google,
    worker_sync_outbox
)

app = FastAPI(
    title="Soldent - Agenda Odontológica API",
    version="2.1.0",
    description="Backend modularizado para gestión de citas, pacientes y bot inteligente de WhatsApp"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
        "https://soldent-agenda.onrender.com",
    ],
    allow_origin_regex=r"^https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Endpoint de salud público minimalista (Cero información interna expuesta)
@app.get("/api/salud")
def salud():
    return {
        "ok": True,
        "status": "online"
    }

# Endpoint administrativo protegido para auditoría y diagnóstico de workers
@app.get("/api/admin/workers/health")
def admin_workers_health(x_auth_token: Optional[str] = Header(None, alias="X-Auth-Token")):
    import secrets
    admin_token = os.getenv("ADMIN_HEALTH_TOKEN", "").strip()
    if not admin_token or not x_auth_token or not secrets.compare_digest(x_auth_token, admin_token):
        raise HTTPException(status_code=401, detail="No autorizado para auditoria de infraestructura")

    from run_workers import WORKER_POLICIES, SAFE_ERROR_CATALOG
    from workers import SAFE_ALLOWED_EXCEPTION_TYPES
    workers_report = {}
    try:
        db = SessionLocal()
        try:
            ahora = datetime.now(timezone.utc)
            hbs = {h.worker_name: h for h in db.query(WorkerHeartbeat).all()}

            for w_name, policy in WORKER_POLICIES.items():
                h = hbs.get(w_name)
                tolerancia = policy["tolerancia_seg"]

                if not h or not h.last_heartbeat:
                    estado = "INACTIVO"
                    segundos = None
                else:
                    hb_dt = h.last_heartbeat
                    if hb_dt.tzinfo is None:
                        hb_dt = hb_dt.replace(tzinfo=timezone.utc)
                    segundos = int((ahora - hb_dt).total_seconds())
                    if segundos > (tolerancia * 1.5):
                        estado = "INACTIVO"
                    elif segundos > tolerancia:
                        estado = "ADVERTENCIA"
                    elif h.last_error:
                        estado = "DEGRADADO"
                    else:
                        estado = "ACTIVO"

                err_obj = None
                if h and h.last_error:
                    try:
                        raw_obj = json.loads(h.last_error)
                        if isinstance(raw_obj, dict):
                            err_code = str(raw_obj.get("error_code", "GENERIC_ERROR"))[:50]
                            if err_code not in SAFE_ERROR_CATALOG:
                                err_code = "GENERIC_ERROR"
                            raw_type = str(raw_obj.get("error_type", "ControlledOperationalException"))[:50]
                            err_type = raw_type if raw_type in SAFE_ALLOWED_EXCEPTION_TYPES else "ControlledOperationalException"
                            # Mensaje controlado garantizado por catálogo inmutable (cero fuga de secretos)
                            err_obj = {
                                "error_type": err_type,
                                "error_code": err_code,
                                "message": SAFE_ERROR_CATALOG.get(err_code, SAFE_ERROR_CATALOG["GENERIC_ERROR"])
                            }
                        else:
                            err_obj = {"error_type": "ControlledOperationalException", "error_code": "GENERIC_ERROR", "message": SAFE_ERROR_CATALOG["GENERIC_ERROR"]}
                    except Exception:
                        err_obj = {"error_type": "ControlledOperationalException", "error_code": "GENERIC_ERROR", "message": SAFE_ERROR_CATALOG["GENERIC_ERROR"]}

                workers_report[w_name] = {
                    "estado": estado,
                    "hace_segundos": segundos,
                    "tolerancia_seg": tolerancia,
                    "ultimo_exito": h.last_success.isoformat() if (h and h.last_success) else None,
                    "error_reciente": err_obj
                }
        finally:
            db.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error consultando telemetria de workers")

    return {"ok": True, "workers": workers_report}

# Incluir Routers Modulares
app.include_router(auth.router)
app.include_router(baileys_sync.router)
app.include_router(pacientes.router)
app.include_router(tratamientos.router)
app.include_router(pagos.router)
app.include_router(citas.router)
app.include_router(ortodoncia.router)
app.include_router(whatsapp.router)
app.include_router(webhooks.router)

# Montar frontend compilado si existe la carpeta dist
dist_path = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.exists(dist_path):
    app.mount("/", StaticFiles(directory=dist_path, html=True), name="frontend")