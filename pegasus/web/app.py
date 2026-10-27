"""The Pegasus web app: JSON API + React app (/app) + marketing site (/)."""

from __future__ import annotations

import logging
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware

from ..api import admin_routes, auth_routes, lead_routes, org_routes
from ..config import get_settings
from ..db import get_engine
from . import site

log = logging.getLogger(__name__)
HERE = Path(__file__).parent
APP_DIST = HERE / "static" / "app"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    if settings.env == "production" and (settings.secret_key.startswith("dev-") or len(settings.secret_key) < 32):
        raise RuntimeError("Set SECRET_KEY to a long random value (openssl rand -hex 32) before running in production")
    get_engine()
    from ..ingest import sync_seed_sources_safely

    sync_seed_sources_safely()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Pegasus", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, session_cookie="pegasus",
                       max_age=60 * 60 * 24 * 30, same_site="lax", https_only=settings.public_url.startswith("https"))

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(self)")
        path = request.url.path
        if path.startswith("/app/assets/"):  # content-hashed build output
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif path.startswith("/static/"):
            response.headers.setdefault("Cache-Control", "public, max-age=604800")
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        if request.url.path.startswith("/api/"):
            detail = exc.detail if isinstance(exc.detail, dict) else {"message": exc.detail}
            return JSONResponse(detail, status_code=exc.status_code)
        if exc.status_code == 401:
            from fastapi.responses import RedirectResponse

            return RedirectResponse("/app/login", status_code=303)
        return HTMLResponse(site.render_error(request, exc.status_code), status_code=exc.status_code)

    for module in (auth_routes, lead_routes, org_routes, admin_routes):
        app.include_router(module.router)
    app.include_router(org_routes.public)
    app.include_router(site.router)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    app.add_middleware(GZipMiddleware, minimum_size=800, compresslevel=6)
    mimetypes.add_type("image/webp", ".webp")  # slim images have no /etc/mime.types; Python 3.12 lacks webp
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    @app.get("/app")
    @app.get("/app/{path:path}")
    def spa(path: str = ""):
        index = APP_DIST / "index.html"
        if not index.exists():
            return HTMLResponse("<h1>App not built</h1><p>Run <code>npm run build</code> in <code>frontend/</code>.</p>",
                                status_code=503)
        asset = APP_DIST / path
        if path and asset.is_file() and APP_DIST in asset.resolve().parents:
            return FileResponse(asset)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
