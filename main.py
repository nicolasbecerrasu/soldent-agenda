import hashlib, uuid, asyncio, os, re, hmac, time as std_time
from datetime import datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo
from typing import Optional
import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Header, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, JSON, BigInteger, Column, Date, DateTime, ForeignKey, Integer, MetaData, Numeric, Text, create_engine, func, select, text, event
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

try:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    Credentials = None
    build = None
    HttpError = Exception

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    TZ_CONSULTORIO: str = os.getenv("TZ_CONSULTORIO", "America/La_Paz")
    WHATSAPP_TOKEN: str = os.getenv("WHATSAPP_TOKEN", "")
    WHATSAPP_PHONE_ID: str = os.getenv("WHATSAPP_PHONE_ID", "")
    GOOGLE_REFRESH_TOKEN: str = os.getenv("GOOGLE_REFRESH_TOKEN", "")
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    CALENDAR_ID: str = os.getenv("CALENDAR_ID", "primary")
    PUBLIC_BASE_URL: str = os.getenv("PUBLIC_BASE_URL", "http://192.168.0.6:8000")
    RECORDATORIO_MIN: int = int(os.getenv("RECORDATORIO_MIN", "175"))
    RECORDATORIO_MAX: int = int(os.getenv("RECORDATORIO_MAX", "185"))
    DOCTORA_PIN: str = os.getenv("DOCTORA_PIN", "1104")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "soldent_secret_key_pamela_2026")

settings = Settings()

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

if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+pg8000://", 1)
elif db_url.startswith("postgresql://") and "+" not in db_url.split("://")[0]:
    db_url = db_url.replace("postgresql://", "postgresql+pg8000://", 1)

# Configurar motor con soporte universal para pg8000 (sin opciones libpq de C) y pool resiliente
engine = create_engine(
    db_url,
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
app = FastAPI(title="Agenda Odontológica API", version="2.0.0")

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
        "https://antonym-gumminess-preachy.ngrok-free.dev",
    ],
    allow_origin_regex=r"^https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# =============================================================
# 2. MODELOS SQLALCHEMY
# =============================================================
class Base(DeclarativeBase):
    metadata = MetaData(schema="agenda")

class Paciente(Base):
    __tablename__ = "pacientes"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(Text, nullable=False)
    apellidos = Column(Text)
    telefono = Column(Text, nullable=True, unique=True)
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
    cita_id = Column(PG_UUID(as_uuid=True), ForeignKey("agenda.citas.id"), nullable=False)
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

# =============================================================
# 3. HELPERS
# =============================================================
def generar_auth_token() -> str:
    timestamp = int(std_time.time())
    mensaje = f"dra_pamela:{timestamp}"
    firma = hmac.new(settings.SECRET_KEY.encode(), mensaje.encode(), hashlib.sha256).hexdigest()
    return f"{mensaje}:{firma}"

def validar_auth_token(token: str) -> bool:
    if not token:
        return False
    partes = token.split(":")
    if len(partes) != 3:
        return False
    user, ts_str, firma = partes
    if user != "dra_pamela":
        return False
    try:
        ts = int(ts_str)
        # Token válido por 90 días en el dispositivo de la doctora
        if std_time.time() - ts > (90 * 86400):
            return False
    except Exception:
        return False
    esperada = hmac.new(settings.SECRET_KEY.encode(), f"{user}:{ts_str}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(firma, esperada)

def verificar_autenticacion(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_auth_token: Optional[str] = Header(None)
):
    # Permitir peticiones internas locales (del bot de WhatsApp que corre en el mismo servidor)
    client_host = request.client.host if request.client else ""
    if client_host in ("127.0.0.1", "localhost", "::1"):
        return True

    if x_auth_token == settings.SECRET_KEY:
        return True

    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    elif x_auth_token:
        token = x_auth_token.strip()

    if not token or not validar_auth_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Acceso restringido. Por favor ingrese el PIN de la Doctora."
        )
    return True

def normalizar_telefono(tel: str) -> str:
    digitos = "".join(c for c in tel if c.isdigit())
    if not digitos.startswith("591") and len(digitos) == 8:
        digitos = "591" + digitos
    return "+" + digitos

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def registrar_auditoria(db: Session, cita_id, actor: str, accion: str, antes: dict = None, despues: dict = None):
    db.add(AuditoriaCita(cita_id=cita_id, actor=actor, accion=accion, antes=antes, despues=despues))

def encolar_outbox(db: Session, cita_id, accion: str, payload: dict):
    db.add(SyncOutbox(entidad="cita", entidad_id=cita_id, accion=accion, payload=payload))

def generar_token_respuesta(db: Session, cita: Cita) -> str:
    token = str(uuid.uuid4())
    cita.token_respuesta_hash = hash_token(token)
    cita.token_expira_en = cita.fin + timedelta(hours=2)
    return token

def _get_google_creds():
    if not Credentials:
        raise RuntimeError("google-auth no está instalado en este entorno.")
    return Credentials(
        token=None, refresh_token=settings.GOOGLE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID, client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/calendar.events"]
    )

def _get_calendar_service():
    if not build:
        raise RuntimeError("google-api-python-client no está instalado en este entorno.")
    return build("calendar", "v3", credentials=_get_google_creds())

# =============================================================
# 4. SCHEMAS PYDANTIC
# =============================================================
class PacienteIn(BaseModel):
    nombre: str
    apellidos: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    fecha_nacimiento: Optional[datetime] = None
    alertas_medicas: dict = Field(default_factory=dict)
    notas: Optional[str] = None

class PacienteUpdateIn(BaseModel):
    nombre: Optional[str] = None
    apellidos: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    notas: Optional[str] = None

class CitaIn(BaseModel):
    paciente_id: uuid.UUID
    tratamiento_id: uuid.UUID
    inicio: datetime
    duracion_min: Optional[int] = None
    fin: Optional[datetime] = None
    motivo: Optional[str] = None
    notas: Optional[str] = None

