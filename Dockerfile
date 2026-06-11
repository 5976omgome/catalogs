FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy app
COPY . .

# Make data directory (will be overridden by volume mount in production)
RUN mkdir -p /app/data /app/.uploads /app/.geni_uploads /app/Outputs /app/GeniOutputs /app/feedback

# Port (Cloud Run injects this)
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

# Start with gunicorn for production (multi-worker, handles concurrent users)
CMD exec gunicorn --bind :$PORT --workers 2 --threads 4 --timeout 120 "app.server:app"
