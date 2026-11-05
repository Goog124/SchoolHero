# syntax=docker/dockerfile:1

# Базовые образы закреплены по точным версиям, чтобы сборка была повторяемой.
# Как дополнительно закрепить по digest и обновлять версии: docs/docker.md.

# --- Frontend build ---------------------------------------------------------
FROM node:22.14.0-bookworm-slim AS frontend-build

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# --- Runtime ----------------------------------------------------------------
FROM python:3.12.10-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_MODE=prod \
    CATALOG_FILE=/data/catalog.json \
    HOME=/home/app \
    HOST=0.0.0.0 \
    PORT=8000 \
    STATIC_DIR=/app/static \
    DATABASE_PATH=/data/school_hero.db

WORKDIR /app

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data \
    && chown -R app:app /data

# Только runtime-зависимости. pytest и прочее для разработки лежат в
# requirements-dev.txt и в образ не попадают.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./
COPY backend ./backend
COPY tools ./tools
COPY landing ./landing
COPY catalog.example.json ./catalog.example.json
COPY --from=frontend-build /app/static ./static

USER app

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"

# umask 077: база, -wal и -shm в томе /data создаются с правами 600.
CMD ["sh", "-c", "umask 077 && exec python app.py"]
