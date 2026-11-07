"""School registration: schools created by directors, class and invite codes,
platform moderation. No file edits on the server are needed."""

from __future__ import annotations

import re
import secrets
import sqlite3
from typing import Any

from .config import Settings
from .db import immediate, school_key
from .game import DEFAULT_TIMEZONE, TIMEZONE_NAMES, iso_utc, normalize_timezone, utc_sql
from .joins import pending_requests
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
    if not settings.sandbox_mode:
        return False
    client_id = viewer["client_id"]
    if client_id and str(client_id) in settings.platform_admin_client_ids:
        return True
    # Switch in the sandbox panel; the column is ignored in prod and demo.
    return bool(viewer["sandbox_admin"]) if "sandbox_admin" in viewer.keys() else False


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
        raise GameError("Город: от 2 до 60 символов, только буквы, пробел, дефис и точка")
    return name, city


def _check_timezone(value: Any) -> str:
    """Zone from the supported list; empty means Moscow."""
    name = str(value or "").strip() or DEFAULT_TIMEZONE
    if name not in TIMEZONE_NAMES:
        raise GameError("Выберите часовой пояс из списка")
    return name


def set_school_timezone(
    conn, viewer: sqlite3.Row, settings: Settings, school_id: int, value: Any
) -> None:
    """The director changes the school zone; the database stays in UTC."""
    _require_director_of(conn, viewer, settings, school_id)
    conn.execute(
        "UPDATE schools SET timezone = ? WHERE id = ?", (_check_timezone(value), school_id)
    )


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
    tz = _check_timezone(payload.get("timezone"))
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
            "Школа с таким названием в этом городе уже зарегистрирована."
        )

    status = "pending" if settings.school_approval == "manual" else "active"
    try:
        cursor = conn.execute(
            "INSERT INTO schools (name, city, status, created_by, created_at, norm_key, timezone) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, city, status, viewer["id"], utc_sql(), key, tz),
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


REJECTED_SCHOOL_MESSAGE = (
    "Школа отклонена администратором платформы. Управление классами и кодами "
    "недоступно, пока администратор не восстановит школу."
)


def _require_director_of(
    conn, viewer: sqlite3.Row, settings: Settings, school_id: int, *, manage: bool = True
) -> sqlite3.Row:
    """The school row, only if the viewer is a real director of it.

    ``manage`` (default) also refuses a school rejected by the platform:
    its director may still look at it but not change classes or codes.
    """
    school = conn.execute("SELECT * FROM schools WHERE id = ?", (school_id,)).fetchone()
    if (
        school is None
        or viewer["role"] != "director"
        or school_id not in director_school_ids(conn, viewer, settings)
        or settings.demo_mode
    ):
        raise GameError("Школа не найдена", 404)
    if manage and school["status"] == "rejected":
        raise GameError(REJECTED_SCHOOL_MESSAGE, 403)
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


def update_class(
    conn,
    viewer: sqlite3.Row,
    settings: Settings,
    class_id: int,
    name: Any = None,
    weekly_goal: Any = None,
) -> None:
    """Rename a class and/or change its weekly XP goal (director of its school)."""
    row = _require_class_of_director(conn, viewer, settings, class_id)
    if name is None and weekly_goal is None:
        raise GameError("Нечего изменять")
    new_name, new_goal = _check_class_fields(
        row["name"] if name is None else name,
        row["weekly_goal"] if weekly_goal is None else weekly_goal,
    )
    taken = {
        str(r["name"]).casefold()
        for r in conn.execute(
            "SELECT name FROM classes WHERE school_id = ? AND id != ?",
            (row["school_id"], class_id),
        )
    }
    if new_name.casefold() in taken:
        raise GameError(f"Класс «{new_name}» уже есть в школе")
    conn.execute(
        "UPDATE classes SET name = ?, weekly_goal = ? WHERE id = ?",
        (new_name, new_goal, class_id),
    )


def delete_class(conn, viewer: sqlite3.Row, settings: Settings, class_id: int) -> None:
    """Delete an empty class.

    A class with members, tasks (and so submissions) or earned XP keeps its
    history and cannot be deleted (400). Exclusions and catalog teacher
    assignments only make sense for this class and are deleted with it.
    """
    _require_class_of_director(conn, viewer, settings, class_id)
    with immediate(conn):
        busy = conn.execute(
            "SELECT (SELECT COUNT(*) FROM users WHERE class_id = ?) AS members, "
            "(SELECT COUNT(*) FROM challenges WHERE class_id = ?) AS tasks, "
            "(SELECT COUNT(*) FROM xp_events WHERE class_id = ?) AS events",
            (class_id, class_id, class_id),
        ).fetchone()
        if busy["members"]:
            raise GameError("В классе есть ученики или педагоги, удалить его нельзя")
        if busy["tasks"] or busy["events"]:
            raise GameError("У класса есть задания или история опыта, удалить его нельзя")
        conn.execute("DELETE FROM class_exclusions WHERE class_id = ?", (class_id,))
        conn.execute("DELETE FROM join_requests WHERE class_id = ?", (class_id,))
        conn.execute("DELETE FROM class_staff WHERE class_id = ?", (class_id,))
        conn.execute("DELETE FROM classes WHERE id = ?", (class_id,))


def reset_code(
    conn,
    viewer: sqlite3.Row,
    settings: Settings,
    class_id: int,
    kind: str,
    disconnect_teachers: bool = False,
) -> None:
    """Issue a new code. A new teacher code alone does not take access away
    from teachers who already joined: ``disconnect_teachers`` does that too."""
    if kind not in {"student", "teacher"}:
        raise GameError("Неизвестный тип кода")
    _require_class_of_director(conn, viewer, settings, class_id)
    column = "invite_code" if kind == "student" else "teacher_code"
    with immediate(conn):
        conn.execute(
            f"UPDATE classes SET {column} = ? WHERE id = ?",
            (generate_code(conn, kind), class_id),
        )
        if kind == "teacher" and disconnect_teachers:
            for teacher in conn.execute(
                "SELECT * FROM users WHERE role = 'teacher' AND class_id = ?", (class_id,)
            ).fetchall():
                _detach_teacher(conn, teacher, class_id)


def _detach_teacher(conn, teacher: sqlite3.Row, class_id: int) -> None:
    """The teacher keeps the role but loses the class; a catalog/env
    assignment to it is removed and is not re-applied at the next login."""
    conn.execute(
        "UPDATE users SET class_id = NULL, class_since = NULL, staff_detached = 1 WHERE id = ?",
        (teacher["id"],),
    )
    if teacher["max_user_id"]:
        conn.execute(
            "DELETE FROM class_staff WHERE max_user_id = ? AND class_id = ?",
            (teacher["max_user_id"], class_id),
        )


def disconnect_teacher(
    conn, viewer: sqlite3.Row, settings: Settings, class_id: int, teacher_id: int
) -> None:
    """A director takes a class away from a teacher (also in a school the
    platform rejected: removing access must always be possible)."""
    row = conn.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()
    if row is None:
        raise GameError("Класс не найден", 404)
    _require_director_of(conn, viewer, settings, int(row["school_id"]), manage=False)
    with immediate(conn):
        teacher = conn.execute(
            "SELECT * FROM users WHERE id = ? AND role = 'teacher' AND class_id = ?",
            (teacher_id, class_id),
        ).fetchone()
        if teacher is None:
            raise GameError("Педагог не найден в этом классе", 404)
        _detach_teacher(conn, teacher, class_id)


def select_school(conn, viewer: sqlite3.Row, settings: Settings, school_id: int) -> None:
    _require_director_of(conn, viewer, settings, school_id, manage=False)
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
    teachers: dict[int, list[dict[str, Any]]] = {}
    for row in conn.execute(
        f"""
        SELECT u.id, u.class_id, u.first_name, u.last_name, u.class_since FROM users u
        JOIN classes c ON c.id = u.class_id
        WHERE u.role = 'teacher' AND c.school_id IN ({marks}) ORDER BY u.id
        """,
        ids,
    ).fetchall():
        teachers.setdefault(int(row["class_id"]), []).append(
            {
                "id": int(row["id"]),
                "name": f"{row['first_name']} {row['last_name']}".strip(),
                "since": iso_utc(row["class_since"]) if row["class_since"] else None,
            }
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
    class_ids = [int(r["id"]) for r in class_rows]
    return {
        "join_requests": pending_requests(conn, class_ids),
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
                "timezone": normalize_timezone(s["timezone"]),
                "reject_reason": (s["reject_reason"] or "") if s["status"] == "rejected" else "",
                "classes": sorted(by_school.get(int(s["id"]), []), key=_class_sort_key),
            }
            for s in schools
        ],
    }


