from datetime import datetime, timezone, timedelta, time
from zoneinfo import ZoneInfo
from database import SessionLocal, Paciente, Cita, NotificacionEnviada
from config import settings
from services.gemini_ai import llamar_gemini_http, safe_print
from bot.state import historial_sesiones

def obtener_metricas_administrador() -> dict:
    """Calcula las métricas operativas en tiempo real de la base de datos para Nicolás."""
    tz_bol = ZoneInfo(settings.TZ_CONSULTORIO)
    ahora_bol = datetime.now(tz_bol)
    hoy = ahora_bol.date()
    manana = hoy + timedelta(days=1)

    total_pacientes = 0
    citas_hoy = []
    citas_manana = []
    confirmados_hoy = 0
    recordatorios_hoy = 0

    db = SessionLocal()
    try:
        total_pacientes = db.query(Paciente).filter(Paciente.activo == True).count()

        inicio_hoy_utc = datetime(hoy.year, hoy.month, hoy.day, 0, 0, 0, tzinfo=tz_bol).astimezone(timezone.utc)
        fin_hoy_utc = datetime(hoy.year, hoy.month, hoy.day, 23, 59, 59, tzinfo=tz_bol).astimezone(timezone.utc)

        inicio_manana_utc = datetime(manana.year, manana.month, manana.day, 0, 0, 0, tzinfo=tz_bol).astimezone(timezone.utc)
        fin_manana_utc = datetime(manana.year, manana.month, manana.day, 23, 59, 59, tzinfo=tz_bol).astimezone(timezone.utc)

        # Citas para hoy
        citas_hoy_rows = db.query(Cita, Paciente).join(Paciente, Cita.paciente_id == Paciente.id).filter(
            Cita.inicio >= inicio_hoy_utc,
            Cita.inicio <= fin_hoy_utc,
            Cita.estado != 'cancelada'
        ).order_by(Cita.inicio).all()

        for c, p in citas_hoy_rows:
            h_ini = c.inicio.astimezone(tz_bol).strftime("%H:%M")
            estado = "✅ Confirmada" if (c.estado or "").lower() == "confirmada" else "⏳ Pendiente"
            if (c.estado or "").lower() == "confirmada":
                confirmados_hoy += 1
            citas_hoy.append(f"• {h_ini}: {p.nombre} ({estado})")

        # Citas para mañana (clasificadas por turno)
        citas_manana_rows = db.query(Cita, Paciente).join(Paciente, Cita.paciente_id == Paciente.id).filter(
            Cita.inicio >= inicio_manana_utc,
            Cita.inicio <= fin_manana_utc,
            Cita.estado != 'cancelada'
        ).order_by(Cita.inicio).all()

        citas_manana_turno_manana = []
        citas_manana_turno_tarde = []

        for c, p in citas_manana_rows:
            dt_ini_bol = c.inicio.astimezone(tz_bol)
            h_ini = dt_ini_bol.strftime("%H:%M")
            estado = "✅ Confirmada" if (c.estado or "").lower() == "confirmada" else "⏳ Pendiente"
            linea_c = f"• {h_ini}: {p.nombre} ({estado})"
            citas_manana.append(linea_c)
            if dt_ini_bol.time() <= time(12, 30):
                citas_manana_turno_manana.append(linea_c)
            else:
                citas_manana_turno_tarde.append(linea_c)

        # Recordatorios automáticos enviados hoy
        recordatorios_hoy = db.query(NotificacionEnviada).filter(
            NotificacionEnviada.tipo == 'recordatorio',
            NotificacionEnviada.estado == 'enviado',
            NotificacionEnviada.enviado_at >= inicio_hoy_utc
        ).count()

    except Exception as e:
        safe_print(f"[Error Metricas Admin]: {e}")
    finally:
        db.close()

    return {
        "total_pacientes": total_pacientes,
        "citas_hoy": citas_hoy,
        "citas_manana": citas_manana,
        "citas_manana_turno_manana": citas_manana_turno_manana,
        "citas_manana_turno_tarde": citas_manana_turno_tarde,
        "confirmados_hoy": confirmados_hoy,
        "recordatorios_hoy": recordatorios_hoy,
        "fecha_hoy": hoy.strftime("%d/%m/%Y"),
        "hora": ahora_bol.strftime("%H:%M")
    }

