"""
Soldent Background Workers Runner con Monitoreo de Heartbeat
Ejecuta de forma autónoma y desacoplada las tareas en segundo plano:
- Sincronización Outbox -> Google Calendar
- Recordatorios automáticos de citas a pacientes (1h antes)
- Resumen matutino/vespertino a la Dra. Pamela (20 min antes del turno)
- Sincronización inversa (Google Calendar / iPhone -> Base de Datos)
- Control mensual de ortodoncia
- Vigilancia de salud de la conexión de WhatsApp
- Keep-alive de respaldo en Render
"""

import asyncio
import logging
import signal
import sys
import httpx
from datetime import datetime, timezone
from database import SessionLocal, WorkerHeartbeat
from workers import (
    worker_sync_outbox,
    worker_recordatorios,
    worker_sync_inverso_google,
    worker_resumen_turnos_doctora,
    worker_control_mensual_ortodoncia,
)
from services.alertas import vigilar_conexion_whatsapp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Workers] %(message)s"
)
logger = logging.getLogger("soldent_workers")

running = True

def handle_exit(sig, frame):
    global running
    logger.info("Recibida señal de detención. Cerrando workers ordenadamente...")
    running = False

signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)

def registrar_heartbeat(db, worker_name: str, error: str = None, meta: dict = None):
    """Registra la última ejecución y estado de salud de cada worker en Supabase."""
    try:
        ahora = datetime.now(timezone.utc)
        hb = db.query(WorkerHeartbeat).filter(WorkerHeartbeat.worker_name == worker_name).first()
        if not hb:
            hb = WorkerHeartbeat(
                worker_name=worker_name,
                last_heartbeat=ahora,
                last_success=ahora if not error else None,
                last_error=error,
                meta=meta or {}
            )
            db.add(hb)
        else:
            hb.last_heartbeat = ahora
            if error:
                hb.last_error = error
            else:
                hb.last_success = ahora
                hb.last_error = None
            if meta:
                hb.meta = meta
        db.commit()
    except Exception as e_hb:
        logger.warning(f"No se pudo registrar heartbeat de {worker_name}: {e_hb}")

async def worker_loop():
    logger.info("🚀 Iniciando Soldent Background Workers con Heartbeat Monitor...")
    ciclo = 0

    while running:
        try:
            db = SessionLocal()
            try:
                # 0. Anti-Sleep Render Keep-Alive (cada ~7 minutos)
                if ciclo % 7 == 0:
                    try:
                        async with httpx.AsyncClient(timeout=10.0) as client_keepalive:
                            r_ping = await client_keepalive.get("https://soldent-agenda.onrender.com/api/salud")
                            if r_ping.status_code == 200:
                                logger.info("⚡ [Render Keep-Alive] Ping enviado con éxito (Servidor 24/7 activo)")
                                registrar_heartbeat(db, "render_keepalive", meta={"status_code": r_ping.status_code})
                    except Exception as err_ping:
                        logger.warning(f"⚠️ [Render Keep-Alive]: {err_ping}")
                        registrar_heartbeat(db, "render_keepalive", error=str(err_ping))

                # 1. Procesar Outbox (Citas locales pendientes -> Google Calendar)
                try:
                    worker_sync_outbox(db)
                    registrar_heartbeat(db, "worker_sync_outbox")
                except Exception as e_outbox:
                    logger.error(f"Error en worker_sync_outbox: {e_outbox}")
                    registrar_heartbeat(db, "worker_sync_outbox", error=str(e_outbox))

                # 2. Recordatorios a pacientes (1 hora antes)
                try:
                    worker_recordatorios(db)
                    registrar_heartbeat(db, "worker_recordatorios")
                except Exception as e_rec:
                    logger.error(f"Error en worker_recordatorios: {e_rec}")
                    registrar_heartbeat(db, "worker_recordatorios", error=str(e_rec))

                # 3. Resumen de citas a la Dra. Pamela (20 min antes del turno)
                try:
                    worker_resumen_turnos_doctora(db)
                    registrar_heartbeat(db, "worker_resumen_turnos_doctora")
                except Exception as e_dra:
                    logger.error(f"Error en worker_resumen_turnos_doctora: {e_dra}")
                    registrar_heartbeat(db, "worker_resumen_turnos_doctora", error=str(e_dra))

                # 4. Sincronización Inversa (Google Calendar / iPhone -> BD)
                if ciclo % 2 == 0:
                    try:
                        worker_sync_inverso_google(db)
                        registrar_heartbeat(db, "worker_sync_inverso_google")
                    except Exception as e_inv:
                        logger.error(f"Error en worker_sync_inverso_google: {e_inv}")
                        registrar_heartbeat(db, "worker_sync_inverso_google", error=str(e_inv))

                # 5. Control Mensual de Ortodoncia
                if ciclo % 10 == 0:
                    try:
                        worker_control_mensual_ortodoncia(db)
                        registrar_heartbeat(db, "worker_control_mensual_ortodoncia")
                    except Exception as e_ort:
                        logger.error(f"Error en worker_control_mensual_ortodoncia: {e_ort}")
                        registrar_heartbeat(db, "worker_control_mensual_ortodoncia", error=str(e_ort))

                # 6. Vigilancia de conexión de WhatsApp
                try:
                    await vigilar_conexion_whatsapp()
                    registrar_heartbeat(db, "vigilar_conexion_whatsapp")
                except Exception as err_mon:
                    logger.warning(f"⚠️ [Alertas Error]: {err_mon}")
                    registrar_heartbeat(db, "vigilar_conexion_whatsapp", error=str(err_mon))

                ciclo += 1

            finally:
                db.close()

        except Exception as e:
            logger.critical(f"Excepción en el ciclo de workers: {e}", exc_info=True)

        # Esperar 60 segundos antes del siguiente ciclo comprobando si se solicitó parar
        for _ in range(60):
            if not running:
                break
            await asyncio.sleep(1)

    logger.info("Soldent Background Workers finalizados correctamente.")

if __name__ == "__main__":
    try:
        asyncio.run(worker_loop())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Proceso de workers terminado.")
