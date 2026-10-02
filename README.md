---
title: Soldent Agenda Odontológica
emoji: 🦷
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Soldent - Sistema de Gestión Odontológica & WhatsApp Bot

Sistema integral para el consultorio **Soldent** de la **Dra. Pamela Pinto Suárez** (Santa Cruz de la Sierra, Bolivia).

## 🚀 Despliegue en Hugging Face Spaces (Docker)

1. En [Hugging Face Spaces](https://huggingface.co/spaces), haz clic en **Create new Space**.
2. Asigna un nombre (ej. `soldent-agenda`), selecciona **Space SDK: Docker** y visibilidad **Private** o **Public**.
3. (Recomendado) En **Settings > Persistent Storage**, activa un disco pequeño (ej. 2GB Free Tier) para que la sesión de WhatsApp en `/data/auth_info_baileys` sea persistente tras reinicios.
4. En **Settings > Variables and secrets**, agrega tus secretos:
   - `DATABASE_URL` (Supabase PostgreSQL)
   - `GEMINI_API_KEY` (Google AI Studio)
   - `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` (Google Calendar)
   - `WHATSAPP_PHONE_NUMBER` (+59162422577)
5. Sube el código mediante Git:
   ```bash
   git remote add space https://huggingface.co/spaces/<TU_USUARIO>/<TU_SPACE>
   git add .
   git commit -m "Despliegue Soldent en Hugging Face Spaces"
   git push space main
   ```
6. Al terminar la compilación del contenedor en Hugging Face:
   - **Agenda Web:** Abre la URL principal del Space (`https://<TU_SPACE>.hf.space`).
   - **Vincular WhatsApp:** Abre `https://<TU_SPACE>.hf.space/qr` para escanear el código QR con el celular de WhatsApp.
   - **Confirmación móvil de pacientes:** Las URLs `/r/{token}` funcionarán de inmediato en los teléfonos de los pacientes.