def procesar_mensaje_administrador(remitente: str, texto: str) -> str:
    """Atiende consultas del Administrador Nicolás (+591 70277520) con métricas y estado del sistema."""
    m = obtener_metricas_administrador()

    if remitente not in historial_sesiones:
        historial_sesiones[remitente] = []
    historial = historial_sesiones[remitente]
    historial.append({"role": "user", "text": texto})

    prompt_sistema = f"""Eres el Asistente Técnico y Administrativo de SOLDENT.
Estás hablando directamente con NICOLÁS ({settings.ADMIN_TELEFONO}), el administrador técnico y creador del sistema de la clínica.
NUNCA lo trates como paciente ni le hables de sacar citas médicas para él. Trátalo como a tu colega y administrador ("Hola Nicolás 👨‍💻", "¡Todo en orden!", etc.).

MÉTRICAS EN TIEMPO REAL DEL SISTEMA ({m['fecha_hoy']} a las {m['hora']} hora Santa Cruz):
- Estado del Sistema: 🟢 100% Operativo y conectado a la pasarela de WhatsApp.
- Total de pacientes registrados en la clínica: {m['total_pacientes']} pacientes.
- Citas programadas para HOY: {len(m['citas_hoy'])} citas ({m['confirmados_hoy']} confirmadas, {len(m['citas_hoy']) - m['confirmados_hoy']} pendientes).
  Detalle citas de hoy:
{chr(10).join(m['citas_hoy']) if m['citas_hoy'] else '  (Sin citas programadas para hoy)'}
- Citas programadas para MAÑANA: {len(m['citas_manana'])} citas en total.
  • Turno Mañana de Mañana (09:00 a 12:00) -> {len(m['citas_manana_turno_manana'])} citas:
{chr(10).join(m['citas_manana_turno_manana']) if m['citas_manana_turno_manana'] else '    (Sin citas en la mañana)'}
  • Turno Tarde de Mañana (15:30 a 19:30) -> {len(m['citas_manana_turno_tarde'])} citas:
{chr(10).join(m['citas_manana_turno_tarde']) if m['citas_manana_turno_tarde'] else '    (Sin citas en la tarde)'}
- Recordatorios automáticos de WhatsApp enviados hoy: {m['recordatorios_hoy']} mensajes enviados a pacientes.
- Sincronización Google Calendar: Sincronización bidireccional activa.

REGLAS OFICIALES DE RECORDATORIOS AUTOMÁTICOS DE SOLDENT:
1. CITAS DEL TURNO MAÑANA DE MAÑANA (ej. 09:00, 09:30, 10:00): El recordatorio por WhatsApp está programado para enviarse hoy de forma 100% automática a las 8:30 PM (20:30) a todos los pacientes matutinos de la Dra. Pamela.
2. BLOQUEO ESTRICTO DE MADRUGADA: De 22:00 a 07:29 el bot tiene PROHIBIDO enviar recordatorios automáticos para no molestar a los pacientes mientras duermen.
3. RESCATE DE LAS 07:30 AM: A las 07:30 AM en punto, el bot revisa si alguna cita de la mañana no recibió aviso anoche y se la envía de inmediato.
4. CITAS DE MEDIA MAÑANA Y TARDE: Se envían durante el día exactamente con 3 HORAS DE ANTICIPACIÓN (ej. cita 15:30 -> envío 12:30; cita 16:00 -> envío 13:00).
5. CONTROL MANUAL (EXCEPCIÓN): Si Nicolás pide enviar un recordatorio ahora (ej: "manda recordatorio a Juan", "enviar recordatorios ahora", "disparar recordatorios"), confirma y añade al final de tu mensaje [ENVIAR_RECORDATORIO: Nombre o Cita o TODOS].
6. REGLA ANTI-INVENCIÓN: NO inventes fallas ni causas técnicas. Afirma con seguridad las métricas de arriba.
"""

    respuesta = llamar_gemini_http(prompt_sistema, historial)
    if not respuesta:
        texto_lower = texto.lower()
        if any(w in texto_lower for w in ("manda recordatorio", "mandale recordatorio", "recordatorio a", "enviar recordatorio", "disparar recordatorio")):
            respuesta = f"Entendido Nicolás 👨‍💻, procedo a despachar el recordatorio de inmediato. [ENVIAR_RECORDATORIO: {texto}]"
        else:
            detalle_citas = "\n".join(m['citas_hoy']) if m['citas_hoy'] else "• Ninguna cita programada para hoy."
            detalle_manana = "\n".join(m['citas_manana']) if m['citas_manana'] else "• Ninguna cita programada para mañana."
            respuesta = (
                f"👋 ¡Hola Nicolás! 👨‍💻\n\n"
                f"🟢 *Estado del Sistema:* Todo en orden y 100% operativo.\n"
                f"👥 *Total de Pacientes de la Dra. Pamela:* {m['total_pacientes']} pacientes registrados.\n"
                f"📨 *Recordatorios enviados hoy:* {m['recordatorios_hoy']} recordatorios.\n"
                f"📅 *Citas para Hoy ({m['fecha_hoy']}):* {len(m['citas_hoy'])} citas ({m['confirmados_hoy']} confirmadas).\n"
                f"{detalle_citas}\n\n"
                f"🗓️ *Citas para Mañana:* {len(m['citas_manana'])} citas.\n"
                f"{detalle_manana}\n\n"
                f"ℹ️ *Recordatorios:* Citas de la mañana se envían hoy a las 8:30 PM (20:30); citas de la tarde se envían con 3h de anticipación (cero mensajes en la madrugada). ✨"
            )

    # Interceptar solicitud de envío manual forzado de recordatorio
    texto_rec_confirm = ""
    import re
    m_rec = re.search(r"\[ENVIAR_RECORDATORIO:\s*([^\]]+)\]", respuesta)
    if m_rec:
        filtro_r = m_rec.group(1).strip()
        try:
            from database import SessionLocal
            from workers import worker_recordatorios
            db_rec = SessionLocal()
            try:
                enviados = worker_recordatorios(db_rec, forzar=True, filtro=filtro_r)
                if enviados:
                    detalles = ", ".join([f"{e['paciente']} para su cita de las {e['hora']} ({e['fecha']})" for e in enviados])
                    texto_rec_confirm = f"\n\n📲 *Recordatorio enviado:* Listo Nicolás 👨‍💻, acabo de enviar el recordatorio a {detalles}."
                else:
                    texto_rec_confirm = f"\n\nℹ️ *Aviso:* No se encontraron citas pendientes para '{filtro_r}' o el paciente no tiene teléfono registrado."
            finally:
                db_rec.close()
        except Exception as e_rec:
            safe_print(f"⚠️ [Error Forzar Recordatorio Admin]: {e_rec}")

    respuesta_limpia = re.sub(r"\[ENVIAR_RECORDATORIO:[^\]]*\]", "", respuesta).strip()
    if texto_rec_confirm:
        respuesta_limpia += texto_rec_confirm

    historial.append({"role": "model", "text": respuesta_limpia})
    return respuesta_limpia

