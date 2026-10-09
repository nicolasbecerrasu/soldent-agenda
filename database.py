import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean, JSON, BigInteger, Column, Date, DateTime, ForeignKey,
    Integer, MetaData, Numeric, String, Text, create_engine, func, event
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, sessionmaker, relationship

from config import settings

# Normalizar URL para compatibilidad de driver PostgreSQL en Termux (pg8000 pure-python) y Render
db_url = settings.DATABASE_URL

# Auto-corrección para el host directo IPv6 de Supabase en nubes IPv4 (Render, etc.)
if "db.uqaprhszthoginyptwrf.supabase.co" in db_url:
    db_url = db_url.replace(
        "db.uqaprhszthoginyptwrf.supabase.co",
        "aws-0-us-west-2.pooler.supabase.com"
    ).replace(
        "postgres:",
        "postgres.uqaprhszthoginyptwrf:",
        1
    )

# En Supabase Pooler: Puerto 5432 es Session mode (limitado estrictamente a 15 clientes)
# Puerto 6543 es Transaction mode (soporta miles de conexiones concurrentes sin agotamiento)
if "pooler.supabase.com" in db_url:
    if ":5432" in db_url:
        db_url = db_url.replace(":5432", ":6543")

if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+pg8000://", 1)
elif db_url.startswith("postgresql://") and "+" not in db_url.split("://")[0]:
    db_url = db_url.replace("postgresql://", "postgresql+pg8000://", 1)

# Configurar motor con soporte universal para pg8000 y pool resiliente
engine = create_engine(
    db_url,
    pool_size=5,
    max_overflow=5,
    pool_recycle=60,
    pool_pre_ping=True
)

@event.listens_for(engine, "connect")
def configurar_search_path(dbapi_connection, connection_record):
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("SET search_path TO agenda, public, extensions;")
        cursor.close()
    except Exception:
        pass

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# =============================================================
# MODELOS SQLALCHEMY (Schema: agenda)
# =============================================================
class Base(DeclarativeBase):
    metadata = MetaData(schema="agenda")

class Paciente(Base):
    __tablename__ = "pacientes"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(Text, nullable=False)
    apellidos = Column(Text)
    telefono = Column(Text, nullable=True, index=True)
    email = Column(Text)
    fecha_nacimiento = Column(Date)
    alertas_medicas = Column(JSON, default=dict)
    notas = Column(Text)
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

class Tratamiento(Base):
    __tablename__ = "tratamientos"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(Text, nullable=False)
    duracion_min = Column(Integer, nullable=False)
    color = Column(Text, default="#3B82F6")
    precio = Column(Numeric(10, 2))
    activo = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Cita(Base):
    __tablename__ = "citas"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paciente_id = Column(PG_UUID(as_uuid=True), ForeignKey("agenda.pacientes.id"), nullable=False)
    tratamiento_id = Column(PG_UUID(as_uuid=True), ForeignKey("agenda.tratamientos.id"), nullable=False)
    inicio = Column(DateTime(timezone=True), nullable=False)
    fin = Column(DateTime(timezone=True), nullable=False)
    estado = Column(Text, default="pendiente")
    motivo = Column(Text)
    notas = Column(Text)
    google_event_id = Column(Text)
    token_respuesta_hash = Column(Text)
    token_recordatorio_hash = Column(Text)
    token_expira_en = Column(DateTime(timezone=True))
    recordatorio_enviado = Column(Boolean, default=False)
    version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    paciente = relationship("Paciente", foreign_keys=[paciente_id])
    tratamiento = relationship("Tratamiento", foreign_keys=[tratamiento_id])

class SyncOutbox(Base):
    __tablename__ = "sync_outbox"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    entidad = Column(Text, default="cita")
    entidad_id = Column(PG_UUID(as_uuid=True), nullable=False)
    accion = Column(Text, nullable=False)
    payload = Column(JSON, default=dict)
    intentos = Column(Integer, default=0)
    max_intentos = Column(Integer, default=5)
    proximo_intento = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    estado = Column(Text, default="pendiente")
    ultimo_error = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    procesado_en = Column(DateTime(timezone=True))

class NotificacionEnviada(Base):
    __tablename__ = "notificaciones_enviadas"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cita_id = Column(PG_UUID(as_uuid=True), ForeignKey("agenda.citas.id"), nullable=True)
    tipo = Column(Text, nullable=False)
    destino = Column(Text, nullable=False)
    estado = Column(Text, default="pendiente")
    intentos = Column(Integer, default=0)
    error = Column(Text)
    enviado_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AuditoriaCita(Base):
    __tablename__ = "auditoria_citas"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    cita_id = Column(PG_UUID(as_uuid=True), nullable=False)
    actor = Column(Text, nullable=False)
    accion = Column(Text, nullable=False)
    antes = Column(JSON)
    despues = Column(JSON)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())

class WhatsAppSession(Base):
    __tablename__ = "whatsapp_session"
    key = Column(String(255), primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Pago(Base):
    __tablename__ = "pagos"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paciente_id = Column(PG_UUID(as_uuid=True), ForeignKey("agenda.pacientes.id"), nullable=False)
    cita_id = Column(PG_UUID(as_uuid=True), ForeignKey("agenda.citas.id"), nullable=True)
    monto_total = Column(Numeric(10, 2), nullable=False, default=0.0)
    monto_pagado = Column(Numeric(10, 2), nullable=False, default=0.0)
    saldo_pendiente = Column(Numeric(10, 2), nullable=False, default=0.0)
    metodo_pago = Column(Text, default="efectivo")
    concepto = Column(Text, nullable=False)
    notas = Column(Text, nullable=True)
    fecha_pago = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    paciente = relationship("Paciente", foreign_keys=[paciente_id])
    cita = relationship("Cita", foreign_keys=[cita_id])
