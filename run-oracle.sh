#!/bin/bash
set -e

cd /home/ubuntu/soldent-agenda

export PORT=8000
export API_BACKEND_URL="http://127.0.0.1:8000"
export EVOLUTION_API_URL="http://127.0.0.1:8080"
export PUBLIC_BASE_URL="https://soldent-agenda.duckdns.org"

cleanup() {
    echo "Deteniendo servicios de Soldent..."
    kill -TERM "$PID_GATEWAY" "$PID_BOT" "$PID_BACKEND" "$PID_WORKERS" 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT

echo "Iniciando Backend FastAPI..."
./venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 &
PID_BACKEND=$!

echo "Esperando que FastAPI responda..."
for i in $(seq 1 30); do
    if curl -s "http://127.0.0.1:8000/api/salud" > /dev/null 2>&1; then
        echo "Backend listo."
        break
    fi
    sleep 1
done

echo "Iniciando Pasarela de WhatsApp..."
cd /home/ubuntu/soldent-agenda/whatsapp-gateway
node --max-old-space-size=250 server.js &
PID_GATEWAY=$!
cd /home/ubuntu/soldent-agenda

sleep 3

echo "Iniciando Bot de WhatsApp con IA..."
./venv/bin/python whatsapp_bot.py &
PID_BOT=$!

echo "Iniciando Soldent Background Workers independientes..."
./venv/bin/python run_workers.py &
PID_WORKERS=$!

echo "Todos los servicios de Soldent iniciados con éxito en Oracle Cloud."
wait -n "$PID_BACKEND" "$PID_BOT" "$PID_GATEWAY" "$PID_WORKERS"
cleanup
