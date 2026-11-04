"""School registration: schools created by directors, class and invite codes,
platform moderation. No file edits on the server are needed."""

from __future__ import annotations

import re
import secrets
import sqlite3
from typing import Any

from .config import Settings
from .db import school_key
from .game import utc_sql
from .ratelimit import limiter
from .service import GameError, director_school_ids

# No 0/O, 1/I/L: codes are read aloud and typed on a phone.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
MAX_CLASSES_PER_SCHOOL = 60
SCHOOL_CREATE_LIMIT = (5, 3600)  # attempts per window (seconds)
CODE_FAIL_LIMIT = (20, 600)

_LETTER = r"[^\W\d_]"
CITY_RE = re.compile(rf"{_LETTER}(?:{_LETTER}|[ .'’\-])*")
CLASS_RE = re.compile(r"\w[\w .\-/]*")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _rate_key(settings: Settings, user_id: int, bucket: str) -> str:
    return f"{settings.db_path}:{user_id}:{bucket}"


def guard_code_attempts(settings: Settings, user_id: int) -> None:
    limit, window = CODE_FAIL_LIMIT
    if limiter.count(_rate_key(settings, user_id, "code"), window) >= limit:
        raise GameError("Слишком много неверных кодов. Попробуйте позже.", 429)


def register_code_failure(settings: Settings, user_id: int) -> None:
    limiter.add(_rate_key(settings, user_id, "code"), CODE_FAIL_LIMIT[1])


def is_platform_admin(viewer: sqlite3.Row, settings: Settings) -> bool:
    max_id = viewer["max_user_id"]
    if max_id and str(max_id) in settings.platform_admin_max_ids:
        return True
    client_id = viewer["client_id"]
    return bool(
        settings.sandbox_mode
        and client_id
        and str(client_id) in settings.platform_admin_client_ids
    )


# ---------------------------------------------------------------------------
# Codes
# ---------------------------------------------------------------------------


def _code_taken(conn, code: str) -> bool:
    plain = code.replace("-", "")
    return bool(
        conn.execute(
            "SELECT 1 FROM classes WHERE REPLACE(UPPER(invite_code), '-', '') = ? "
            "OR REPLACE(UPPER(teacher_code), '-', '') = ? LIMIT 1",
            (plain, plain),
        ).fetchone()
    )


def generate_code(conn, kind: str) -> str:
    """Student codes: ``XXX-XXX``; teacher codes are longer: ``XXXX-XXXX``."""
    size = 3 if kind == "student" else 4
    for _ in range(100):
        code = "-".join(
            "".join(secrets.choice(CODE_ALPHABET) for _ in range(size))
            for _ in range(2)
        )
        if not _code_taken(conn, code):
            return code
    raise GameError("Не удалось сгенерировать код. Повторите попытку.", 500)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _check_school_fields(name: Any, city: Any) -> tuple[str, str]:
    name = _clean(name)
    city = _clean(city)
    if not 3 <= len(name) <= 80 or not re.search(_LETTER, name):
        raise GameError("Название школы: от 3 до 80 символов, должно содержать буквы")
    if not 2 <= len(city) <= 60 or not CITY_RE.fullmatch(city):
        raise GameError("Город: от 2 до 60 символов, только буквы, пробел и дефис")
    return name, city


def _check_class_fields(name: Any, goal: Any) -> tuple[str, int]:
    name = _clean(name)
    if not 1 <= len(name) <= 12 or not CLASS_RE.fullmatch(name):
        raise GameError("Название класса: от 1 до 12 символов, например 8А")
    try:
        goal_value = int(goal if goal not in (None, "") else 1600)
    except (TypeError, ValueError):
        raise GameError("Цель недели должна быть числом") from None
    if not 100 <= goal_value <= 20000:
        raise GameError("Цель недели: от 100 до 20 000 XP")
    return name, goal_value


def _insert_class(conn, school_id: int, name: str, goal: int) -> int:
    cursor = conn.execute(
        "INSERT INTO classes (school_id, name, weekly_goal, invite_code, teacher_code) "
        "VALUES (?, ?, ?, ?, ?)",
        (school_id, name, goal, generate_code(conn, "student"), generate_code(conn, "teacher")),
    )
    return int(cursor.lastrowid)


# ---------------------------------------------------------------------------
# Director actions
# ---------------------------------------------------------------------------


