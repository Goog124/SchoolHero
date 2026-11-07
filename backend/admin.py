"""Platform administrator panel: all schools, users, deleting a school,
blocking users. Every function here is for the platform admin only; anyone
else gets 404, so the panel does not reveal that it exists."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import Settings
from .db import immediate
from .game import iso_utc, normalize_timezone, utc_sql
from .registration import _class_sort_key, _clean, is_platform_admin
from .service import GameError, full_name

log = logging.getLogger("uvicorn.error")

PAGE_LIMIT = 50
SCHOOL_FILTERS = ("pending", "active", "rejected")
BLOCKED_MESSAGE = "Доступ к приложению ограничен"


def require_admin(viewer: sqlite3.Row, settings: Settings) -> None:
    if not is_platform_admin(viewer, settings):
        raise GameError("Не найдено", 404)


def _week_ago_day() -> str:
    """First day (ISO date) of the "last 7 days" window, counted in UTC."""
    return (datetime.now(timezone.utc).date() - timedelta(days=6)).isoformat()


def _like(query: str) -> str:
    escaped = query.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _page(offset: int, limit: int) -> tuple[int, int]:
    return max(0, int(offset)), max(1, min(PAGE_LIMIT, int(limit)))


# ---------------------------------------------------------------------------
# Summary and schools
# ---------------------------------------------------------------------------


def platform_summary(conn) -> dict[str, Any]:
    schools = {"pending": 0, "active": 0, "rejected": 0}
    for row in conn.execute("SELECT status, COUNT(*) AS n FROM schools GROUP BY status"):
        schools[row["status"]] = schools.get(row["status"], 0) + int(row["n"])
    users = {"student": 0, "teacher": 0, "director": 0}
    for row in conn.execute("SELECT role, COUNT(*) AS n FROM users GROUP BY role"):
        users[row["role"]] = int(row["n"])
    extra = conn.execute(
        """
        SELECT
          (SELECT COUNT(DISTINCT a.user_id) FROM activity_days a
             JOIN users u ON u.id = a.user_id
             WHERE u.role = 'student' AND a.day >= ?) AS active_students,
          (SELECT COUNT(*) FROM completions WHERE status = 'pending') AS pending_works,
          (SELECT COUNT(*) FROM users WHERE blocked_at IS NOT NULL) AS blocked
        """,
        (_week_ago_day(),),
    ).fetchone()
    return {
        "schools": {**schools, "total": sum(schools.values())},
        "users": {**users, "total": sum(users.values())},
        "active_students_week": int(extra["active_students"]),
        "pending_works": int(extra["pending_works"]),
        "blocked_users": int(extra["blocked"]),
    }


_SCHOOL_SELECT = """
    SELECT s.id, s.name, s.city, s.timezone, s.status, s.created_at, s.reject_reason,
           u.first_name AS dir_first, u.last_name AS dir_last,
           (SELECT COUNT(*) FROM classes c WHERE c.school_id = s.id) AS classes,
           (SELECT COUNT(*) FROM users x JOIN classes c ON c.id = x.class_id
              WHERE c.school_id = s.id AND x.role = 'student') AS students,
           (SELECT COUNT(*) FROM users x JOIN classes c ON c.id = x.class_id
              WHERE c.school_id = s.id AND x.role = 'teacher') AS teachers,
           (SELECT COUNT(DISTINCT a.user_id) FROM activity_days a
              JOIN users x ON x.id = a.user_id JOIN classes c ON c.id = x.class_id
              WHERE c.school_id = s.id AND x.role = 'student' AND a.day >= ?) AS active_week
    FROM schools s
    LEFT JOIN users u ON u.id = COALESCE(
        s.created_by, (SELECT MIN(user_id) FROM school_staff WHERE school_id = s.id))
