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


class GameError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def effective_role(user: sqlite3.Row, settings: Settings) -> str:
    if settings.demo_mode and user["preview_role"] in {"student", "teacher", "director"}:
        return str(user["preview_role"])
    return str(user["role"])


def full_name(user: sqlite3.Row) -> str:
    return " ".join(
        part for part in (user["first_name"], user["last_name"]) if part
    ).strip()


ROLE_RANK = {"student": 0, "teacher": 1, "director": 2}


def _staff_class_id(conn, identity: Identity, settings: Settings) -> int | None:
    """Class a teacher manages: from the catalog, else the default class."""
    if identity.max_user_id:
        row = conn.execute(
            "SELECT class_id FROM class_staff WHERE max_user_id = ?",
            (identity.max_user_id,),
        ).fetchone()
        if row:
            return int(row["class_id"])
    return settings.default_class_id


def director_school_ids(conn, viewer: sqlite3.Row, settings: Settings) -> list[int]:
    """Schools whose data the viewer may see and manage as a director.

    Only explicit assignments count (``school_staff``). The demo has no
    registration, so its preview director sees the school of the demo class.
    """
    ids = [
        int(r["school_id"])
        for r in conn.execute(
            "SELECT school_id FROM school_staff WHERE user_id = ? ORDER BY school_id",
            (viewer["id"],),
        ).fetchall()
    ]
    if not ids and settings.demo_mode and viewer["class_id"] is not None:
        row = conn.execute(
            "SELECT school_id FROM classes WHERE id = ?", (viewer["class_id"],)
        ).fetchone()
        if row:
            ids = [int(row["school_id"])]
    return ids


def active_school_id(conn, viewer: sqlite3.Row, settings: Settings) -> int | None:
    ids = director_school_ids(conn, viewer, settings)
    if not ids:
        return None
    current = viewer["school_id"]
    return int(current) if current in ids else ids[0]


def can_manage_class(conn, viewer: sqlite3.Row, settings: Settings, class_id: int | None) -> bool:
    """A teacher manages their own class, a director every class of their schools."""
    if class_id is None:
        return False
    role = effective_role(viewer, settings)
    if role == "teacher":
        return viewer["class_id"] is not None and int(viewer["class_id"]) == int(class_id)
    if role == "director":
        row = conn.execute(
            "SELECT school_id FROM classes WHERE id = ?", (class_id,)
        ).fetchone()
        return bool(row) and int(row["school_id"]) in director_school_ids(conn, viewer, settings)
    return False


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
            # Env lists only ever raise a role: a director created through
            # registration must not be demoted by TEACHER_MAX_IDS.
            if ROLE_RANK.get(identity.role_hint, 0) > ROLE_RANK.get(row["role"], 0):
                updates["role"] = identity.role_hint
            if identity.role_hint == "teacher" and row["role"] != "director":
                staff_class = _staff_class_id(conn, identity, settings)
                in_catalog = bool(
                    identity.max_user_id
                    and conn.execute(
                        "SELECT 1 FROM class_staff WHERE max_user_id = ?",
                        (identity.max_user_id,),
                    ).fetchone()
                )
                # A class taken with a teacher code is kept unless the catalog
                # explicitly assigns this person.
                if staff_class is not None and (in_catalog or row["class_id"] is None):
                    if staff_class != row["class_id"]:
                        updates["class_id"] = staff_class
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
                _staff_class_id(conn, identity, settings)
                if role == "teacher"
                else settings.default_class_id,
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
        from .demo_seed import seed_demo_progress

        seed_demo_progress(conn, user_id, settings.default_class_id)
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def ensure_user(conn, identity: Identity, settings: Settings) -> sqlite3.Row:
    row = _load_or_create(conn, identity, settings)
    if identity.kind == "max" and identity.role_hint == "director" and settings.default_class_id:
        # DIRECTOR_MAX_IDS stays a fallback: such a director runs the school of
        # the default class, like before registration existed.
        school = conn.execute(
            "SELECT school_id FROM classes WHERE id = ?", (settings.default_class_id,)
        ).fetchone()
        if school and not conn.execute(
            "SELECT 1 FROM school_staff WHERE user_id = ? AND school_id = ?",
            (row["id"], school["school_id"]),
        ).fetchone():
            conn.execute(
                "INSERT OR IGNORE INTO school_staff (user_id, school_id) VALUES (?, ?)",
                (row["id"], school["school_id"]),
            )
            conn.commit()
    return row


# ---------------------------------------------------------------------------
# State assembly
# ---------------------------------------------------------------------------


LEADERBOARD_CAP = 100


def _weekly_map(conn, *, class_id: int | None = None) -> dict[int, int]:
    """Weekly XP per user of one class (empty when there is no class)."""
    if class_id is None:
        return {}
    rows = conn.execute(
        "SELECT e.user_id, SUM(e.amount) AS xp FROM xp_events e "
        "JOIN users u ON u.id = e.user_id "
        "WHERE u.class_id = ? AND e.created_at >= ? GROUP BY e.user_id",
        (class_id, week_start_utc_sql()),
    ).fetchall()
    return {int(row["user_id"]): int(row["xp"] or 0) for row in rows}


