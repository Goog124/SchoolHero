"""Join requests: choosing a class from the public school list.

The catalog of schools and classes is public, so picking a class there must
not grant access to the class (names, avatars and XP of children). It files a
request that the class teacher or the school director approves. A student
code still joins at once: whoever has it got it from the school.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from .config import Settings
from .db import immediate
from .game import iso_utc, load_avatar
from .service import (
    GameError,
    _class_for_join,
    can_manage_class,
    check_not_excluded,
    full_name,
    is_excluded,
    EXCLUDED_MESSAGE,
)

JOIN_REQUESTS_PER_DAY = 5
JOIN_REQUESTS_SHOWN = 100


def _pending_for_user(conn, user_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT r.*, c.name AS class_name, s.name AS school_name
        FROM join_requests r
        JOIN classes c ON c.id = r.class_id
        JOIN schools s ON s.id = c.school_id
        WHERE r.user_id = ? AND r.status = 'pending'
        """,
        (user_id,),
    ).fetchone()


def _request_public(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "status": row["status"],
        "class_id": int(row["class_id"]),
        "class_name": row["class_name"],
        "school_name": row["school_name"],
        "created_at": iso_utc(row["created_at"]),
        "decided_at": iso_utc(row["decided_at"]) if row["decided_at"] else None,
    }


def create_join_request(
    conn, viewer: sqlite3.Row, settings: Settings, class_id: int
) -> dict[str, Any]:
    """File a request to join a class picked from the list.

    One active request per student and at most JOIN_REQUESTS_PER_DAY a day,
    so teachers are not flooded. A student excluded from any class of the
    school cannot ask for any class of it.
    """
    if viewer["role"] != "student":
        raise GameError("Подать заявку в класс может только ученик", 403)
    _class_for_join(conn, int(class_id))  # 404 for unknown or not approved
    with immediate(conn):
        user = conn.execute("SELECT * FROM users WHERE id = ?", (viewer["id"],)).fetchone()
        if user["class_id"] is not None and int(user["class_id"]) == int(class_id):
            raise GameError("Вы уже состоите в этом классе")
        check_not_excluded(conn, int(user["id"]), int(class_id))
        existing = _pending_for_user(conn, int(user["id"]))
        if existing is not None:
            if int(existing["class_id"]) == int(class_id):
                return _request_public(existing)
            raise GameError(
                f"У вас уже есть заявка в класс {existing['class_name']}. "
                "Отмените её, чтобы подать новую.",
                409,
            )
        today = conn.execute(
            "SELECT COUNT(*) FROM join_requests "
            "WHERE user_id = ? AND created_at >= datetime('now', '-1 day')",
            (user["id"],),
        ).fetchone()[0]
        if today >= JOIN_REQUESTS_PER_DAY:
            raise GameError(
                f"Не больше {JOIN_REQUESTS_PER_DAY} заявок в сутки. "
                "Попробуйте завтра или войдите по коду класса.",
                429,
            )
        cursor = conn.execute(
            "INSERT INTO join_requests (user_id, class_id, status) VALUES (?, ?, 'pending')",
            (user["id"], class_id),
        )
        request_id = int(cursor.lastrowid)
    row = conn.execute(
        """
        SELECT r.*, c.name AS class_name, s.name AS school_name
        FROM join_requests r JOIN classes c ON c.id = r.class_id
        JOIN schools s ON s.id = c.school_id WHERE r.id = ?
        """,
        (request_id,),
    ).fetchone()
    return _request_public(row)


def cancel_pending(conn, user_id: int, by: int | None, status: str = "cancelled") -> None:
    """Close the student's active request (joined by code, removed, cancelled)."""
    conn.execute(
        "UPDATE join_requests SET status = ?, decided_at = datetime('now'), decided_by = ? "
        "WHERE user_id = ? AND status = 'pending'",
        (status, by, user_id),
    )


