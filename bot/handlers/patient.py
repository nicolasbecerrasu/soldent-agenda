import re
import httpx
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from config import settings, MENSAJE_OFICIAL_DEFAULT
from database import SessionLocal, Cita, Paciente
from services.gemini_ai import llamar_gemini_http, safe_print
from services.booking_tools import crear_cita
from bot.state import historial_sesiones

def actualizar_estado_cita_paciente(tel_paciente: str, nuevo_estado: str) -> dict:
    """Actualiza la cita más próxima del paciente a 'confirmada' o 'cancelada' y devuelve sus datos con control de idempotencia."""
    tz_bol = ZoneInfo(settings.TZ_CONSULTORIO)
    ahora = datetime.now(tz_bol)
    tel_limpio = re.sub(r"\D", "", str(tel_paciente or ""))
    tel_8 = tel_limpio[-8:] if len(tel_limpio) >= 8 else tel_limpio

    try:
        db = SessionLocal()
        try:
            rows = db.query(Cita, Paciente).join(Paciente, Cita.paciente_id == Paciente.id).filter(
                Cita.estado.in_(["pendiente", "confirmada"])
            ).order_by(Cita.inicio.asc()).all()

            candidatas = []
            for cita, pac in rows:
                c_ini = cita.inicio.astimezone(tz_bol) if cita.inicio.tzinfo else cita.inicio.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz_bol)
                # Solo citas futuras o que empezaron hace menos de 2 horas
                if c_ini < ahora - timedelta(hours=2):
                    continue

                pac_tel_clean = re.sub(r"\D", "", str(pac.telefono or ""))
                pac_tel_8 = pac_tel_clean[-8:] if len(pac_tel_clean) >= 8 else pac_tel_clean

                if (pac_tel_clean and len(pac_tel_clean) >= 7 and tel_8 and 
                    (tel_8 == pac_tel_8 or tel_8 in pac_tel_clean or pac_tel_8 in tel_limpio)):
                    candidatas.append((cita, pac, c_ini))

            if not candidatas:
                return {}

            # Prioridad: buscar cita que esté en estado 'pendiente'
            cita_elegida = None
            pac_elegido = None
            c_ini_elegido = None

            for c, p, c_ini in candidatas:
                if c.estado == "pendiente":
                    cita_elegida = c
                    pac_elegido = p
                    c_ini_elegido = c_ini
                    break

            # Si no hay pendientes, tomar la primera existente (ej. ya confirmada)
            if not cita_elegida:
                cita_elegida, pac_elegido, c_ini_elegido = candidatas[0]

            estado_anterior = cita_elegida.estado
            ya_estaba_confirmada = (estado_anterior == "confirmada" and nuevo_estado == "confirmada")

            if cita_elegida.estado != nuevo_estado:
                cita_elegida.estado = nuevo_estado
                cita_elegida.updated_at = datetime.now(ZoneInfo("UTC"))
                db.commit()

            dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
            d_nom = dias[c_ini_elegido.weekday()]
            return {
                "paciente_nombre": pac_elegido.nombre,
                "fecha": f"{d_nom} {c_ini_elegido.day:02d}/{c_ini_elegido.month:02d}",
                "hora": c_ini_elegido.strftime("%H:%M"),
                "estado_anterior": estado_anterior,
                "ya_estaba_confirmada": ya_estaba_confirmada,
                "cita_id": str(cita_elegida.id)
            }
        finally:
            db.close()
    except Exception as e:
        safe_print(f"[Error Actualizar Estado Cita Paciente]: {e}")
    return {}