class CitaUpdateIn(BaseModel):
    inicio: Optional[datetime] = None
    tratamiento_id: Optional[uuid.UUID] = None
    estado: Optional[str] = None
    motivo: Optional[str] = None
    notas: Optional[str] = None
    version: int

ESTADOS_VALIDOS = {"pendiente", "confirmada", "cancelada", "atendida", "no_asistio"}

class PinLoginIn(BaseModel):
    pin: str

# =============================================================
# 4.5. ENDPOINTS AUTENTICACIÓN (PIN DOCTORA)
# =============================================================
@app.post("/api/auth/pin")
def login_pin(data: PinLoginIn):
    pin_limpio = data.pin.strip() if data.pin else ""
    if pin_limpio != settings.DOCTORA_PIN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="PIN de acceso incorrecto. Por favor verifica e intenta de nuevo."
        )
    token = generar_auth_token()
    return {
        "ok": True,
        "token": token,
        "usuario": "Dra. Pamela Pinto Suárez",
        "mensaje": "Acceso autorizado"
    }

@app.get("/api/auth/verificar")
def verificar_sesion(_auth: bool = Depends(verificar_autenticacion)):
    return {
        "ok": True,
        "valido": True,
        "usuario": "Dra. Pamela Pinto Suárez"
    }

# =============================================================
# 4.6. PERSISTENCIA DE SESIÓN WHATSAPP (BAILEYS / POSTGRESQL)
# =============================================================
class SessionItemIn(BaseModel):
    key: str
    value: str

class SessionBatchIn(BaseModel):
    items: dict[str, str]

@app.get("/api/internal/baileys-session")
def obtener_sesion_baileys(db: Session = Depends(get_db)):
    rows = db.execute(select(WhatsAppSession)).scalars().all()
    return {r.key: r.value for r in rows}

@app.post("/api/internal/baileys-session")
def guardar_archivo_sesion(item: SessionItemIn, db: Session = Depends(get_db)):
    existente = db.get(WhatsAppSession, item.key)
    if existente:
        existente.value = item.value
    else:
        db.add(WhatsAppSession(key=item.key, value=item.value))
    db.commit()
    return {"ok": True, "key": item.key}

@app.post("/api/internal/baileys-session/batch")
def guardar_archivos_sesion_batch(data: SessionBatchIn, db: Session = Depends(get_db)):
    for key, val in data.items.items():
        existente = db.get(WhatsAppSession, key)
        if existente:
            existente.value = val
        else:
            db.add(WhatsAppSession(key=key, value=val))
    db.commit()
    return {"ok": True, "total": len(data.items)}

@app.delete("/api/internal/baileys-session")
def borrar_sesion_baileys(db: Session = Depends(get_db)):
    db.execute(text("DELETE FROM agenda.whatsapp_session"))
    db.commit()
    return {"ok": True, "mensaje": "Sesión eliminada de base de datos"}

# =============================================================
# 5. ENDPOINTS CRUD
# =============================================================
@app.post("/api/pacientes", status_code=status.HTTP_201_CREATED)
def crear_paciente(data: PacienteIn, db: Session = Depends(get_db), _auth: bool = Depends(verificar_autenticacion)):
    tel = normalizar_telefono(data.telefono) if (data.telefono and data.telefono.strip()) else None
    if tel:
        existente = db.execute(select(Paciente).where(Paciente.telefono == tel)).scalar_one_or_none()
        if existente:
            if data.nombre and data.nombre.strip():
                existente.nombre = data.nombre.strip()
                db.commit()
            return {"id": str(existente.id)}
    elif data.nombre and data.nombre.strip():
        existente_nom = db.execute(select(Paciente).where(func.lower(Paciente.nombre) == data.nombre.strip().lower())).scalars().first()
        if existente_nom:
            return {"id": str(existente_nom.id)}
    p = Paciente(**data.model_dump(exclude={"telefono"}), telefono=tel)
    db.add(p)
    try:
        db.commit(); db.refresh(p)
    except IntegrityError:
        db.rollback()
        if tel:
            existente = db.execute(select(Paciente).where(Paciente.telefono == tel)).scalar_one_or_none()
            if existente:
                return {"id": str(existente.id)}
        raise HTTPException(409, "Paciente duplicado")
    return {"id": str(p.id)}

@app.patch("/api/pacientes/{pid}")
def actualizar_paciente(pid: uuid.UUID, data: PacienteUpdateIn, db: Session = Depends(get_db), _auth: bool = Depends(verificar_autenticacion)):
    p = db.get(Paciente, pid)
    if not p:
        raise HTTPException(404, "Paciente no encontrado")
    if data.telefono is not None:
        if data.telefono.strip() == "":
            p.telefono = None
        else:
            tel = normalizar_telefono(data.telefono)
            otro = db.execute(select(Paciente).where(Paciente.telefono == tel, Paciente.id != pid)).scalar_one_or_none()
            if otro:
                raise HTTPException(409, "Ya existe otro paciente con ese teléfono")
            p.telefono = tel
    if data.nombre is not None and data.nombre.strip():
        p.nombre = data.nombre.strip()
    if data.apellidos is not None:
        p.apellidos = data.apellidos.strip() or None
    if data.email is not None:
        p.email = data.email.strip() or None
    if data.notas is not None:
        p.notas = data.notas
    db.commit()
    db.refresh(p)
    return {"id": str(p.id), "nombre": p.nombre, "telefono": p.telefono}

@app.delete("/api/pacientes/{pid}")
def eliminar_paciente(pid: uuid.UUID, db: Session = Depends(get_db), _auth: bool = Depends(verificar_autenticacion)):
    paciente = db.get(Paciente, pid)
    if not paciente:
        raise HTTPException(404, "Paciente no encontrado")

    # Si tiene citas asociadas, asegurar borrado limpio en Google Calendar y lápidas en auditoría
    citas = db.execute(select(Cita).where(Cita.paciente_id == pid)).scalars().all()
    for cita in citas:
        gid = cita.google_event_id
        if gid:
            try:
                service = _get_calendar_service()
                service.events().delete(calendarId=settings.CALENDAR_ID, eventId=gid).execute()
                print(f"🗑️ [Google Calendar] Cita vinculada {cita.id} (evento {gid}) eliminada.")
            except Exception:
                encolar_outbox(db, cita.id, "delete", {"google_event_id": gid})
        registrar_auditoria(db, cita.id, "doctora", "eliminar", antes={"estado": cita.estado, "inicio": str(cita.inicio), "google_event_id": gid})
        db.delete(cita)

    db.delete(paciente)
    db.commit()
    return {"ok": True, "id": str(pid)}

