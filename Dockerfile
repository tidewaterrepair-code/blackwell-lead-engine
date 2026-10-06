FROM python:3.12-slim

# Set INSTALL_BROWSER=true to include headless Chromium for Accela portals
# (Chesapeake eBUILD etc.). Adds ~500 MB to the image.
ARG INSTALL_BROWSER=false

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LEADENGINE_DATA_DIR=/data \
    SOURCES_FILE=/app/sources.yaml \
    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers

WORKDIR /app
COPY pyproject.toml README.md ./
COPY leadengine ./leadengine
RUN pip install . \
 && if [ "$INSTALL_BROWSER" = "true" ]; then \
      pip install playwright && playwright install --with-deps chromium; \
    fi
COPY sources.yaml ./sources.yaml

RUN useradd --create-home --uid 1000 app && mkdir -p /data && chown app /data
USER app
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')" || exit 1
CMD ["leadengine", "serve", "--host", "0.0.0.0", "--port", "8000"]