def create_school(
    conn, viewer: sqlite3.Row, settings: Settings, payload: dict[str, Any]
) -> int:
    if settings.demo_mode:
        raise GameError("В демо-режиме регистрация школы недоступна", 403)
    # Only someone without a class (or an existing director) may register a
    # school: otherwise a pupil or teacher would silently lose their class.
    if viewer["role"] != "director" and viewer["class_id"] is not None:
        raise GameError("Вы уже состоите в классе. Школу может зарегистрировать только пользователь без класса.", 403)
    name, city = _check_school_fields(payload.get("name"), payload.get("city"))
    raw_classes = payload.get("classes") or []
    if not 1 <= len(raw_classes) <= 40:
        raise GameError("Добавьте от 1 до 40 классов")
    classes: list[tuple[str, int]] = []
    seen: set[str] = set()
    for item in raw_classes:
        class_name, goal = _check_class_fields(item.get("name"), item.get("weekly_goal"))
        key = class_name.casefold()
        if key in seen:
            raise GameError(f"Класс «{class_name}» указан дважды")
        seen.add(key)
        classes.append((class_name, goal))

    limit, window = SCHOOL_CREATE_LIMIT
    if not limiter.hit(_rate_key(settings, int(viewer["id"]), "school"), limit, window):
        raise GameError("Слишком много попыток. Повторите позже.", 429)

    owned = conn.execute(
        "SELECT COUNT(*) AS n FROM schools WHERE created_by = ? AND status != 'rejected'",
        (viewer["id"],),
    ).fetchone()["n"]
    if owned >= settings.max_schools_per_user:
        raise GameError(
            f"Можно зарегистрировать не более {settings.max_schools_per_user} школ", 403
        )
    key = school_key(name, city)
    if conn.execute("SELECT 1 FROM schools WHERE norm_key = ?", (key,)).fetchone():
        raise GameError(
            "Школа с таким названием в этом городе уже зарегистрирована. "
            "Если это ваша школа, попросите у директора код педагога."
        )

    status = "pending" if settings.school_approval == "manual" else "active"
    try:
        cursor = conn.execute(
            "INSERT INTO schools (name, city, status, created_by, created_at, norm_key) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, city, status, viewer["id"], utc_sql(), key),
        )
    except sqlite3.IntegrityError:
        raise GameError("Школа с таким названием в этом городе уже зарегистрирована") from None
    school_id = int(cursor.lastrowid)
    for class_name, goal in classes:
        _insert_class(conn, school_id, class_name, goal)
    conn.execute(
        "INSERT OR IGNORE INTO school_staff (user_id, school_id) VALUES (?, ?)",
        (viewer["id"], school_id),
    )
    conn.execute(
        "UPDATE users SET role = 'director', school_id = ?, class_id = NULL, onboarded = 1 "
        "WHERE id = ?",
        (school_id, viewer["id"]),
    )
    return school_id


def _require_director_of(conn, viewer: sqlite3.Row, settings: Settings, school_id: int) -> sqlite3.Row:
    """The school row, only if the viewer is a real director of it."""
    school = conn.execute("SELECT * FROM schools WHERE id = ?", (school_id,)).fetchone()
    if (
        school is None
        or viewer["role"] != "director"
        or school_id not in director_school_ids(conn, viewer, settings)
        or settings.demo_mode
    ):
        raise GameError("Школа не найдена", 404)
    return school