def construir_prompt_sistema(tel_paciente: str) -> str:
    tz_bolivia = ZoneInfo(settings.TZ_CONSULTORIO)
    ahora = datetime.now(tz_bolivia)
    dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    dia_nombre = dias[ahora.weekday()]
    fecha_actual_legible = f"{dia_nombre} {ahora.day}/{ahora.month}/{ahora.year}, hora actual: {ahora.strftime('%H:%M')} (Bolivia)"
    fecha_actual_iso = ahora.strftime("%Y-%m-%d")

    tel_limpio = re.sub(r"\D", "", str(tel_paciente or ""))
    tel_8 = tel_limpio[-8:] if len(tel_limpio) >= 8 else tel_limpio

    citas_este_paciente = []
    citas_ocupadas_otros = []

    try:
        db = SessionLocal()
        try:
            rows = db.query(Cita, Paciente).join(Paciente, Cita.paciente_id == Paciente.id).filter(
                Cita.estado.in_(["pendiente", "confirmada"])
            ).all()
            for cita, pac in rows:
                c_ini = cita.inicio.astimezone(tz_bolivia) if cita.inicio.tzinfo else cita.inicio.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz_bolivia)
                c_fin = cita.fin.astimezone(tz_bolivia) if cita.fin.tzinfo else cita.fin.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz_bolivia)
                pac_nom = pac.nombre or ""
                pac_tel_clean = re.sub(r"\D", "", str(pac.telefono or ""))

                d_nom = dias[c_ini.weekday()]
                fecha_fmt = f"{d_nom} {c_ini.day:02d}/{c_ini.month:02d}"
                hora_fmt = f"{c_ini.strftime('%H:%M')} a {c_fin.strftime('%H:%M')}"
                hora_12 = f"{c_ini.strftime('%I:%M %p').lstrip('0')}"
                estado_c = "Confirmada" if cita.estado == "confirmada" else "Pendiente de confirmación"

                es_de_este_paciente = False
                if pac_tel_clean and len(pac_tel_clean) >= 7 and tel_8:
                    pac_tel_8 = pac_tel_clean[-8:] if len(pac_tel_clean) >= 8 else pac_tel_clean
                    if tel_8 == pac_tel_8 or tel_8 in pac_tel_clean or pac_tel_8 in tel_limpio:
                        es_de_este_paciente = True

                if es_de_este_paciente:
                    citas_este_paciente.append(
                        f"• {fecha_fmt} a las {c_ini.strftime('%H:%M')} ({hora_12}) - Estado: {estado_c} (Paciente: {pac_nom})"
                    )
                else:
                    if ahora - timedelta(hours=2) <= c_ini <= ahora + timedelta(days=7):
                        citas_ocupadas_otros.append(f"{c_ini.strftime('%d/%m')} {c_ini.strftime('%H:%M')}-{c_fin.strftime('%H:%M')}")
        finally:
            db.close()
    except Exception as err_p:
        safe_print(f"[Prompt Citas Query Error]: {err_p}")

    if citas_este_paciente:
        texto_citas_paciente = "CITAS AGENDADAS A NOMBRE DE ESTE PACIENTE EN NUESTRO SISTEMA:\n" + "\n".join(citas_este_paciente)
    else:
        texto_citas_paciente = "El paciente NO registra citas agendadas con su número actual."

    ocupadas_texto = "; ".join(citas_ocupadas_otros[:14]) if citas_ocupadas_otros else "Sin turnos ocupados próximos"

    return f"""Eres el asistente virtual oficial de WhatsApp de 'SOLDENT - Clínica Odontológica', ubicada en {settings.CLINICA_DIRECCION}.
Especialista a cargo: {settings.DOCTORA_NOMBRE} (Especialista en Odontología Integral & Ortodoncia).
Teléfono de este bot (número automatizado): {settings.BOT_PHONE_NUMBER}.
Teléfono directo de la Dra. Pamela (contacto personal / urgencias): {settings.DOCTORA_TELEFONO}.
Teléfono del paciente que escribe: {tel_paciente}.

FECHA Y HORA ACTUAL: {fecha_actual_legible} (Fecha ISO: {fecha_actual_iso}).

{texto_citas_paciente}

TURNOS OCUPADOS EN CONSULTORIO POR OTROS PACIENTES:
{ocupadas_texto}.

HORARIOS OFICIALES DE ATENCIÓN DE SOLDENT (ESTRICTO):
• Lunes a Viernes: 09:00 a 12:00 y 15:30 a 19:30.
• Receso de Mediodía (CERRADO): 12:00 a 15:30 (NO atender ni ofrecer turnos).
• Sábados: 09:00 a 12:00 (Tardes de sábado cerrado).
• Domingos: CERRADO todo el día.

POLÍTICA DE SERVICIOS Y PRECIOS:
- ESPECIALIDADES DE LA DRA. PAMELA: La Dra. Pamela Pinto Suárez es especialista en Odontología Integral y Ortodoncia. Si el paciente pregunta qué tratamientos realiza o qué le puede hacer la doctora, explícale amablemente y con orgullo profesional: Ortodoncia (brackets y alineadores dentales), limpiezas profundas y profilaxis, curaciones y restauraciones estéticas en resina, evaluación general y diseño de sonrisas. Explícale que todo tratamiento inicia con una Evaluación Clínica / Consulta Odontológica para valorar su boca.
- PRECIOS: PROHIBIDO DAR PRECIOS O COTIZACIONES EXACTAS POR WHATSAPP. Si preguntan precios, indica amablemente que los costos se definen de manera personalizada tras la evaluación clínica presencial con la Dra. Pamela Pinto Suárez.
- PREGUNTAS CASUALES (ej. el clima, cómo estás, etc.): Responde con simpatía y calidez cruceña ("¡Por aquí todo excelente y con el consultorio listo para atenderte!", etc.) y conecta amablemente la conversación invitando a consultar dudas dentales o agendar su consulta.

REGLAS DE ATENCIÓN Y AGENDAMIENTO:
1. REGLA ESTRICTA - MARTES Y JUEVES (NO AGENDAR POR BOT, DERIVAR A LA DRA. PAMELA):
   - Los días MARTES y JUEVES este bot TIENE ESTRICTAMENTE PROHIBIDO agendar citas o confirmar turnos.
   - La atención de los días martes y jueves se coordina de manera EXCLUSIVA Y DIRECTA con la Dra. Pamela Pinto Suárez.
   - Si el paciente pide cita para un día MARTES o JUEVES, o pregunta por horarios de esos días:
     1. Explícale con amabilidad que la agenda de los días martes y jueves se coordina de forma personalizada y directa con la Dra. Pamela Pinto Suárez.
     2. Dale el número directo de la doctora: {settings.DOCTORA_TELEFONO} para que le escriba o llame directamente.
     3. Indícale que si prefiere agendar por aquí mismo mediante el bot, con mucho gusto le puedes agendar para los días LUNES, MIÉRCOLES, VIERNES o SÁBADOS por la mañana.
     4. NUNCA generes la etiqueta [RESERVAR: ...] para un martes o jueves.

2. SI EL PACIENTE PREGUNTA SI TIENE CITA, CUÁNDO ES SU CITA O CONSULTA SU ESTADO:
   - Revisa la sección 'CITAS AGENDADAS A NOMBRE DE ESTE PACIENTE'.
   - Si tiene cita registrada, CONFÍRMASELO con total claridad y amabilidad, indicándole la fecha, la hora exacta (ej. "Lunes 05 de Octubre a las 19:00 (7:00 PM)") y su estado.
   - Si NO tiene ninguna cita registrada, dile con amabilidad que no figura ninguna cita a su nombre con este número y ofrécele con gusto los horarios disponibles para agendar.

2. SI EL PACIENTE PIDE AGENDAR EN UN HORARIO QUE ÉL MISMO YA TIENE AGENDADO (ej. a las 7:00 PM / 19:00 del lunes):
   - Aclárale con amabilidad que ese turno ya está reservado a su nombre en nuestro sistema:
     "¡Estimado/a! Justamente ese horario de las 7:00 PM (19:00) del lunes ya se encuentra reservado y agendado a su nombre en nuestro sistema. ¡Su espacio ya está asegurado!"
   - NO intentes reservarlo de nuevo ni digas que está ocupado por otra persona. Pregúntale si confirma su asistencia o si desea reprogramarlo a otro horario.

3. AGENDAR NUEVA CITA:
   - Para agendar necesitas: (1) Nombre completo del paciente, (2) Día y hora exacta dentro del horario de atención disponible.
   - Si el paciente CONFIRMA su nombre y un horario válido disponible (que no pertenezca a turnos ocupados), incluye al final de tu mensaje:
     [RESERVAR: Nombre Del Paciente | YYYY-MM-DDTHH:MM:SS]

4. CONFIRMACIÓN DE CITA (REGLA ESTRICTA):
   - Solo incluye la etiqueta [CONFIRMAR_CITA] si el paciente afirma explícitamente que asistirá o confirma (ej: "Confirmo", "Ahí estaré", "Sí voy", "Asistiré").
   - NUNCA agregues la etiqueta [CONFIRMAR_CITA] si el mensaje es únicamente de cortesía, agradecimiento o despedida (ej: "Muchas gracias", "Gracias", "Ok", "De nada", "Hasta luego"). Para agradecimientos responde con una sola frase corta y amable (ej: "¡Con gusto! Nos vemos en su cita. 🦷✨").
   - Si en el historial la cita ya fue confirmada, NO agregues [CONFIRMAR_CITA] de nuevo.

5. SI EL PACIENTE CANCELA SU CITA O AVISA QUE NO PODRÁ IR (ej: "No podré ir", "Cancelo", "No voy a poder"):
   - Incluye al final de tu mensaje la etiqueta [CANCELAR_CITA].
   - Confirma de forma breve la liberación del horario e invítale en 1 línea a reagendar para otro día si lo desea.
   - Si el paciente en el mismo mensaje pide reagendar para una fecha/hora válida disponible, incluye además la etiqueta [RESERVAR: Nombre | YYYY-MM-DDTHH:MM:SS].

6. LONGITUD Y CONCISIÓN (REGLA FUNDAMENTAL - MENSAJES CORTOS):
   - En WhatsApp los pacientes leen en el móvil: las respuestas deben ser BREVES, directas y cordiales (máximo 2 a 3 líneas).
   - PROHIBIDO enviar parrafadas explicativas, mensajes recargados o discursos de bienvenida en medio de una conversación.
   - Ve directo al grano con amabilidad y educación cruceña.

7. UBICACIÓN, DIRECCIÓN Y GPS:
   - SOLDENT está ubicada en {settings.CLINICA_DIRECCION}.
   - Enlace oficial a Google Maps: {settings.CLINICA_MAPS_URL}
   - Si el paciente pregunta dónde queda la clínica, pide la dirección, cómo llegar, el croquis o la ubicación en GPS/Maps:
     1. Indícale la dirección brevemente ("Calle Parapetí (o Lemoine) #407, casi esquina Vallegrande, a una casa del Condominio Portales") y el enlace de Google Maps ({settings.CLINICA_MAPS_URL}).
     2. Agrega al final de tu mensaje la etiqueta [ENVIAR_UBICACION]. Nuestro sistema le enviará automáticamente la tarjeta interactiva de WhatsApp con el mapa GPS.
"""