"""


def _school_item(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "name": row["name"],
        "city": row["city"],
        "timezone": normalize_timezone(row["timezone"]),
        "status": row["status"],
        "created_at": iso_utc(row["created_at"]) if row["created_at"] else "",
        "director": f"{row['dir_first'] or ''} {row['dir_last'] or ''}".strip(),
        "classes": int(row["classes"]),
        "students": int(row["students"]),
        "teachers": int(row["teachers"]),
        "active_week": int(row["active_week"]),
        "reject_reason": row["reject_reason"] or "",
    }


def list_schools(
    conn,
    viewer: sqlite3.Row,
    settings: Settings,
    status: str = "",
    q: str = "",
    offset: int = 0,
    limit: int = PAGE_LIMIT,
) -> dict[str, Any]:
    require_admin(viewer, settings)
    status = (status or "").strip()
    if status in {"", "all"}:
        status = ""
    elif status not in SCHOOL_FILTERS:
        raise GameError("Неизвестный статус")
    offset, limit = _page(offset, limit)
    where, params = [], []
    if status:
        where.append("s.status = ?")
        params.append(status)
    query = _clean(q)
    if query:
        where.append("(casefold(s.name) LIKE ? ESCAPE '\\' OR casefold(s.city) LIKE ? ESCAPE '\\')")
        params += [_like(query), _like(query)]
    clause = f" WHERE {' AND '.join(where)}" if where else ""
    total = int(
        conn.execute(f"SELECT COUNT(*) FROM schools s{clause}", params).fetchone()[0]
    )
    rows = conn.execute(
        f"{_SCHOOL_SELECT}{clause} ORDER BY s.id DESC LIMIT ? OFFSET ?",
        [_week_ago_day(), *params, limit, offset],
    ).fetchall()
    return {
        "items": [_school_item(r) for r in rows],
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(rows) < total,
        "summary": platform_summary(conn),
    }


def school_detail(conn, viewer: sqlite3.Row, settings: Settings, school_id: int) -> dict[str, Any]:
    """Read-only card of a school: classes with head counts, no codes."""
    require_admin(viewer, settings)
    row = conn.execute(
        f"{_SCHOOL_SELECT} WHERE s.id = ?", (_week_ago_day(), school_id)
    ).fetchone()
    if row is None:
        raise GameError("Школа не найдена", 404)
    classes = [
        {
            "id": int(c["id"]),
            "name": c["name"],
            "students": int(c["students"]),
            "teachers": int(c["teachers"]),
            "teacher_names": [],
        }
        for c in conn.execute(
            """
            SELECT c.id, c.name,
                   (SELECT COUNT(*) FROM users u WHERE u.class_id = c.id AND u.role = 'student') AS students,
                   (SELECT COUNT(*) FROM users u WHERE u.class_id = c.id AND u.role = 'teacher') AS teachers
            FROM classes c WHERE c.school_id = ?
            """,
            (school_id,),
        ).fetchall()
    ]
    by_id = {c["id"]: c for c in classes}
    for t in conn.execute(
        "SELECT u.class_id, u.first_name, u.last_name FROM users u "
        "JOIN classes c ON c.id = u.class_id WHERE c.school_id = ? AND u.role = 'teacher' "
        "ORDER BY u.id",
        (school_id,),
    ).fetchall():
        by_id[int(t["class_id"])]["teacher_names"].append(
            f"{t['first_name'] or ''} {t['last_name'] or ''}".strip()
        )
    classes.sort(key=_class_sort_key)
    return {"school": _school_item(row), "classes": classes}


# ---------------------------------------------------------------------------
# Deleting a school
# ---------------------------------------------------------------------------


def _marks(ids: list[int]) -> str:
    return ",".join("?" for _ in ids)


def delete_school(
    conn,
    viewer: sqlite3.Row,
    settings: Settings,
    school_id: int,
    confirm_name: Any,
) -> dict[str, int]:
    """Delete a school for good, in one transaction.

    Removed: classes, challenges, submissions (completions) with their photo
    rows, join requests, exclusions, class_staff, school_staff and the XP
    events of the classes. Users stay: pupils and teachers lose the class
    (teachers keep the role and are marked detached, like after a director
    disconnects them), directors lose the school. ``users.xp`` / ``sparks`` /
    purchases are not touched. Photo files are removed from disk after the
    commit. Returns what was removed.
    """
    require_admin(viewer, settings)
    school = conn.execute("SELECT * FROM schools WHERE id = ?", (school_id,)).fetchone()
    if school is None:
        raise GameError("Школа не найдена", 404)
    if _clean(confirm_name) != _clean(school["name"]):
        raise GameError("Название школы введено неверно. Удаление отменено.")

    files: list[str] = []
    with immediate(conn):
        class_ids = [
            int(r["id"])
            for r in conn.execute("SELECT id FROM classes WHERE school_id = ?", (school_id,))
        ]
        challenge_ids: list[int] = []
        completion_ids: list[int] = []
        if class_ids:
            cm = _marks(class_ids)
            challenge_ids = [
                int(r["id"])
                for r in conn.execute(
                    f"SELECT id FROM challenges WHERE class_id IN ({cm})", class_ids
                )
            ]
        if challenge_ids:
            chm = _marks(challenge_ids)
            completion_ids = [
                int(r["id"])
                for r in conn.execute(
                    f"SELECT id FROM completions WHERE challenge_id IN ({chm})", challenge_ids
                )
            ]
        upload_ids: set[int] = set()
        if completion_ids:
            com = _marks(completion_ids)
            for r in conn.execute(
                f"SELECT id, path FROM uploads WHERE completion_id IN ({com}) "
                f"OR id IN (SELECT upload_id FROM completions WHERE id IN ({com}) "
                "AND upload_id IS NOT NULL)",
                [*completion_ids, *completion_ids],
            ).fetchall():
                upload_ids.add(int(r["id"]))
                files.append(r["path"])

        result = {
            "classes": len(class_ids),
            "challenges": len(challenge_ids),
            "completions": len(completion_ids),
            "uploads": len(upload_ids),
            "students": 0,
            "teachers": 0,
            "directors": 0,
            "xp_events": 0,
            "join_requests": 0,
            "exclusions": 0,
        }
        if upload_ids:
            ids = sorted(upload_ids)
            conn.execute(f"DELETE FROM uploads WHERE id IN ({_marks(ids)})", ids)
        if completion_ids:
            conn.execute(
                f"DELETE FROM completions WHERE id IN ({_marks(completion_ids)})", completion_ids
            )
        if challenge_ids:
            conn.execute(
                f"DELETE FROM challenges WHERE id IN ({_marks(challenge_ids)})", challenge_ids
            )
        if class_ids:
            cm = _marks(class_ids)
            result["students"] = int(
                conn.execute(
                    f"SELECT COUNT(*) FROM users WHERE role = 'student' AND class_id IN ({cm})",
                    class_ids,
                ).fetchone()[0]
            )
            result["teachers"] = int(
                conn.execute(
                    f"SELECT COUNT(*) FROM users WHERE role = 'teacher' AND class_id IN ({cm})",
                    class_ids,
                ).fetchone()[0]
            )
            # Teachers: like a disconnect, so env lists do not reattach them.
            conn.execute(
                f"UPDATE users SET class_id = NULL, class_since = NULL, staff_detached = 1 "
                f"WHERE role = 'teacher' AND class_id IN ({cm})",
                class_ids,
            )
            conn.execute(
                f"UPDATE users SET class_id = NULL, class_since = NULL WHERE class_id IN ({cm})",
                class_ids,
            )
            result["xp_events"] = conn.execute(
                f"DELETE FROM xp_events WHERE class_id IN ({cm})", class_ids
            ).rowcount
            result["join_requests"] = conn.execute(
                f"DELETE FROM join_requests WHERE class_id IN ({cm})", class_ids
            ).rowcount
            result["exclusions"] = conn.execute(
                f"DELETE FROM class_exclusions WHERE class_id IN ({cm})", class_ids
            ).rowcount
            conn.execute(f"DELETE FROM class_staff WHERE class_id IN ({cm})", class_ids)
            conn.execute(f"DELETE FROM classes WHERE id IN ({cm})", class_ids)
        result["directors"] = int(
            conn.execute(
                "SELECT COUNT(*) FROM school_staff WHERE school_id = ?", (school_id,)
            ).fetchone()[0]
        )
        conn.execute("DELETE FROM school_staff WHERE school_id = ?", (school_id,))
        conn.execute("UPDATE users SET school_id = NULL WHERE school_id = ?", (school_id,))
        conn.execute("DELETE FROM schools WHERE id = ?", (school_id,))

    removed_files = 0
    base = settings.upload_dir
    for name in files:
        try:
            (base / Path(name).name).unlink(missing_ok=True)
            removed_files += 1
        except OSError:
            log.warning("Не удалось удалить файл загрузки %s удалённой школы", name)
    result["files_removed"] = removed_files
    log.warning(
        "Администратор платформы user_id=%s удалил школу id=%s «%s» (%s): %s",
        viewer["id"],
        school_id,
        school["name"],
        school["city"],
        ", ".join(f"{key}={value}" for key, value in result.items()),
    )
    return result


# ---------------------------------------------------------------------------
# Users and blocking
# ---------------------------------------------------------------------------


def _user_item(row: sqlite3.Row, settings: Settings, viewer_id: int) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "name": full_name(row) or "—",
        "role": row["role"],
        "external_id": row["max_user_id"] or row["client_id"] or "",
        "school": row["school_name"] or "",
        "class_name": row["class_name"] or "",
        "created_at": iso_utc(row["created_at"]) if row["created_at"] else "",
        "last_active": row["last_active"] or "",
        "blocked": row["blocked_at"] is not None,
        "blocked_at": iso_utc(row["blocked_at"]) if row["blocked_at"] else "",
        "blocked_reason": row["blocked_reason"] or "",
        "is_admin": is_platform_admin(row, settings),
        "is_self": int(row["id"]) == viewer_id,
    }


_USER_SELECT = """
    SELECT u.*, c.name AS class_name,
           COALESCE(sc.name, ss.name) AS school_name,
           (SELECT MAX(a.day) FROM activity_days a WHERE a.user_id = u.id) AS last_active
    FROM users u
    LEFT JOIN classes c ON c.id = u.class_id
    LEFT JOIN schools sc ON sc.id = c.school_id
    LEFT JOIN schools ss ON ss.id = u.school_id
