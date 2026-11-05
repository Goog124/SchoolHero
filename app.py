"""School Hero — a MAX mini app with a FastAPI + SQLite backend.

Run ``python app.py`` after building the frontend (``npm run build`` in
``frontend/``). During frontend development use Vite on :5173; it proxies
``/api`` to this server on :8000.

``python app.py`` binds to ``HOST``/``PORT`` from the validated settings, so
``APP_MODE=sandbox`` (and ``demo`` without ``ALLOW_PUBLIC_DEMO=1``) cannot be
bound to a public address this way. Starting ``uvicorn app:app --host ...``
directly bypasses that check and is not supported for demo/sandbox.
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from backend.api import router as api_router
from backend.maxbot import router as maxbot_router
from backend.config import Settings
from backend.db import connect, init_db
from backend.catalog import import_catalog
from backend.demo_seed import seed_demo_database
from backend.service import GameError

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass


settings = Settings.from_env()


def _sandbox_boot_id(cfg: Settings, db_existed: bool) -> str:
    """Identifies one life of the sandbox database.

    A new value whenever the database was wiped; otherwise the value stored
    next to the database is reused, so a client can tell whether
    its remembered test users still exist on the server.
    """
    path = cfg.db_path.with_name("sandbox_boot_id")
    if not cfg.sandbox_wipe and db_existed:
        try:
            stored = path.read_text(encoding="utf-8").strip()
            if stored:
                return stored
        except OSError:
            pass
    value = uuid.uuid4().hex
    try:
        path.write_text(value, encoding="utf-8")
    except OSError:
        pass
    return value


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.validate()
    if settings.sandbox_mode and settings.sandbox_wipe:
        for suffix in ("", "-wal", "-shm"):
            Path(str(settings.db_path) + suffix).unlink(missing_ok=True)
    if settings.sandbox_mode:
        app.state.boot_id = _sandbox_boot_id(settings, settings.db_path.exists())
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        if settings.demo_mode:
            seed_demo_database(conn)
        elif settings.sandbox_mode:
            pass  # empty by design: no demo data, no catalog
        else:
            # catalog.json is an optional initial fill; without it production
            # starts empty and schools register themselves.
            import_catalog(conn, settings.catalog_file)
            if settings.default_class_id is not None and not conn.execute(
                "SELECT 1 FROM classes WHERE id = ?", (settings.default_class_id,)
            ).fetchone():
                # Production may start empty: users pick a class during
                # registration, so a missing default class is not an error.
                logging.getLogger("uvicorn.error").warning(
                    "DEFAULT_CLASS_ID=%s не найден, класс по умолчанию отключён",
                    settings.default_class_id,
                )
                object.__setattr__(settings, "default_class_id", None)
    finally:
        conn.close()
    yield


# Interactive API docs are for demo/sandbox only; production does not publish
# the schema.
_docs_enabled = settings.app_mode != "prod"
app = FastAPI(
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
    title="Школьный герой",
    description="Мини-приложение для MAX: прокачивай героя за учёбу и школьную активность.",
    version="1.0.0",
    lifespan=lifespan,
)
app.state.settings = settings


@app.exception_handler(GameError)
async def game_error_handler(_: Request, exc: GameError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content={"detail": exc.message})


# SPA policy: own scripts plus the MAX bridge; images may come from https links
# students attach as proof; inline style attributes are used by React/SVG.
# MAX opens mini apps inside its clients (and the web client may embed the
# page in a frame), so framing is allowed for MAX hosts via frame-ancestors
# (no X-Frame-Options, it cannot express an allow-list).
CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self' https://st.max.ru",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: https:",
        "font-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'self' https://max.ru https://*.max.ru",
    ]
)
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"


_DOC_PATHS = {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    # Docs routes are registered at import; hide them whenever the running
    # settings are prod (also when tests/lifespan swapped the settings).
    if request.url.path.rstrip("/") in _DOC_PATHS and _settings(request).app_mode == "prod":
        response = JSONResponse(status_code=404, content={"detail": "Not found"})
    else:
        response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
    response.headers["Permissions-Policy"] = PERMISSIONS_POLICY
    if request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif request.url.path == "/" or request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(api_router)
app.include_router(maxbot_router)


def _settings(request: Request) -> Settings:
    """Settings of the running app (tests and the lifespan may replace them)."""
    return getattr(request.app.state, "settings", settings)


def _static_file(cfg: Settings, path: str) -> Path | None:
    base = cfg.static_dir.resolve()
    candidate = (base / path).resolve()
    if not candidate.is_relative_to(base):
        return None
    return candidate if candidate.is_file() else None


@app.get("/portal", include_in_schema=False)
@app.get("/landing", include_in_schema=False)
@app.get("/about", include_in_schema=False)
def portal():
    portal_file = Path(__file__).resolve().parent / "landing" / "index.html"
    if portal_file.is_file():
        return FileResponse(portal_file)
    raise HTTPException(status_code=404, detail="Portal landing page is not found")


@app.get("/landing/{file_name:path}", include_in_schema=False)
def landing_static(file_name: str):
    landing_dir = (Path(__file__).resolve().parent / "landing").resolve()
    candidate = (landing_dir / file_name).resolve()
    if candidate.is_relative_to(landing_dir) and candidate.is_file():
        return FileResponse(candidate)
    raise HTTPException(status_code=404, detail="Landing asset not found")


@app.get("/", include_in_schema=False)
def index(request: Request):
    cfg = _settings(request)
    if not cfg.serve_frontend:
        return {
            "service": "schoolhero-api",
            "status": "ok",
            "api": "/api",
            "docs": "/docs" if cfg.app_mode != "prod" else None,
            "frontend": "http://127.0.0.1:5173",
            "portal": "/portal",
        }
    built = _static_file(cfg, "index.html")
    if built:
        return FileResponse(built)
    return JSONResponse(
        status_code=503,
        content={"service": "schoolhero-api", "detail": "Frontend is not built"},
    )


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(request: Request, full_path: str):
    cfg = _settings(request)
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    if cfg.app_mode == "prod" and full_path.rstrip("/") in {"docs", "redoc", "openapi.json"}:
        raise HTTPException(status_code=404, detail="Not found")
    if not cfg.serve_frontend:
        raise HTTPException(status_code=404, detail="API server does not serve frontend")
    candidate = _static_file(cfg, full_path)
    if candidate:
        return FileResponse(candidate)
    if Path(full_path).suffix:
        raise HTTPException(status_code=404, detail="Not found")
    built = _static_file(cfg, "index.html")
    if built:
        return FileResponse(built)
    raise HTTPException(status_code=404, detail="Frontend is not built")


if __name__ == "__main__":
    import uvicorn

    # Validate before binding: the address comes from the same settings that
    # validate() checked, so sandbox/demo cannot be bound to 0.0.0.0 here.
    settings.validate()
    uvicorn.run(
        app,
        host=settings.host,
        port=int(os.getenv("PORT", "8000")),
        reload=False,
    )
