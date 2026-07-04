# Pull base image
FROM python:3.11-slim

# Zona horaria: la tool obtener_fecha_hora usa zoneinfo, que en slim
# necesita el paquete de datos tzdata (no viene preinstalado)
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

# cd /app
WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

EXPOSE 8000

CMD ["uvicorn", "main_chatwoot:app", "--host", "0.0.0.0", "--port", "8000"]