@app.get("/api/pacientes")
def buscar_pacientes(q: str = "", db: Session = Depends(get_db), _auth: bool = Depends(verificar_autenticacion)):
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

@app.get("/api/tratamientos")
def listar_tratamientos(db: Session = Depends(get_db), _auth: bool = Depends(verificar_autenticacion)):
    rows = db.execute(select(Tratamiento)).scalars().all()
    return [{"id": str(r.id), "nombre": r.nombre, "duracion_min": r.duracion_min, "color": r.color, "precio": float(r.precio) if r.precio else None} for r in rows]

@app.get("/api/citas")
def listar_citas(
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    estado: Optional[str] = None,
    db: Session = Depends(get_db),
    _auth: bool = Depends(verificar_autenticacion)
):
    stmt = (
        select(Cita, Paciente, Tratamiento)
        .join(Paciente, Cita.paciente_id == Paciente.id)
        .join(Tratamiento, Cita.tratamiento_id == Tratamiento.id)
        .order_by(Cita.inicio.asc())
    )
    if desde:
        stmt = stmt.where(Cita.inicio >= desde)
    if hasta:
        stmt = stmt.where(Cita.inicio <= hasta)
    if estado:
        stmt = stmt.where(Cita.estado == estado)
    
    rows = db.execute(stmt).all()
    resultado = []
    for cita, pac, trat in rows:
        resultado.append({
            "id": str(cita.id),
            "paciente_id": str(cita.paciente_id),
            "tratamiento_id": str(cita.tratamiento_id),
            "inicio": cita.inicio.isoformat() if cita.inicio else None,
            "fin": cita.fin.isoformat() if cita.fin else None,
            "estado": cita.estado,
            "motivo": cita.motivo,
            "notas": cita.notas,
            "google_event_id": cita.google_event_id,
            "version": cita.version,
            "paciente": {
                "id": str(pac.id),
                "nombre": pac.nombre,
                "apellidos": pac.apellidos,
                "telefono": pac.telefono,
                "email": pac.email,
            },
            "tratamiento": {
                "id": str(trat.id),
                "nombre": trat.nombre,
                "color": trat.color,
                "duracion_min": trat.duracion_min,
                "precio": float(trat.precio) if trat.precio is not None else None,
            }
        })
    return resultado

def validar_horario_soldent(dt_inicio: datetime, dt_fin: datetime):
    """
    Valida las restricciones oficiales de horarios de atención en Soldent:
    - Lunes a Viernes: Mañana 09:00 a 12:00 | Tarde 15:30 a 19:30
    - Sábados: Mañana 09:00 a 12:00 (Tardes y domingos cerrado)
    """
    tz_bol = ZoneInfo(settings.TZ_CONSULTORIO)
    dt_ini_bol = dt_inicio.astimezone(tz_bol) if dt_inicio.tzinfo else dt_inicio.replace(tzinfo=timezone.utc).astimezone(tz_bol)
    dt_fin_bol = dt_fin.astimezone(tz_bol) if dt_fin.tzinfo else dt_fin.replace(tzinfo=timezone.utc).astimezone(tz_bol)

    weekday = dt_ini_bol.weekday()  # 0 = Lunes, 5 = Sábado, 6 = Domingo
    t_ini = dt_ini_bol.time()
    t_fin = dt_fin_bol.time()

    t_0900 = time(9, 0)
    t_1200 = time(12, 0)
    t_1530 = time(15, 30)
    t_1930 = time(19, 30)

    if weekday == 6:
        raise HTTPException(
            status_code=422,
            detail="Soldent permanece cerrado los domingos. Por favor seleccione un turno de Lunes a Sábado."
        )

    if weekday == 5:  # Sábado
        if not (t_ini >= t_0900 and t_fin <= t_1200):
            raise HTTPException(
                status_code=422,
                detail="Los sábados la clínica atiende únicamente en el turno de la mañana (09:00 a 12:00). Las tardes de sábado y domingos estamos cerrados."
            )
        return

    # Lunes a Viernes (0 a 4)
    en_manana = (t_ini >= t_0900 and t_fin <= t_1200)
    en_tarde = (t_ini >= t_1530 and t_fin <= t_1930)

    if not (en_manana or en_tarde):
        if t_ini >= t_1200 and t_ini < t_1530:
            raise HTTPException(
                status_code=422,
                detail="El horario solicitado coincide con el receso del mediodía (12:00 a 15:30). Los turnos disponibles son en la mañana (09:00 a 12:00) o en la tarde (15:30 a 19:30)."
            )
        raise HTTPException(
            status_code=422,
            detail="El horario solicitado está fuera del horario de atención de Soldent. Horarios oficiales: Lunes a Viernes de 09:00 a 12:00 y de 15:30 a 19:30; Sábados de 09:00 a 12:00."
        )

