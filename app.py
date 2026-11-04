"""School Hero — a MAX mini app with a FastAPI + SQLite backend.

Run ``python app.py`` after building the frontend (``npm run build`` in
``frontend/``). During frontend development use Vite on :5173; it proxies
``/api`` to this server on :8000.
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


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    # MAX opens mini apps inside its clients (and the web client may embed the
    # page in a frame), so allow MAX hosts instead of blocking framing outright.
    response.headers["Content-Security-Policy"] = (
        "frame-ancestors 'self' https://max.ru https://*.max.ru"
    )
    if request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif request.url.path == "/" or request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(api_router)


def _static_file(path: str) -> Path | None:
    base = settings.static_dir.resolve()
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
def index():
    if not settings.serve_frontend:
        return {
            "service": "schoolhero-api",
            "status": "ok",
            "api": "/api",
            "docs": "/docs",
            "frontend": "http://127.0.0.1:5173",
            "portal": "/portal",
        }
    built = _static_file("index.html")
    if built:
        return FileResponse(built)
    return JSONResponse(
        status_code=503,
        content={"service": "schoolhero-api", "detail": "Frontend is not built"},
    )


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    if not _docs_enabled and full_path.rstrip("/") in {"docs", "redoc", "openapi.json"}:
        raise HTTPException(status_code=404, detail="Not found")
    if not settings.serve_frontend:
        raise HTTPException(status_code=404, detail="API server does not serve frontend")
    candidate = _static_file(full_path)
    if candidate:
        return FileResponse(candidate)
    if Path(full_path).suffix:
        raise HTTPException(status_code=404, detail="Not found")
    built = _static_file("index.html")
    if built:
        return FileResponse(built)
    raise HTTPException(status_code=404, detail="Frontend is not built")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        reload=False,
    )
