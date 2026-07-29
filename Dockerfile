# Orca Agent — Python 3.11 slim, single-stage, optimized
FROM python:3.11-slim

# System deps (curl for healthcheck + tzdata for logs)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates tzdata git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Runtime dirs
RUN mkdir -p logs data backups

# Healthcheck — uses python stdlib so we don't need the bot process up
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,json; r=urllib.request.urlopen('https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe', timeout=4); d=json.loads(r.read()); assert d.get('ok')" \
    || exit 1

EXPOSE 8080

# Single canonical entrypoint — orca.py handles bot|sync|status|doctor
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

CMD ["python", "-u", "orca.py", "bot"]
