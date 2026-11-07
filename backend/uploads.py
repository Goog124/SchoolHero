"""Photos sent as proof of a challenge.

POST /api/uploads takes the raw image bytes (no multipart) and answers
``{"id": ...}``; the id is then passed to the submit endpoint, which attaches
the photo to the work. GET /api/uploads/{id} returns the file to its author,
the staff of the class of the challenge and the director of the school.
Files live in ``settings.upload_dir`` under a random name, mode 600.
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from .api import Context, IdPath, get_context
from .config import Settings
from .db import immediate
from .game import day_start_utc_sql
from .service import GameError, can_manage_class, class_timezone, effective_role

log = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api")

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_UPLOADS_PER_DAY = 30
ORPHAN_MAX_AGE = "-1 day"

EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def sniff_type(head: bytes) -> str | None:
    """Image type by the first bytes of the file, None if not a supported image."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def _too_large() -> GameError:
    return GameError("Файл больше 5 МБ. Выберите фото поменьше.", 413)


def _uploads_today(conn, user_id: int, tz: str) -> int:
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM uploads WHERE user_id = ? AND created_at >= ?",
            (user_id, day_start_utc_sql(tz)),
        ).fetchone()[0]
    )


def _limit_error() -> GameError:
    return GameError(
        f"Лимит загрузок: {MAX_UPLOADS_PER_DAY} фото в день. Попробуйте завтра.", 429
    )


@router.post("/uploads")
async def upload_photo(request: Request, ctx: Context = Depends(get_context)) -> dict[str, Any]:
    settings: Settings = ctx.settings
    viewer = ctx.user
    if effective_role(viewer, settings) != "student" or viewer["class_id"] is None:
        raise GameError("Загружать фото могут только ученики класса", 403)
    declared = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if declared not in EXTENSIONS:
        raise GameError("Поддерживаются JPEG, PNG и WebP", 415)
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_UPLOAD_BYTES:
        raise _too_large()
    tz = class_timezone(ctx.conn, int(viewer["class_id"]))
    if _uploads_today(ctx.conn, int(viewer["id"]), tz) >= MAX_UPLOADS_PER_DAY:
        raise _limit_error()

    directory = settings.upload_dir
    directory.mkdir(parents=True, exist_ok=True)
    name = uuid.uuid4().hex + EXTENSIONS[declared]
    path = directory / name
    size = 0
    head = b""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
        with os.fdopen(fd, "wb") as out:
            async for chunk in request.stream():
                if not chunk:
                    continue
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise _too_large()
                if len(head) < 12:
                    head = (head + chunk)[:12]
                out.write(chunk)
        if size == 0:
            raise GameError("Файл пустой")
        if sniff_type(head) != declared:
            raise GameError("Содержимое файла не соответствует типу изображения", 415)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        with immediate(ctx.conn):
            if _uploads_today(ctx.conn, int(viewer["id"]), tz) >= MAX_UPLOADS_PER_DAY:
                raise _limit_error()
            cursor = ctx.conn.execute(
                "INSERT INTO uploads (user_id, path, content_type, size) VALUES (?, ?, ?, ?)",
                (viewer["id"], name, declared, size),
            )
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return {"id": int(cursor.lastrowid)}


@router.get("/uploads/{upload_id}")
def get_upload(upload_id: IdPath, ctx: Context = Depends(get_context)) -> Response:
    conn, viewer = ctx.conn, ctx.user
    row = conn.execute(
        """
        SELECT up.*, ch.class_id AS challenge_class_id
        FROM uploads up
        LEFT JOIN completions cp ON cp.id = up.completion_id
        LEFT JOIN challenges ch ON ch.id = cp.challenge_id
        WHERE up.id = ?
        """,
        (upload_id,),
    ).fetchone()
    allowed = False
    if row is not None:
        allowed = int(row["user_id"]) == int(viewer["id"]) or (
            row["challenge_class_id"] is not None
            and can_manage_class(conn, viewer, ctx.settings, int(row["challenge_class_id"]))
        )
    path = ctx.settings.upload_dir / Path(row["path"]).name if row is not None else None
    if not allowed or path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Фото не найдено")
    return Response(
        content=path.read_bytes(),
        media_type=row["content_type"],
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )


def cleanup_orphan_uploads(conn, settings: Settings) -> int:
    """Remove photos that were uploaded but never attached to a submission
    (older than a day): file and row. Returns the number removed."""
    rows = conn.execute(
        "SELECT id, path FROM uploads WHERE completion_id IS NULL "
        "AND created_at < datetime('now', ?)",
        (ORPHAN_MAX_AGE,),
    ).fetchall()
    for row in rows:
        try:
            (settings.upload_dir / Path(row["path"]).name).unlink(missing_ok=True)
        except OSError:
            log.warning("Не удалось удалить файл загрузки %s", row["path"])
            continue
        conn.execute("DELETE FROM uploads WHERE id = ?", (row["id"],))
    conn.commit()
    return len(rows)
