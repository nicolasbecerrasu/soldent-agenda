"""
Script independiente para ser ejecutado por cron cada 1-2 minutos.
Procesa la cola de sincronización y envía recordatorios.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import SessionLocal, worker_sync_outbox, worker_recordatorios, worker_sync_inverso_google

def main():
    db = SessionLocal()
    try:
        print("Ejecutando worker_sync_outbox...")
        worker_sync_outbox(db)
        print("Ejecutando worker_recordatorios...")
        worker_recordatorios(db)
        print("Ejecutando worker_sync_inverso_google...")
        worker_sync_inverso_google(db)
        print("Workers completados exitosamente.")
    except Exception as e:
        print(f"Error en workers: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()

