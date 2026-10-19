import os
import sys
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)

from database import engine
from sqlalchemy import text

SQL_TRIGGER = """
CREATE OR REPLACE FUNCTION agenda.check_cita_overlap()
RETURNS TRIGGER AS $func$
BEGIN
    -- Si es UPDATE y las fechas de inicio y fin no cambiaron, no validar solapamiento (ej. actualizar token, estado, notas)
    IF TG_OP = 'UPDATE' AND OLD.inicio = NEW.inicio AND OLD.fin = NEW.fin THEN
        RETURN NEW;
    END IF;

    IF NEW.estado NOT IN ('cancelada', 'no_asistio') THEN
        IF EXISTS (
            SELECT 1 FROM agenda.citas
            WHERE id != NEW.id
              AND estado NOT IN ('cancelada', 'no_asistio')
              AND tstzrange(inicio, fin, '[)') && tstzrange(NEW.inicio, NEW.fin, '[)')
        ) THEN
            RAISE EXCEPTION 'Colision detectada: El horario solicitado ya esta ocupado por otra cita en el consultorio.'
                USING ERRCODE = '23P01';
        END IF;
    END IF;
    RETURN NEW;
END;
$func$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_check_cita_overlap ON agenda.citas;

CREATE TRIGGER trg_check_cita_overlap
BEFORE INSERT OR UPDATE ON agenda.citas
FOR EACH ROW EXECUTE FUNCTION agenda.check_cita_overlap();
"""

def main():
    print("Creando trigger de bloqueo concurrente en PostgreSQL...")
    with engine.connect() as conn:
        conn.execute(text(SQL_TRIGGER))
        conn.commit()
    print("✅ [EXITO] Trigger de concurrencia trg_check_cita_overlap creado correctamente en agenda.citas.")

if __name__ == '__main__':
    main()
