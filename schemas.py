import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class PacienteIn(BaseModel):
    nombre: str
    apellidos: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    fecha_nacimiento: Optional[datetime] = None
    alertas_medicas: dict = Field(default_factory=dict)
    notas: Optional[str] = None
    permitir_compartido: Optional[bool] = False

class PacienteUpdateIn(BaseModel):
    nombre: Optional[str] = None
    apellidos: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    notas: Optional[str] = None
    alertas_medicas: Optional[dict] = None
    permitir_compartido: Optional[bool] = False

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
    duracion_min: Optional[int] = None
    estado: Optional[str] = None
    motivo: Optional[str] = None
    notas: Optional[str] = None
    version: int

ESTADOS_VALIDOS = {"pendiente", "confirmada", "cancelada", "atendida", "no_asistio"}

class PinLoginIn(BaseModel):
    pin: str

class PagoIn(BaseModel):
    paciente_id: uuid.UUID
    cita_id: Optional[uuid.UUID] = None
    monto_total: float
    monto_pagado: float
    metodo_pago: str = "efectivo"
    concepto: str
    notas: Optional[str] = None
    fecha_pago: Optional[datetime] = None

class TratamientoIn(BaseModel):
    nombre: str
    duracion_min: int
    color: Optional[str] = "#3B82F6"
    precio: Optional[float] = 0.0

class SessionItemIn(BaseModel):
    key: str
    value: str

class SessionBatchIn(BaseModel):
    items: dict[str, str]
