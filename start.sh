#!/bin/bash
set -e

echo "=========================================================="
echo "🚀 INICIANDO SOLDENT - AGENDA ODONTOLÓGICA (CLOUD/DOCKER)"
echo "=========================================================="

# 1. Determinar puerto de la aplicación (Render asigna $PORT, Hugging Face usa 7860)
APP_PORT="${PORT:-7860}"
export PORT="$APP_PORT"
export API_BACKEND_URL="http://127.0.0.1:${APP_PORT}"
export EVOLUTION_API_URL="http://127.0.0.1:8080"

# 2. Configurar directorio para Baileys (persistencia de sesión WhatsApp)
if [ -d "/data" ] && [ -w "/data" ]; then
    echo "📁 Almacenamiento persistente detectado en /data"
    export AUTH_DIR="/data/auth_info_baileys"
else
    echo "📁 Usando almacenamiento en /app/whatsapp-gateway/auth_info_baileys"
    export AUTH_DIR="/app/whatsapp-gateway/auth_info_baileys"
fi
mkdir -p "$AUTH_DIR" 2>/dev/null || true

# 3. Detectar dominio público automáticamente si no está configurado
if [ -z "$PUBLIC_BASE_URL" ] || [[ "$PUBLIC_BASE_URL" == *"192.168"* ]] || [[ "$PUBLIC_BASE_URL" == *"localhost"* ]]; then
    if [ -n "$RENDER_EXTERNAL_URL" ]; then
        export PUBLIC_BASE_URL="$RENDER_EXTERNAL_URL"
        echo "🌐 Render detectado: PUBLIC_BASE_URL=$PUBLIC_BASE_URL"
    elif [ -n "$SPACE_HOST" ]; then
        export PUBLIC_BASE_URL="https://$SPACE_HOST"
        echo "🌐 Hugging Face Spaces detectado: PUBLIC_BASE_URL=$PUBLIC_BASE_URL"
    elif [ -n "$KOYEB_PUBLIC_DOMAIN" ]; then
        export PUBLIC_BASE_URL="https://$KOYEB_PUBLIC_DOMAIN"
        echo "🌐 Koyeb detectado: PUBLIC_BASE_URL=$PUBLIC_BASE_URL"
    fi
fi

echo "ℹ️  PUBLIC_BASE_URL configurada: ${PUBLIC_BASE_URL:-http://localhost:${APP_PORT}}"

# 4. Manejador para terminación limpia de procesos
cleanup() {
    echo "🛑 Recibida señal de parada. Finalizando procesos en segundo plano..."
    kill -TERM "$PID_GATEWAY" "$PID_BOT" "$PID_BACKEND" 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT

# 5. Iniciar pasarela de WhatsApp Baileys (puerto interno 8080)
echo "📱 [1/3] Iniciando pasarela de WhatsApp Baileys (puerto 8080)..."
cd /app/whatsapp-gateway
node server.js &
PID_GATEWAY=$!
cd /app

# Esperar 3 segundos para que Node.js inicie
sleep 3

# 6. Iniciar WhatsApp Bot con Gemini + Workers automáticos (puerto interno 5005)
echo "🤖 [2/3] Iniciando WhatsApp Bot y ciclo de workers automáticos (puerto 5005)..."
python whatsapp_bot.py &
PID_BOT=$!

# Esperar 2 segundos para que el bot inicie
sleep 2

# 7. Iniciar servidor principal FastAPI en el puerto de la nube ($APP_PORT)
echo "🌐 [3/3] Iniciando Backend FastAPI en puerto $APP_PORT..."
uvicorn main:app --host 0.0.0.0 --port "$APP_PORT" &
PID_BACKEND=$!

# Esperar activamente a los procesos
wait -n "$PID_BACKEND" "$PID_BOT" "$PID_GATEWAY"
cleanup
