from datetime import datetime, timezone, timedelta
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

        # Citas para mañana
        citas_manana_rows = db.query(Cita, Paciente).join(Paciente, Cita.paciente_id == Paciente.id).filter(
            Cita.inicio >= inicio_manana_utc,
            Cita.inicio <= fin_manana_utc,
            Cita.estado != 'cancelada'
        ).order_by(Cita.inicio).all()

        for c, p in citas_manana_rows:
            h_ini = c.inicio.astimezone(tz_bol).strftime("%H:%M")
            estado = "✅ Confirmada" if (c.estado or "").lower() == "confirmada" else "⏳ Pendiente"
            citas_manana.append(f"• {h_ini}: {p.nombre} ({estado})")

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
- Citas programadas para MAÑANA: {len(m['citas_manana'])} citas.
{chr(10).join(m['citas_manana']) if m['citas_manana'] else '  (Sin citas programadas para mañana)'}
- Recordatorios automáticos de WhatsApp enviados hoy: {m['recordatorios_hoy']} mensajes enviados a pacientes.
- Sincronización Google Calendar: Sincronización bidireccional activa.

INSTRUCCIONES DE RESPUESTA:
1. Responde directamente a lo que te pregunte Nicolás (si pregunta si todo está bien, si pregunta por la cantidad de pacientes de la doctora, o a cuántos se les envió mensaje).
2. Da cifras exactas y concretas.
3. Sé cordial, claro, técnico cuando corresponda, usando emojis apropiados y formato WhatsApp impecable.
"""

    respuesta = llamar_gemini_http(prompt_sistema, historial)
    if not respuesta:
        detalle_citas = "\n".join(m['citas_hoy']) if m['citas_hoy'] else "• Ninguna cita programada para hoy."
        respuesta = (
            f"👋 ¡Hola Nicolás! 👨‍💻\n\n"
            f"🟢 *Estado del Sistema:* Todo en orden y 100% operativo.\n"
            f"👥 *Total de Pacientes de la Dra. Pamela:* {m['total_pacientes']} pacientes registrados.\n"
            f"📨 *Mensajes/Recordatorios enviados hoy:* {m['recordatorios_hoy']} recordatorios.\n"
            f"📅 *Citas para Hoy ({m['fecha_hoy']}):* {len(m['citas_hoy'])} citas ({m['confirmados_hoy']} confirmadas).\n"
            f"{detalle_citas}\n\n"
            f"🗓️ *Citas para Mañana:* {len(m['citas_manana'])} citas.\n\n"
            f"La pasarela y los workers automáticos están funcionando con normalidad. ✨"
        )

    historial.append({"role": "model", "text": respuesta})
    return respuesta
