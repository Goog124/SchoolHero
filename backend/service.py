"""Application logic: identity bootstrap, state assembly, game actions."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, time, timezone
from typing import Any

from .config import Settings
from .game import (
    BASIC_AVATAR,
    CATEGORIES,
    COSMETICS,
    COSMETIC_BY_ID,
    DEFAULT_AVATAR,
    KINDS,
    achievements_for,
    award_xp,
    cosmetic_state,
    deadline_in,
    dump_avatar,
    dump_owned,
    is_past,
    iso_utc,
    level_info,
    load_avatar,
    load_owned,
    mark_active,
    now_local,
    streak_days,
    today_local,
    utc_sql,
    validate_avatar_patch,
    week_days,
    week_start_utc_sql,
)
from .security import DEMO_FIRST_NAME, DEMO_LAST_NAME, DEMO_USERNAME, Identity
from .seed import seed_demo_progress


class GameError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def effective_role(user: sqlite3.Row, settings: Settings) -> str:
    if settings.demo_mode and user["preview_role"] in {"student", "teacher"}:
        return str(user["preview_role"])
    return str(user["role"])


def full_name(user: sqlite3.Row) -> str:
    return " ".join(
        part for part in (user["first_name"], user["last_name"]) if part
    ).strip()


def _load_or_create(conn, identity: Identity, settings: Settings) -> sqlite3.Row:
    if identity.kind == "max":
        row = conn.execute(
            "SELECT * FROM users WHERE max_user_id = ?", (identity.max_user_id,)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM users WHERE client_id = ?", (identity.client_id,)
        ).fetchone()

    if row is not None:
        if identity.kind == "max":
            updates = {}
            if identity.first_name and identity.first_name != row["first_name"]:
                updates["first_name"] = identity.first_name
            if identity.last_name and identity.last_name != row["last_name"]:
                updates["last_name"] = identity.last_name
            if identity.username and identity.username != row["username"]:
                updates["username"] = identity.username
            if identity.photo_url and identity.photo_url != row["photo_url"]:
                updates["photo_url"] = identity.photo_url
            if identity.role_hint == "teacher" and row["role"] != "teacher":
                updates["role"] = "teacher"
            if updates:
                assignments = ", ".join(f"{key} = ?" for key in updates)
                conn.execute(
                    f"UPDATE users SET {assignments} WHERE id = ?",
                    (*updates.values(), row["id"]),
                )
                conn.commit()
                row = conn.execute(
                    "SELECT * FROM users WHERE id = ?", (row["id"],)
                ).fetchone()
        return row

    initial_name = identity.first_name or "Герой"
    last_name = identity.last_name or ""
    demo = identity.kind == "demo"
    role = identity.role_hint if identity.kind == "max" else "student"
    onboarded = 0 if role == "student" else 1

    try:
        cursor = conn.execute(
            """
            INSERT INTO users
                (max_user_id, client_id, first_name, last_name, username,
                 photo_url, role, class_id, xp, sparks, streak,
                 last_active_date, avatar, owned, onboarded)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 0, NULL, ?, '[]', ?)
            """,
            (
                identity.max_user_id,
                identity.client_id,
                initial_name[:32],
                last_name[:32],
                identity.username,
                identity.photo_url,
                role,
                settings.default_class_id,
                40 if not demo else 0,
                dump_avatar(DEFAULT_AVATAR if not demo else BASIC_AVATAR),
                onboarded,
            ),
        )
        user_id = int(cursor.lastrowid)
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        if identity.kind == "max":
            row = conn.execute(
                "SELECT * FROM users WHERE max_user_id = ?", (identity.max_user_id,)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM users WHERE client_id = ?", (identity.client_id,)
            ).fetchone()
        if row is None:
            raise
        return row

    if demo:
        seed_demo_progress(conn, user_id, settings.default_class_id)
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def ensure_user(conn, identity: Identity, settings: Settings) -> sqlite3.Row:
    return _load_or_create(conn, identity, settings)


# ---------------------------------------------------------------------------
# State assembly
# ---------------------------------------------------------------------------


def _weekly_map(conn) -> dict[int, int]:
    rows = conn.execute(
        "SELECT user_id, SUM(amount) AS xp FROM xp_events "
        "WHERE created_at >= ? GROUP BY user_id",
        (week_start_utc_sql(),),
    ).fetchall()
    return {int(row["user_id"]): int(row["xp"] or 0) for row in rows}


def _all_students(conn) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT u.*, c.name AS class_name, c.school_id, c.weekly_goal,
               s.name AS school_name, s.city
        FROM users u
        JOIN classes c ON c.id = u.class_id
        JOIN schools s ON s.id = c.school_id
        WHERE u.role = 'student'
        ORDER BY u.xp DESC, u.id
        """
    ).fetchall()