def _class_students(conn, class_id: int | None) -> list[sqlite3.Row]:
    if class_id is None:
        return []
    return conn.execute(
        "SELECT * FROM users WHERE role = 'student' AND class_id = ? "
        "ORDER BY xp DESC, id",
        (class_id,),
    ).fetchall()


def _class_aggregates(conn, visible_school_id: int | None) -> list[sqlite3.Row]:
    """XP, weekly XP and head count per class, computed by SQL aggregates.

    Classes of schools that are not active (awaiting approval) are visible
    only to their own school.
    """
    return conn.execute(
        """
        SELECT c.id, c.name, c.school_id, c.weekly_goal,
               s.name AS school_name, s.city,
               COALESCE(a.xp, 0) AS xp, COALESCE(a.members, 0) AS members,
               COALESCE(w.weekly, 0) AS weekly
        FROM classes c
        JOIN schools s ON s.id = c.school_id
        LEFT JOIN (
            SELECT class_id, SUM(xp) AS xp, COUNT(*) AS members
            FROM users WHERE role = 'student' AND class_id IS NOT NULL
            GROUP BY class_id
        ) a ON a.class_id = c.id
        LEFT JOIN (
            SELECT u.class_id, SUM(e.amount) AS weekly
            FROM xp_events e JOIN users u ON u.id = e.user_id
            WHERE u.role = 'student' AND u.class_id IS NOT NULL AND e.created_at >= ?
            GROUP BY u.class_id
        ) w ON w.class_id = c.id
        WHERE s.status = 'active' OR s.id = ?
        ORDER BY c.id
        """,
        (week_start_utc_sql(), visible_school_id if visible_school_id is not None else -1),
    ).fetchall()


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
    class_students: list[sqlite3.Row],
    week: dict[int, int],
    viewer_school_id: int | None,
) -> tuple[dict[str, Any], int, int, int]:
    viewer_class_id = viewer["class_id"]
    classes = _class_aggregates(conn, viewer_school_id)

    class_entries: list[dict[str, Any]] = []
    for item in classes:
        class_entries.append(
            {
                "id": int(item["id"]),
                "name": item["name"],
                "school": item["school_name"],
                "city": item["city"],
                "xp": int(item["xp"]),
                "weekly_xp": int(item["weekly"]),
                "goal": int(item["weekly_goal"]),
                "members": int(item["members"]),
                "is_viewer_class": viewer_class_id is not None
                and int(item["id"]) == int(viewer_class_id),
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
                "is_viewer_school": viewer_school_id is not None
                and school_id == viewer_school_id,
            },
        )
        bucket["xp"] += int(item["xp"])
        bucket["weekly_xp"] += int(item["weekly"])
        bucket["classes"] += 1
        bucket["members"] += int(item["members"])
    school_entries = sorted(
        schools.values(), key=lambda entry: (-entry["xp"], entry["name"])
    )
    for rank, entry in enumerate(school_entries, start=1):
        entry["rank"] = rank
    school_leader = school_entries[0]["xp"] if school_entries else 1
    for entry in school_entries:
        entry["progress"] = round(entry["xp"] / school_leader * 100, 1) if school_leader else 0

    personal = []
    for rank, member in enumerate(class_students, start=1):
        entry = _student_public(member, week.get(int(member["id"]), 0), int(viewer["id"]))
        entry["rank"] = rank
        personal.append(entry)

    viewer_class_rank = next(
        (entry["rank"] for entry in class_entries if entry["is_viewer_class"]), 0
    )
    viewer_school_rank = next(
        (entry["rank"] for entry in school_entries if entry["is_viewer_school"]), 0
    )
    viewer_personal_rank = next(
        (entry["rank"] for entry in personal if entry["is_viewer"]),
        len(personal) or 1,
    )

    # Ranks above are global; only the response is capped, so the table stays
    # small however many schools are registered.
    leaderboard = {
        "students": personal,
        "classes": [
            e for e in class_entries if e["rank"] <= LEADERBOARD_CAP or e["is_viewer_class"]
        ],
        "schools": [
            e for e in school_entries if e["rank"] <= LEADERBOARD_CAP or e["is_viewer_school"]
        ],
    }
    return leaderboard, viewer_class_rank, viewer_school_rank, viewer_personal_rank