def _require_class_of_director(conn, viewer, settings, class_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()
    if row is None:
        raise GameError("Класс не найден", 404)
    _require_director_of(conn, viewer, settings, int(row["school_id"]))
    return row


def add_class(
    conn, viewer: sqlite3.Row, settings: Settings, school_id: int, name: Any, goal: Any
) -> int:
    _require_director_of(conn, viewer, settings, school_id)
    class_name, weekly_goal = _check_class_fields(name, goal)
    existing = [
        str(r["name"]).casefold()
        for r in conn.execute("SELECT name FROM classes WHERE school_id = ?", (school_id,))
    ]
    if len(existing) >= MAX_CLASSES_PER_SCHOOL:
        raise GameError(f"В школе не может быть больше {MAX_CLASSES_PER_SCHOOL} классов")
    if class_name.casefold() in existing:
        raise GameError(f"Класс «{class_name}» уже есть в школе")
    return _insert_class(conn, school_id, class_name, weekly_goal)


def delete_class(conn, viewer: sqlite3.Row, settings: Settings, class_id: int) -> None:
    _require_class_of_director(conn, viewer, settings, class_id)
    busy = conn.execute(
        "SELECT (SELECT COUNT(*) FROM users WHERE class_id = ?) + "
        "(SELECT COUNT(*) FROM challenges WHERE class_id = ?) AS n",
        (class_id, class_id),
    ).fetchone()["n"]
    if busy:
        raise GameError("В классе уже есть ученики или задания, удалить его нельзя")
    conn.execute("DELETE FROM class_staff WHERE class_id = ?", (class_id,))
    conn.execute("DELETE FROM classes WHERE id = ?", (class_id,))


def reset_code(
    conn, viewer: sqlite3.Row, settings: Settings, class_id: int, kind: str
) -> None:
    if kind not in {"student", "teacher"}:
        raise GameError("Неизвестный тип кода")
    _require_class_of_director(conn, viewer, settings, class_id)
    column = "invite_code" if kind == "student" else "teacher_code"
    conn.execute(
        f"UPDATE classes SET {column} = ? WHERE id = ?",
        (generate_code(conn, kind), class_id),
    )


def select_school(conn, viewer: sqlite3.Row, settings: Settings, school_id: int) -> None:
    _require_director_of(conn, viewer, settings, school_id)
    conn.execute("UPDATE users SET school_id = ? WHERE id = ?", (school_id, viewer["id"]))


# ---------------------------------------------------------------------------
# State payloads
# ---------------------------------------------------------------------------


def _class_sort_key(item: dict[str, Any]):
    digits = "".join(ch for ch in item["name"] if ch.isdigit())
    return (int(digits) if digits else 999, item["name"])


def school_admin_data(
    conn, viewer: sqlite3.Row, settings: Settings, active_school_id: int | None
) -> dict[str, Any] | None:
    """Management view of the schools the viewer directs (None for demo/legacy)."""
    if settings.demo_mode or viewer["role"] != "director":
        return None
    ids = director_school_ids(conn, viewer, settings)
    if not ids:
        return None
    marks = ",".join("?" for _ in ids)
    # Classes imported from an older catalog may lack a teacher code.
    for row in conn.execute(
        f"SELECT id, invite_code, teacher_code FROM classes WHERE school_id IN ({marks}) "
        "AND (teacher_code IS NULL OR invite_code IS NULL)",
        ids,
    ).fetchall():
        if not row["invite_code"]:
            conn.execute(
                "UPDATE classes SET invite_code = ? WHERE id = ?",
                (generate_code(conn, "student"), row["id"]),
            )
        if not row["teacher_code"]:
            conn.execute(
                "UPDATE classes SET teacher_code = ? WHERE id = ?",
                (generate_code(conn, "teacher"), row["id"]),
            )
    conn.commit()

    schools = conn.execute(
        f"SELECT * FROM schools WHERE id IN ({marks}) ORDER BY id", ids
    ).fetchall()
    class_rows = conn.execute(
        f"""
        SELECT c.id, c.school_id, c.name, c.weekly_goal, c.invite_code, c.teacher_code,
               COUNT(u.id) AS members
        FROM classes c
        LEFT JOIN users u ON u.class_id = c.id AND u.role = 'student'
        WHERE c.school_id IN ({marks})
        GROUP BY c.id
        """,
        ids,
    ).fetchall()
    teachers: dict[int, list[str]] = {}
    for row in conn.execute(
        f"""
        SELECT u.class_id, u.first_name, u.last_name FROM users u
        JOIN classes c ON c.id = u.class_id
        WHERE u.role = 'teacher' AND c.school_id IN ({marks}) ORDER BY u.id
        """,
        ids,
    ).fetchall():
        teachers.setdefault(int(row["class_id"]), []).append(
            f"{row['first_name']} {row['last_name']}".strip()
        )
    by_school: dict[int, list[dict[str, Any]]] = {}
    for row in class_rows:
        by_school.setdefault(int(row["school_id"]), []).append(
            {
                "id": int(row["id"]),
                "name": row["name"],
                "weekly_goal": int(row["weekly_goal"]),
                "members": int(row["members"]),
                "invite_code": row["invite_code"] or "",
                "teacher_code": row["teacher_code"] or "",
                "teachers": teachers.get(int(row["id"]), []),
            }
        )
    owned = conn.execute(
        "SELECT COUNT(*) AS n FROM schools WHERE created_by = ? AND status != 'rejected'",
        (viewer["id"],),
    ).fetchone()["n"]
    return {
        "active_school_id": active_school_id,
        "max_schools": settings.max_schools_per_user,
        "schools_left": max(0, settings.max_schools_per_user - int(owned)),
        "max_classes": MAX_CLASSES_PER_SCHOOL,
        "schools": [
            {
                "id": int(s["id"]),
                "name": s["name"],
                "city": s["city"],
                "status": s["status"],
                "classes": sorted(by_school.get(int(s["id"]), []), key=_class_sort_key),
            }
            for s in schools
        ],
    }


def platform_admin_data(conn, viewer: sqlite3.Row, settings: Settings) -> dict[str, Any] | None:
    if not is_platform_admin(viewer, settings):
        return None
    rows = conn.execute(
        """
        SELECT s.id, s.name, s.city, s.created_at, u.first_name, u.last_name,
               (SELECT COUNT(*) FROM classes c WHERE c.school_id = s.id) AS classes
        FROM schools s LEFT JOIN users u ON u.id = s.created_by
        WHERE s.status = 'pending' ORDER BY s.id LIMIT 100
        """
    ).fetchall()
    return {
        "approval_mode": settings.school_approval,
        "pending": [
            {
                "id": int(r["id"]),
                "name": r["name"],
                "city": r["city"],
                "classes": int(r["classes"]),
                "created_by": f"{r['first_name'] or ''} {r['last_name'] or ''}".strip(),
                "created_at": r["created_at"] or "",
            }
            for r in rows
        ],
    }


def set_school_status(
    conn, viewer: sqlite3.Row, settings: Settings, school_id: int, status: str
) -> None:
    if not is_platform_admin(viewer, settings):
        raise GameError("Недостаточно прав", 403)
    if status not in {"active", "rejected"}:
        raise GameError("Неизвестный статус")
    cursor = conn.execute("UPDATE schools SET status = ? WHERE id = ?", (status, school_id))
    if cursor.rowcount == 0:
        raise GameError("Школа не найдена", 404)
