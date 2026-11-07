"""Application logic: identity bootstrap, state assembly, game actions."""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import date, datetime, time, timezone
from typing import Any

from .config import Settings
from .db import immediate
from .game import (
    BASIC_AVATAR,
    CATEGORIES,
    SORTED_COSMETICS,
    COSMETIC_BY_ID,
    DEFAULT_AVATAR,
    KINDS,
    achievements_for,
    award_xp,
    cosmetic_state,
    current_streak,
    day_start_utc_sql,
    DEFAULT_TIMEZONE,
    normalize_timezone,
    deadline_in,
    deadline_on,
    dump_avatar,
    dump_owned,
    is_past,
    iso_utc,
    level_info,
    load_avatar,
    load_owned,
    mark_active,
    get_tz,
    streak_days,
    today_local,
    utc_sql,
    timezone_options,
    validate_avatar_patch,
    week_days,
    week_start_utc_sql,
)
from .security import DEFAULT_FIRST_NAME, DEMO_FIRST_NAME, DEMO_LAST_NAME, DEMO_USERNAME, Identity
from .game import SUBJECT_NONE, SUBJECT_OTHER, SUBJECTS


def school_timezone(conn, school_id: int | None) -> str:
    """IANA zone of a school (Moscow without a school)."""
    if school_id is None:
        return DEFAULT_TIMEZONE
    row = conn.execute("SELECT timezone FROM schools WHERE id = ?", (school_id,)).fetchone()
    return normalize_timezone(row["timezone"] if row else None)


def class_timezone(conn, class_id: int | None) -> str:
    if class_id is None:
        return DEFAULT_TIMEZONE
    row = conn.execute(
        "SELECT s.timezone FROM classes c JOIN schools s ON s.id = c.school_id WHERE c.id = ?",
        (class_id,),
    ).fetchone()
    return normalize_timezone(row["timezone"] if row else None)


def user_timezone(conn, user: sqlite3.Row) -> str:
    """Zone of the user's school: by class, else by the school they manage."""
    if user["class_id"] is not None:
        return class_timezone(conn, int(user["class_id"]))
    row = conn.execute(
        "SELECT s.timezone FROM school_staff st JOIN schools s ON s.id = st.school_id "
        "WHERE st.user_id = ? ORDER BY st.school_id LIMIT 1",
        (user["id"],),
    ).fetchone()
    return normalize_timezone(row["timezone"] if row else None)


class GameError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


REVIEW_ACTIONS = ("approve", "reject")

# Manual XP from staff (POST /api/teacher/reward), per local day of the school zone.
MANUAL_XP_PER_STUDENT_DAY = 300  # from all teachers together
MANUAL_XP_PER_TEACHER_DAY = 3000  # given by one teacher/director

PROOF_MIN, PROOF_MAX = 3, 1000
PROOF_URL_MAX = 500

_GRADE_RE = re.compile(r"\s*(\d{1,2})")