def procesar_mensaje_con_gemini(remitente: str, nombre: str, texto: str, tel_paciente: str) -> str:
    """Procesa el mensaje del paciente con Gemini HTTP directo o devuelve respuesta oficial segura."""
    prompt_sistema = construir_prompt_sistema(tel_paciente)

    if remitente not in historial_sesiones:
        historial_sesiones[remitente] = []

    historial = historial_sesiones[remitente]
    historial.append({"role": "user", "text": f"Paciente ({nombre}): {texto}"})

    # Mantener últimos 6 mensajes para no sobrecargar el payload
    if len(historial) > 6:
        historial = historial[-6:]
        historial_sesiones[remitente] = historial

    respuesta_raw = llamar_gemini_http(prompt_sistema, historial)
    if not respuesta_raw:
        safe_print("⚠️ [Gemini HTTP] No hubo respuesta del modelo o API key ausente. Usando mensaje oficial por defecto.")
        return MENSAJE_OFICIAL_DEFAULT

    # Detectar si Gemini decidió ejecutar una reserva mediante la etiqueta [RESERVAR: Nombre | FechaHora]
    m_reserva = re.search(r"\[RESERVAR:\s*([^\|\]]+)\|\s*([^\]]+)\]", respuesta_raw)
    if m_reserva:
        nombre_cita = m_reserva.group(1).strip() or nombre
        fecha_cita = m_reserva.group(2).strip()
        safe_print(f"🎯 [Agendamiento Detectado]: {nombre_cita} para {fecha_cita}")

        resultado_reserva = crear_cita(nombre_cita, tel_paciente, fecha_cita)

        if "CITA_CONFIRMADA_201" in resultado_reserva:
            try:
                dt_c = datetime.fromisoformat(fecha_cita.replace(" ", "T"))
                dias_esp = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
                f_dia = f"{dias_esp[dt_c.weekday()]} {dt_c.strftime('%d/%m')}"
                f_hora = dt_c.strftime("%H:%M")
            except Exception:
                f_dia = "la fecha solicitada"
                f_hora = ""

            msg_confirmacion = (
                f"¡Cita agendada con éxito, {nombre_cita}! 🦷✨\n"
                f"Le esperamos el *{f_dia} a las {f_hora}* con la {settings.DOCTORA_NOMBRE} en Soldent ({settings.CLINICA_DIRECCION}). ¡Hasta pronto!"
            )
            historial.append({"role": "model", "text": msg_confirmacion})

            # NOTIFICACIÓN INMEDIATA A LA DRA. PAMELA (+591 78472875)
            msg_alerta_doctora = (
                "🦷 *SOLDENT - Nueva Cita Agendada por Bot*\n\n"
                f"👤 *Paciente:* {nombre_cita} ({tel_paciente})\n"
                f"🗓️ *Fecha y Hora:* {f_dia} a las {f_hora}\n"
                f"🩺 *Servicio:* Consulta Odontológica\n"
                "✅ Guardada en agenda y Google Calendar."
            )
            try:
                httpx.post(
                    f"{settings.EVOLUTION_API_URL}/send-message",
                    json={"number": settings.DOCTORA_TELEFONO, "text": msg_alerta_doctora, "message": msg_alerta_doctora},
                    timeout=5.0
                )
                safe_print(f"✅ [Alerta Doctora] Notificación enviada a la Dra. Pamela ({settings.DOCTORA_TELEFONO}) por nueva cita de {nombre_cita}")
            except Exception as err_doc:
                safe_print(f"⚠️ [Alerta Doctora Error] No se pudo enviar notificación a la doctora: {err_doc}")

            return msg_confirmacion

        elif "ERROR_HORARIO_OCUPADO" in resultado_reserva:
            msg_ocupado = (
                "Ese horario ya se encuentra ocupado en el consultorio. "
                "Con gusto le ofrezco agendar en el siguiente turno libre o en un horario diferente dentro de nuestros turnos oficiales."
            )
            historial.append({"role": "model", "text": msg_ocupado})
            return msg_ocupado

        elif "AVISO_CITA_EXISTENTE" in resultado_reserva:
            historial.append({"role": "model", "text": resultado_reserva})
            return (
                f"¡Estimado/a {nombre_cita}! Le recordamos que ya cuenta con una cita activa agendada en Soldent. "
                f"Le esperamos en {settings.CLINICA_DIRECCION}."
            )

        elif "ERROR_MARTES_JUEVES_DIRECTO_DOCTORA" in resultado_reserva:
            msg_directo = (
                f"Las citas de martes y jueves se coordinan directamente con la {settings.DOCTORA_NOMBRE} al WhatsApp *{settings.DOCTORA_TELEFONO}*.\n\n"
                "Si prefiere agendar por aquí mediante el asistente, con mucho gusto le ayudamos para Lunes, Miércoles, Viernes o Sábado."
            )
            historial.append({"role": "model", "text": msg_directo})
            return msg_directo

        elif any(err in resultado_reserva for err in ("ERROR_RECESO_MEDIODIA", "ERROR_SABADO_TARDE_CERRADO", "ERROR_DOMINGO_CERRADO", "ERROR_HORARIO_NO_PERMITIDO")):
            historial.append({"role": "model", "text": resultado_reserva})
            return (
                "Ese horario está fuera de atención. "
                "Atendemos Lun-Vie 09:00-12:00 y 15:30-19:30, y Sáb 09:00-12:00. ¿Qué horario le queda mejor?"
            )

    # 1. Detectar confirmación de cita (vía tag de Gemini o intención explícita del paciente)
    texto_l = texto.lower()

    # Cortesías habituales que NO deben interpretarse como confirmación nueva
    es_solo_cortesia = any(w in texto_l for w in ("muchas gracias", "muchisimas gracias", "mil gracias", "gracias", "ok gracias", "de nada", "igualmente", "que tenga buen dia")) and not any(w in texto_l for w in ("confirmo", "confirmado", "ahi estare", "ahí estaré", "voy a ir", "asistire", "asistiré"))

    es_confirmacion = not es_solo_cortesia and (
        "[CONFIRMAR_CITA]" in respuesta_raw or
        any(w in texto_l for w in ("confirmo", "confirmado", "confirmar", "ahi estare", "ahí estaré", "si voy", "sí voy", "asistire", "asistiré", "voy a ir", "estare puntual", "estaré puntual", "seguro voy"))
    )
    if es_confirmacion:
        info_c = actualizar_estado_cita_paciente(tel_paciente, "confirmada")
        nombre_p = info_c.get("paciente_nombre") or nombre

        if info_c and info_c.get("ya_estaba_confirmada"):
            msg_resp = f"¡Con mucho gusto, {nombre_p}! Su cita para el *{info_c['fecha']} a las {info_c['hora']}* ya se encuentra confirmada. ¡Le esperamos en Soldent! 🦷✨"
            historial.append({"role": "model", "text": msg_resp})
            return msg_resp

        elif info_c:
            msg_resp = (
                f"¡Cita confirmada, {nombre_p}! 🦷✨\n"
                f"La {settings.DOCTORA_NOMBRE} le espera el *{info_c['fecha']} a las {info_c['hora']}* en Soldent ({settings.CLINICA_DIRECCION}). ¡Hasta pronto!"
            )
            historial.append({"role": "model", "text": msg_resp})

            # Notificar a la Dra. Pamela (+591 78472875) UNA SOLA VEZ
            msg_doc = (
                f"🦷 *SOLDENT - Cita Confirmada por Paciente*\n\n"
                f"Estimada Dra. Pamela, el paciente *{nombre_p}* ({tel_paciente}) "
                f"acaba de confirmar su asistencia para el *{info_c['fecha']} a las {info_c['hora']}* mediante WhatsApp."
            )
            try:
                httpx.post(
                    f"{settings.EVOLUTION_API_URL}/send-message",
                    json={"number": settings.DOCTORA_TELEFONO, "text": msg_doc, "message": msg_doc},
                    timeout=5.0
                )
                safe_print(f"✅ [Alerta Confirmación] Notificación enviada a la Dra. Pamela por {nombre_p}")
            except Exception as e:
                safe_print(f"⚠️ [Alerta Doctora Confirmacion]: {e}")

            return msg_resp

        else:
            msg_resp = (
                f"Hola {nombre}. No encontramos ninguna cita pendiente de confirmación a su nombre. "
                "Si desea agendar una consulta, indíquenos qué día y horario le queda cómodo y con gusto le ayudamos."
            )
            historial.append({"role": "model", "text": msg_resp})
            return msg_resp

    # 2. Detectar cancelación de cita (vía tag de Gemini o intención explícita del paciente)
    es_cancelacion = (
        "[CANCELAR_CITA]" in respuesta_raw or
        any(w in texto_l for w in ("cancelo", "cancelar", "no podre", "no podré", "no voy a poder", "no asistire", "no asistiré", "no voy a ir"))
    )
    if es_cancelacion:
        info_c = actualizar_estado_cita_paciente(tel_paciente, "cancelada")
        nombre_p = info_c.get("paciente_nombre") or nombre
        msg_resp = (
            f"Entendido, {nombre_p}. Su cita fue cancelada y el horario liberado. 🦷\n\n"
            f"Si desea reagendar para otro día, avíseme qué fecha u horario (mañana o tarde) prefiere y con gusto se la programo."
        )
        historial.append({"role": "model", "text": msg_resp})

        # Notificar a la Dra. Pamela (+591 78472875)
        if info_c:
            msg_doc = (
                f"⚠️ *SOLDENT - Cita Cancelada por Paciente*\n\n"
                f"Estimada Dra. Pamela, el paciente *{nombre_p}* ({tel_paciente}) "
                f"ha cancelado su cita del *{info_c['fecha']} a las {info_c['hora']}*. El horario ha quedado liberado en su agenda."
            )
            try:
                httpx.post(
                    f"{settings.EVOLUTION_API_URL}/send-message",
                    json={"number": settings.DOCTORA_TELEFONO, "text": msg_doc, "message": msg_doc},
                    timeout=5.0
                )
                safe_print(f"⚠️ [Alerta Cancelación] Notificación enviada a la Dra. Pamela por {nombre_p}")
            except Exception as e:
                safe_print(f"⚠️ [Alerta Doctora Cancelacion]: {e}")

        return msg_resp

    # Si fue respuesta conversacional normal, limpiar posibles etiquetas internas y devolver
    enviar_gps = "[ENVIAR_UBICACION]" in respuesta_raw
    texto_limpio = re.sub(r"\[(RESERVAR|CONFIRMAR_CITA|CANCELAR_CITA|ENVIAR_UBICACION):?[^\]]*\]", "", respuesta_raw).strip()
    if not texto_limpio:
        texto_limpio = MENSAJE_OFICIAL_DEFAULT

    historial.append({"role": "model", "text": texto_limpio})
    if enviar_gps:
        texto_limpio = f"{texto_limpio} [ENVIAR_UBICACION]"
    return texto_limpio