@app.post("/api/citas", status_code=status.HTTP_201_CREATED)
def crear_cita(data: CitaIn, db: Session = Depends(get_db), _auth: bool = Depends(verificar_autenticacion)):
    trat = db.get(Tratamiento, data.tratamiento_id)
    if not trat: raise HTTPException(404, "Tratamiento no encontrado")
    duracion = data.duracion_min if (data.duracion_min and data.duracion_min > 0) else trat.duracion_min
    fin = data.fin if data.fin else (data.inicio + timedelta(minutes=duracion))
    validar_horario_soldent(data.inicio, fin)
    paciente = db.get(Paciente, data.paciente_id)
    if not paciente: raise HTTPException(404, "Paciente no encontrado")
    # 2. Validación estricta anti-traslapes por consultorio/médico (Dra. Pamela Pinto Suárez)
    solapada = db.execute(
        select(Cita)
        .where(
            Cita.estado.notin_(["cancelada", "no_asistio"]),
            Cita.inicio < fin,
            Cita.fin > data.inicio
        )
    ).scalars().first()
    if solapada:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El horario solicitado ya se encuentra ocupado por otra cita en el consultorio."
        )

    ahora_utc = datetime.now(timezone.utc)
    inicio_utc = data.inicio.astimezone(timezone.utc) if data.inicio.tzinfo else data.inicio.replace(tzinfo=timezone.utc)

    # 4. Regla para citas inmediatas (< 3 horas):
    # Si un paciente solicita un espacio libre que inicie en menos de 3 horas:
    # - Guarda la cita directamente con estado = 'confirmada'
    # - Marca recordatorio_enviado = TRUE para que el worker de recordatorios no envíe mensaje redundante
    # - Encola la sincronización inmediata a Google Calendar para el iPhone de la doctora
    es_inmediata = (inicio_utc - ahora_utc) < timedelta(hours=3)
    estado_inicial = "confirmada" if es_inmediata else "pendiente"

    cita = Cita(
        paciente_id=data.paciente_id,
        tratamiento_id=data.tratamiento_id,
        inicio=data.inicio,
        fin=fin,
        motivo=data.motivo,
        notas=data.notas,
        estado=estado_inicial,
        recordatorio_enviado=es_inmediata
    )
    token = generar_token_respuesta(db, cita)
    try:
        db.add(cita)
        db.flush()

        if es_inmediata and paciente and paciente.telefono:
            ya = NotificacionEnviada(
                cita_id=cita.id,
                tipo="recordatorio",
                destino=paciente.telefono,
                estado="enviado",
                enviado_at=ahora_utc
            )
            db.add(ya)

        encolar_outbox(
            db, cita.id, "create",
            {
                "inicio": cita.inicio.isoformat(),
                "fin": fin.isoformat(),
                "paciente_nombre": paciente.nombre if paciente else "Paciente",
                "notas": data.notas
            }
        )
        registrar_auditoria(db, cita.id, "doctora", "crear", despues={"inicio": str(cita.inicio), "estado": estado_inicial})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ese hueco ya está ocupado o el paciente ya tiene cita en ese horario")
    return {
        "id": str(cita.id),
        "fin": fin.isoformat(),
        "estado": cita.estado,
        "es_inmediata": es_inmediata,
        "version": cita.version,
        "token_respuesta": token,
        "link_respuesta": f"{settings.PUBLIC_BASE_URL}/r/{token}"
    }

@app.patch("/api/citas/{cid}")
def actualizar_cita(cid: uuid.UUID, data: CitaUpdateIn, db: Session = Depends(get_db), _auth: bool = Depends(verificar_autenticacion)):
    cita = db.get(Cita, cid)
    if not cita: raise HTTPException(404, "Cita no encontrada")
    if data.estado and data.estado not in ESTADOS_VALIDOS: raise HTTPException(422, "Estado inválido")
    antes = {"estado": cita.estado, "inicio": str(cita.inicio), "version": cita.version}
    cambios = data.model_dump(exclude_unset=True, exclude={"version"})
    if not cambios: raise HTTPException(422, "Nada que actualizar")

    if data.inicio:
        trat_id = data.tratamiento_id or cita.tratamiento_id
        trat = db.get(Tratamiento, trat_id)
        duracion = trat.duracion_min if trat else 30
        fin_calc = data.inicio + timedelta(minutes=duracion)
        validar_horario_soldent(data.inicio, fin_calc)

        solapada = db.execute(
            select(Cita)
            .where(
                Cita.id != cid,
                Cita.estado.notin_(["cancelada", "no_asistio"]),
                Cita.inicio < fin_calc,
                Cita.fin > data.inicio
            )
        ).scalars().first()
        if solapada:
            raise HTTPException(409, "El nuevo horario se traslapa con otra cita activa en el consultorio")
    
    q = text("""UPDATE agenda.citas SET inicio = COALESCE(:inicio, inicio), tratamiento_id = COALESCE(:tratamiento_id, tratamiento_id), 
                estado = COALESCE(:estado, estado), motivo = COALESCE(:motivo, motivo), notas = COALESCE(:notas, notas), 
                version = version + 1, updated_at = now() 
                WHERE id = :cid AND version = :version RETURNING version, fin""")
    try:
        row = db.execute(q, {"cid": cid, "version": data.version, "inicio": cambios.get("inicio"), 
            "tratamiento_id": str(cambios["tratamiento_id"]) if cambios.get("tratamiento_id") else None,
            "estado": cambios.get("estado"), "motivo": cambios.get("motivo"), "notas": cambios.get("notas")}).mappings().first()
    except IntegrityError as e:
        db.rollback(); raise HTTPException(409, "El nuevo horario se traslapa con otra cita")
    if row is None:
        db.rollback(); raise HTTPException(409, "La cita fue modificada por otro proceso. Recarga e inténtalo de nuevo.")
    
    encolar_outbox(db, cid, "update", {"estado": cambios.get("estado", cita.estado), "inicio": str(cambios.get("inicio", cita.inicio))})
    registrar_auditoria(db, cid, "doctora", "actualizar", antes=antes, despues={"estado": cambios.get("estado", cita.estado), "version": row["version"]})
    db.commit()
    return {"id": str(cid), "version": row["version"], "fin": row["fin"].isoformat()}

