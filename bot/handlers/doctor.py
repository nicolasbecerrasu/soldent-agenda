import re
import httpx
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from config import settings
from services.gemini_ai import llamar_gemini_http, safe_print
from services.booking_tools import crear_cita, BOT_HEADERS
from bot.state import historial_sesiones

def obtener_datos_completos_agenda_doctora() -> tuple[str, str]:
    """Obtiene la agenda estructurada y calcula los horarios libres de los próximos 7 días para la doctora."""
    tz_bol = ZoneInfo(settings.TZ_CONSULTORIO)
    ahora_bol = datetime.now(tz_bol)
    hoy = ahora_bol.date()

    citas_raw = []
    try:
        r = httpx.get(f"{settings.API_BACKEND_URL}/api/citas", headers=BOT_HEADERS, timeout=6.0)
        if r.status_code == 200:
            citas_raw = r.json()
    except Exception as e:
        safe_print(f"[Agenda Doctora Backend Error]: {e}")

    dias_esp = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    resumen_citas_por_dia = {}
    citas_por_dia_times = {}

    for i in range(7):
        d_target = hoy + timedelta(days=i)
        resumen_citas_por_dia[d_target] = []
        citas_por_dia_times[d_target] = []

    for c in citas_raw:
        if (c.get("estado") or "").lower() in ("pendiente", "confirmada"):
            ini_str = c.get("inicio", "")
            fin_str = c.get("fin", "")
            if ini_str and fin_str:
                ini_dt = datetime.fromisoformat(ini_str.replace("Z", "+00:00")).astimezone(tz_bol)
                fin_dt = datetime.fromisoformat(fin_str.replace("Z", "+00:00")).astimezone(tz_bol)
                d_cita = ini_dt.date()
                if d_cita in resumen_citas_por_dia:
                    pac_obj = c.get("paciente") or {}
                    pac_nom = pac_obj.get("nombre") or c.get("paciente_nombre") or "Paciente"
                    pac_tel = pac_obj.get("telefono") or "Sin cel"
                    estado_str = "✅ Confirmada" if (c.get("estado") or "").lower() == "confirmada" else "⏳ Pendiente"
                    h_ini = ini_dt.strftime("%H:%M")
                    h_fin = fin_dt.strftime("%H:%M")
                    notas = f" (Nota: {c.get('notas')})" if c.get("notas") else ""
                    resumen_citas_por_dia[d_cita].append(
                        f"• {h_ini} - {h_fin}: {pac_nom} (Tel: {pac_tel}) [{estado_str}]{notas}"
                    )
                    citas_por_dia_times[d_cita].append((ini_dt.time(), fin_dt.time()))

    # Armar texto de citas
    lineas_citas = []
    for d_target, lista in resumen_citas_por_dia.items():
        nom_d = dias_esp[d_target.weekday()]
        f_str = d_target.strftime("%d/%m")
        etiqueta = "HOY" if d_target == hoy else ("MAÑANA" if d_target == hoy + timedelta(days=1) else nom_d)
        if not lista:
            lineas_citas.append(f"📅 {etiqueta} ({nom_d} {f_str}): Sin citas registradas.")
        else:
            lineas_citas.append(f"📅 {etiqueta} ({nom_d} {f_str}):\n" + "\n".join(lista))

    texto_citas = "\n\n".join(lineas_citas)

    # Armar texto de horarios libres listos para enviar a pacientes
    lineas_libres = []
    for d_target, lista_times in citas_por_dia_times.items():
        nom_d = dias_esp[d_target.weekday()]
        f_str = d_target.strftime("%d/%m")
        etiqueta = "HOY" if d_target == hoy else ("MAÑANA" if d_target == hoy + timedelta(days=1) else nom_d)

        weekday = d_target.weekday()
        if weekday == 6:
            lineas_libres.append(f"📅 {etiqueta} ({nom_d} {f_str}): Domingo cerrado todo el día.")
            continue

        lista_times.sort(key=lambda x: x[0])
        turnos = [(time(9, 0), time(12, 0))]
        if weekday <= 4:
            turnos.append((time(15, 30), time(19, 30)))

        bloques_dia = []
        for t_ini, t_fin in turnos:
            nom_t = "🌅 Turno Mañana (09:00 a 12:00)" if t_ini == time(9, 0) else "🌇 Turno Tarde (15:30 a 19:30)"
            libres_turno = []
            cursor = t_ini
            citas_turno = [c for c in lista_times if c[0] < t_fin and c[1] > t_ini]
            for c_ini, c_fin in citas_turno:
                c_ini_clamp = max(cursor, c_ini)
                if c_ini_clamp > cursor:
                    libres_turno.append(f"• {cursor.strftime('%H:%M')} a {c_ini_clamp.strftime('%H:%M')}")
                cursor = max(cursor, c_fin)
            if cursor < t_fin:
                libres_turno.append(f"• {cursor.strftime('%H:%M')} a {t_fin.strftime('%H:%M')}")

            if libres_turno:
                bloques_dia.append(f"{nom_t}:\n" + "\n".join(libres_turno))
            else:
                bloques_dia.append(f"{nom_t}: (Turno completo ocupado)")

        lineas_libres.append(f"📅 {etiqueta} ({nom_d} {f_str}):\n" + "\n".join(bloques_dia))

    texto_libres = "\n\n".join(lineas_libres)
    return texto_citas, texto_libres