def platform_admin_data(conn, viewer: sqlite3.Row, settings: Settings) -> dict[str, Any] | None:
    if not is_platform_admin(viewer, settings):
        return None
    def schools_with(status: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT s.id, s.name, s.city, s.created_at, u.first_name, u.last_name,
                   (SELECT COUNT(*) FROM classes c WHERE c.school_id = s.id) AS classes
            FROM schools s LEFT JOIN users u ON u.id = s.created_by
            WHERE s.status = ? ORDER BY s.id DESC LIMIT 100
            """,
            (status,),
        ).fetchall()
        return [
            {
                "id": int(r["id"]),
                "name": r["name"],
                "city": r["city"],
                "classes": int(r["classes"]),
                "created_by": f"{r['first_name'] or ''} {r['last_name'] or ''}".strip(),
                "created_at": r["created_at"] or "",
            }
            for r in rows
        ]

    return {
        "approval_mode": settings.school_approval,
        "pending": list(reversed(schools_with("pending"))),
        "rejected": schools_with("rejected"),
    }


def set_school_status(
    conn,
    viewer: sqlite3.Row,
    settings: Settings,
    school_id: int,
    status: str,
    reason: Any = "",
) -> None:
    """Approve / return (active) or reject a school. The optional reason of a
    rejection is shown to the director; it is cleared when the school is
    activated again."""
    if not is_platform_admin(viewer, settings):
        raise GameError("Недостаточно прав", 403)
    if status not in {"active", "rejected"}:
        raise GameError("Неизвестный статус")
    note = _clean(reason)[:200] if status == "rejected" else ""
    cursor = conn.execute(
        "UPDATE schools SET status = ?, reject_reason = ? WHERE id = ?",
        (status, note, school_id),
    )
    if cursor.rowcount == 0:
        raise GameError("Школа не найдена", 404)


def set_sandbox_admin(conn, viewer: sqlite3.Row, settings: Settings, enabled: bool) -> None:
    """Sandbox only: make the current test user a platform admin (or not)."""
    if not settings.sandbox_mode:
        raise GameError("Не найдено", 404)
    conn.execute(
        "UPDATE users SET sandbox_admin = ? WHERE id = ?", (1 if enabled else 0, viewer["id"])
    )
