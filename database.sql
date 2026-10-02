-- =============================================================
-- ESQUEMA DEDICADO: agenda
-- Aísla completamente las tablas de esta app dentro de la misma BD
-- =============================================================
CREATE SCHEMA IF NOT EXISTS agenda;

-- Asegurar que las extensiones estén en schema 'extensions' o 'public'
CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA extensions;

-- Establecer el search_path para esta sesión de migración
SET search_path TO agenda, public, extensions;

-- 1. Pacientes
CREATE TABLE IF NOT EXISTS pacientes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre TEXT NOT NULL,
    apellidos TEXT,
    telefono TEXT UNIQUE NOT NULL,
    email TEXT,
    fecha_nacimiento DATE,
    alertas_medicas JSONB DEFAULT '{}',
    notas TEXT,
    activo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pacientes_telefono ON pacientes(telefono);

-- 2. Tratamientos
CREATE TABLE IF NOT EXISTS tratamientos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre TEXT NOT NULL,
    duracion_min INTEGER NOT NULL,
    color TEXT DEFAULT '#3B82F6',
    precio NUMERIC(10, 2),
    activo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tratamientos_nombre ON tratamientos(nombre);

-- Catálogo oficial de tratamientos de Soldent
INSERT INTO tratamientos (nombre, duracion_min, precio, color, activo) VALUES
('Consulta y Diagnóstico', 30, 100.00, '#3B82F6', TRUE),
('Limpieza y Profilaxis', 45, 150.00, '#10B981', TRUE),
('Curación / Resina', 45, 180.00, '#F59E0B', TRUE),
('Extracción Simple', 45, 200.00, '#EF4444', TRUE),
('Endodoncia (Tratamiento de Conducto)', 90, 600.00, '#8B5CF6', TRUE),
('Blanqueamiento Dental', 60, 500.00, '#06B6D4', TRUE)
ON CONFLICT (nombre) DO UPDATE SET
    duracion_min = EXCLUDED.duracion_min,
    precio = EXCLUDED.precio,
    color = EXCLUDED.color,
    activo = EXCLUDED.activo;

-- 3. Citas (Con Optimistic Locking y Prevención de Traslapes)
CREATE TABLE IF NOT EXISTS citas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paciente_id UUID NOT NULL REFERENCES pacientes(id) ON DELETE CASCADE,
    tratamiento_id UUID NOT NULL REFERENCES tratamientos(id) ON DELETE RESTRICT,
    inicio TIMESTAMPTZ NOT NULL,
    fin TIMESTAMPTZ NOT NULL,
    estado TEXT DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'confirmada', 'cancelada', 'atendida', 'no_asistio')),
    motivo TEXT,
    notas TEXT,
    google_event_id TEXT,
    token_respuesta_hash TEXT,
    token_recordatorio_hash TEXT,
    token_expira_en TIMESTAMPTZ,
    version INTEGER DEFAULT 1 NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Restricción EXCLUDE para evitar que un paciente tenga dos citas activas al mismo tiempo
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'no_traslape_citas'
    ) THEN
        ALTER TABLE citas ADD CONSTRAINT no_traslape_citas
        EXCLUDE USING gist (
            paciente_id WITH =,
            tstzrange(inicio, fin) WITH &&
        ) WHERE (estado NOT IN ('cancelada', 'no_asistio'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_citas_inicio ON citas(inicio);
CREATE INDEX IF NOT EXISTS idx_citas_google_id ON citas(google_event_id);

-- 4. Sync Outbox (Patrón Outbox)
CREATE TABLE IF NOT EXISTS sync_outbox (
    id BIGSERIAL PRIMARY KEY,
    entidad TEXT DEFAULT 'cita',
    entidad_id UUID NOT NULL,
    accion TEXT NOT NULL CHECK (accion IN ('create', 'update', 'delete')),
    payload JSONB DEFAULT '{}',
    intentos INTEGER DEFAULT 0,
    max_intentos INTEGER DEFAULT 5,
    proximo_intento TIMESTAMPTZ DEFAULT NOW(),
    estado TEXT DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'completado', 'fallido')),
    ultimo_error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    procesado_en TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_sync_outbox_pendiente ON sync_outbox(estado, proximo_intento);

-- 5. Notificaciones Enviadas (Idempotencia)
CREATE TABLE IF NOT EXISTS notificaciones_enviadas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cita_id UUID NOT NULL REFERENCES citas(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL CHECK (tipo IN ('recordatorio', 'confirmacion', 'cancelacion')),
    destino TEXT NOT NULL,
    estado TEXT DEFAULT 'pendiente',
    intentos INTEGER DEFAULT 0,
    error TEXT,
    enviado_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(cita_id, tipo)
);

-- 6. Auditoría
CREATE TABLE IF NOT EXISTS auditoria_citas (
    id BIGSERIAL PRIMARY KEY,
    cita_id UUID NOT NULL,
    actor TEXT NOT NULL,
    accion TEXT NOT NULL,
    antes JSONB,
    despues JSONB,
    creado_en TIMESTAMPTZ DEFAULT NOW()
);

-- Trigger para updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_pacientes_updated_at ON pacientes;
CREATE TRIGGER update_pacientes_updated_at BEFORE UPDATE ON pacientes FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_citas_updated_at ON citas;
CREATE TRIGGER update_citas_updated_at BEFORE UPDATE ON citas FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();