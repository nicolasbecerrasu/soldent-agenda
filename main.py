import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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

# Endpoint de salud del sistema
@app.get("/api/salud")
def salud():
    return {
        "ok": True,
        "version": "2.1.0",
        "estado": "operativo",
        "tz": settings.TZ_CONSULTORIO
    }

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