"""


def list_users(
    conn,
    viewer: sqlite3.Row,
    settings: Settings,
    q: str = "",
    offset: int = 0,
    limit: int = PAGE_LIMIT,
    blocked_only: bool = False,
) -> dict[str, Any]:
    require_admin(viewer, settings)
    offset, limit = _page(offset, limit)
    where, params = [], []
    query = _clean(q)
    if query:
        pattern = _like(query)
        where.append(
            "(casefold(TRIM(u.first_name || ' ' || u.last_name)) LIKE ? ESCAPE '\\' "
            "OR casefold(u.username) LIKE ? ESCAPE '\\' "
            "OR u.max_user_id = ? OR u.client_id = ? "
            "OR casefold(u.client_id) LIKE ? ESCAPE '\\')"
        )
        params += [pattern, pattern, query, query, pattern]
    if blocked_only:
        where.append("u.blocked_at IS NOT NULL")
    clause = f" WHERE {' AND '.join(where)}" if where else ""
    total = int(conn.execute(f"SELECT COUNT(*) FROM users u{clause}", params).fetchone()[0])
    rows = conn.execute(
        f"{_USER_SELECT}{clause} ORDER BY u.id DESC LIMIT ? OFFSET ?", [*params, limit, offset]
    ).fetchall()
    viewer_id = int(viewer["id"])
    return {
        "items": [_user_item(r, settings, viewer_id) for r in rows],
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(rows) < total,
        "summary": platform_summary(conn),
    }


def _load_user_item(conn, user_id: int, settings: Settings, viewer_id: int) -> dict[str, Any]:
    row = conn.execute(f"{_USER_SELECT} WHERE u.id = ?", (user_id,)).fetchone()
    if row is None:
        raise GameError("Пользователь не найден", 404)
    return _user_item(row, settings, viewer_id)


def block_user(
    conn, viewer: sqlite3.Row, settings: Settings, user_id: int, reason: Any
) -> dict[str, Any]:
    require_admin(viewer, settings)
    target = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if target is None:
        raise GameError("Пользователь не найден", 404)
    if int(target["id"]) == int(viewer["id"]):
        raise GameError("Нельзя заблокировать самого себя")
    if is_platform_admin(target, settings):
        raise GameError("Администратора платформы заблокировать нельзя")
    note = _clean(reason)[:200]
    if len(note) < 3:
        raise GameError("Укажите причину блокировки (от 3 символов)")
    with immediate(conn):
        conn.execute(
            "UPDATE users SET blocked_at = COALESCE(blocked_at, ?), blocked_reason = ? WHERE id = ?",
            (utc_sql(), note, user_id),
        )
    log.warning(
        "Администратор платформы user_id=%s заблокировал пользователя id=%s: %s",
        viewer["id"], user_id, note,
    )
    return _load_user_item(conn, user_id, settings, int(viewer["id"]))


def unblock_user(
    conn, viewer: sqlite3.Row, settings: Settings, user_id: int
) -> dict[str, Any]:
    require_admin(viewer, settings)
    if conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone() is None:
        raise GameError("Пользователь не найден", 404)
    with immediate(conn):
        conn.execute(
            "UPDATE users SET blocked_at = NULL, blocked_reason = '' WHERE id = ?", (user_id,)
        )
    log.warning(
        "Администратор платформы user_id=%s разблокировал пользователя id=%s",
        viewer["id"], user_id,
    )
    return _load_user_item(conn, user_id, settings, int(viewer["id"]))


def is_blocked(user: sqlite3.Row, settings: Settings) -> bool:
    """True when the user is blocked; a platform admin is never locked out."""
    if user["blocked_at"] is None:
        return False
    return not is_platform_admin(user, settings)