def _challenge_list(conn, viewer: sqlite3.Row) -> list[dict[str, Any]]:
    if viewer["class_id"] is None:
        return []
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
        SELECT cp.challenge_id, COUNT(*) AS n
        FROM completions cp JOIN challenges ch ON ch.id = cp.challenge_id
        WHERE ch.class_id = ? AND cp.status IN ('pending', 'approved')
        GROUP BY cp.challenge_id
        """,
        (viewer["class_id"],),
    ).fetchall()
    participants = {int(row["challenge_id"]): int(row["n"]) for row in participant_rows}
    pending_rows = conn.execute(
        """
        SELECT cp.challenge_id, COUNT(*) AS n
        FROM completions cp JOIN challenges ch ON ch.id = cp.challenge_id
        WHERE ch.class_id = ? AND cp.status = 'pending'
        GROUP BY cp.challenge_id
        """,
        (viewer["class_id"],),
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
                "proof_url": completion["proof_url"] if (completion and "proof_url" in completion.keys()) else "",
                "subject": row["subject"] if "subject" in row.keys() else "Общее",
                "proof_type": row["proof_type"] if "proof_type" in row.keys() else "text",
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
    class_students = sorted(students, key=lambda row: -int(row["xp"]))
    pending_rows = conn.execute(
        """
        SELECT cp.id, cp.proof, cp.proof_url, cp.created_at, cp.user_id,
               c.title, c.category, c.xp, c.kind, c.subject, c.proof_type,
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
                "proof_url": row["proof_url"] or "",
                "subject": row["subject"] or "Общее",
                "proof_type": row["proof_type"] or "text",
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

    # Fetch all completions for class students to populate history and attention indicators
    all_completions = conn.execute(
        """
        SELECT cp.id, cp.user_id, cp.status, cp.proof, cp.proof_url, cp.created_at, cp.reject_reason,
               c.title, c.category, c.subject, c.xp
        FROM completions cp
        JOIN challenges c ON c.id = cp.challenge_id
        JOIN users u ON u.id = cp.user_id
        WHERE u.class_id = ?
        ORDER BY cp.created_at DESC
        """,
        (class_id,),
    ).fetchall()
    user_completions: dict[int, list[sqlite3.Row]] = {}
    for comp in all_completions:
        uid = int(comp["user_id"])
        user_completions.setdefault(uid, []).append(comp)

    today = today_local()
    student_rows = []
    for rank, student in enumerate(class_students, start=1):
        last_active = student["last_active_date"]
        last_label = "Нет активности"
        delta = 999
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
            except ValueError:
                pass

        uid = int(student["id"])
        student_comps = user_completions.get(uid, [])
        approved_comps = [c for c in student_comps if c["status"] == "approved"]
        rejected_comps = [c for c in student_comps if c["status"] == "rejected"]

        # Subject achievements
        subj_map: dict[str, dict[str, int]] = {}
        for c in approved_comps:
            sname = c["subject"] or "Общее"
            if sname not in subj_map:
                subj_map[sname] = {"count": 0, "xp": 0}
            subj_map[sname]["count"] += 1
            subj_map[sname]["xp"] += int(c["xp"])
        subject_stats = [
            {"subject": sname, "count": data["count"], "xp": data["xp"]}
            for sname, data in subj_map.items()
        ]
        subject_stats.sort(key=lambda s: -s["xp"])

        recent_works = [
            {
                "id": int(c["id"]),
                "title": c["title"],
                "category": c["category"],
                "subject": c["subject"] or "Общее",
                "xp": int(c["xp"]),
                "status": c["status"],
                "date": iso_utc(c["created_at"]),
                "proof": c["proof"] or "",
                "proof_url": c["proof_url"] or "",
                "reject_reason": c["reject_reason"] or "",
            }
            for c in student_comps[:8]
        ]

        risk_reasons: list[str] = []
        if delta >= 3:
            if delta >= 900:
                risk_reasons.append("Нет активности в системе")
            else:
                risk_reasons.append(f"Без активности {delta} дн.")
        if rejected_comps:
            risk_reasons.append(f"Отклонено заданий: {len(rejected_comps)} (требуется помощь)")

        at_risk = len(risk_reasons) > 0
        info = level_info(int(student["xp"]))
        student_rows.append(
            {
                "id": uid,
                "name": full_name(student),
                "first_name": student["first_name"],
                "avatar": load_avatar(student["avatar"]),
                "xp": int(student["xp"]),
                "weekly_xp": week.get(uid, 0),
                "level": info["level"],
                "level_title": info["title"],
                "streak": int(student["streak"] or 0),
                "pending_count": pending_counts.get(uid, 0),
                "approved_count": len(approved_comps),
                "rejected_count": len(rejected_comps),
                "risk_reasons": risk_reasons,
                "recent_works": recent_works,
                "subject_stats": subject_stats,
                "last_active": last_label,
                "at_risk": at_risk,
                "is_viewer": uid == int(viewer["id"]),
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

    code_row = conn.execute("SELECT invite_code FROM classes WHERE id = ?", (class_id,)).fetchone()
    teacher_invite_code = code_row["invite_code"] if code_row and code_row["invite_code"] else ""

    return {
        "invite_code": teacher_invite_code,
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



def batch_review_completions(
    conn,
    viewer: sqlite3.Row,
    settings: Settings,
    completion_ids: list[int],
    action: str,
    reason: str = "",
) -> dict[str, Any]:
    if effective_role(viewer, settings) not in {"teacher", "director"}:
        raise GameError("Массовая проверка доступна только педагогу или администрации", 403)
    approved_count = 0
    rejected_count = 0
    results = []
    for cid in completion_ids:
        try:
            res = review_completion(conn, viewer, settings, cid, action, reason)
            results.append({"id": cid, "success": True, "result": res})
            if action == "approve":
                approved_count += 1
            else:
                rejected_count += 1
        except Exception as e:
            results.append({"id": cid, "success": False, "error": str(e)})
    return {
        "action": action,
        "approved": approved_count,
        "rejected": rejected_count,
        "total": len(completion_ids),
        "results": results,
    }


def _director_data(conn, viewer: sqlite3.Row, school_id: int) -> dict[str, Any]:
    """Figures for one school, computed with SQL aggregates scoped to it."""
    class_rows = conn.execute(
        """
        SELECT c.id, c.name, c.weekly_goal, s.name AS school_name, s.city,
               COUNT(u.id) AS members,
               COALESCE(SUM(u.xp), 0) AS xp,
               COALESCE(SUM(w.weekly), 0) AS weekly_xp,
               COALESCE(SUM(CASE WHEN w.weekly > 0 THEN 1 ELSE 0 END), 0) AS active
        FROM classes c
        JOIN schools s ON s.id = c.school_id
        LEFT JOIN users u ON u.class_id = c.id AND u.role = 'student'
        LEFT JOIN (
            SELECT e.user_id, SUM(e.amount) AS weekly
            FROM xp_events e
            JOIN users uu ON uu.id = e.user_id
            JOIN classes cc ON cc.id = uu.class_id
            WHERE cc.school_id = ? AND e.created_at >= ?
            GROUP BY e.user_id
        ) w ON w.user_id = u.id
        WHERE c.school_id = ?
        GROUP BY c.id
        """,
        (school_id, week_start_utc_sql(), school_id),
    ).fetchall()

    total_students = sum(int(r["members"]) for r in class_rows)
    active_students_week = sum(int(r["active"]) for r in class_rows)
    engagement_rate = round(active_students_week / total_students * 100, 1) if total_students else 0
    total_school_xp = sum(int(r["xp"]) for r in class_rows)
    total_weekly_xp = sum(int(r["weekly_xp"]) for r in class_rows)

    # Grades aggregation (parallel 5..11)
    grades_map: dict[str, dict[str, Any]] = {}
    for c in class_rows:
        name = c["name"].strip()
        # Extract leading digit(s) e.g. "8А" -> "8"
        grade_num = "".join(ch for ch in name if ch.isdigit()) or "Другие"
        grade_label = f"{grade_num} классы" if grade_num != "Другие" else "Спецгруппы"
        bucket = grades_map.setdefault(
            grade_num,
            {
                "grade": grade_num,
                "label": grade_label,
                "classes_count": 0,
                "students_count": 0,
                "total_xp": 0,
                "weekly_xp": 0,
                "active_students": 0,
            },
        )
        bucket["classes_count"] += 1
        bucket["students_count"] += int(c["members"])
        bucket["total_xp"] += int(c["xp"])
        bucket["weekly_xp"] += int(c["weekly_xp"])
        bucket["active_students"] += int(c["active"])

    # Ensure all standard school grades (5..11) exist in the breakdown
    for g_num in ["5", "6", "7", "8", "9", "10", "11"]:
        if g_num not in grades_map:
            grades_map[g_num] = {
                "grade": g_num,
                "label": f"{g_num} классы",
                "classes_count": 0,
                "students_count": 0,
                "total_xp": 0,
                "weekly_xp": 0,
                "active_students": 0,
            }

    grades = sorted(grades_map.values(), key=lambda g: int(g["grade"]) if g["grade"].isdigit() else 99)
    for g in grades:
        g["engagement"] = round(g["active_students"] / g["students_count"] * 100, 1) if g["students_count"] else 0
        g["avg_student_xp"] = round(g["weekly_xp"] / g["students_count"]) if g["students_count"] else 0

    # Determine leading parallel
    active_grades = [g for g in grades if g["students_count"] > 0]
    leading_parallel = max(
        active_grades,
        key=lambda g: (g["engagement"], g["total_xp"]),
        default=None,
    )
    leading_grade_label = leading_parallel["label"] if leading_parallel else "8 классы"

    # Approved tasks of this school grouped by category. The directions follow
    # the school's educational (upbringing) programme sections; "completed_fop_tasks"
    # is the total of approved tasks and "social_activity_index" is derived from
    # the volunteering direction (count + xp // 10).
    cat_counts = conn.execute(
        """
        SELECT c.category, COUNT(cp.id) AS total_approved, SUM(c.xp) as sum_xp
        FROM completions cp
        JOIN challenges c ON c.id = cp.challenge_id
        JOIN users u ON u.id = cp.user_id
        WHERE cp.status = 'approved' AND u.class_id IN (SELECT id FROM classes WHERE school_id = ?)
        GROUP BY c.category
        """,
        (school_id,),
    ).fetchall()

    directions = {
        "study": {"label": "Учебно-исследовательское", "count": 0, "xp": 0},
        "olympiads": {"label": "Олимпиадное движение", "count": 0, "xp": 0},
        "patriotic": {"label": "Гражданско-патриотическое", "count": 0, "xp": 0},
        "sport_creative": {"label": "ЗОЖ, спорт и творчество", "count": 0, "xp": 0},
        "volunteering": {"label": "Волонтёрство и соцпроекты", "count": 0, "xp": 0},
    }
    completed_fop_tasks = 0
    for row in cat_counts:
        cat = row["category"]
        cnt = int(row["total_approved"])
        xp = int(row["sum_xp"] or 0)
        completed_fop_tasks += cnt
        if cat in {"homework", "weekly"}:
            directions["study"]["count"] += cnt
            directions["study"]["xp"] += xp
        elif cat == "olympiad":
            directions["olympiads"]["count"] += cnt
            directions["olympiads"]["xp"] += xp
        elif cat == "event":
            directions["patriotic"]["count"] += cnt
            directions["patriotic"]["xp"] += xp
        elif cat == "club":
            directions["sport_creative"]["count"] += cnt
            directions["sport_creative"]["xp"] += xp
        else:  # help, streak
            directions["volunteering"]["count"] += cnt
            directions["volunteering"]["xp"] += xp

    social_activity_index = directions["volunteering"]["count"] + (directions["volunteering"]["xp"] // 10)

    # Per-class table: same shape as the leaderboard ClassEntry; classes without
    # students get zeros. Ordered by weekly XP, then total XP.
    viewer_class = viewer["class_id"]
    ranked_classes = [
        {
            "id": int(c["id"]),
            "name": c["name"],
            "school": c["school_name"],
            "city": c["city"],
            "xp": int(c["xp"]),
            "weekly_xp": int(c["weekly_xp"]),
            "goal": int(c["weekly_goal"] or 0),
            "members": int(c["members"]),
            "is_viewer_class": viewer_class is not None and int(c["id"]) == int(viewer_class),
        }
        for c in class_rows
    ]
    ranked_classes.sort(key=lambda c: (-c["weekly_xp"], -c["xp"], c["id"]))
    for rank, entry in enumerate(ranked_classes, start=1):
        entry["rank"] = rank
        entry["progress"] = (
            round(min(100.0, max(0, entry["weekly_xp"]) / entry["goal"] * 100), 1)
            if entry["goal"] > 0
            else 0
        )

    return {
        "kpi": {
            "total_students": total_students,
            "total_classes": len(class_rows),
            "active_students_week": active_students_week,
            "engagement_rate": engagement_rate,
            "total_school_xp": total_school_xp,
            "total_weekly_xp": total_weekly_xp,
            "completed_fop_tasks": completed_fop_tasks,
            "social_activity_index": social_activity_index,
            "leading_grade": leading_grade_label,
        },
        "grades": grades,
        "directions": directions,
        "classes": ranked_classes,
        "report_generated_at": iso_utc(utc_sql()),
    }


def build_state(conn, viewer: sqlite3.Row, settings: Settings) -> dict[str, Any]:
    from .registration import is_platform_admin, platform_admin_data, school_admin_data

    viewer = conn.execute("SELECT * FROM users WHERE id = ?", (viewer["id"],)).fetchone()
    role = effective_role(viewer, settings)
    class_id = int(viewer["class_id"]) if viewer["class_id"] is not None else None

    class_row = None
    if class_id is not None:
        class_row = conn.execute(
            """
            SELECT c.name, c.weekly_goal, c.invite_code, c.teacher_code,
                   s.name AS school_name, s.city, s.id AS school_id, s.status AS school_status
            FROM classes c JOIN schools s ON s.id = c.school_id WHERE c.id = ?
            """,
            (class_id,),
        ).fetchone()

    admin_school_id = active_school_id(conn, viewer, settings) if role == "director" else None
    view_school_id = int(class_row["school_id"]) if class_row else admin_school_id
    school_row = class_row
    if school_row is None and view_school_id is not None:
        school_row = conn.execute(
            "SELECT name AS school_name, city, status AS school_status FROM schools WHERE id = ?",
            (view_school_id,),
        ).fetchone()

    week = _weekly_map(conn, class_id=class_id)
    class_students = _class_students(conn, class_id)
    leaderboard, class_rank, school_rank, personal_rank = _build_leaderboards(
        conn, viewer, class_students, week, view_school_id
    )
    achievements = achievements_for(conn, viewer, class_rank or None)
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
    top_weekly = max(
        (item for item in leaderboard["students"] if item["weekly_xp"] > 0),
        key=lambda item: item["weekly_xp"],
        default=None,
    )
    teacher = None
    director = None
    school_admin = None
    if role == "teacher" and class_row is not None:
        teacher = _teacher_data(conn, viewer, class_students, week, challenges, leaderboard)
    elif role == "director":
        if admin_school_id is not None:
            director = _director_data(conn, viewer, admin_school_id)
        school_admin = school_admin_data(conn, viewer, settings, admin_school_id)

    weekly_goal = int(class_row["weekly_goal"]) if class_row else 0
    viewer_public = {
        "id": int(viewer["id"]),
        "name": full_name(viewer),
        "first_name": viewer["first_name"],
        "last_name": viewer["last_name"],
        "username": viewer["username"],
        "role": role,
        "is_teacher_preview": settings.demo_mode
        and viewer["preview_role"] == "teacher",
        "class_id": class_id,
        "class_name": class_row["name"] if class_row else "",
        "school_id": view_school_id,
        "school_name": school_row["school_name"] if school_row else "",
        "school_status": school_row["school_status"] if school_row else "",
        "city": school_row["city"] if school_row else "",
        "invite_code": (class_row["invite_code"] or "") if class_row else "",
        "is_platform_admin": is_platform_admin(viewer, settings),
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

    class_weekly = class_entry["weekly_xp"] if class_entry else 0
    return {
        "mode": settings.app_mode,
        "verified": not (settings.demo_mode or settings.sandbox_mode),
        "today": today_local().isoformat(),
        "viewer": viewer_public,
        "class_sprint": {
            "name": class_row["name"] if class_row else "",
            "school": class_row["school_name"] if class_row else "",
            "xp": class_weekly,
            "goal": weekly_goal,
            "percent": (
                round(min(100.0, class_weekly / weekly_goal * 100), 1) if weekly_goal else 0
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
        "director": director,
        "school_admin": school_admin,
        "platform_admin": platform_admin_data(conn, viewer, settings),
        "demo_teacher_available": settings.demo_mode,
        "demo_director_available": settings.demo_mode,
    }


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------




# Cyrillic letters that look like Latin ones: codes are typed on RU keyboards.
_CODE_LOOKALIKES = str.maketrans(
    {
        "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H",
        "Р": "P", "С": "C", "Т": "T", "Х": "X", "О": "O",
    }
)


def normalize_invite_code(code: str) -> str:
    return "".join(code.strip().upper().split()).translate(_CODE_LOOKALIKES)


def lookup_class_by_code(conn, code: str) -> dict[str, Any] | None:
    """Find an active class by student code, else by teacher code.

    ``kind`` tells which one matched. Classes of schools that are not yet
    approved are not reachable by code.
    """
    normalized = normalize_invite_code(code)
    if not normalized:
        return None
    no_dash = normalized.replace("-", "")
    row = None
    kind = "student"
    for kind, column in (("student", "invite_code"), ("teacher", "teacher_code")):
        row = conn.execute(
            f"""
            SELECT c.*, s.name AS school_name, s.city
            FROM classes c
            JOIN schools s ON s.id = c.school_id
            WHERE s.status = 'active'
              AND (UPPER(c.{column}) = ?
                   OR UPPER(REPLACE(c.{column}, '-', '')) = ?)
            LIMIT 1
            """,
            (normalized, no_dash),
        ).fetchone()
        if row:
            break
    if not row:
        return None

    teacher_name = ""
    if kind == "student":
        teacher = conn.execute(
            "SELECT first_name, last_name FROM users "
            "WHERE class_id = ? AND role = 'teacher' ORDER BY id LIMIT 1",
            (row["id"],),
        ).fetchone()
        teacher_name = (
            f"{teacher['first_name']} {teacher['last_name']}".strip() if teacher else ""
        )
    return {
        "valid": True,
        "kind": kind,
        "class_id": int(row["id"]),
        "class_name": row["name"],
        "school_name": row["school_name"],
        "city": row["city"],
        "teacher_name": teacher_name,
        "invite_code": (row["invite_code"] if kind == "student" else row["teacher_code"]) or "",
    }


def _natural_key(name: str) -> tuple[int, str]:
    digits = "".join(ch for ch in name if ch.isdigit())
    return (int(digits) if digits else 999, name)


def get_school_catalog(
    conn,
    city: str = "",
    query: str = "",
    limit: int = 500,
    only_cities: bool = False,
) -> dict[str, Any]:
    """Public list of active schools. Invite codes are never included.

    ``city``/``query`` narrow the list on the server so it stays small however
    many schools exist; ``only_cities`` skips schools and classes entirely.
    """
    cities = [
        row["city"]
        for row in conn.execute(
            "SELECT DISTINCT city FROM schools WHERE status = 'active' ORDER BY city"
        )
    ]
    if only_cities:
        return {"cities": cities, "schools": [], "classes": []}
    limit = max(1, min(int(limit), 500))
    schools_rows = conn.execute(
        "SELECT id, name, city FROM schools WHERE status = 'active' "
        "AND (? = '' OR city = ?) ORDER BY city, name, id",
        (city, city),
    ).fetchall()
    needle = query.strip().casefold()
    if needle:
        schools_rows = [s for s in schools_rows if needle in s["name"].casefold()]
    schools_rows = schools_rows[:limit]
    schools = [
        {"id": int(s["id"]), "name": s["name"], "city": s["city"]} for s in schools_rows
    ]
    classes: list[dict[str, Any]] = []
    if schools:
        marks = ",".join("?" for _ in schools)
        classes_rows = conn.execute(
            f"SELECT id, school_id, name FROM classes WHERE school_id IN ({marks})",
            [s["id"] for s in schools],
        ).fetchall()
        classes = sorted(
            (
                {"id": int(c["id"]), "school_id": int(c["school_id"]), "name": c["name"]}
                for c in classes_rows
            ),
            key=lambda c: (c["school_id"], _natural_key(c["name"])),
        )
    return {"cities": cities, "schools": schools, "classes": classes}


def _class_for_join(conn, class_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT c.id FROM classes c JOIN schools s ON s.id = c.school_id "
        "WHERE c.id = ? AND s.status = 'active'",
        (class_id,),
    ).fetchone()
    if row is None:
        raise GameError("Класс не найден", 404)
    return row


def _resolve_code(conn, viewer: sqlite3.Row, settings: Settings, code: str) -> dict[str, Any]:
    from .registration import guard_code_attempts, register_code_failure

    guard_code_attempts(settings, int(viewer["id"]))
    info = lookup_class_by_code(conn, code)
    if not info:
        register_code_failure(settings, int(viewer["id"]))
        raise GameError("Класс с указанным кодом приглашения не найден", 404)
    return info


def _check_can_become_teacher(viewer: sqlite3.Row) -> None:
    if viewer["role"] == "director":
        raise GameError("Директор уже управляет всеми классами своей школы", 400)
    if viewer["role"] == "student" and viewer["class_id"] is not None:
        raise GameError("Вы уже состоите в классе как ученик", 403)


def _become_teacher(conn, viewer: sqlite3.Row, class_id: int) -> None:
    _check_can_become_teacher(viewer)
    conn.execute(
        "UPDATE users SET role = 'teacher', class_id = ?, onboarded = 1 WHERE id = ?",
        (class_id, viewer["id"]),
    )


def join_school_class(
    conn,
    viewer: sqlite3.Row,
    settings: Settings,
    class_id: int | None = None,
    invite_code: str = "",
) -> dict[str, Any]:
    if invite_code:
        info = _resolve_code(conn, viewer, settings, invite_code)
        target_class_id = int(info["class_id"])
        if info["kind"] == "teacher":
            _become_teacher(conn, viewer, target_class_id)
            return {"class_id": target_class_id, "state": build_state(conn, viewer, settings)}
    elif class_id:
        target_class_id = int(_class_for_join(conn, int(class_id))["id"])
    else:
        raise GameError("Укажите код приглашения или идентификатор класса", 400)

    if viewer["role"] != "student":
        raise GameError("Вступить в класс по коду ученика может только ученик", 403)
    conn.execute(
        "UPDATE users SET class_id = ? WHERE id = ?",
        (target_class_id, viewer["id"]),
    )
    return {
        "class_id": target_class_id,
        "state": build_state(conn, viewer, settings),
    }


def save_onboarding(conn, viewer: sqlite3.Row, settings: Settings, payload: dict[str, Any]) -> None:
    entered_name = " ".join(str(payload.get("first_name", "")).split())
    if not 2 <= len(entered_name) <= 24:
        raise GameError("Имя должно быть от 2 до 24 символов")
    parts = entered_name.split()
    first_name = parts[0]
    raw_last_name = str(payload.get("last_name", "")).strip()
    if raw_last_name:
        last_name = raw_last_name[:32]
    elif len(parts) > 1:
        last_name = " ".join(parts[1:])[:32]
    else:
        last_name = viewer["last_name"]

    target_class_id = viewer["class_id"]
    new_role = viewer["role"]
    if payload.get("class_id"):
        target_class_id = int(_class_for_join(conn, int(payload["class_id"]))["id"])
    elif payload.get("invite_code"):
        info = _resolve_code(conn, viewer, settings, str(payload["invite_code"]))
        target_class_id = int(info["class_id"])
        if info["kind"] == "teacher":
            _check_can_become_teacher(viewer)
            new_role = "teacher"
    if viewer["role"] != "student" and new_role == viewer["role"]:
        target_class_id = viewer["class_id"]

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
        "UPDATE users SET first_name = ?, last_name = ?, class_id = ?, role = ?, avatar = ?, "
        "onboarded = 1 WHERE id = ?",
        (first_name, last_name, target_class_id, new_role, dump_avatar(avatar), viewer["id"]),
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
    proof_url: str = "",
) -> dict[str, Any]:
    if effective_role(viewer, settings) == "teacher":
        raise GameError("В режиме педагога нельзя отправлять задания", 403)
    if viewer["class_id"] is None:
        raise GameError("Сначала выберите класс")
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
    proof_url = str(proof_url or "").strip()[:500]
    if existing:
        conn.execute(
            """
            UPDATE completions
            SET status = 'pending', proof = ?, proof_url = ?, created_at = ?, reviewed_at = NULL,
                reviewed_by = NULL, reject_reason = ''
            WHERE id = ?
            """,
            (proof, proof_url, utc_sql(), existing["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO completions (user_id, challenge_id, status, proof, proof_url, created_at) "
            "VALUES (?, ?, 'pending', ?, ?, ?)",
            (viewer["id"], challenge_id, proof, proof_url, utc_sql()),
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
    if effective_role(viewer, settings) not in {"teacher", "director"}:
        raise GameError("Подтверждать достижения может только педагог или администратор", 403)
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
    if not can_manage_class(conn, viewer, settings, int(row["class_id"])):
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
    if effective_role(viewer, settings) not in {"teacher", "director"}:
        raise GameError("Создавать задания может только педагог или администратор", 403)
    target_class = payload.get("class_id") or viewer["class_id"]
    if target_class is None:
        raise GameError("Выберите класс для задания")
    if not can_manage_class(conn, viewer, settings, int(target_class)):
        raise GameError("Нельзя создавать задания для чужого класса", 403)
    target_class = int(target_class)
    title = str(payload.get("title", "")).strip()
    description = str(payload.get("description", "")).strip()
    category = str(payload.get("category", ""))
    kind = str(payload.get("kind", ""))
    xp = int(payload.get("xp", 0))
    subject = str(payload.get("subject", "Общее")).strip() or "Общее"
    proof_type = str(payload.get("proof_type", "text")).strip()
    if proof_type not in {"text", "link", "photo"}:
        proof_type = "text"
    if not 3 <= len(title) <= 80:
        raise GameError("Название должно быть от 3 до 80 символов")
    if len(description) > 320:
        raise GameError("Описание слишком длинное")
    if category not in CATEGORIES:
        raise GameError("Неизвестная категория")
    if kind not in KINDS:
        raise GameError("Неизвестный тип задания")
    if not 10 <= xp <= 300:
        raise GameError("Награда: целое число от 10 до 300 XP")
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
            (class_id, title, description, category, xp, kind, deadline, subject, proof_type,
             created_by, active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (target_class, title, description, category, xp, kind, deadline, subject, proof_type, viewer["id"]),
    )


def award_student_by_teacher(
    conn,
    viewer: sqlite3.Row,
    settings: Settings,
    student_id: int,
    amount: int = 50,
    reason: str = "Активность на уроке",
) -> None:
    if effective_role(viewer, settings) not in {"teacher", "director"}:
        raise GameError("Поощрять учеников может только педагог или администратор", 403)
    student = conn.execute(
        "SELECT * FROM users WHERE id = ? AND role = 'student'", (student_id,)
    ).fetchone()
    if student is None:
        raise GameError("Ученик не найден", 404)
    if not can_manage_class(conn, viewer, settings, student["class_id"]):
        raise GameError("Ученик из другого класса", 403)
    if not (10 <= amount <= 300):
        raise GameError("Количество баллов должно быть от 10 до 300")
    clean_reason = reason.strip() or "Активность на уроке"
    award_xp(conn, student_id, amount, clean_reason, "homework")
    conn.execute("UPDATE users SET sparks = sparks + 5 WHERE id = ?", (student_id,))
    mark_active(conn, student_id)


def archive_challenge(
    conn, viewer: sqlite3.Row, settings: Settings, challenge_id: int
) -> None:
    if effective_role(viewer, settings) not in {"teacher", "director"}:
        raise GameError("Это действие доступно педагогу", 403)
    row = conn.execute(
        "SELECT class_id FROM challenges WHERE id = ?", (challenge_id,)
    ).fetchone()
    if row is None:
        raise GameError("Задание не найдено", 404)
    if not can_manage_class(conn, viewer, settings, int(row["class_id"])):
        raise GameError("Задание из другого класса", 403)
    conn.execute("UPDATE challenges SET active = 0 WHERE id = ?", (challenge_id,))


def switch_role(conn, viewer: sqlite3.Row, settings: Settings, role: str) -> None:
    if not settings.demo_mode:
        raise GameError("Переключение роли доступно только в демо-режиме", 403)
    if role not in {"student", "teacher", "director"}:
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
    from .demo_seed import seed_demo_progress

    seed_demo_progress(conn, int(viewer["id"]), int(viewer["class_id"]))