def class_grade(name: str) -> str | None:
    """Parallel of a class from its leading digits: "10-1" -> "10", "11А" -> "11"."""
    match = _GRADE_RE.match(str(name or ""))
    return str(int(match.group(1))) if match else None


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
            # A name typed by the person is never replaced by MAX data.
            if not row["name_locked"]:
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
            if (
                identity.role_hint == "teacher"
                and row["role"] != "director"
                and not row["staff_detached"]
            ):
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

    initial_name = identity.first_name or DEFAULT_FIRST_NAME
    last_name = identity.last_name or ""
    demo = identity.kind == "demo"
    role = identity.role_hint if identity.kind == "max" else "student"
    onboarded = 0 if role == "student" else 1

    bootstrap = (
        identity.kind == "max"
        and settings.app_mode == "prod"
        and settings.bootstrap_first_admin
        and not settings.platform_admin_max_ids
    )
    first_admin = 0
    try:
        if bootstrap:
            # Check "the database is empty" and insert in one write transaction:
            # two simultaneous first logins cannot both become admins.
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            if (
                conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
            ):
                first_admin = 1
        cursor = conn.execute(
            """
            INSERT INTO users
                (max_user_id, client_id, first_name, last_name, username,
                 photo_url, role, class_id, xp, sparks, streak,
                 last_active_date, avatar, owned, onboarded, platform_admin)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 0, NULL, ?, '[]', ?, ?)
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
                first_admin,
            ),
        )
        user_id = int(cursor.lastrowid)
        conn.commit()
        if first_admin:
            logging.getLogger("uvicorn.error").warning(
                "Первый пользователь %s назначен администратором платформы",
                identity.max_user_id,
            )
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


def _weekly_map(conn, *, class_id: int | None = None, tz: str | None = None) -> dict[int, int]:
    """Weekly XP per user earned in one class (empty when there is no class).

    Only events recorded for this class count: XP earned in another class
    stays with the student but is not added to the new class.
    """
    if class_id is None:
        return {}
    rows = conn.execute(
        "SELECT e.user_id, SUM(e.amount) AS xp FROM xp_events e "
        "WHERE e.class_id = ? AND e.created_at >= ? GROUP BY e.user_id",
        (class_id, week_start_utc_sql(tz)),
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


def _class_aggregates(
    conn, visible_school_id: int | None, tz: str | None = None
) -> list[sqlite3.Row]:
    """XP, weekly XP and head count per class, computed by SQL aggregates.

    Class XP is the XP earned *in that class* (``xp_events.class_id``), so a
    student who moves to another class keeps their XP but does not carry it
    into the new class rating. Classes of schools that are not active
    (awaiting approval) are visible only to their own school.
    """
    return conn.execute(
        """
        SELECT c.id, c.name, c.school_id, c.weekly_goal,
               s.name AS school_name, s.city,
               COALESCE(x.xp, 0) AS xp, COALESCE(a.members, 0) AS members,
               COALESCE(x.weekly, 0) AS weekly
        FROM classes c
        JOIN schools s ON s.id = c.school_id
        LEFT JOIN (
            SELECT class_id, COUNT(*) AS members
            FROM users WHERE role = 'student' AND class_id IS NOT NULL
            GROUP BY class_id
        ) a ON a.class_id = c.id
        LEFT JOIN (
            SELECT class_id, SUM(amount) AS xp,
                   SUM(CASE WHEN created_at >= ? THEN amount ELSE 0 END) AS weekly
            FROM xp_events WHERE class_id IS NOT NULL
            GROUP BY class_id
        ) x ON x.class_id = c.id
        WHERE s.status = 'active' OR s.id = ?
        ORDER BY c.id
        """,
        (week_start_utc_sql(tz), visible_school_id if visible_school_id is not None else -1),
    ).fetchall()


def _student_public(
    row: sqlite3.Row, week_xp: int, viewer_id: int, tz: str | None = None
) -> dict[str, Any]:
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
        "streak": current_streak(row["streak"], row["last_active_date"], tz),
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
    tz = user_timezone(conn, viewer)
    classes = _class_aggregates(conn, viewer_school_id, tz)

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
        entry = _student_public(member, week.get(int(member["id"]), 0), int(viewer["id"]), tz)
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
        JOIN users u ON u.id = cp.user_id AND u.class_id = ch.class_id
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
        JOIN users u ON u.id = cp.user_id AND u.class_id = ch.class_id
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
            # Work returned for rework cannot be resent after the deadline:
            # show it as expired (the reject reason stays visible).
            if status == "rejected" and is_past(row["deadline"]):
                status = "expired"
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
                # Kind is not a repetition schedule: the label follows the deadline.
                "kind_label": term_label(row["deadline"]),
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
    if viewer["class_id"] is None:
        return []
    rows = conn.execute(
        """
        SELECT e.amount, e.reason, e.category, e.created_at,
               u.first_name, u.last_name, u.avatar, u.id AS user_id
        FROM xp_events e
        JOIN users u ON u.id = e.user_id
        WHERE e.class_id = ? AND u.class_id = e.class_id AND u.role = 'student'
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
    # Only work that the current class's teacher can review: pending work of a
    # previous class is not reviewable after a class change.
    pending = conn.execute(
        "SELECT COUNT(*) AS n FROM completions cp "
        "JOIN challenges c ON c.id = cp.challenge_id "
        "WHERE cp.user_id = ? AND cp.status = 'pending' AND c.class_id = ?",
        (viewer["id"], viewer["class_id"]),
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
    tz = class_timezone(conn, class_id)
    class_students = sorted(students, key=lambda row: -int(row["xp"]))
    pending_rows = conn.execute(
        """
        SELECT cp.id, cp.proof, cp.proof_url, cp.upload_id, cp.created_at, cp.user_id,
               c.title, c.category, c.xp, c.kind, c.subject, c.proof_type,
               u.first_name, u.last_name, u.avatar, u.xp AS user_xp, u.id AS student_id
        FROM completions cp
        JOIN challenges c ON c.id = cp.challenge_id
        JOIN users u ON u.id = cp.user_id
        WHERE c.class_id = ? AND cp.status = 'pending' AND u.role = 'student'
          AND u.class_id = c.class_id
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
                "upload_id": int(row["upload_id"]) if row["upload_id"] else None,
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
            JOIN users u ON u.id = cp.user_id AND u.class_id = c.class_id
            WHERE c.class_id = ? AND cp.status = 'pending' AND u.role = 'student'
            GROUP BY cp.user_id
            """,
            (class_id,),
        ).fetchall()
    }

    # Work on this class's challenges (the class of the challenge, not the
    # student's current class): history and attention indicators.
    all_completions = conn.execute(
        """
        SELECT cp.id, cp.user_id, cp.status, cp.proof, cp.proof_url, cp.created_at, cp.reject_reason,
               c.title, c.category, c.subject, c.xp
        FROM completions cp
        JOIN challenges c ON c.id = cp.challenge_id
        WHERE c.class_id = ?
        ORDER BY cp.created_at DESC
        """,
        (class_id,),
    ).fetchall()
    user_completions: dict[int, list[sqlite3.Row]] = {}
    for comp in all_completions:
        uid = int(comp["user_id"])
        user_completions.setdefault(uid, []).append(comp)

    today = today_local(tz)
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
                "streak": current_streak(student["streak"], student["last_active_date"], tz),
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
        for item in week_days(tz)
    ]
    day_index = {item["date"]: index for index, item in enumerate(chart)}
    event_rows = conn.execute(
        """
        SELECT e.created_at, e.amount
        FROM xp_events e
        WHERE e.class_id = ? AND e.created_at >= ?
        """,
        (class_id, week_start_utc_sql(tz)),
    ).fetchall()
    for event in event_rows:
        moment = event["created_at"]
        try:
            parsed = datetime.strptime(moment, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
        except (TypeError, ValueError):
            continue
        local = parsed.astimezone(get_tz(tz)).date().isoformat()
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
        JOIN users u ON u.id = cp.user_id AND u.class_id = c.class_id
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

    from .joins import pending_requests

    return {
        "excluded": _excluded_list(conn, class_id),
        "join_requests": pending_requests(conn, [class_id]),
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
    if action not in REVIEW_ACTIONS:
        raise GameError("Неизвестное действие: ожидается approve или reject")
    counts = {"approved": 0, "rejected": 0, "failed": 0}
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    # Each item is its own transaction: one failed item does not undo the rest.
    for cid in dict.fromkeys(completion_ids):
        try:
            res = review_completion(conn, viewer, settings, cid, action, reason)
        except GameError as exc:
            counts["failed"] += 1
            errors.append({"id": cid, "detail": exc.message, "status": exc.status})
            results.append({"id": cid, "success": False, "error": exc.message})
            continue
        counts["approved" if action == "approve" else "rejected"] += 1
        results.append({"id": cid, "success": True, "result": res})
    return {
        "action": action,
        "approved": counts["approved"],
        "rejected": counts["rejected"],
        "failed": counts["failed"],
        "total": len(results),
        "counts": counts,
        "errors": errors,
        "results": results,
    }


def _director_data(conn, viewer: sqlite3.Row, school_id: int) -> dict[str, Any]:
    """Figures for one school, computed with SQL aggregates scoped to it."""
    # XP of a class is the XP earned in it (xp_events.class_id); "active" is a
    # current member who earned XP in this class this week.
    week_start = week_start_utc_sql(school_timezone(conn, school_id))
    class_rows = conn.execute(
        """
        SELECT c.id, c.name, c.weekly_goal, s.name AS school_name, s.city,
               (SELECT COUNT(*) FROM users u
                 WHERE u.class_id = c.id AND u.role = 'student') AS members,
               (SELECT COALESCE(SUM(e.amount), 0) FROM xp_events e
                 WHERE e.class_id = c.id) AS xp,
               (SELECT COALESCE(SUM(e.amount), 0) FROM xp_events e
                 WHERE e.class_id = c.id AND e.created_at >= ?) AS weekly_xp,
               (SELECT COUNT(DISTINCT e.user_id) FROM xp_events e
                 JOIN users u ON u.id = e.user_id
                 WHERE e.class_id = c.id AND e.created_at >= ? AND e.amount > 0
                   AND u.class_id = c.id AND u.role = 'student') AS active
        FROM classes c
        JOIN schools s ON s.id = c.school_id
        WHERE c.school_id = ?
        """,
        (week_start, week_start, school_id),
    ).fetchall()

    total_students = sum(int(r["members"]) for r in class_rows)
    active_students_week = sum(int(r["active"]) for r in class_rows)
    engagement_rate = round(active_students_week / total_students * 100, 1) if total_students else 0
    total_school_xp = sum(int(r["xp"]) for r in class_rows)
    total_weekly_xp = sum(int(r["weekly_xp"]) for r in class_rows)

    # Grades aggregation (parallel 5..11)
    grades_map: dict[str, dict[str, Any]] = {}
    for c in class_rows:
        grade_num = class_grade(c["name"]) or "Другие"
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
    # No students yet: there is no leading parallel to show.
    leading_grade_label = leading_parallel["label"] if leading_parallel else None

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
        WHERE cp.status = 'approved' AND u.role = 'student'
          AND c.class_id IN (SELECT id FROM classes WHERE school_id = ?)
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
    from .joins import viewer_join_request
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

    tz = user_timezone(conn, viewer)
    week = _weekly_map(conn, class_id=class_id, tz=tz)
    class_students = _class_students(conn, class_id)
    leaderboard, class_rank, school_rank, personal_rank = _build_leaderboards(
        conn, viewer, class_students, week, view_school_id
    )
    achievements = achievements_for(conn, viewer, class_rank or None, tz)
    challenges = _challenge_list(conn, viewer)
    feed = _feed(conn, viewer)
    viewer_week_xp = week.get(int(viewer["id"]), 0)
    stats = _student_stats(conn, viewer, viewer_week_xp)
    level = level_info(int(viewer["xp"]))
    avatar = load_avatar(viewer["avatar"])
    owned = load_owned(viewer["owned"])
    cosmetics = [
        cosmetic_state(item, level["level"], owned, avatar) for item in SORTED_COSMETICS
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
        "removed_from": _removed_from(conn, viewer) if class_id is None else None,
        "join_request": viewer_join_request(conn, viewer) if role == "student" else None,
        # Teachers and directors are asked for a name when they have none.
        "needs_name": role in {"teacher", "director"}
        and not viewer["name_locked"]
        and (not viewer["first_name"] or viewer["first_name"] == DEFAULT_FIRST_NAME),
        "xp": int(viewer["xp"]),
        "level": level,
        "sparks": int(viewer["sparks"]),
        "streak": current_streak(viewer["streak"], viewer["last_active_date"], tz),
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
        "today": today_local(tz).isoformat(),
        "timezone": tz,
        "timezones": timezone_options(),
        "timezone_label": next(
            (o["label"] for o in timezone_options() if o["id"] == tz), tz
        ),
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
        "week": streak_days(conn, int(viewer["id"]), tz=tz),
        "achievements": achievements,
        "cosmetics": cosmetics,
        "teacher": teacher,
        "director": director,
        "school_admin": school_admin,
        "platform_admin": platform_admin_data(conn, viewer, settings),
        "demo_teacher_available": settings.demo_mode,
        "demo_director_available": settings.demo_mode,
        # Subjects for the challenge form: the server validates against the same list.
        "subjects": list(SUBJECTS) if role in {"teacher", "director"} else [],
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


def search_cities(
    conn, query: str = "", limit: int = 10
) -> dict[str, Any]:
    """Cities with active schools (what a pupil may pick) for suggestions.

    Substring match ignoring case; cities starting with the text come first.
    """
    needle = query.strip().casefold()[:60]
    limit = max(1, min(int(limit), 20))
    rows = conn.execute(
        """
        SELECT city, COUNT(*) AS n FROM schools
        WHERE status = 'active' AND (? = '' OR instr(casefold(city), ?) > 0)
        GROUP BY city
        ORDER BY (instr(casefold(city), ?) = 1) DESC, n DESC, city
        LIMIT ?
        """,
        (needle, needle, needle, limit),
    ).fetchall()
    total = conn.execute(
        "SELECT COUNT(*) FROM (SELECT 1 FROM schools WHERE status = 'active' "
        "AND (? = '' OR instr(casefold(city), ?) > 0) GROUP BY city)",
        (needle, needle),
    ).fetchone()[0]
    return {
        "cities": [{"name": r["city"], "schools": int(r["n"])} for r in rows],
        "total": int(total),
    }


def get_school_catalog(
    conn,
    city: str = "",
    query: str = "",
    limit: int = 500,
    only_cities: bool = False,
    offset: int = 0,
) -> dict[str, Any]:
    """Public list of active schools. Invite codes are never included.

    ``city``/``query`` narrow the list on the server (``limit``/``offset`` page
    it) so it stays small however many schools exist. The full city list is
    returned only for an unfiltered request or ``only_cities``; use
    ``search_cities`` for typing suggestions.
    """
    cities: list[str] = []
    if only_cities or not (city or query.strip()):
        cities = [
            row["city"]
            for row in conn.execute(
                "SELECT DISTINCT city FROM schools WHERE status = 'active' "
                "ORDER BY city LIMIT 500"
            )
        ]
    if only_cities:
        return {"cities": cities, "schools": [], "classes": [], "total": 0, "has_more": False}
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    needle = query.strip().casefold()
    where = "status = 'active' AND (? = '' OR city = ?) AND (? = '' OR instr(casefold(name), ?) > 0)"
    params = (city, city, needle, needle)
    total = conn.execute(f"SELECT COUNT(*) FROM schools WHERE {where}", params).fetchone()[0]
    schools_rows = conn.execute(
        f"SELECT id, name, city FROM schools WHERE {where} ORDER BY city, name, id LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()
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
    return {
        "cities": cities,
        "schools": schools,
        "classes": classes,
        "total": int(total),
        "has_more": offset + len(schools) < int(total),
    }


EXCLUDED_MESSAGE = "Вы отчислены из класса этой школы. Обратитесь к педагогу."


def is_excluded(conn, user_id: int, class_id: int) -> bool:
    """Excluded from any class of the school of ``class_id``.

    An exclusion works for the whole school: otherwise a removed student
    would simply move into the next class of the same school.
    """
    return bool(
        conn.execute(
            """
            SELECT 1 FROM class_exclusions e
            JOIN classes ce ON ce.id = e.class_id
            JOIN classes ct ON ct.id = ?
            WHERE e.user_id = ? AND ce.school_id = ct.school_id
            LIMIT 1
            """,
            (class_id, user_id),
        ).fetchone()
    )


def check_not_excluded(conn, user_id: int, class_id: int) -> None:
    if is_excluded(conn, user_id, class_id):
        raise GameError(EXCLUDED_MESSAGE, 403)


def _removed_from(conn, viewer: sqlite3.Row) -> dict[str, str] | None:
    """The class a classless student was last removed from (for the hint)."""
    row = conn.execute(
        """
        SELECT c.name AS class_name, s.name AS school_name
        FROM class_exclusions e
        JOIN classes c ON c.id = e.class_id
        JOIN schools s ON s.id = c.school_id
        WHERE e.user_id = ? ORDER BY e.created_at DESC, e.rowid DESC LIMIT 1
        """,
        (viewer["id"],),
    ).fetchone()
    return dict(row) if row else None


def _excluded_list(conn, class_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT e.user_id, e.reason, e.created_at, u.first_name, u.last_name
        FROM class_exclusions e JOIN users u ON u.id = e.user_id
        WHERE e.class_id = ? ORDER BY e.created_at DESC, e.rowid DESC LIMIT 100
        """,
        (class_id,),
    ).fetchall()
    return [
        {
            "id": int(r["user_id"]),
            "name": f"{r['first_name']} {r['last_name']}".strip(),
            "reason": r["reason"] or "",
            "removed_at": iso_utc(r["created_at"]),
        }
        for r in rows
    ]


def remove_student(
    conn, viewer: sqlite3.Row, settings: Settings, student_id: int, reason: str = ""
) -> None:
    """Take a student out of the class. XP, items, hero and task history stay,
    so the student can come back after the exclusion is lifted."""
    student = conn.execute("SELECT * FROM users WHERE id = ?", (student_id,)).fetchone()
    if student is None:
        raise GameError("Ученик не найден", 404)
    if int(student["id"]) == int(viewer["id"]):
        raise GameError("Нельзя исключить себя")
    if student["role"] != "student":
        raise GameError("Исключить можно только ученика")
    if student["class_id"] is None:
        raise GameError("Ученик уже не состоит в классе")
    if not can_manage_class(conn, viewer, settings, student["class_id"]):
        raise GameError("Ученик из другого класса", 403)
    with immediate(conn):
        conn.execute(
            "INSERT OR REPLACE INTO class_exclusions (user_id, class_id, removed_by, reason, created_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            (student_id, student["class_id"], viewer["id"], str(reason or "").strip()[:120]),
        )
        conn.execute(
            "UPDATE users SET class_id = NULL, class_since = NULL WHERE id = ?", (student_id,)
        )
        # The ban covers the school: an open request to another class of it goes.
        conn.execute(
            """
            UPDATE join_requests SET status = 'declined', decided_at = datetime('now'),
                   decided_by = ?
            WHERE user_id = ? AND status = 'pending' AND class_id IN (
                SELECT id FROM classes WHERE school_id =
                    (SELECT school_id FROM classes WHERE id = ?))
            """,
            (viewer["id"], student_id, student["class_id"]),
        )


def restore_student(conn, viewer: sqlite3.Row, settings: Settings, student_id: int) -> None:
    """Lift the ban. The student chooses a class again by list or code."""
    rows = conn.execute(
        "SELECT class_id FROM class_exclusions WHERE user_id = ?", (student_id,)
    ).fetchall()
    allowed = [
        int(r["class_id"])
        for r in rows
        if can_manage_class(conn, viewer, settings, int(r["class_id"]))
    ]
    if not allowed:
        raise GameError("Исключённый ученик не найден", 404)
    marks = ",".join("?" for _ in allowed)
    conn.execute(
        f"DELETE FROM class_exclusions WHERE user_id = ? AND class_id IN ({marks})",
        (student_id, *allowed),
    )


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
    with immediate(conn):
        conn.execute(
            "UPDATE users SET role = 'teacher', class_id = ?, class_since = datetime('now'), "
            "onboarded = 1 WHERE id = ?",
            (class_id, viewer["id"]),
        )
        # A request filed earlier as a student is no longer needed.
        conn.execute(
            "UPDATE join_requests SET status = 'cancelled', decided_at = datetime('now') "
            "WHERE user_id = ? AND status = 'pending'",
            (viewer["id"],),
        )


def _join_by_student_code(conn, viewer: sqlite3.Row, class_id: int) -> None:
    """A student code joins at once (and closes an open request)."""
    from .joins import cancel_pending

    if viewer["role"] != "student":
        raise GameError("Вступить в класс по коду ученика может только ученик", 403)
    check_not_excluded(conn, int(viewer["id"]), class_id)
    with immediate(conn):
        conn.execute(
            "UPDATE users SET class_id = ?, class_since = datetime('now') WHERE id = ?",
            (class_id, viewer["id"]),
        )
        cancel_pending(conn, int(viewer["id"]), int(viewer["id"]))


def join_school_class(
    conn,
    viewer: sqlite3.Row,
    settings: Settings,
    class_id: int | None = None,
    invite_code: str = "",
) -> dict[str, Any]:
    """Join by code at once, or file a request for a class picked from the list.

    ``status`` in the answer is ``joined`` or ``requested``; with a request the
    student stays where they were until a teacher approves it.
    """
    from .joins import create_join_request

    if invite_code:
        info = _resolve_code(conn, viewer, settings, invite_code)
        target_class_id = int(info["class_id"])
        if info["kind"] == "teacher":
            _become_teacher(conn, viewer, target_class_id)
            return {
                "status": "joined",
                "class_id": target_class_id,
                "state": build_state(conn, viewer, settings),
            }
        _join_by_student_code(conn, viewer, target_class_id)
        return {
            "status": "joined",
            "class_id": target_class_id,
            "state": build_state(conn, viewer, settings),
        }
    if class_id:
        request = create_join_request(conn, viewer, settings, int(class_id))
        return {
            "status": "requested",
            "class_id": None,
            "request": request,
            "state": build_state(conn, viewer, settings),
        }
    raise GameError("Укажите код приглашения или идентификатор класса", 400)


_NAME_RE = re.compile(r"[^\W\d_](?:[^\W\d_]|[ .'\u2019\-])*")


def _parse_name(viewer: sqlite3.Row, payload: dict[str, Any]) -> tuple[str, str]:
    """Name rules shared by onboarding and the profile: first name 2-24 chars,
    last name up to 32; one "Имя Фамилия" field is accepted too."""
    entered_name = " ".join(str(payload.get("first_name", "")).split())
    if not 2 <= len(entered_name) <= 24:
        raise GameError("Имя должно быть от 2 до 24 символов")
    parts = entered_name.split()
    first_name = parts[0]
    raw_last_name = " ".join(str(payload.get("last_name", "")).split())
    if raw_last_name:
        last_name = raw_last_name[:32]
    elif len(parts) > 1:
        last_name = " ".join(parts[1:])[:32]
    else:
        last_name = viewer["last_name"]
    typed = [first_name] + ([last_name] if (raw_last_name or len(parts) > 1) else [])
    for value in typed:
        if value and not _NAME_RE.fullmatch(value):
            raise GameError("Имя и фамилия: только буквы, пробел, дефис, точка и апостроф")
    return first_name, last_name


def set_profile_name(conn, viewer: sqlite3.Row, payload: dict[str, Any]) -> None:
    first_name, last_name = _parse_name(viewer, payload)
    conn.execute(
        "UPDATE users SET first_name = ?, last_name = ?, name_locked = 1 WHERE id = ?",
        (first_name, last_name, viewer["id"]),
    )


def save_onboarding(conn, viewer: sqlite3.Row, settings: Settings, payload: dict[str, Any]) -> None:
    """Name, hero and class of a new student.

    A class picked from the list becomes a join request (the student stays
    without a class until it is approved); a code joins at once.
    """
    from .joins import cancel_pending, create_join_request

    first_name, last_name = _parse_name(viewer, payload)

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

    code_info = None
    if not payload.get("class_id") and payload.get("invite_code"):
        code_info = _resolve_code(conn, viewer, settings, str(payload["invite_code"]))
        if code_info["kind"] == "teacher":
            _check_can_become_teacher(viewer)
        elif viewer["role"] == "student":
            check_not_excluded(conn, int(viewer["id"]), int(code_info["class_id"]))

    with immediate(conn):
        target_class_id = viewer["class_id"]
        new_role = viewer["role"]
        joined = False
        if payload.get("class_id") and viewer["role"] == "student":
            create_join_request(conn, viewer, settings, int(payload["class_id"]))
        elif code_info is not None:
            if code_info["kind"] == "teacher":
                new_role = "teacher"
                target_class_id = int(code_info["class_id"])
                joined = True
            elif viewer["role"] == "student":
                target_class_id = int(code_info["class_id"])
                joined = True
        if joined:
            cancel_pending(conn, int(viewer["id"]), int(viewer["id"]))
        conn.execute(
            "UPDATE users SET first_name = ?, last_name = ?, class_id = ?, role = ?, avatar = ?, "
            "onboarded = 1, name_locked = 1, "
            "class_since = CASE WHEN ? THEN datetime('now') ELSE class_since END WHERE id = ?",
            (
                first_name,
                last_name,
                target_class_id,
                new_role,
                dump_avatar(avatar),
                1 if joined else 0,
                viewer["id"],
            ),
        )


def _require_student_hero(viewer: sqlite3.Row) -> None:
    """The hero, level and shop belong to students; staff do not have one."""
    if viewer["role"] != "student" and not (viewer["preview_role"] or "") == "student":
        raise GameError("Герой и магазин доступны только ученикам", 403)


def equip_item(
    conn, viewer: sqlite3.Row, key: str, item_id: str
) -> None:
    _require_student_hero(viewer)
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
    _require_student_hero(viewer)
    item = COSMETIC_BY_ID.get(item_id)
    if item is None:
        raise GameError("Предмет не найден")
    if item.price <= 0:
        raise GameError("Этот предмет уже доступен")
    # Balance and ownership are read inside the write lock, and the debit is
    # conditional, so two parallel purchases cannot spend the same sparks.
    with immediate(conn):
        user = conn.execute(
            "SELECT xp, sparks, owned FROM users WHERE id = ?", (viewer["id"],)
        ).fetchone()
        if user is None:
            raise GameError("Пользователь не найден", 404)
        owned = load_owned(user["owned"])
        if item.id in owned:
            raise GameError("Предмет уже куплен")
        level = level_info(int(user["xp"]))["level"]
        if level < item.unlock_level:
            raise GameError(f"Предмет откроется на {item.unlock_level} уровне")
        owned.append(item.id)
        cursor = conn.execute(
            "UPDATE users SET sparks = sparks - ?, owned = ? WHERE id = ? AND sparks >= ?",
            (item.price, dump_owned(owned), viewer["id"], item.price),
        )
        if cursor.rowcount != 1:
            raise GameError("Не хватает искр")


_URL_RE = re.compile(r"https?://[^\s/$.?#][^\s]*", re.IGNORECASE)


def _clean_proof(proof: Any, proof_url: Any, proof_type: str) -> tuple[str, str]:
    """Server-side rules for a submission (the client checks the same)."""
    text = str(proof or "").strip()
    if not PROOF_MIN <= len(text) <= PROOF_MAX:
        raise GameError(
            f"Опишите, что сделано: от {PROOF_MIN} до {PROOF_MAX} символов"
        )
    url = str(proof_url or "").strip()
    if url:
        if len(url) > PROOF_URL_MAX or not _URL_RE.fullmatch(url):
            raise GameError(
                "Ссылка должна начинаться с http:// или https:// "
                f"и быть не длиннее {PROOF_URL_MAX} символов"
            )
    elif proof_type == "link":
        raise GameError("Для этого задания нужна ссылка на материал")
    return text, url


def _require_school_open(conn, class_id: int | None) -> None:
    """Classes of a school rejected by the platform are read-only."""
    if class_id is None:
        return
    row = conn.execute(
        "SELECT s.status FROM classes c JOIN schools s ON s.id = c.school_id WHERE c.id = ?",
        (class_id,),
    ).fetchone()
    if row is not None and row["status"] == "rejected":
        raise GameError(
            "Школа отклонена администратором платформы. Действия в классе недоступны, "
            "пока школа не будет восстановлена.",
            403,
        )


def submit_challenge(
    conn,
    viewer: sqlite3.Row,
    settings: Settings,
    challenge_id: int,
    proof: str,
    proof_url: str = "",
    upload_id: int | None = None,
) -> dict[str, Any]:
    if effective_role(viewer, settings) != "student":
        raise GameError("Отправлять задания может только ученик", 403)
    with immediate(conn):
        user = conn.execute("SELECT * FROM users WHERE id = ?", (viewer["id"],)).fetchone()
        if user is None or user["class_id"] is None:
            raise GameError("Сначала выберите класс")
        challenge = conn.execute(
            "SELECT * FROM challenges WHERE id = ? AND active = 1", (challenge_id,)
        ).fetchone()
        if challenge is None:
            raise GameError("Задание не найдено", 404)
        if int(challenge["class_id"]) != int(user["class_id"]):
            raise GameError("Задание для другого класса", 403)
        _require_school_open(conn, int(challenge["class_id"]))
        if is_past(challenge["deadline"]):
            raise GameError("Срок выполнения уже истёк")
        proof, proof_url = _clean_proof(proof, proof_url, challenge["proof_type"] or "text")
        upload = None
        if upload_id is not None:
            # Only the student's own photo that is not attached to any work yet.
            upload = conn.execute(
                "SELECT * FROM uploads WHERE id = ? AND user_id = ? AND completion_id IS NULL",
                (upload_id, viewer["id"]),
            ).fetchone()
            if upload is None:
                raise GameError("Фото не найдено или уже использовано. Загрузите его снова.")
        existing = conn.execute(
            "SELECT * FROM completions WHERE user_id = ? AND challenge_id = ?",
            (viewer["id"], challenge_id),
        ).fetchone()
        if existing and existing["status"] in {"pending", "approved"}:
            raise GameError(
                "Задание уже на проверке" if existing["status"] == "pending" else "Задание уже выполнено"
            )
        if upload is None and (challenge["proof_type"] or "text") == "photo":
            raise GameError("Для этого задания нужно приложить фото")
        if existing:
            cursor = conn.execute(
                """
                UPDATE completions
                SET status = 'pending', proof = ?, proof_url = ?, created_at = ?, reviewed_at = NULL,
                    reviewed_by = NULL, reject_reason = ''
                WHERE id = ? AND status = 'rejected'
                """,
                (proof, proof_url, utc_sql(), existing["id"]),
            )
            if cursor.rowcount != 1:
                raise GameError("Задание уже на проверке")
            completion_id = int(existing["id"])
            # The earlier photo is detached; startup removes unattached files.
            conn.execute(
                "UPDATE uploads SET completion_id = NULL WHERE completion_id = ?",
                (completion_id,),
            )
            conn.execute("UPDATE completions SET upload_id = NULL WHERE id = ?", (completion_id,))
        else:
            try:
                cursor = conn.execute(
                    "INSERT INTO completions (user_id, challenge_id, status, proof, proof_url, created_at) "
                    "VALUES (?, ?, 'pending', ?, ?, ?)",
                    (viewer["id"], challenge_id, proof, proof_url, utc_sql()),
                )
            except sqlite3.IntegrityError:
                raise GameError("Задание уже отправлено на проверку") from None
            completion_id = int(cursor.lastrowid)
        if upload is not None:
            bound = conn.execute(
                "UPDATE uploads SET completion_id = ? WHERE id = ? AND completion_id IS NULL",
                (completion_id, upload["id"]),
            )
            if bound.rowcount != 1:
                raise GameError("Фото уже использовано. Загрузите его снова.")
            conn.execute(
                "UPDATE completions SET upload_id = ? WHERE id = ?",
                (upload["id"], completion_id),
            )
        # Sending own work is the student's activity for the day (streak).
        mark_active(conn, int(viewer["id"]), class_timezone(conn, int(user["class_id"])))
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
    if action not in REVIEW_ACTIONS:
        raise GameError("Неизвестное действие: ожидается approve или reject")
    with immediate(conn):
        row = conn.execute(
            """
            SELECT cp.*, c.title, c.xp, c.category, c.class_id,
                   u.first_name, u.last_name, u.role AS student_role,
                   u.class_id AS student_class
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
        # Staff never review their own work; in the demo the shared profile
        # previews the teacher role over its own student submissions.
        if int(row["user_id"]) == int(viewer["id"]) and not settings.demo_mode:
            raise GameError("Нельзя проверять собственную работу", 403)
        if row["student_role"] != "student":
            raise GameError("Проверять можно только работы учеников", 403)
        if row["student_class"] is None or int(row["student_class"]) != int(row["class_id"]):
            raise GameError("Ученик больше не состоит в классе")
        _require_school_open(conn, int(row["class_id"]))
        if row["status"] != "pending":
            raise GameError("Эта заявка уже проверена")
        now = utc_sql()
        student_name = f"{row['first_name']} {row['last_name']}".strip()
        if action == "reject":
            cursor = conn.execute(
                "UPDATE completions SET status = 'rejected', reject_reason = ?, "
                "reviewed_at = ?, reviewed_by = ? WHERE id = ? AND status = 'pending'",
                (str(reason or "").strip()[:200], now, viewer["id"], completion_id),
            )
            if cursor.rowcount != 1:
                raise GameError("Эта заявка уже проверена")
            return {"status": "rejected", "student_name": student_name, "xp_awarded": 0}

        # Only the request that actually moved the row out of 'pending' awards XP.
        cursor = conn.execute(
            "UPDATE completions SET status = 'approved', reviewed_at = ?, "
            "reviewed_by = ?, reject_reason = '' WHERE id = ? AND status = 'pending'",
            (now, viewer["id"], completion_id),
        )
        if cursor.rowcount != 1:
            raise GameError("Эта заявка уже проверена")
        award = award_xp(
            conn,
            int(row["user_id"]),
            int(row["xp"]),
            row["title"],
            row["category"],
            class_id=int(row["class_id"]),
            source="challenge",
            awarded_by=int(viewer["id"]),
        )
        conn.execute("UPDATE users SET sparks = sparks + 5 WHERE id = ?", (row["user_id"],))
    return {
        "status": "approved",
        "student_name": student_name,
        "xp_awarded": int(row["xp"]),
        "student_level": award["level"],
        "level_up": award["level_up"],
    }


_MONTHS_GENITIVE = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


def term_label(deadline: str | None) -> str:
    """Card label of a challenge by its deadline: today, this week or a date.

    The deadline is stored as local time with an offset, so its own date is
    the day the teacher picked.
    """
    if not deadline:
        return ""
    try:
        day = datetime.fromisoformat(str(deadline).replace("Z", "+00:00")).date()
    except ValueError:
        return ""
    today = today_local()
    if day < today:
        return "Срок прошёл"
    if day == today:
        return "На сегодня"
    if (day - today).days <= 6 - today.weekday():
        return "До конца недели"
    return f"До {day.day} {_MONTHS_GENITIVE[day.month - 1]}"


def clean_subject(subject: Any, other: Any = "") -> str:
    """Subject of a new challenge: one of SUBJECTS, or "Другое" with own text.

    Empty means no subject (SUBJECT_NONE). Own text that matches a listed
    subject (any case) is stored as the listed one, so statistics group well.
    """
    value = " ".join(str(subject or "").split())
    if not value or value == SUBJECT_NONE:
        return SUBJECT_NONE
    by_lower = {item.casefold(): item for item in SUBJECTS}
    if value == SUBJECT_OTHER:
        text = " ".join(str(other or "").split())
        if not 2 <= len(text) <= 40:
            raise GameError("Название предмета: от 2 до 40 символов")
        return by_lower.get(text.casefold(), text)
    if value.casefold() in by_lower:
        return by_lower[value.casefold()]
    raise GameError("Выберите предмет из списка или «Другое»")


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
    _require_school_open(conn, target_class)
    title = str(payload.get("title", "")).strip()
    description = str(payload.get("description", "")).strip()
    category = str(payload.get("category", ""))
    kind = str(payload.get("kind", ""))
    xp = int(payload.get("xp", 0))
    subject = clean_subject(payload.get("subject"), payload.get("subject_other"))
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
    tz = class_timezone(conn, target_class)
    deadline_raw = str(payload.get("deadline", "")).strip()
    if deadline_raw:
        try:
            day = date.fromisoformat(deadline_raw)
        except ValueError as exc:
            raise GameError("Некорректная дата") from exc
        if day < today_local(tz):
            raise GameError("Дата уже прошла")
        deadline = deadline_on(day, tz)
    else:
        # No date given: "today" and "until the end of the week" follow the kind.
        if kind == "daily":
            deadline = deadline_in(0, tz)
        elif kind == "weekly":
            deadline = deadline_in(6 - today_local(tz).weekday(), tz)
        else:
            deadline = deadline_in(2, tz)
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
    amount: int,
    reason: str,
) -> None:
    if effective_role(viewer, settings) not in {"teacher", "director"}:
        raise GameError("Поощрять учеников может только педагог или администратор", 403)
    if not (10 <= int(amount) <= 300):
        raise GameError("Количество баллов должно быть от 10 до 300")
    clean_reason = " ".join(str(reason or "").split())
    if not 3 <= len(clean_reason) <= 120:
        raise GameError("Укажите причину начисления: от 3 до 120 символов")
    with immediate(conn):
        student = conn.execute(
            "SELECT * FROM users WHERE id = ? AND role = 'student'", (student_id,)
        ).fetchone()
        if student is None:
            raise GameError("Ученик не найден", 404)
        if int(student["id"]) == int(viewer["id"]):
            raise GameError("Нельзя начислять опыт самому себе", 403)
        if not can_manage_class(conn, viewer, settings, student["class_id"]):
            raise GameError("Ученик из другого класса", 403)
        _require_school_open(conn, int(student["class_id"]))
        day_start = day_start_utc_sql(class_timezone(conn, int(student["class_id"])))
        to_student = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM xp_events "
            "WHERE user_id = ? AND source = 'manual' AND created_at >= ?",
            (student_id, day_start),
        ).fetchone()[0]
        if int(to_student) + int(amount) > MANUAL_XP_PER_STUDENT_DAY:
            left = max(0, MANUAL_XP_PER_STUDENT_DAY - int(to_student))
            raise GameError(
                f"Лимит ручных начислений ученику: {MANUAL_XP_PER_STUDENT_DAY} XP в день "
                f"от всех педагогов. Сегодня можно ещё {left} XP."
            )
        by_teacher = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM xp_events "
            "WHERE awarded_by = ? AND source = 'manual' AND created_at >= ?",
            (viewer["id"], day_start),
        ).fetchone()[0]
        if int(by_teacher) + int(amount) > MANUAL_XP_PER_TEACHER_DAY:
            left = max(0, MANUAL_XP_PER_TEACHER_DAY - int(by_teacher))
            raise GameError(
                f"Лимит ручных начислений педагога: {MANUAL_XP_PER_TEACHER_DAY} XP в день. "
                f"Сегодня можно ещё {left} XP."
            )
        award_xp(
            conn, student_id, int(amount), clean_reason, "homework",
            class_id=int(student["class_id"]), source="manual", awarded_by=int(viewer["id"]),
        )
        conn.execute("UPDATE users SET sparks = sparks + 5 WHERE id = ?", (student_id,))


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
    class_id = _demo_class_id(conn, settings)
    if class_id is None:
        raise GameError("В демо-базе нет классов", 409)
    conn.execute("DELETE FROM completions WHERE user_id = ?", (viewer["id"],))
    conn.execute("DELETE FROM xp_events WHERE user_id = ?", (viewer["id"],))
    conn.execute("DELETE FROM activity_days WHERE user_id = ?", (viewer["id"],))
    # The viewer may have left the demo class (joined another by code, was
    # removed, filed a request): the reset brings them back to the default one.
    conn.execute("DELETE FROM class_exclusions WHERE user_id = ?", (viewer["id"],))
    conn.execute("DELETE FROM join_requests WHERE user_id = ?", (viewer["id"],))
    conn.execute(
        """
        UPDATE users SET first_name = ?, last_name = ?, username = ?,
            xp = 0, sparks = 0, streak = 0, last_active_date = NULL,
            avatar = ?, owned = '[]', onboarded = 0, preview_role = NULL,
            class_id = ?
        WHERE id = ?
        """,
        (
            DEMO_FIRST_NAME,
            DEMO_LAST_NAME,
            DEMO_USERNAME,
            dump_avatar(BASIC_AVATAR),
            class_id,
            viewer["id"],
        ),
    )
    from .demo_seed import seed_demo_progress

    seed_demo_progress(conn, int(viewer["id"]), class_id)


def _demo_class_id(conn, settings: Settings) -> int | None:
    """Default demo class: DEFAULT_CLASS_ID when it exists, else the first class."""
    if settings.default_class_id is not None:
        row = conn.execute(
            "SELECT id FROM classes WHERE id = ?", (settings.default_class_id,)
        ).fetchone()
        if row:
            return int(row["id"])
    row = conn.execute("SELECT id FROM classes ORDER BY id LIMIT 1").fetchone()
    return int(row["id"]) if row else None