def _classes_with_schools(conn) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT c.id, c.name, c.school_id, c.weekly_goal,
               s.name AS school_name, s.city
        FROM classes c JOIN schools s ON s.id = c.school_id
        ORDER BY c.id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _student_public(row: sqlite3.Row, week_xp: int, viewer_id: int) -> dict[str, Any]:
    info = level_info(int(row["xp"]))
    return {
        "id": int(row["id"]),
        "name": full_name(row),
        "first_name": row["first_name"],
        "last_name": row["last_name"],
        "avatar": load_avatar(row["avatar"]),
        "xp": int(row["xp"]),
        "weekly_xp": int(week_xp),
        "level": info["level"],
        "level_title": info["title"],
        "streak": int(row["streak"] or 0),
        "is_viewer": int(row["id"]) == viewer_id,
    }


def _build_leaderboards(
    conn,
    viewer: sqlite3.Row,
    students: list[sqlite3.Row],
    week: dict[int, int],
    viewer_school_id: int,
) -> tuple[dict[str, Any], int, int, int]:
    classes = _classes_with_schools(conn)
    students_by_class: dict[int, list[sqlite3.Row]] = {}
    for student in students:
        students_by_class.setdefault(int(student["class_id"]), []).append(student)

    class_entries: list[dict[str, Any]] = []
    for item in classes:
        members = students_by_class.get(int(item["id"]), [])
        total_xp = sum(int(member["xp"]) for member in members)
        week_xp = sum(week.get(int(member["id"]), 0) for member in members)
        class_entries.append(
            {
                "id": int(item["id"]),
                "name": item["name"],
                "school": item["school_name"],
                "city": item["city"],
                "xp": total_xp,
                "weekly_xp": week_xp,
                "goal": int(item["weekly_goal"]),
                "members": len(members),
                "is_viewer_class": int(item["id"]) == int(viewer["class_id"]),
            }
        )
    class_entries.sort(key=lambda entry: (-entry["xp"], entry["id"]))
    for rank, entry in enumerate(class_entries, start=1):
        entry["rank"] = rank
    leader_xp = class_entries[0]["xp"] if class_entries else 1
    for entry in class_entries:
        entry["progress"] = round(entry["xp"] / leader_xp * 100, 1) if leader_xp else 0

    schools: dict[int, dict[str, Any]] = {}
    for item in classes:
        school_id = int(item["school_id"])
        bucket = schools.setdefault(
            school_id,
            {
                "id": school_id,
                "name": item["school_name"],
                "city": item["city"],
                "xp": 0,
                "weekly_xp": 0,
                "classes": 0,
                "members": 0,
                "is_viewer_school": False,
            },
        )
        members = students_by_class.get(int(item["id"]), [])
        bucket["xp"] += sum(int(member["xp"]) for member in members)
        bucket["weekly_xp"] += sum(week.get(int(member["id"]), 0) for member in members)
        bucket["classes"] += 1
        bucket["members"] += len(members)
        if int(item["school_id"]) == viewer_school_id:
            bucket["is_viewer_school"] = True
    school_entries = sorted(
        schools.values(), key=lambda entry: (-entry["xp"], entry["name"])
    )
    for rank, entry in enumerate(school_entries, start=1):
        entry["rank"] = rank
    school_leader = school_entries[0]["xp"] if school_entries else 1
    for entry in school_entries:
        entry["progress"] = round(entry["xp"] / school_leader * 100, 1) if school_leader else 0

    class_members = sorted(
        students_by_class.get(int(viewer["class_id"]), []),
        key=lambda member: (-int(member["xp"]), int(member["id"])),
    )
    personal = []
    for rank, member in enumerate(class_members, start=1):
        entry = _student_public(member, week.get(int(member["id"]), 0), int(viewer["id"]))
        entry["rank"] = rank
        personal.append(entry)

    viewer_class_rank = next(
        (
            entry["rank"]
            for entry in class_entries
            if int(entry["id"]) == int(viewer["class_id"])
        ),
        0,
    )
    viewer_school_rank = next(
        (
            entry["rank"]
            for entry in school_entries
            if int(entry["id"]) == viewer_school_id
        ),
        0,
    )
    viewer_personal_rank = next(
        (entry["rank"] for entry in personal if entry["is_viewer"]),
        len(personal) or 1,
    )

    leaderboard = {
        "students": personal,
        "classes": class_entries,
        "schools": school_entries,
    }
    return leaderboard, viewer_class_rank, viewer_school_rank, viewer_personal_rank


