#!/bin/bash
set -e

echo "=========================================================="
echo "ðŸš€ INICIANDO SOLDENT - AGENDA ODONTOLÃ“GICA (CLOUD/DOCKER)"
echo "=========================================================="

APP_PORT="${PORT:-8000}"
export API_BACKEND_URL="http://127.0.0.1:${APP_PORT}"

# 1. Configurar directorio persistente para Baileys
if [ -d "/data" ]; then
    echo "ðŸ“ Almacenamiento persistente detectado en /data"
    export AUTH_DIR="/data/auth_info_baileys"
    mkdir -p "$AUTH_DIR"
else
    echo "ðŸ“ Usando almacenamiento local para Baileys"
    export AUTH_DIR="/app/whatsapp-gateway/auth_info_baileys"
    mkdir -p "$AUTH_DIR"
fi

# 2. Configurar URL pÃºblica dinÃ¡mica segÃºn la plataforma (Render, Koyeb, Hugging Face)
if [ -z "$PUBLIC_BASE_URL" ] || [[ "$PUBLIC_BASE_URL" == *"192.168"* ]] || [[ "$PUBLIC_BASE_URL" == *"localhost"* ]]; then
    if [ -n "$RENDER_EXTERNAL_URL" ]; then
        export PUBLIC_BASE_URL="$RENDER_EXTERNAL_URL"
        echo "ðŸŒ Render detectado: PUBLIC_BASE_URL=$PUBLIC_BASE_URL"
    elif [ -n "$KOYEB_PUBLIC_DOMAIN" ]; then
        export PUBLIC_BASE_URL="https://$KOYEB_PUBLIC_DOMAIN"
        echo "ðŸŒ Koyeb detectado: PUBLIC_BASE_URL=$PUBLIC_BASE_URL"
    elif [ -n "$SPACE_HOST" ]; then
        export PUBLIC_BASE_URL="https://$SPACE_HOST"
        echo "ðŸŒ Hugging Face detectado: PUBLIC_BASE_URL=$PUBLIC_BASE_URL"
    fi
fi

# 3. Iniciar pasarela de WhatsApp Baileys (puerto interno 8080)
echo "ðŸ“± [1/4] Iniciando pasarela de WhatsApp Baileys..."
cd /app/whatsapp-gateway
node server.js &
cd /app

# Esperar 2 segundos para asegurar inicializaciÃ³n de la pasarela
sleep 2

# 4. Iniciar WhatsApp Bot con Google Gemini (puerto interno 5005)
echo "ðŸ¤– [2/4] Iniciando WhatsApp Bot con Gemini..."
python whatsapp_bot.py &

# 5. Iniciar Worker cÃ­clico para recordatorios y sincronizaciÃ³n con Google Calendar
echo "â° [3/4] Iniciando ciclo de recordatorios y sincronizaciÃ³n..."
(
    while true; do
        sleep 60
        python run_workers.py || true
    done
) &

# 6. Iniciar servidor principal FastAPI en el puerto dinÃ¡mico de la plataforma
echo "ðŸŒ [4/4] Iniciando FastAPI en puerto $APP_PORT..."
exec uvicorn main:app --host 0.0.0.0 --port "$APP_PORT"