def cancel_join_request(conn, viewer: sqlite3.Row) -> None:
    with immediate(conn):
        if _pending_for_user(conn, int(viewer["id"])) is None:
            raise GameError("Активной заявки нет", 404)
        cancel_pending(conn, int(viewer["id"]), int(viewer["id"]))


def decide_join_request(
    conn, viewer: sqlite3.Row, settings: Settings, request_id: int, action: str
) -> dict[str, Any]:
    """Approve or decline. Only the class teacher or the school director may,
    others get 404 (the request is not theirs to see)."""
    if action not in {"approve", "decline"}:
        raise GameError("Неизвестное действие")
    with immediate(conn):
        req = conn.execute("SELECT * FROM join_requests WHERE id = ?", (request_id,)).fetchone()
        if req is None or not can_manage_class(conn, viewer, settings, int(req["class_id"])):
            raise GameError("Заявка не найдена", 404)
        if req["status"] != "pending":
            raise GameError("Заявка уже рассмотрена", 409)
        student = conn.execute("SELECT * FROM users WHERE id = ?", (req["user_id"],)).fetchone()
        if action == "approve":
            if student is None or student["role"] != "student":
                raise GameError("Этот пользователь больше не ученик. Отклоните заявку.", 409)
            if is_excluded(conn, int(student["id"]), int(req["class_id"])):
                raise GameError(f"{EXCLUDED_MESSAGE} Отклоните заявку.", 409)
            _class_for_join(conn, int(req["class_id"]))
            # Approval moves the student: leaving the previous class, if any.
            conn.execute(
                "UPDATE users SET class_id = ?, class_since = datetime('now') WHERE id = ?",
                (req["class_id"], student["id"]),
            )
        conn.execute(
            "UPDATE join_requests SET status = ?, decided_at = datetime('now'), decided_by = ? "
            "WHERE id = ?",
            ("approved" if action == "approve" else "declined", viewer["id"], request_id),
        )
    return {
        "status": "approved" if action == "approve" else "declined",
        "student_name": full_name(student) if student else "",
    }


def pending_requests(conn, class_ids: list[int]) -> list[dict[str, Any]]:
    """Active requests to the given classes, oldest first."""
    if not class_ids:
        return []
    marks = ",".join("?" for _ in class_ids)
    rows = conn.execute(
        f"""
        SELECT r.id, r.class_id, r.created_at, c.name AS class_name, c.school_id,
               u.id AS student_id, u.first_name, u.last_name, u.avatar,
               cur.name AS current_class
        FROM join_requests r
        JOIN users u ON u.id = r.user_id
        JOIN classes c ON c.id = r.class_id
        LEFT JOIN classes cur ON cur.id = u.class_id
        WHERE r.status = 'pending' AND r.class_id IN ({marks})
        ORDER BY r.created_at, r.id
        LIMIT ?
        """,
        (*class_ids, JOIN_REQUESTS_SHOWN),
    ).fetchall()
    return [
        {
            "id": int(r["id"]),
            "class_id": int(r["class_id"]),
            "class_name": r["class_name"],
            "school_id": int(r["school_id"]),
            "student_id": int(r["student_id"]),
            "name": f"{r['first_name']} {r['last_name']}".strip(),
            "avatar": load_avatar(r["avatar"]),
            "created_at": iso_utc(r["created_at"]),
            "current_class": r["current_class"] or "",
        }
        for r in rows
    ]


def viewer_join_request(conn, viewer: sqlite3.Row) -> dict[str, Any] | None:
    """The student's own request: active, or the last declined one while the
    student still has no class (so the screen can say it was declined)."""
    row = conn.execute(
        """
        SELECT r.*, c.name AS class_name, s.name AS school_name
        FROM join_requests r JOIN classes c ON c.id = r.class_id
        JOIN schools s ON s.id = c.school_id
        WHERE r.user_id = ? ORDER BY r.id DESC LIMIT 1
        """,
        (viewer["id"],),
    ).fetchone()
    if row is None:
        return None
    if row["status"] == "pending":
        return _request_public(row)
    if row["status"] == "declined" and viewer["class_id"] is None:
        return _request_public(row)
    return None