def _challenge_list(conn, viewer: sqlite3.Row) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT c.*, u.first_name AS author_first, u.last_name AS author_last
        FROM challenges c
        LEFT JOIN users u ON u.id = c.created_by
        WHERE c.class_id = ? AND c.active = 1
        ORDER BY c.deadline ASC, c.id ASC
        """,
        (viewer["class_id"],),
    ).fetchall()
    completions = {
        int(row["challenge_id"]): row
        for row in conn.execute(
            "SELECT * FROM completions WHERE user_id = ?", (viewer["id"],)
        ).fetchall()
    }
    participant_rows = conn.execute(
        """
        SELECT challenge_id, COUNT(*) AS n
        FROM completions
        WHERE status IN ('pending', 'approved')
        GROUP BY challenge_id
        """
    ).fetchall()
    participants = {int(row["challenge_id"]): int(row["n"]) for row in participant_rows}
    pending_rows = conn.execute(
        """
        SELECT challenge_id, COUNT(*) AS n
        FROM completions
        WHERE status = 'pending'
        GROUP BY challenge_id
        """
    ).fetchall()
    pending = {int(row["challenge_id"]): int(row["n"]) for row in pending_rows}

    result = []
    for row in rows:
        completion = completions.get(int(row["id"]))
        if completion is not None:
            status = completion["status"]
        elif is_past(row["deadline"]):
            status = "expired"
        else:
            status = "available"
        result.append(
            {
                "id": int(row["id"]),
                "title": row["title"],
                "description": row["description"],
                "category": row["category"],
                "category_label": CATEGORIES.get(row["category"], row["category"]),
                "xp": int(row["xp"]),
                "kind": row["kind"],
                "kind_label": KINDS.get(row["kind"], row["kind"]),
                "deadline": row["deadline"],
                "status": status,
                "proof": completion["proof"] if completion else "",
                "submitted_at": iso_utc(completion["created_at"]) if completion else None,
                "reject_reason": completion["reject_reason"] if completion else "",
                "participants": participants.get(int(row["id"]), 0),
                "pending_count": pending.get(int(row["id"]), 0),
                "author": " ".join(
                    part
                    for part in (row["author_first"], row["author_last"])
                    if part
                )
                or "Школьный герой",
            }
        )
    return result


def _feed(conn, viewer: sqlite3.Row) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT e.amount, e.reason, e.category, e.created_at,
               u.first_name, u.last_name, u.avatar, u.id AS user_id
        FROM xp_events e
        JOIN users u ON u.id = e.user_id
        WHERE u.class_id = ? AND u.role = 'student'
        ORDER BY e.created_at DESC, e.id DESC
        LIMIT 12
        """,
        (viewer["class_id"],),
    ).fetchall()
    return [
        {
            "id": index,
            "user_id": int(row["user_id"]),
            "name": " ".join(
                part for part in (row["first_name"], row["last_name"]) if part
            ),
            "avatar": load_avatar(row["avatar"]),
            "amount": int(row["amount"]),
            "reason": row["reason"],
            "category": row["category"],
            "created_at": iso_utc(row["created_at"]),
        }
        for index, row in enumerate(rows, start=1)
    ]


