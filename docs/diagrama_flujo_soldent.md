# 📊 Diagrama de Flujo Integral - Sistema Soldent

Este documento detalla el funcionamiento completo del ecosistema **Soldent**: su infraestructura en la nube, el flujo de decisiones del bot de WhatsApp con Inteligencia Artificial, y la sincronización con la base de datos y Google Calendar.

---

## 1. 🏗️ Arquitectura General del Sistema

```mermaid
flowchart TD
    subgraph Usuarios ["👥 Actores del Sistema"]
        PAC["🩺 Pacientes"]
        DOC["👩‍⚕️ Dra. Pamela (+591 78472875)"]
        ADM["👨‍💻 Nicolás Admin (+591 70277520)"]
    end

    subgraph Canales ["📡 Canales de Entrada"]
        WA_APP["💬 WhatsApp Web / App"]
        WEB_UI["🌐 Agenda Web (Navegador)"]
    end

    subgraph ServidorOracle ["☁️ Servidor Principal (Oracle Cloud 146.181.38.79)"]
        NGINX["🛡️ Nginx Reverse Proxy (Puerto 80)"]
        FASTAPI["⚙️ Backend FastAPI (main.py :8000)"]
        GATEWAY["📱 Baileys Gateway (server.js :8080)"]
        BOT_AI["🤖 Bot IA & Workers (whatsapp_bot.py :5005)"]
    end

    subgraph ServidorBackup ["☁️ Servidor Respaldo (Render Cloud)"]
        RENDER_BACKEND["⚙️ FastAPI Backup (Modo Web / Bot Standby)"]
    end

    subgraph ServiciosNube ["🗄️ Servicios Externos en la Nube"]
        SUPABASE[("🐘 Supabase PostgreSQL\n- Schema: agenda\n- Sesión Baileys\n- Pacientes, Citas, Pagos")]
        GCAL["📅 Google Calendar API\n(Sincronización Bidireccional)"]
        GEMINI["🧠 Google Gemini AI\n(Procesamiento de Lenguaje Natural)"]
    end

    PAC -->|Escribe mensaje| WA_APP
    DOC -->|Escribe mensaje| WA_APP
    ADM -->|Escribe comando / consulta| WA_APP
    DOC & ADM -->|Gestionan agenda| WEB_UI

    WEB_UI -->|HTTP / HTTPS| NGINX
    NGINX -->|Proxy pass :8000| FASTAPI

    WA_APP <-->|WebSocket Baileys| GATEWAY
    GATEWAY -->|HTTP POST Webhook :5005| BOT_AI
    BOT_AI -->|HTTP POST /send-message :8080| GATEWAY

    BOT_AI <-->|Consultas CRUD internas| FASTAPI
    FASTAPI <-->|SQL Pooler (Transacciones y UPSERT)| SUPABASE
    GATEWAY <-->|Persistencia y restauración de sesión| SUPABASE

    FASTAPI <-->|OAuth2 Sync Citas| GCAL
    BOT_AI <-->|Prompt + Historial| GEMINI

    RENDER_BACKEND -.->|Standby Failover| SUPABASE
```

---

## 2. 🧠 Flujo de Procesamiento de Mensajes de WhatsApp

```mermaid
flowchart TD
    INICIO(["📩 Mensaje entrante recibido por Baileys"]) --> GATEWAY_PARSE["Extracción de JID, teléfono, texto y nombre"]
    GATEWAY_PARSE --> CHECK_LID{"¿Es número LID?"}
    
    CHECK_LID -- Sí --> RESOLVE_LID["Traducir LID a número real en Supabase"]
    CHECK_LID -- No --> SET_PHONE["Usar número directo"]
    
    RESOLVE_LID --> WEBHOOK["Enviar HTTP POST a whatsapp_bot.py (:5005)"]
    SET_PHONE --> WEBHOOK

    WEBHOOK --> ROUTER{"Identificación de Remitente"}

    %% CANAL ADMINISTRADOR (NICOLÁS)
    ROUTER -- "+591 70277520 (Nicolás)" --> ADMIN_CHANNEL["👨‍💻 Canal de Administrador"]
    ADMIN_CHANNEL --> FETCH_METRICS["Consultar métricas en tiempo real:\n- Pacientes totales\n- Citas de hoy y mañana\n- Mensajes y recordatorios enviados\n- Salud del servidor"]
    FETCH_METRICS --> GEMINI_ADMIN["Procesar consulta con Gemini\n(Tono técnico y de soporte colega)"]
    GEMINI_ADMIN --> SEND_ADMIN["Enviar respuesta a Nicolás"]

    %% CANAL DOCTORA (PAMELA)
    ROUTER -- "+591 78472875 (Dra. Pamela)" --> DOC_CHANNEL["👩‍⚕️ Canal Personal Doctora"]
    DOC_CHANNEL --> CHECK_CMD_DOC{"¿Solicitud de agenda o bloqueo?"}
    CHECK_CMD_DOC -- Sí --> MOD_AGENDA["Crear cita / Bloquear horario en sistema"]
    CHECK_CMD_DOC -- No --> DOC_ASSIST["Asistente de consultas clínicas y turnos"]
    MOD_AGENDA --> SYNC_GCAL_DOC["Reflejar en Google Calendar"]
    SYNC_GCAL_DOC --> SEND_DOC["Enviar confirmación a la Dra."]
    DOC_ASSIST --> SEND_DOC

    %% CANAL PACIENTE
    ROUTER -- "Paciente / Usuario General" --> PAC_CHANNEL["🩺 Canal de Pacientes"]
    PAC_CHANNEL --> CHECK_DUPLICATE{"¿Mensaje duplicado en <15s?"}
    CHECK_DUPLICATE -- Sí --> DROP_MSG["Ignorar duplicado silenciosamente"]
    CHECK_DUPLICATE -- No --> LOAD_HISTORY["Cargar historial de chat de la sesión"]
    
    LOAD_HISTORY --> DETECT_INTENT["Analizar intención del mensaje"]
    
    DETECT_INTENT --> INTENT_SWITCH{"Tipo de Intención"}
    
    INTENT_SWITCH -- "Consultar Horarios / Disponibilidad" --> GET_DISP["Consultar disponibilidad en FastAPI"]
    GET_DISP --> GEMINI_RESP["Gemini redacta opciones libres"]
    
    INTENT_SWITCH -- "Agendar Cita Odontológica" --> CHECK_SLOT{"¿Horario libre y en horario laboral?"}
    CHECK_SLOT -- Sí --> CREATE_CITA["Registrar paciente y cita en Supabase"]
    CREATE_CITA --> GCAL_INSERT["Insertar evento en Google Calendar"]
    GCAL_INSERT --> CONFIRM_RESP["Generar confirmación con dirección y recomendaciones"]
    CHECK_SLOT -- No --> SUGGEST_RESP["Sugerir próximos turnos disponibles"]
    
    INTENT_SWITCH -- "Precios / Ubicación / Dudas Clínicas" --> INFO_RESP["Gemini responde según información oficial de Soldent"]

    GEMINI_RESP --> FORMAT_OUT["Simular escritura humana (typing 1.8s - 3s)"]
    CONFIRM_RESP --> FORMAT_OUT
    SUGGEST_RESP --> FORMAT_OUT
    INFO_RESP --> FORMAT_OUT

    FORMAT_OUT --> GATEWAY_OUT["Baileys envía mensaje a WhatsApp del Paciente"]
    SEND_ADMIN --> FORMAT_OUT
    SEND_DOC --> FORMAT_OUT
    GATEWAY_OUT --> FIN(["✅ Mensaje Entregado"])
```