@app.delete("/api/citas/{cid}")
def eliminar_cita(cid: uuid.UUID, db: Session = Depends(get_db), _auth: bool = Depends(verificar_autenticacion)):
    cita = db.get(Cita, cid)
    if not cita:
        raise HTTPException(404, "Cita no encontrada")
    
    gid = cita.google_event_id
    if gid:
        try:
            service = _get_calendar_service()
            service.events().delete(calendarId=settings.CALENDAR_ID, eventId=gid).execute()
            print(f"🗑️ [Google Calendar] Evento {gid} eliminado de inmediato.")
        except Exception as err:
            print(f"⚠️ [Google Calendar] No se pudo borrar evento directo ({err}), encolando outbox.")
            encolar_outbox(db, cid, "delete", {"google_event_id": gid})
    
    registrar_auditoria(db, cid, "doctora", "eliminar", antes={"estado": cita.estado, "inicio": str(cita.inicio), "google_event_id": gid})
    db.delete(cita)
    db.commit()
    return {"ok": True, "id": str(cid)}

# =============================================================
# 6. ENDPOINT PÚBLICO (WhatsApp Response)
# =============================================================
PAGE_HTML = """<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Confirmar Cita - Soldent</title>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;margin:0;background:#f8fafc;color:#1e293b;display:flex;justify-content:center;align-items:center;min-height:100vh;padding:16px;box-sizing:border-box}}
.card{{background:#fff;padding:32px 24px;border-radius:24px;box-shadow:0 10px 30px rgba(0,0,0,.06);max-width:400px;width:100%;text-align:center;border:1px solid #e2e8f0}}
.badge{{display:inline-flex;align-items:center;gap:6px;padding:6px 14px;background:#eff6ff;color:#2563eb;border-radius:999px;font-size:12px;font-weight:700;text-transform:uppercase;margin-bottom:16px}}
h1{{font-size:22px;margin:0 0 8px;color:#0f172a}}
.info-box{{background:#f8fafc;border-radius:14px;padding:16px;margin:16px 0 24px;text-align:left;font-size:14px;border:1px solid #edf2f7;line-height:1.6}}
.info-box p{{margin:6px 0;color:#475569}}
.info-box b{{color:#0f172a}}
button{{width:100%;padding:15px;border:none;border-radius:14px;font-size:15px;font-weight:700;cursor:pointer;margin-bottom:12px;transition:all .2s;display:flex;align-items:center;justify-content:center;gap:8px}}
button:active{{transform:scale(0.98)}}
.ok{{background:#16a34a;color:#fff;box-shadow:0 4px 12px rgba(22,163,74,.25)}}
.no{{background:#ef4444;color:#fff;box-shadow:0 4px 12px rgba(239,68,68,.25)}}
.msg{{display:none;padding:16px;border-radius:14px;font-weight:600;font-size:14px;margin-top:12px;line-height:1.4}}
.footer{{font-size:12px;color:#94a3b8;margin-top:20px;border-top:1px solid #f1f5f9;padding-top:14px}}
</style></head><body>
<div class="card">
  <div class="badge">🦷 Soldent • Clínica Odontológica</div>
  <h1>{titulo}</h1>
  <div class="info-box">{detalle}</div>
  <div id="ok" style="display:{show_btns}">
    <button class="ok" onclick="responder('confirmar')">✅ Confirmar Asistencia</button>
    <button class="no" onclick="responder('cancelar')">❌ Cancelar Cita</button>
  </div>
  <div id="msg" class="msg"></div>
  <div class="footer">Calle Lemoine 407 esq. Vallegrande<br>Santa Cruz de la Sierra, Bolivia</div>
</div>
<script>
async function responder(accion){{
  document.getElementById('ok').style.display='none';
  const msg=document.getElementById('msg');
  msg.style.display='block';
  msg.textContent='Procesando tu respuesta...';
  try {{
    const r=await fetch('/r/{token}/'+accion,{{method:'POST'}});
    const j=await r.json();
    msg.textContent=r.ok?j.mensaje:('Error: '+j.detail);
    msg.style.background=r.ok?'#dcfce7':'#fee2e2';
    msg.style.color=r.ok?'#15803d':'#b91c1c';
  }} catch(e){{
    msg.textContent='Error al conectar con la clínica.';
    msg.style.background='#fee2e2';
    msg.style.color='#b91c1c';
  }}
}}
</script></body></html>"""

def _buscar_por_token(db: Session, token: str) -> Optional[Cita]:
    h = hash_token(token)
    return db.execute(select(Cita).where((Cita.token_respuesta_hash == h) | (Cita.token_recordatorio_hash == h))).scalar_one_or_none()

@app.get("/r/{token}", response_class=HTMLResponse)
def pagina_respuesta(token: str, db: Session = Depends(get_db)):
    cita = _buscar_por_token(db, token)
    if not cita or (cita.token_expira_en and cita.token_expira_en < datetime.now(timezone.utc)):
        return HTMLResponse(PAGE_HTML.format(
            titulo="Enlace no válido o expirado",
            detalle="<p>El enlace de confirmación ha caducado o no se encuentra registrado en el sistema.</p><p>Por favor contáctate directamente con la clínica Soldent al <b>+591 78472875</b>.</p>",
            token=token,
            show_btns="none"
        ))
    p = db.get(Paciente, cita.paciente_id)
    trat = db.get(Tratamiento, cita.tratamiento_id)
    trat_nom = trat.nombre if trat else "Consulta Odontológica"
    tz_bol = ZoneInfo(settings.TZ_CONSULTORIO)
    dt_bol = cita.inicio.astimezone(tz_bol) if cita.inicio.tzinfo else cita.inicio.replace(tzinfo=timezone.utc).astimezone(tz_bol)
    f_fecha = dt_bol.strftime("%d/%m/%Y")
    f_hora = dt_bol.strftime("%H:%M")
    
    detalle_html = (
        f"<p><b>Paciente:</b> {p.nombre} {p.apellidos or ''}</p>"
        f"<p><b>Servicio:</b> Consulta Odontológica</p>"
        f"<p><b>Fecha:</b> {f_fecha}</p>"
        f"<p><b>Hora:</b> {f_hora} (hora de Santa Cruz)</p>"
        f"<p><b>Especialista:</b> Dra. Pamela Pinto Suárez</p>"
    )
    return HTMLResponse(PAGE_HTML.format(
        titulo=f"¡Hola, {p.nombre}!",
        detalle=detalle_html,
        token=token,
        show_btns="block" if cita.estado in ("pendiente", "confirmada") else "none"
    ))

