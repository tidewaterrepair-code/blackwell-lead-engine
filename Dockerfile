# Pegasus: one image for the web app and the background worker.
#   docker compose up -d --build        (see docker-compose.yml and docs/DEPLOY.md)

# ---- 1. Build the React app (served by FastAPI at /app)
FROM node:20-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. Python runtime
FROM python:3.12-slim

# INSTALL_BROWSER=true adds headless Chromium (~500 MB): needed for Accela-style permit
# portals and for `pegasus marketing render` (banner PNGs).
ARG INSTALL_BROWSER=false

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PEGASUS_ENV=production \
    PEGASUS_DATA_DIR=/data \
    SOURCES_FILE=/app/sources.yaml \
    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers

WORKDIR /app
COPY pyproject.toml README.md ./
COPY pegasus ./pegasus
COPY --from=frontend /src/pegasus/web/static/app ./pegasus/web/static/app
RUN pip install . \
 && if [ "$INSTALL_BROWSER" = "true" ]; then \
      pip install playwright && playwright install --with-deps chromium; \
    fi
COPY sources.yaml ./sources.yaml
COPY marketing ./marketing

RUN useradd --create-home --uid 1000 app && mkdir -p /data && chown app /data /app/marketing
USER app
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')" || exit 1
# Apply database migrations, then serve. The worker service overrides this command.
CMD ["sh", "-c", "pegasus db upgrade && exec pegasus serve --host 0.0.0.0 --port 8000 --workers ${WEB_WORKERS:-2}"]
