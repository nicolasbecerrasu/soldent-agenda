import hashlib, uuid, asyncio, os
from datetime import datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo
from typing import Optional
import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from sqlalchemy import Boolean, JSON, BigInteger, Column, Date, DateTime, ForeignKey, Integer, MetaData, Numeric, Text, create_engine, func, select, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# =============================================================
# 1. CONFIGURACIÓN
# =============================================================
class Settings(BaseSettings):
    DATABASE_URL: str
    TZ_CONSULTORIO: str = "America/La_Paz"
    WHATSAPP_TOKEN: str = ""
    WHATSAPP_PHONE_ID: str = ""
    GOOGLE_REFRESH_TOKEN: str = ""
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    CALENDAR_ID: str = "primary"
    PUBLIC_BASE_URL: str = "http://192.168.0.6:8000"
    RECORDATORIO_MIN: int = 175
    RECORDATORIO_MAX: int = 185
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

# Normalizar URL para compatibilidad de driver PostgreSQL en SQLAlchemy 2.0 y soporte IPv4
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
    db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif db_url.startswith("postgresql://") and "+" not in db_url.split("://")[0]:
    db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

engine = create_engine(
    db_url,
    connect_args={"options": "-csearch_path=agenda,public,extensions"},
    pool_pre_ping=True
)
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
    telefono = Column(Text, nullable=False, unique=True)
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

# =============================================================
# 3. HELPERS
# =============================================================
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

def _get_google_creds() -> Credentials:
    return Credentials(
        token=None, refresh_token=settings.GOOGLE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID, client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/calendar.events"]
    )

def _get_calendar_service():
    return build("calendar", "v3", credentials=_get_google_creds())

# =============================================================
# 4. SCHEMAS PYDANTIC
# =============================================================
class PacienteIn(BaseModel):
    nombre: str
    apellidos: Optional[str] = None
    telefono: str
    email: Optional[str] = None
    fecha_nacimiento: Optional[datetime] = None
    alertas_medicas: dict = Field(default_factory=dict)
    notas: Optional[str] = None

class CitaIn(BaseModel):
    paciente_id: uuid.UUID
    tratamiento_id: uuid.UUID
    inicio: datetime
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

# =============================================================
# 5. ENDPOINTS CRUD
# =============================================================
@app.post("/api/pacientes", status_code=status.HTTP_201_CREATED)
def crear_paciente(data: PacienteIn, db: Session = Depends(get_db)):
    tel = normalizar_telefono(data.telefono)
    if db.execute(select(Paciente).where(Paciente.telefono == tel)).scalar_one_or_none():
        raise HTTPException(409, "Ya existe un paciente con ese teléfono")
    p = Paciente(**data.model_dump(exclude={"telefono"}), telefono=tel)
    db.add(p)
    try:
        db.commit(); db.refresh(p)
    except IntegrityError:
        db.rollback(); raise HTTPException(409, "Paciente duplicado")
    return {"id": str(p.id)}

@app.get("/api/pacientes")
def buscar_pacientes(q: str = "", db: Session = Depends(get_db)):
    like = f"%{q}%"
    rows = db.execute(select(Paciente).where(
        (Paciente.nombre.ilike(like)) | (func.coalesce(Paciente.apellidos, "").ilike(like)) | (Paciente.telefono.ilike(like))
    ).limit(10)).scalars().all()
    return [{"id": str(r.id), "nombre": r.nombre, "apellidos": r.apellidos, "telefono": r.telefono, "alertas": r.alertas_medicas} for r in rows]

@app.get("/api/tratamientos")
def listar_tratamientos(db: Session = Depends(get_db)):
    rows = db.execute(select(Tratamiento)).scalars().all()
    return [{"id": str(r.id), "nombre": r.nombre, "duracion_min": r.duracion_min, "color": r.color, "precio": float(r.precio) if r.precio else None} for r in rows]

@app.get("/api/citas")
def listar_citas(
    desde: Optional[datetime] = None,
    hasta: Optional[datetime] = None,
    estado: Optional[str] = None,
    db: Session = Depends(get_db)
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
def crear_cita(data: CitaIn, db: Session = Depends(get_db)):
    trat = db.get(Tratamiento, data.tratamiento_id)
    if not trat: raise HTTPException(404, "Tratamiento no encontrado")
    fin = data.inicio + timedelta(minutes=trat.duracion_min)
    validar_horario_soldent(data.inicio, fin)
    paciente = db.get(Paciente, data.paciente_id)

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
def actualizar_cita(cid: uuid.UUID, data: CitaUpdateIn, db: Session = Depends(get_db)):
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
            event_body = {"summary": f"Cita: {outbox.payload.get('paciente_nombre', 'Paciente')}", "start": {"dateTime": outbox.payload["inicio"], "timeZone": settings.TZ_CONSULTORIO}, "end": {"dateTime": outbox.payload["fin"], "timeZone": settings.TZ_CONSULTORIO}}
            
            if outbox.accion == "create":
                res = service.events().insert(calendarId=settings.CALENDAR_ID, body=event_body).execute()
                db.execute(text("UPDATE agenda.citas SET google_event_id=:gid WHERE id=:cid"), {"gid": res["id"], "cid": outbox.entidad_id})
                outbox.estado, outbox.procesado_en = "completado", ahora
            elif outbox.accion == "update" and event_id:
                service.events().update(calendarId=settings.CALENDAR_ID, eventId=event_id, body=event_body).execute()
                outbox.estado, outbox.procesado_en = "completado", ahora
            elif outbox.accion == "delete" and event_id:
                service.events().delete(calendarId=settings.CALENDAR_ID, eventId=event_id).execute()
                outbox.estado, outbox.procesado_en = "completado", ahora
            db.commit()
        except Exception as e:
            outbox.intentos += 1; outbox.ultimo_error = str(e)
            if outbox.intentos >= outbox.max_intentos:
                outbox.estado, outbox.procesado_en = "fallido", ahora
            else:
                outbox.proximo_intento = ahora + timedelta(minutes=2 ** outbox.intentos)
            db.commit()

def worker_recordatorios(db: Session):
    ahora = datetime.now(timezone.utc)
    # Detecta citas que inicien en la ventana de 175 a 185 minutos (3 horas) y sin recordatorio previo
    rows = db.execute(
        select(Cita, Paciente)
        .join(Paciente, Cita.paciente_id == Paciente.id)
        .where(
            Cita.estado.in_(["pendiente", "confirmada"]),
            Cita.recordatorio_enviado == False,
            Cita.inicio >= ahora + timedelta(minutes=settings.RECORDATORIO_MIN),
            Cita.inicio <= ahora + timedelta(minutes=settings.RECORDATORIO_MAX)
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
            tz_bol = ZoneInfo(settings.TZ_CONSULTORIO)
            dt_bol = cita.inicio.astimezone(tz_bol) if cita.inicio.tzinfo else cita.inicio.replace(tzinfo=timezone.utc).astimezone(tz_bol)
            hora_str = dt_bol.strftime("%H:%M")
            link = f"{settings.PUBLIC_BASE_URL}/r/{token}"
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
                    "http://localhost:8080/send-message",
                    json={"number": paciente.telefono, "text": mensaje},
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