@app.post("/r/{token}/{accion}")
def responder_cita(token: str, accion: str, db: Session = Depends(get_db)):
    if accion not in ("confirmar", "cancelar"): raise HTTPException(404, "Acción no válida")
    cita = _buscar_por_token(db, token)
    if not cita: raise HTTPException(404, "Enlace no válido")
    if cita.estado == "cancelada": return {"mensaje": "Esta cita ya fue cancelada previamente."}
    
    nuevo_estado = "confirmada" if accion == "confirmar" else "cancelada"
    q = text("UPDATE agenda.citas SET estado=:estado, version=version+1, updated_at=now() WHERE id=:cid AND version=:v RETURNING version")
    row = db.execute(q, {"estado": nuevo_estado, "cid": cita.id, "v": cita.version}).mappings().first()
    if row is None:
        db.rollback(); raise HTTPException(409, "La cita cambió mientras respondías.")
    
    encolar_outbox(db, cita.id, "update", {"estado": nuevo_estado})
    registrar_auditoria(db, cita.id, "paciente", accion, antes={"estado": cita.estado}, despues={"estado": nuevo_estado})
    db.commit()
    if accion == "cancelar":
        db.add(NotificacionEnviada(cita_id=cita.id, tipo="cancelacion", destino="DOCTORA", estado="pendiente"))
        return {"mensaje": "Tu cita ha sido cancelada exitosamente."}
    return {"mensaje": "¡Cita confirmada! Te esperamos con mucho gusto en Soldent."}

# =============================================================
# 7. WEBHOOK GOOGLE CALENDAR
# =============================================================
@app.post("/api/webhooks/google")
async def webhook_google(req: Request, db: Session = Depends(get_db)):
    if req.headers.get("X-Goog-Resource-State") not in ("exists", "not_exists", "sync"):
        return {"ok": True}
    try:
        service = _get_calendar_service()
        tiempo_limite = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat() + "Z"
        result = service.events().list(calendarId=settings.CALENDAR_ID, updatedMin=tiempo_limite, singleEvents=True, orderBy="updated").execute()
        for evento in result.get("items", []):
            cita = db.execute(select(Cita).where(Cita.google_event_id == evento.get("id"))).scalar_one_or_none()
            if not cita: continue
            g_updated = datetime.fromisoformat(evento.get("updated").replace("Z", "+00:00"))
            if g_updated <= cita.updated_at.replace(tzinfo=timezone.utc): continue
            
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
        db.rollback(); return {"ok": False, "error": str(e)}

# =============================================================
# 8. WORKERS (Lógica pura, ejecutada por run_workers.py)
# =============================================================
def worker_sync_outbox(db: Session):
    ahora = datetime.now(timezone.utc)
    pendientes = db.execute(select(SyncOutbox).where(SyncOutbox.estado == "pendiente", SyncOutbox.proximo_intento <= ahora).order_by(SyncOutbox.created_at).limit(50)).scalars().all()
    for outbox in pendientes:
        try:
            service = _get_calendar_service()
            event_id = outbox.payload.get("google_event_id")

            # 1. Eliminación de eventos en Google Calendar
            if outbox.accion == "delete":
                if event_id:
                    try:
                        service.events().delete(calendarId=settings.CALENDAR_ID, eventId=event_id).execute()
                    except Exception as del_err:
                        # Si ya no existe en Google (404 o 410 Gone), se considera exitosa la eliminación
                        if "404" not in str(del_err) and "410" not in str(del_err):
                            raise del_err
                outbox.estado, outbox.procesado_en = "completado", ahora
                db.commit()
                continue

            # 2. Creación o Actualización de eventos
            inicio_iso = outbox.payload.get("inicio")
            fin_iso = outbox.payload.get("fin")
            if not inicio_iso or not fin_iso:
                outbox.estado, outbox.ultimo_error = "fallido", "Falta fecha de inicio o fin en payload"
                outbox.procesado_en = ahora
                db.commit()
                continue

            event_body = {
                "summary": f"Cita: {outbox.payload.get('paciente_nombre', 'Paciente')}",
                "start": {"dateTime": inicio_iso, "timeZone": settings.TZ_CONSULTORIO},
                "end": {"dateTime": fin_iso, "timeZone": settings.TZ_CONSULTORIO}
            }
            
            if outbox.accion == "create":
                res = service.events().insert(calendarId=settings.CALENDAR_ID, body=event_body).execute()
                db.execute(text("UPDATE agenda.citas SET google_event_id=:gid WHERE id=:cid"), {"gid": res["id"], "cid": outbox.entidad_id})
                outbox.estado, outbox.procesado_en = "completado", ahora
            elif outbox.accion == "update" and event_id:
                service.events().update(calendarId=settings.CALENDAR_ID, eventId=event_id, body=event_body).execute()
                outbox.estado, outbox.procesado_en = "completado", ahora
            db.commit()
        except Exception as e:
            outbox.intentos += 1; outbox.ultimo_error = str(e)
            if outbox.intentos >= outbox.max_intentos:
                outbox.estado, outbox.procesado_en = "fallido", ahora
            else:
                outbox.proximo_intento = ahora + timedelta(minutes=2 ** outbox.intentos)
            db.commit()

