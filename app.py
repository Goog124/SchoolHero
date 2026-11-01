"""School Hero — a MAX mini app with a FastAPI + SQLite backend.

Run ``python app.py`` after building the frontend (``npm run build`` in
``frontend/``). During frontend development use Vite on :5173; it proxies
``/api`` to this server on :8000.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from backend.api import router as api_router
from backend.config import Settings
from backend.db import connect, init_db
from backend.seed import seed_database
from backend.service import GameError

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass


settings = Settings.from_env()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        seed_database(conn)
    finally:
        conn.close()
    yield


app = FastAPI(
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


@app.get("/", include_in_schema=False)
def index():
    built = _static_file("index.html")
    if built:
        return FileResponse(built)
    return HTMLResponse(
        """
        <!doctype html><html lang="ru"><meta charset="utf-8">
        <title>Школьный герой</title>
        <body style="font-family:system-ui;background:#12091f;color:#f5ecff;padding:40px">
        <h1>Школьный герой</h1>
        <p>Фронтенд ещё не собран.</p>
        <p>Для разработки: <code>cd frontend &amp;&amp; npm install &amp;&amp; npm run dev</code>.</p>
        <p>Для сборки: <code>npm run build</code>, затем перезапустите сервер.</p>
        </body></html>
        """,
        status_code=200,
    )


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
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
