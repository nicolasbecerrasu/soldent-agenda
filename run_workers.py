"""
Soldent Background Workers Runner con Monitoreo de Heartbeat y Sanitización
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
import json
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
    sanitizar_error,
    SAFE_ERROR_CATALOG
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

# 1. Política estricta por worker con correspondencia 1-a-1 real comprobada
# NOTA DE ARQUITECTURA:
# - 'render_keepalive' actúa como sondeo de respaldo preventivo hacia la instancia secundaria/standby en Render,
#   evitando que entre en suspensión fría en caso de contingencia o conmutación por error. El servidor primario de
#   producción reside de forma nativa en la máquina virtual Oracle Cloud (146.181.38.79) bajo systemd.
# - 'worker_control_mensual_ortodoncia' se ejecuta cada 10 ciclos de worker (ciclo % 10 == 0), lo que representa
#   un intervalo empírico de ~600 a 750 segundos según la latencia de la red. La tolerancia se establece en 1800s (30m)
#   para permitir hasta 2-3 ciclos sin generar falsos positivos de indisponibilidad durante operaciones normales.
WORKER_POLICIES = {
    "worker_sync_outbox": {"intervalo_seg": 60, "tolerancia_seg": 180},
    "worker_recordatorios": {"intervalo_seg": 60, "tolerancia_seg": 180},
    "worker_resumen_turnos_doctora": {"intervalo_seg": 60, "tolerancia_seg": 180},
    "worker_sync_inverso_google": {"intervalo_seg": 120, "tolerancia_seg": 360},
    "worker_control_mensual_ortodoncia": {"intervalo_seg": 750, "tolerancia_seg": 1800},
    "vigilar_conexion_whatsapp": {"intervalo_seg": 60, "tolerancia_seg": 180},
    "render_keepalive": {"intervalo_seg": 420, "tolerancia_seg": 1200},
}

def registrar_heartbeat(db, worker_name: str, error: Exception = None, meta: dict = None):
    """Registra la última ejecución y estado de salud de cada worker en Supabase."""
    try:
        # Asegurar que cualquier transacción fallida previa se limpie antes de consultar/guardar
        try:
            db.rollback()
        except Exception:
            pass
        ahora = datetime.now(timezone.utc)
        hb = db.query(WorkerHeartbeat).filter(WorkerHeartbeat.worker_name == worker_name).first()
        err_data = json.dumps(sanitizar_error(error)) if error else None
        if not hb:
            hb = WorkerHeartbeat(
                worker_name=worker_name,
                last_heartbeat=ahora,
                last_success=ahora if not error else None,
                last_error=err_data,
                meta=meta or {}
            )
            db.add(hb)
        else:
            hb.last_heartbeat = ahora
            if error:
                hb.last_error = err_data
                # IMPORTANTE: last_success se mantiene intacto si hay error
            else:
                hb.last_success = ahora
                hb.last_error = None
            if meta:
                hb.meta = meta
        db.commit()
    except Exception as e_hb:
        try:
            db.rollback()
        except Exception as e_rb:
            logger.warning(f"Fallo adicional al ejecutar rollback tras error en heartbeat de {worker_name}: {sanitizar_error(e_rb)['message']}")
        logger.warning(f"No se pudo registrar heartbeat de {worker_name}: {sanitizar_error(e_hb)['message']}")

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
                        timeout_keepalive = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)
                        async with httpx.AsyncClient(timeout=timeout_keepalive) as client_keepalive:
                            r_ping = await client_keepalive.get("https://soldent-agenda.onrender.com/api/salud")
                            if r_ping.status_code == 200:
                                logger.info("⚡ [Render Keep-Alive] Ping enviado con éxito (Servidor 24/7 activo)")
                                registrar_heartbeat(db, "render_keepalive", meta={"status_code": r_ping.status_code})
                    except Exception as err_ping:
                        safe_msg = sanitizar_error(err_ping)['message']
                        logger.warning(f"⚠️ [Render Keep-Alive]: {safe_msg}")
                        registrar_heartbeat(db, "render_keepalive", error=err_ping)

                # 1. Procesar Outbox (Citas locales pendientes -> Google Calendar)
                try:
                    worker_sync_outbox(db)
                    registrar_heartbeat(db, "worker_sync_outbox")
                except Exception as e_outbox:
                    try: db.rollback()
                    except Exception: pass
                    safe_msg = sanitizar_error(e_outbox)['message']
                    logger.error(f"Error en worker_sync_outbox: {safe_msg}")
                    registrar_heartbeat(db, "worker_sync_outbox", error=e_outbox)

                # 2. Recordatorios a pacientes (1 hora antes)
                try:
                    worker_recordatorios(db)
                    registrar_heartbeat(db, "worker_recordatorios")
                except Exception as e_rec:
                    try: db.rollback()
                    except Exception: pass
                    safe_msg = sanitizar_error(e_rec)['message']
                    logger.error(f"Error en worker_recordatorios: {safe_msg}")
                    registrar_heartbeat(db, "worker_recordatorios", error=e_rec)

                # 3. Resumen de citas a la Dra. Pamela (20 min antes del turno)
                try:
                    worker_resumen_turnos_doctora(db)
                    registrar_heartbeat(db, "worker_resumen_turnos_doctora")
                except Exception as e_dra:
                    try: db.rollback()
                    except Exception: pass
                    safe_msg = sanitizar_error(e_dra)['message']
                    logger.error(f"Error en worker_resumen_turnos_doctora: {safe_msg}")
                    registrar_heartbeat(db, "worker_resumen_turnos_doctora", error=e_dra)

                # 4. Sincronización Inversa (Google Calendar / iPhone -> BD)
                if ciclo % 2 == 0:
                    try:
                        worker_sync_inverso_google(db)
                        registrar_heartbeat(db, "worker_sync_inverso_google")
                    except Exception as e_inv:
                        try: db.rollback()
                        except Exception: pass
                        safe_msg = sanitizar_error(e_inv)['message']
                        logger.error(f"Error en worker_sync_inverso_google: {safe_msg}")
                        registrar_heartbeat(db, "worker_sync_inverso_google", error=e_inv)

                # 5. Control Mensual de Ortodoncia
                if ciclo % 10 == 0:
                    try:
                        worker_control_mensual_ortodoncia(db)
                        registrar_heartbeat(db, "worker_control_mensual_ortodoncia")
                    except Exception as e_ort:
                        try: db.rollback()
                        except Exception: pass
                        safe_msg = sanitizar_error(e_ort)['message']
                        logger.error(f"Error en worker_control_mensual_ortodoncia: {safe_msg}")
                        registrar_heartbeat(db, "worker_control_mensual_ortodoncia", error=e_ort)

                # 6. Vigilancia de conexión de WhatsApp
                try:
                    await vigilar_conexion_whatsapp()
                    registrar_heartbeat(db, "vigilar_conexion_whatsapp")
                except Exception as err_mon:
                    try: db.rollback()
                    except Exception: pass
                    safe_msg = sanitizar_error(err_mon)['message']
                    logger.warning(f"⚠️ [Alertas Error]: {safe_msg}")
                    registrar_heartbeat(db, "vigilar_conexion_whatsapp", error=err_mon)

                ciclo += 1

            finally:
                db.close()

        except Exception as e:
            safe_msg = sanitizar_error(e)['message']
            logger.critical(f"Excepción en el ciclo de workers: {safe_msg}")

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