def worker_sync_inverso_google(db: Session):
    """
    Sondeo periódico de Google Calendar (iPhone / Google Calendar -> App Web):
    Consulta los eventos en el calendario 'primary' (pamelaps6186@gmail.com).
    - Si un evento fue cancelado o eliminado en Google Calendar, actualiza la cita en Supabase a 'cancelada'.
    - Si el evento ya existe en agenda.citas y cambiaron sus horarios, actualiza inicio y fin.
    - Si el evento fue creado manualmente en el iPhone (no existe en agenda.citas):
      extrae nombre del paciente, fechas/horas, asocia o crea el paciente e inserta la cita como 'confirmada'.
    """
    try:
        service = _get_calendar_service()
    except Exception as e:
        print(f"[Sync Inverso Google] Error al obtener credenciales de Google Calendar: {e}")
        return

    ahora_utc = datetime.now(timezone.utc)
    tiempo_limite = (ahora_utc - timedelta(days=7)).isoformat()

    try:
        try:
            res = service.events().list(
                calendarId=settings.CALENDAR_ID,
                updatedMin=tiempo_limite,
                showDeleted=True,
                singleEvents=False,
                maxResults=100
            ).execute()
        except Exception:
            res = service.events().list(
                calendarId=settings.CALENDAR_ID,
                updatedMin=tiempo_limite,
                maxResults=100
            ).execute()

        eventos = res.get("items", [])
        if not eventos:
            return

        tz_bol = ZoneInfo(settings.TZ_CONSULTORIO)

        for evento in eventos:
            gid = evento.get("id")
            if not gid:
                continue

            status = evento.get("status")
            cita = db.execute(select(Cita).where(Cita.google_event_id == gid)).scalar_one_or_none()

            # 1. Evento eliminado o cancelado en Google Calendar
            if status == "cancelled":
                if cita and cita.estado != "cancelada":
                    print(f"🗑️ [Sync Inverso Google] Cita cancelada en Google Calendar detectada: ID {cita.id}")
                    cita.estado = "cancelada"
                    cita.updated_at = ahora_utc
                    registrar_auditoria(db, cita.id, "doctora_iphone", "cancelar_google", antes={"estado": cita.estado}, despues={"estado": "cancelada"})
                    db.commit()
                continue

            # 2. Extraer horarios de inicio y fin
            start_data = evento.get("start", {})
            end_data = evento.get("end", {})
            inicio_raw = start_data.get("dateTime") or start_data.get("date")
            fin_raw = end_data.get("dateTime") or end_data.get("date")

            if not inicio_raw or len(inicio_raw) == 10:
                continue

            try:
                dt_inicio = datetime.fromisoformat(inicio_raw.replace("Z", "+00:00"))
                if dt_inicio.tzinfo is None:
                    dt_inicio = dt_inicio.replace(tzinfo=tz_bol)
            except Exception:
                continue

            if fin_raw and len(fin_raw) > 10:
                try:
                    dt_fin = datetime.fromisoformat(fin_raw.replace("Z", "+00:00"))
                    if dt_fin.tzinfo is None:
                        dt_fin = dt_fin.replace(tzinfo=tz_bol)
                except Exception:
                    dt_fin = dt_inicio + timedelta(minutes=30)
            else:
                dt_fin = dt_inicio + timedelta(minutes=30)

            summary = (evento.get("summary") or "Consulta Dra. Pamela").strip()

            # 3. Cita existente: Actualizar horario si fue reprogramada en el iPhone
            if cita:
                c_ini_utc = cita.inicio.astimezone(timezone.utc) if cita.inicio.tzinfo else cita.inicio.replace(tzinfo=timezone.utc)
                dt_ini_utc = dt_inicio.astimezone(timezone.utc)
                if abs((c_ini_utc - dt_ini_utc).total_seconds()) > 60:
                    print(f"🔄 [Sync Inverso Google] Reprogramando cita {cita.id} desde iPhone a {dt_inicio}")
                    cita.inicio = dt_inicio
                    cita.fin = dt_fin
                    cita.updated_at = ahora_utc
                    registrar_auditoria(db, cita.id, "doctora_iphone", "reprogramar_google", despues={"inicio": str(dt_inicio), "fin": str(dt_fin)})
                    db.commit()
                continue

            # 3.5. Comprobar si esta cita fue eliminada explícitamente en el sistema (evitar bucle de reimportación)
            ya_eliminado = db.execute(
                select(AuditoriaCita).where(
                    AuditoriaCita.accion == "eliminar",
                    text("antes->>'google_event_id' = :gid").params(gid=gid)
                )
            ).scalars().first()

            if not ya_eliminado:
                ya_eliminado = db.execute(
                    select(SyncOutbox).where(
                        SyncOutbox.accion == "delete",
                        text("payload->>'google_event_id' = :gid").params(gid=gid)
                    )
                ).scalars().first()

            if ya_eliminado:
                print(f"🛑 [Sync Inverso Google] Evento {gid} ({summary}) fue eliminado voluntariamente de la agenda. Ignorando re-importación.")
                if status != "cancelled":
                    try:
                        service.events().delete(calendarId=settings.CALENDAR_ID, eventId=gid).execute()
                        print(f"🗑️ [Sync Inverso Google] Evento huérfano {gid} purgado de Google Calendar.")
                    except Exception:
                        pass
                continue

            # 4. Nueva cita creada manualmente en el iPhone: Importar a agenda.citas
            nombre_paciente = summary
            if summary.lower().startswith("cita:"):
                nombre_paciente = summary[5:].strip()
            elif summary.lower().startswith("cita "):
                nombre_paciente = summary[5:].strip()
            elif summary.lower().startswith("consulta "):
                nombre_paciente = summary[9:].strip()

            descripcion = evento.get("description", "") or ""
            texto_busqueda = f"{summary} {descripcion}"
            m_tel = re.search(r"(?:(?:\+?591\s*)?([67]\d{7}))", texto_busqueda)
            tel_extraido = normalizar_telefono(m_tel.group(0)) if m_tel else None

            # Si el teléfono estaba dentro del título (ej: "Marlerly Vargas 77123456"), limpiamos el nombre
            if m_tel and m_tel.group(0) in nombre_paciente:
                nombre_paciente = nombre_paciente.replace(m_tel.group(0), "").strip()
            if not nombre_paciente:
                nombre_paciente = "Paciente iPhone"

            paciente = None
            if tel_extraido:
                paciente = db.execute(select(Paciente).where(Paciente.telefono == tel_extraido)).scalar_one_or_none()
            if not paciente:
                paciente = db.execute(
                    select(Paciente).where(func.lower(Paciente.nombre) == nombre_paciente.lower())
                ).scalars().first()

            if not paciente:
                paciente = Paciente(
                    nombre=nombre_paciente,
                    telefono=tel_extraido,  # None si no hay teléfono, ¡NO inventa números ficticios!
                    notas="Registrado automáticamente desde Google Calendar (iPhone de la Doctora)"
                )
                db.add(paciente)
                db.flush()

            trat = db.execute(
                select(Tratamiento).where(Tratamiento.activo == True).order_by(Tratamiento.id)
            ).scalars().first()
            if not trat:
                trat = Tratamiento(nombre="Consulta y Diagnóstico", duracion_min=30, precio=100.0)
                db.add(trat)
                db.flush()

            nueva_cita = Cita(
                paciente_id=paciente.id,
                tratamiento_id=trat.id,
                inicio=dt_inicio,
                fin=dt_fin,
                estado="confirmada",
                motivo=summary,
                notas="Sincronizado automáticamente desde iPhone (Google Calendar)",
                google_event_id=gid,
                recordatorio_enviado=True
            )
            generar_token_respuesta(db, nueva_cita)

            try:
                db.add(nueva_cita)
                db.flush()
                registrar_auditoria(db, nueva_cita.id, "doctora_iphone", "crear_desde_google", despues={"inicio": str(dt_inicio), "estado": "confirmada"})
                db.commit()
                print(f"✅ [Sync Inverso Google] Cita de iPhone importada con éxito: '{nombre_paciente}' ({dt_inicio.strftime('%d/%m/%Y %H:%M')})")
            except IntegrityError as err_int:
                db.rollback()
                print(f"⚠️ [Sync Inverso Google] Aviso de colisión al importar cita de iPhone '{summary}': {err_int}")
            except Exception as err_ins:
                db.rollback()
                print(f"⚠️ [Sync Inverso Google] Error al guardar cita de iPhone: {err_ins}")

    except Exception as e:
        print(f"[Sync Inverso Google] Error en el ciclo de sondeo: {e}")