def procesar_mensaje_doctora(remitente: str, texto: str) -> str:
    """Atiende a la Dra. Pamela como su Asistente Personal: citas, horarios libres, datos de pacientes y bloqueos."""
    if remitente not in historial_sesiones:
        historial_sesiones[remitente] = []

    historial = historial_sesiones[remitente]
    historial.append({"role": "user", "text": texto})
    if len(historial) > 10:
        historial = historial[-10:]
        historial_sesiones[remitente] = historial

    texto_citas, texto_libres = obtener_datos_completos_agenda_doctora()

    tz_bol = ZoneInfo(settings.TZ_CONSULTORIO)
    ahora_bol = datetime.now(tz_bol)
    dias_esp = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    dia_actual_nom = dias_esp[ahora_bol.weekday()]
    fecha_actual_legible = f"{dia_actual_nom} {ahora_bol.day}/{ahora_bol.month}/{ahora_bol.year}"
    hora_actual = ahora_bol.strftime("%H:%M")

    prompt_sistema = f"""Eres el Asistente Médico y Administrativo Personal de la Dra. Pamela Pinto Suárez, odontóloga y directora de 'SOLDENT - Soluciones Dentales'.
Estás hablando DIRECTAMENTE con la Dra. Pamela en su WhatsApp privado ({settings.DOCTORA_TELEFONO}).
NUNCA la trates como a un paciente ni le preguntes su nombre o motivo de consulta. Trátala como tu jefa y especialista de la clínica ("Dra. Pamela", "Con todo gusto, doctora").

HORA ACTUAL EN SANTA CRUZ: {fecha_actual_legible}, hora {hora_actual}.

HORARIOS OFICIALES DE SOLDENT:
• Lunes a Viernes: 09:00 a 12:00 y 15:30 a 19:30 (receso de mediodía de 12:00 a 15:30).
• Sábados: 09:00 a 12:00 (tardes cerrado).
• Domingos: Cerrado todo el día.

AGENDA ACTUALIZADA DE CITAS:
{texto_citas}

HORARIOS LIBRES CALCULADOS (Listos para enviar a pacientes):
{texto_libres}

TUS INSTRUCCIONES:
1. SI LA DOCTORA PIDE HORARIOS LIBRES O DISPONIBLES (ej: de hoy, mañana o un día específico):
   Entrégale la lista limpia de horarios disponibles para el día solicitado en un formato listo para copiar y reenviar a su paciente.
   Organízalo en:
   🌅 Turno Mañana (09:00 a 12:00)
   🌇 Turno Tarde (15:30 a 19:30)
   Añade al final: "📋 (Puede copiar este mensaje y reenviarlo directamente a su paciente)".

2. SI LA DOCTORA PREGUNTA POR SUS CITAS O AGENDA (ej: de hoy o mañana):
   Muéstrale los pacientes programados con sus horas, nombres, teléfonos, estado (✅ Confirmada / ⏳ Pendiente) y notas clínicas.

3. SI LA DOCTORA TE PIDE AGENDAR O BLOQUEAR UN HORARIO:
   - Para agendar: confirma amablemente y añade al final de tu mensaje [RESERVAR: Nombre | YYYY-MM-DDTHH:MM:SS]
   - Para bloquear un turno: confirma amablemente y añade al final de tu mensaje [BLOQUEAR: Motivo | YYYY-MM-DDTHH:MM:SS]

4. SI LA DOCTORA PREGUNTA QUIÉNES CONFIRMARON:
   Muéstrale quiénes ya confirmaron asistencia mediante WhatsApp y quiénes siguen pendientes.

5. TONO:
   Extremadamente servicial, rápido, organizado y respetuoso. Formato impecable con emojis moderados.
"""

    respuesta = llamar_gemini_http(prompt_sistema, historial)
    if not respuesta:
        texto_lower = texto.lower()
        if any(w in texto_lower for w in ("libre", "disponib", "espacio", "horario")):
            respuesta = (
                f"Dra. Pamela, estos son los horarios disponibles más próximos en su agenda:\n\n"
                f"{texto_libres[:1200]}\n\n"
                "📋 (Puede copiar este bloque y reenviarlo directamente a su paciente)."
            )
        elif any(w in texto_lower for w in ("cita", "agenda", "paciente", "quien", "programad")):
            respuesta = (
                f"Dra. Pamela, este es el detalle de sus citas registradas:\n\n"
                f"{texto_citas[:1200]}"
            )
        else:
            respuesta = (
                "Con todo gusto, Dra. Pamela. Estoy a su servicio. Puede consultarme:\n"
                "• '¿Qué citas tengo hoy (o mañana)?'\n"
                "• 'Horarios libres de mañana para pasarle a un paciente'\n"
                "• '¿Quiénes ya confirmaron para hoy?'\n"
                "• 'Agéndame a [Nombre] el [Día] a las [Hora]'\n"
                "• 'Bloquea el [Día] de [Hora] a [Hora] por cirugía/personal'"
            )

    # Si se solicitó reserva o bloqueo
    m_res = re.search(r"\[RESERVAR:\s*([^\|\]]+)\|\s*([^\]]+)\]", respuesta)
    if m_res:
        nom_c = m_res.group(1).strip()
        f_c = m_res.group(2).strip()
        crear_cita(nom_c, settings.DOCTORA_TELEFONO, f_c)

    m_bloq = re.search(r"\[BLOQUEAR:\s*([^\|\]]+)\|\s*([^\]]+)\]", respuesta)
    if m_bloq:
        motivo_b = m_bloq.group(1).strip()
        f_b = m_bloq.group(2).strip()
        crear_cita(f"BLOQUEADO: {motivo_b}", settings.DOCTORA_TELEFONO, f_b)

    respuesta_limpia = re.sub(r"\[RESERVAR:[^\]]*\]", "", respuesta)
    respuesta_limpia = re.sub(r"\[BLOQUEAR:[^\]]*\]", "", respuesta_limpia).strip()

    historial.append({"role": "model", "text": respuesta_limpia})
    return respuesta_limpia