---

## 3. ⏰ Ciclo de Workers Automáticos en Segundo Plano

```mermaid
flowchart TD
    CRON_START(["⏱️ Cron Loop en whatsapp_bot.py"]) --> TICK{"Evaluación cada minuto"}

    %% RECORDATORIOS MATUTINOS
    TICK -- "08:30 AM" --> RUN_DAILY["Recordatorios de Citas de Hoy"]
    RUN_DAILY --> GET_TODAY["Obtener citas confirmadas de hoy desde Supabase"]
    GET_TODAY --> LOOP_PAC_TODAY{"Para cada paciente"}
    LOOP_PAC_TODAY --> SEND_REMINDER_TODAY["Enviar: 'Hola [Nombre], te recordamos tu cita hoy a las [Hora] en Soldent...'"]
    SEND_REMINDER_TODAY --> DELAY_1["Pausa de seguridad anti-spam (5-10s)"]
    DELAY_1 --> LOOP_PAC_TODAY

    %% RECORDATORIOS 24H PREVIAS
    TICK -- "Cada 30 minutos" --> RUN_24H["Verificación ventana 24 horas"]
    RUN_24H --> GET_24H["Buscar citas del día siguiente sin recordatorio enviado"]
    GET_24H --> LOOP_PAC_24H{"¿Hay citas pendientes de aviso?"}
    LOOP_PAC_24H -- Sí --> SEND_REMINDER_24H["Enviar: 'Estimado/a [Nombre], tienes cita programada para mañana a las [Hora]...'"]
    SEND_REMINDER_24H --> MARK_SENT["Marcar recordatorio como enviado en BD"]
    MARK_SENT --> LOOP_PAC_24H
    LOOP_PAC_24H -- No --> WAIT_NEXT["Dormir hasta el siguiente ciclo"]

    %% SINCRONIZACIÓN GOOGLE CALENDAR
    TICK -- "Cada 5 minutos" --> SYNC_GCAL["Sincronizador Bidireccional Google Calendar"]
    SYNC_GCAL --> FETCH_GCAL["Consultar cambios en calendario de la Doctora"]
    FETCH_GCAL --> UPDATE_LOCAL["Actualizar o crear citas en base de datos Soldent"]
    UPDATE_LOCAL --> WAIT_NEXT
```

---

## 4. 🛡️ Blindaje y Tolerancia a Fallos (Failover)

| Componente | Mecanismo de Protección | Solución Implementada |
| :--- | :--- | :--- |
| **Persistencia Baileys** | Colisión de claves al sincronizar | `UPSERT` atómico en PostgreSQL (`ON CONFLICT (key) DO UPDATE`) |
| **Conflicto Multiserver** | Dos servidores corriendo Baileys (Código 440) | Detección de `connectionReplaced` + pausa de 5 min + `DISABLE_WHATSAPP` en Render |
| **Reinicio de Servidor** | Reinicio no planeado de la máquina virtual | Servicio `systemd (soldent.service)` con auto-restart continuo |
| **Memoria RAM** | Límite de 1 GB en VM gratuita | Swappiness optimizado con swapfile de 2 GB + límite V8 `--max-old-space-size=250` |
| **Anti-Spam de Meta** | Detección de automatización en WhatsApp | Delay aleatorio de tipeo humano (1.8s a 3.3s) antes de cada mensaje |