def worker_recordatorios(db: Session):
    ahora = datetime.now(timezone.utc)
    rec_min = int(getattr(settings, "RECORDATORIO_MIN", 175))
    rec_max = int(getattr(settings, "RECORDATORIO_MAX", 185))
    # Detecta citas que inicien en la ventana de 175 a 185 minutos (3 horas) y sin recordatorio previo
    rows = db.execute(
        select(Cita, Paciente)
        .join(Paciente, Cita.paciente_id == Paciente.id)
        .where(
            Cita.estado.in_(["pendiente", "confirmada"]),
            Cita.recordatorio_enviado == False,
            Cita.inicio >= ahora + timedelta(minutes=rec_min),
            Cita.inicio <= ahora + timedelta(minutes=rec_max)
        )
    ).all()
    for cita, paciente in rows:
        if db.execute(select(NotificacionEnviada).where(NotificacionEnviada.cita_id == cita.id, NotificacionEnviada.tipo == "recordatorio", NotificacionEnviada.estado == "enviado")).scalar_one_or_none():
            cita.recordatorio_enviado = True
            db.commit()
            continue
        token = str(uuid.uuid4())
        cita.token_recordatorio_hash = hash_token(token)
        ya = NotificacionEnviada(cita_id=cita.id, tipo="recordatorio", destino=paciente.telefono)
        db.add(ya)
        try:
            db.flush()
            tz_bol = ZoneInfo(getattr(settings, "TZ_CONSULTORIO", "America/La_Paz"))
            dt_bol = cita.inicio.astimezone(tz_bol) if cita.inicio.tzinfo else cita.inicio.replace(tzinfo=timezone.utc).astimezone(tz_bol)
            hora_str = dt_bol.strftime("%H:%M")
            base_url = getattr(settings, "PUBLIC_BASE_URL", "http://192.168.0.6:8000")
            link = f"{base_url}/r/{token}"
            mensaje = (
                f"🦷 *SOLDENT - Recordatorio de Cita*\n"
                f"Estimado/a *{paciente.nombre}*, le recordamos que tiene una consulta odontológica programada con la *Dra. Pamela Pinto Suárez* para las *{hora_str}*.\n\n"
                f"📍 *Consultorio:* Calle Lemoine 407 esq. Vallegrande, Santa Cruz de la Sierra.\n\n"
                f"👉 Por favor confirme o cancele su asistencia en este enlace:\n"
                f"{link}\n\n"
                f"¡Le esperamos!"
            )
            try:
                httpx.post(
                    "http://127.0.0.1:8080/send-message",
                    json={"number": paciente.telefono, "text": mensaje, "message": mensaje},
                    timeout=5.0
                )
                print(f"[WhatsApp] Recordatorio de 3 horas enviado a {paciente.telefono}")
            except Exception as err_w:
                print(f"[WhatsApp Error] No se pudo enviar a {paciente.telefono}: {err_w}")

            ya.estado, ya.enviado_at = "enviado", ahora
            cita.recordatorio_enviado = True
            db.commit()
        except IntegrityError:
            db.rollback()

@app.get("/api/salud")
def salud(): return {"ok": True, "version": "2.0.0", "tz": settings.TZ_CONSULTORIO}

@app.get("/whatsapp", response_class=HTMLResponse)
@app.get("/qr", response_class=HTMLResponse)
async def ver_qr_whatsapp():
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get("http://127.0.0.1:8080/qr")
            return HTMLResponse(content=resp.text, status_code=resp.status_code)
    except Exception as e:
        return HTMLResponse(
            "<!DOCTYPE html><html><head><meta http-equiv='refresh' content='3'><title>Soldent</title></head>"
            "<body style='font-family:sans-serif;text-align:center;padding-top:50px;'>"
            "<h3>Iniciando pasarela de WhatsApp... por favor espera unos segundos.</h3>"
            "</body></html>"
        )

# Montar frontend compilado si existe la carpeta dist
dist_path = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.exists(dist_path):
    app.mount("/", StaticFiles(directory=dist_path, html=True), name="frontend")