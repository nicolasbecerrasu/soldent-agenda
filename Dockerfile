# ========================================================
# SOLDENT - AGENDA ODONTOLÓGICA & BOT WHATSAPP
# Dockerfile optimizado para Despliegue en la Nube (Render / Koyeb / Docker)
# ========================================================
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# Instalar Node.js 20, curl, librerías de PostgreSQL y compilación
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    build-essential \
    libpq-dev \
    git \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list \
    && apt-get update && apt-get install -y nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Crear usuario estándar para Hugging Face Spaces (UID 1000)
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR /app

# Crear carpeta de persistencia para Baileys
RUN mkdir -p /data/auth_info_baileys && chown -R user:user /data /app

# Instalar dependencias Python
COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Instalar dependencias Node.js de la pasarela WhatsApp
COPY --chown=user:user whatsapp-gateway/package*.json ./whatsapp-gateway/
RUN cd whatsapp-gateway && npm install --omit=dev

# Copiar el código fuente completo del proyecto (incluye frontend/dist)
COPY --chown=user:user . .

# Limpiar cualquier formato de fin de línea Windows o BOM y asignar permisos
RUN sed -i -e '1s/^\xef\xbb\xbf//' -e 's/\r$//' /app/start.sh && chmod +x /app/start.sh

# Puerto expuesto por defecto
EXPOSE 8000

USER user

CMD ["/bin/bash", "/app/start.sh"]
