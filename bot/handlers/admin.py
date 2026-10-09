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
1. CITAS DEL TURNO MAÑANA DE MAÑANA (ej. 09:00, 09:30): El recordatorio por WhatsApp está programado para enviarse hoy de forma 100% automática a las 8:30 PM (20:30) a todos los pacientes de la Dra. Pamela de ese turno (como Paul y Victoria Ugarte).
2. CITAS DEL TURNO TARDE: Se envían durante el día de la cita con anticipación estándar de 4 horas.
3. SI NICOLÁS PREGUNTA POR RECORDATORIOS: Explícale con total claridad y seguridad que el cron worker automático está activo y que los recordatorios para las citas del turno mañana de mañana se dispararán automáticamente a las 8:30 PM (20:30). NUNCA le digas que hay un fallo porque el contador esté en 0 antes de esa hora, ni le ofrezcas dispararlo de forma manual a menos que él explícitamente lo exija.
4. Sé cordial, claro, técnico cuando corresponda, usando emojis apropiados y formato WhatsApp impecable.
5. REGLA ANTI-INVENCIÓN: NO tienes acceso a los logs del servidor ni a stack traces. Si Nicolás pregunta por qué se cayó/desconectó el bot o por cualquier fallo técnico, NUNCA inventes causas (pool TCP, garbage collection, etc.). Di con honestidad que no tienes acceso a los registros del servidor y que debe revisarlos (journalctl en Oracle) o pedírselo al asistente de desarrollo. Solo puedes afirmar lo que está en las métricas de arriba.
"""

    respuesta = llamar_gemini_http(prompt_sistema, historial)
    if not respuesta:
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
            f"ℹ️ *Recordatorios del Turno Mañana:* Se enviarán automáticamente hoy a las 8:30 PM (20:30) para todos los pacientes matutinos. ✨"
        )

    historial.append({"role": "model", "text": respuesta})
    return respuesta