def _student_stats(conn, viewer: sqlite3.Row, week_xp: int) -> dict[str, Any]:
    approved = conn.execute(
        "SELECT COUNT(*) AS n FROM completions WHERE user_id = ? AND status = 'approved'",
        (viewer["id"],),
    ).fetchone()["n"]
    pending = conn.execute(
        "SELECT COUNT(*) AS n FROM completions WHERE user_id = ? AND status = 'pending'",
        (viewer["id"],),
    ).fetchone()["n"]
    help_count = conn.execute(
        """
        SELECT COUNT(*) AS n FROM completions cp
        JOIN challenges c ON c.id = cp.challenge_id
        WHERE cp.user_id = ? AND cp.status = 'approved' AND c.category = 'help'
        """,
        (viewer["id"],),
    ).fetchone()["n"]
    return {
        "confirmed": int(approved),
        "pending": int(pending),
        "help_count": int(help_count),
        "weekly_xp": int(week_xp),
    }


def _teacher_data(
    conn,
    viewer: sqlite3.Row,
    students: list[sqlite3.Row],
    week: dict[int, int],
    challenges: list[dict[str, Any]],
    leaderboard: dict[str, Any],
) -> dict[str, Any]:
    class_id = int(viewer["class_id"])
    class_students = [s for s in students if int(s["class_id"]) == class_id]
    class_students.sort(key=lambda row: -int(row["xp"]))
    pending_rows = conn.execute(
        """
        SELECT cp.id, cp.proof, cp.created_at, cp.user_id,
               c.title, c.category, c.xp, c.kind,
               u.first_name, u.last_name, u.avatar, u.xp AS user_xp, u.id AS student_id
        FROM completions cp
        JOIN challenges c ON c.id = cp.challenge_id
        JOIN users u ON u.id = cp.user_id
        WHERE c.class_id = ? AND cp.status = 'pending' AND u.role = 'student'
        ORDER BY cp.created_at ASC
        """,
        (class_id,),
    ).fetchall()
    pending = []
    for row in pending_rows:
        student_level = level_info(int(row["user_xp"]))
        pending.append(
            {
                "id": int(row["id"]),
                "student_id": int(row["student_id"]),
                "student_name": " ".join(
                    part for part in (row["first_name"], row["last_name"]) if part
                ),
                "avatar": load_avatar(row["avatar"]),
                "student_level": student_level["level"],
                "student_level_title": student_level["title"],
                "title": row["title"],
                "category": row["category"],
                "category_label": CATEGORIES.get(row["category"], row["category"]),
                "kind": row["kind"],
                "xp": int(row["xp"]),
                "proof": row["proof"],
                "created_at": iso_utc(row["created_at"]),
                "is_self": int(row["student_id"]) == int(viewer["id"]),
            }
        )

    pending_counts = {
        int(row["user_id"]): int(row["n"])
        for row in conn.execute(
            """
            SELECT cp.user_id, COUNT(*) AS n
            FROM completions cp
            JOIN challenges c ON c.id = cp.challenge_id
            WHERE c.class_id = ? AND cp.status = 'pending' AND c.active = 1
            GROUP BY cp.user_id
            """,
            (class_id,),
        ).fetchall()
    }

    today = today_local()
    student_rows = []
    for rank, student in enumerate(class_students, start=1):
        last_active = student["last_active_date"]
        at_risk = False
        last_label = "Нет активности"
        if last_active:
            try:
                last_date = date.fromisoformat(last_active)
                delta = (today - last_date).days
                if delta <= 0:
                    last_label = "Сегодня"
                elif delta == 1:
                    last_label = "Вчера"
                else:
                    last_label = f"{delta} дн. назад"
                at_risk = delta >= 3
            except ValueError:
                pass
        info = level_info(int(student["xp"]))
        student_rows.append(
            {
                "id": int(student["id"]),
                "name": full_name(student),
                "first_name": student["first_name"],
                "avatar": load_avatar(student["avatar"]),
                "xp": int(student["xp"]),
                "weekly_xp": week.get(int(student["id"]), 0),
                "level": info["level"],
                "level_title": info["title"],
                "streak": int(student["streak"] or 0),
                "pending_count": pending_counts.get(int(student["id"]), 0),
                "last_active": last_label,
                "at_risk": at_risk,
                "is_viewer": int(student["id"]) == int(viewer["id"]),
                "rank": rank,
            }
        )

    # Activity by weekday for the current week.
    chart = [
        {"date": item["date"], "label": item["label"], "xp": 0}
        for item in week_days()
    ]
    day_index = {item["date"]: index for index, item in enumerate(chart)}
    event_rows = conn.execute(
        """
        SELECT e.created_at, e.amount
        FROM xp_events e
        JOIN users u ON u.id = e.user_id
        WHERE u.class_id = ? AND u.role = 'student' AND e.created_at >= ?
        """,
        (class_id, week_start_utc_sql()),
    ).fetchall()
    for event in event_rows:
        moment = event["created_at"]
        try:
            parsed = datetime.strptime(moment, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
        except (TypeError, ValueError):
            continue
        local = parsed.astimezone(now_local().tzinfo).date().isoformat()
        if local in day_index:
            chart[day_index[local]]["xp"] += int(event["amount"])

    class_entry = next(
        (entry for entry in leaderboard["classes"] if entry["is_viewer_class"]), None
    )
    avg_level = (
        round(sum(item["level"] for item in student_rows) / len(student_rows), 1)
        if student_rows
        else 0
    )
    avg_weekly = (
        round(sum(item["weekly_xp"] for item in student_rows) / len(student_rows))
        if student_rows
        else 0
    )
    active_week = sum(1 for item in student_rows if item["weekly_xp"] > 0)
    at_risk_count = sum(1 for item in student_rows if item["at_risk"])

    challenge_stats = [
        {
            **challenge,
            "pending_total": challenge["pending_count"],
            "approved_total": 0,
        }
        for challenge in challenges
    ]
    approved_rows = conn.execute(
        """
        SELECT c.id, COUNT(*) AS n
        FROM completions cp JOIN challenges c ON c.id = cp.challenge_id
        WHERE c.class_id = ? AND cp.status = 'approved'
        GROUP BY c.id
        """,
        (class_id,),
    ).fetchall()
    approved_map = {int(row["id"]): int(row["n"]) for row in approved_rows}
    for item in challenge_stats:
        item["approved_total"] = approved_map.get(item["id"], 0)

    return {
        "pending": pending,
        "students": student_rows,
        "stats": {
            "students": len(student_rows),
            "active_week": active_week,
            "pending": len(pending),
            "avg_level": avg_level,
            "avg_weekly_xp": avg_weekly,
            "at_risk": at_risk_count,
            "class_xp": class_entry["xp"] if class_entry else 0,
            "weekly_xp": class_entry["weekly_xp"] if class_entry else 0,
        },
        "chart": chart,
        "challenges": challenge_stats,
    }


def build_state(conn, viewer: sqlite3.Row, settings: Settings) -> dict[str, Any]:
    viewer = conn.execute("SELECT * FROM users WHERE id = ?", (viewer["id"],)).fetchone()
    role = effective_role(viewer, settings)
    week = _weekly_map(conn)
    students = _all_students(conn)
    class_row = conn.execute(
        """
        SELECT c.name, c.weekly_goal, s.name AS school_name, s.city, s.id AS school_id
        FROM classes c JOIN schools s ON s.id = c.school_id WHERE c.id = ?
        """,
        (viewer["class_id"],),
    ).fetchone()
    leaderboard, class_rank, school_rank, personal_rank = _build_leaderboards(
        conn, viewer, students, week, int(class_row["school_id"])
    )
    achievements = achievements_for(conn, viewer, class_rank)
    challenges = _challenge_list(conn, viewer)
    feed = _feed(conn, viewer)
    viewer_week_xp = week.get(int(viewer["id"]), 0)
    stats = _student_stats(conn, viewer, viewer_week_xp)
    level = level_info(int(viewer["xp"]))
    avatar = load_avatar(viewer["avatar"])
    owned = load_owned(viewer["owned"])
    cosmetics = [
        cosmetic_state(item, level["level"], owned, avatar) for item in COSMETICS
    ]
    class_entry = next(
        (entry for entry in leaderboard["classes"] if entry["is_viewer_class"]), None
    )
    class_students = leaderboard["students"]
    top_weekly = max(
        (item for item in class_students if item["weekly_xp"] > 0),
        key=lambda item: item["weekly_xp"],
        default=None,
    )
    teacher = None
    if role == "teacher":
        teacher = _teacher_data(conn, viewer, students, week, challenges, leaderboard)

    viewer_public = {
        "id": int(viewer["id"]),
        "name": full_name(viewer),
        "first_name": viewer["first_name"],
        "last_name": viewer["last_name"],
        "username": viewer["username"],
        "role": role,
        "is_teacher_preview": settings.demo_mode
        and viewer["preview_role"] == "teacher",
        "class_id": int(viewer["class_id"]),
        "class_name": class_row["name"],
        "school_name": class_row["school_name"],
        "city": class_row["city"],
        "xp": int(viewer["xp"]),
        "level": level,
        "sparks": int(viewer["sparks"]),
        "streak": int(viewer["streak"] or 0),
        "avatar": avatar,
        "owned": owned,
        "onboarded": bool(viewer["onboarded"]),
        "weekly_xp": viewer_week_xp,
        "class_rank": class_rank,
        "school_rank": school_rank,
        "personal_rank": personal_rank,
        "stats": stats,
        "to_next": (
            max(0, int(level["next_xp"]) - int(viewer["xp"]))
            if level["next_xp"] is not None
            else 0
        ),
        "next_level": level["level"] + 1 if level["level"] < 5 else None,
    }

    return {
        "mode": "demo" if settings.demo_mode else "max",
        "verified": not settings.demo_mode,
        "today": today_local().isoformat(),
        "viewer": viewer_public,
        "class_sprint": {
            "name": class_row["name"],
            "school": class_row["school_name"],
            "xp": class_entry["weekly_xp"] if class_entry else 0,
            "goal": int(class_row["weekly_goal"]),
            "percent": (
                round(
                    min(100.0, (class_entry["weekly_xp"] if class_entry else 0) / int(class_row["weekly_goal"]) * 100),
                    1,
                )
                if int(class_row["weekly_goal"])
                else 0
            ),
            "rank": class_rank,
            "members": len(class_students),
            "top": (
                {
                    "name": top_weekly["name"],
                    "avatar": top_weekly["avatar"],
                    "xp": top_weekly["weekly_xp"],
                }
                if top_weekly
                else None
            ),
        },
        "challenges": challenges,
        "leaderboard": leaderboard,
        "feed": feed,
        "week": streak_days(conn, int(viewer["id"])),
        "achievements": achievements,
        "cosmetics": cosmetics,
        "teacher": teacher,
        "demo_teacher_available": settings.demo_mode,
    }


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


def save_onboarding(conn, viewer: sqlite3.Row, settings: Settings, payload: dict[str, Any]) -> None:
    entered_name = " ".join(str(payload.get("first_name", "")).split())
    if not 2 <= len(entered_name) <= 24:
        raise GameError("Имя должно быть от 2 до 24 символов")
    # The game shows a first name only; drop an accidentally typed surname.
    first_name = entered_name.split(" ")[0]
    avatar = dict(load_avatar(viewer["avatar"]))
    patch = payload.get("avatar") or {}
    if not isinstance(patch, dict):
        raise GameError("Некорректный образ героя")
    level = level_info(int(viewer["xp"]))["level"]
    owned = load_owned(viewer["owned"])
    try:
        allowed = validate_avatar_patch(
            {key: str(value) for key, value in patch.items()}, level, owned
        )
    except ValueError as exc:
        raise GameError(str(exc)) from exc
    avatar.update(allowed)
    conn.execute(
        "UPDATE users SET first_name = ?, avatar = ?, onboarded = 1 WHERE id = ?",
        (first_name, dump_avatar(avatar), viewer["id"]),
    )


def equip_item(
    conn, viewer: sqlite3.Row, key: str, item_id: str
) -> None:
    level = level_info(int(viewer["xp"]))["level"]
    owned = load_owned(viewer["owned"])
    avatar = load_avatar(viewer["avatar"])
    try:
        patch = validate_avatar_patch({key: item_id}, level, owned)
    except ValueError as exc:
        raise GameError(str(exc)) from exc
    avatar.update(patch)
    conn.execute(
        "UPDATE users SET avatar = ? WHERE id = ?", (dump_avatar(avatar), viewer["id"])
    )


def buy_item(conn, viewer: sqlite3.Row, item_id: str) -> None:
    item = COSMETIC_BY_ID.get(item_id)
    if item is None:
        raise GameError("Предмет не найден")
    if item.price <= 0:
        raise GameError("Этот предмет уже доступен")
    owned = load_owned(viewer["owned"])
    if item.id in owned:
        raise GameError("Предмет уже куплен")
    level = level_info(int(viewer["xp"]))["level"]
    if level < item.unlock_level:
        raise GameError(f"Предмет откроется на {item.unlock_level} уровне")
    if int(viewer["sparks"]) < item.price:
        raise GameError("Не хватает искр")
    owned.append(item.id)
    conn.execute(
        "UPDATE users SET sparks = sparks - ?, owned = ? WHERE id = ?",
        (item.price, dump_owned(owned), viewer["id"]),
    )


def submit_challenge(
    conn,
    viewer: sqlite3.Row,
    settings: Settings,
    challenge_id: int,
    proof: str,
) -> dict[str, Any]:
    if effective_role(viewer, settings) == "teacher":
        raise GameError("В режиме педагога нельзя отправлять задания", 403)
    challenge = conn.execute(
        "SELECT * FROM challenges WHERE id = ? AND active = 1", (challenge_id,)
    ).fetchone()
    if challenge is None:
        raise GameError("Задание не найдено", 404)
    if int(challenge["class_id"]) != int(viewer["class_id"]):
        raise GameError("Задание для другого класса", 403)
    if is_past(challenge["deadline"]):
        raise GameError("Срок выполнения уже истёк")
    existing = conn.execute(
        "SELECT * FROM completions WHERE user_id = ? AND challenge_id = ?",
        (viewer["id"], challenge_id),
    ).fetchone()
    if existing and existing["status"] in {"pending", "approved"}:
        raise GameError(
            "Задание уже на проверке" if existing["status"] == "pending" else "Задание уже выполнено"
        )
    proof = str(proof or "").strip()[:300]
    if existing:
        conn.execute(
            """
            UPDATE completions
            SET status = 'pending', proof = ?, created_at = ?, reviewed_at = NULL,
                reviewed_by = NULL, reject_reason = ''
            WHERE id = ?
            """,
            (proof, utc_sql(), existing["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO completions (user_id, challenge_id, status, proof, created_at) "
            "VALUES (?, ?, 'pending', ?, ?)",
            (viewer["id"], challenge_id, proof, utc_sql()),
        )
    mark_active(conn, int(viewer["id"]))
    return {"status": "pending", "challenge_title": challenge["title"]}


def review_completion(
    conn,
    viewer: sqlite3.Row,
    settings: Settings,
    completion_id: int,
    action: str,
    reason: str,
) -> dict[str, Any]:
    if effective_role(viewer, settings) != "teacher":
        raise GameError("Подтверждать достижения может только педагог", 403)
    row = conn.execute(
        """
        SELECT cp.*, c.title, c.xp, c.category, c.class_id,
               u.first_name, u.last_name, u.xp AS student_xp
        FROM completions cp
        JOIN challenges c ON c.id = cp.challenge_id
        JOIN users u ON u.id = cp.user_id
        WHERE cp.id = ?
        """,
        (completion_id,),
    ).fetchone()
    if row is None:
        raise GameError("Заявка не найдена", 404)
    if int(row["class_id"]) != int(viewer["class_id"]):
        raise GameError("Заявка из другого класса", 403)
    if row["status"] != "pending":
        raise GameError("Эта заявка уже проверена")
    if action not in {"approve", "reject"}:
        raise GameError("Неизвестное действие")
    now = utc_sql()
    if action == "reject":
        conn.execute(
            "UPDATE completions SET status = 'rejected', reject_reason = ?, "
            "reviewed_at = ?, reviewed_by = ? WHERE id = ?",
            (str(reason or "").strip()[:200], now, viewer["id"], completion_id),
        )
        return {
            "status": "rejected",
            "student_name": f"{row['first_name']} {row['last_name']}".strip(),
            "xp_awarded": 0,
        }

    conn.execute(
        "UPDATE completions SET status = 'approved', reviewed_at = ?, "
        "reviewed_by = ?, reject_reason = '' WHERE id = ?",
        (now, viewer["id"], completion_id),
    )
    award = award_xp(
        conn,
        int(row["user_id"]),
        int(row["xp"]),
        row["title"],
        row["category"],
    )
    conn.execute(
        "UPDATE users SET sparks = sparks + 5 WHERE id = ?", (row["user_id"],)
    )
    mark_active(conn, int(row["user_id"]))
    return {
        "status": "approved",
        "student_name": f"{row['first_name']} {row['last_name']}".strip(),
        "xp_awarded": int(row["xp"]),
        "student_level": award["level"],
        "level_up": award["level_up"],
    }


def create_challenge(
    conn,
    viewer: sqlite3.Row,
    settings: Settings,
    payload: dict[str, Any],
) -> None:
    if effective_role(viewer, settings) != "teacher":
        raise GameError("Создавать челленджи может только педагог", 403)
    title = str(payload.get("title", "")).strip()
    description = str(payload.get("description", "")).strip()
    category = str(payload.get("category", ""))
    kind = str(payload.get("kind", ""))
    xp = int(payload.get("xp", 0))
    if not 3 <= len(title) <= 80:
        raise GameError("Название должно быть от 3 до 80 символов")
    if len(description) > 320:
        raise GameError("Описание слишком длинное")
    if category not in CATEGORIES:
        raise GameError("Неизвестная категория")
    if kind not in KINDS:
        raise GameError("Неизвестный тип задания")
    if xp not in {20, 30, 40, 50, 100}:
        raise GameError("Опыт должен быть 20, 30, 40, 50 или 100")
    deadline_raw = str(payload.get("deadline", "")).strip()
    if deadline_raw:
        try:
            day = date.fromisoformat(deadline_raw)
        except ValueError as exc:
            raise GameError("Некорректная дата") from exc
        if day < today_local():
            raise GameError("Дата уже прошла")
        deadline = datetime.combine(day, time(23, 59), tzinfo=now_local().tzinfo).isoformat()
    else:
        deadline = deadline_in(2)
    conn.execute(
        """
        INSERT INTO challenges
            (class_id, title, description, category, xp, kind, deadline,
             created_by, active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (viewer["class_id"], title, description, category, xp, kind, deadline, viewer["id"]),
    )


def archive_challenge(
    conn, viewer: sqlite3.Row, settings: Settings, challenge_id: int
) -> None:
    if effective_role(viewer, settings) != "teacher":
        raise GameError("Это действие доступно педагогу", 403)
    row = conn.execute(
        "SELECT class_id FROM challenges WHERE id = ?", (challenge_id,)
    ).fetchone()
    if row is None:
        raise GameError("Задание не найдено", 404)
    if int(row["class_id"]) != int(viewer["class_id"]):
        raise GameError("Задание из другого класса", 403)
    conn.execute("UPDATE challenges SET active = 0 WHERE id = ?", (challenge_id,))


def switch_role(conn, viewer: sqlite3.Row, settings: Settings, role: str) -> None:
    if not settings.demo_mode:
        raise GameError("Переключение роли доступно только в демо-режиме", 403)
    if role not in {"student", "teacher"}:
        raise GameError("Неизвестная роль")
    conn.execute(
        "UPDATE users SET preview_role = ? WHERE id = ?", (role, viewer["id"])
    )


def reset_demo(conn, viewer: sqlite3.Row, settings: Settings) -> None:
    if not settings.demo_mode:
        raise GameError("Сброс доступен только в демо-режиме", 403)
    conn.execute("DELETE FROM completions WHERE user_id = ?", (viewer["id"],))
    conn.execute("DELETE FROM xp_events WHERE user_id = ?", (viewer["id"],))
    conn.execute("DELETE FROM activity_days WHERE user_id = ?", (viewer["id"],))
    conn.execute(
        """
        UPDATE users SET first_name = ?, last_name = ?, username = ?,
            xp = 0, sparks = 0, streak = 0, last_active_date = NULL,
            avatar = ?, owned = '[]', onboarded = 0, preview_role = NULL
        WHERE id = ?
        """,
        (
            DEMO_FIRST_NAME,
            DEMO_LAST_NAME,
            DEMO_USERNAME,
            dump_avatar(BASIC_AVATAR),
            viewer["id"],
        ),
    )
    seed_demo_progress(conn, int(viewer["id"]), int(viewer["class_id"]))



