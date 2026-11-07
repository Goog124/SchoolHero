"""SQLite connection, schema and migrations."""

from __future__ import annotations

import logging
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

log = logging.getLogger("uvicorn.error")

# Column list of ``users``: shared by SCHEMA and the table rebuild that
# replaces an old CHECK(role IN ('student', 'teacher')) without 'director'.
USERS_COLUMNS = """    id INTEGER PRIMARY KEY AUTOINCREMENT,
    max_user_id TEXT UNIQUE,
    client_id TEXT UNIQUE,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL DEFAULT '',
    username TEXT NOT NULL DEFAULT '',
    photo_url TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'student' CHECK(role IN ('student', 'teacher', 'director')),
    preview_role TEXT,
    class_id INTEGER REFERENCES classes(id),
    school_id INTEGER REFERENCES schools(id),
    name_locked INTEGER NOT NULL DEFAULT 0,
    -- when the current class was taken (code, approved request); shown to directors
    class_since TEXT,
    -- 1 = a director disconnected this teacher: env lists must not reattach them
    staff_detached INTEGER NOT NULL DEFAULT 0,
    -- 1 = platform administrator (set by the first-user bootstrap, by another
    -- admin, or by the sandbox switch); PLATFORM_ADMIN_MAX_IDS works besides it
    platform_admin INTEGER NOT NULL DEFAULT 0,
    -- set by a platform admin: the user gets 403 on every /api/* but /api/health
    blocked_at TEXT,
    blocked_reason TEXT NOT NULL DEFAULT '',
    xp INTEGER NOT NULL DEFAULT 0 CHECK(xp >= 0),
    sparks INTEGER NOT NULL DEFAULT 0 CHECK(sparks >= 0),
    streak INTEGER NOT NULL DEFAULT 0,
    last_active_date TEXT,
    avatar TEXT NOT NULL,
    owned TEXT NOT NULL DEFAULT '[]',
    onboarded INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
"""

SCHOOLS_COLUMNS = """    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_by INTEGER REFERENCES users(id),
    created_at TEXT,
    norm_key TEXT,
    -- IANA zone of the school: "today", weeks, deadlines, daily limits
    timezone TEXT NOT NULL DEFAULT 'Europe/Moscow',
    -- why the platform admin rejected the school (shown to its director)
    reject_reason TEXT NOT NULL DEFAULT '',
    UNIQUE(name, city)
"""

SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schools (
{SCHOOLS_COLUMNS});

CREATE TABLE IF NOT EXISTS classes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    school_id INTEGER NOT NULL REFERENCES schools(id),
    name TEXT NOT NULL,
    weekly_goal INTEGER NOT NULL DEFAULT 1600,
    invite_code TEXT,
    teacher_code TEXT,
    UNIQUE(school_id, name)
);

CREATE TABLE IF NOT EXISTS users (
{USERS_COLUMNS});

CREATE INDEX IF NOT EXISTS idx_users_class ON users(class_id);
CREATE INDEX IF NOT EXISTS idx_users_xp ON users(xp DESC);

CREATE TABLE IF NOT EXISTS challenges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_id INTEGER NOT NULL REFERENCES classes(id),
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL,
    xp INTEGER NOT NULL CHECK(xp > 0 AND xp <= 500),
    kind TEXT NOT NULL DEFAULT 'daily' CHECK(kind IN ('daily', 'weekly', 'event')),
    deadline TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT 'Общее',
    proof_type TEXT NOT NULL DEFAULT 'text' CHECK(proof_type IN ('text', 'link', 'photo')),
    created_by INTEGER REFERENCES users(id),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_challenges_class ON challenges(class_id, active);

CREATE TABLE IF NOT EXISTS completions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    challenge_id INTEGER NOT NULL REFERENCES challenges(id),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending', 'approved', 'rejected')),
    proof TEXT NOT NULL DEFAULT '',
    proof_url TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    reviewed_at TEXT,
    reviewed_by INTEGER REFERENCES users(id),
    reject_reason TEXT NOT NULL DEFAULT '',
    -- photo of the current submission (uploads.id), NULL without a photo
    upload_id INTEGER REFERENCES uploads(id) ON DELETE SET NULL,
    UNIQUE(user_id, challenge_id)
);

-- Photos sent as proof. The file lives in the uploads directory next to the
-- database (``path`` is the file name there); ``completion_id`` is set when
-- the photo is attached to a submission. Unattached rows older than a day are
-- removed at startup.
CREATE TABLE IF NOT EXISTS uploads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    path TEXT NOT NULL UNIQUE,
    content_type TEXT NOT NULL,
    size INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completion_id INTEGER REFERENCES completions(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_uploads_user ON uploads(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_uploads_completion ON uploads(completion_id);

CREATE INDEX IF NOT EXISTS idx_completions_status ON completions(status, created_at);

CREATE TABLE IF NOT EXISTS xp_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    amount INTEGER NOT NULL,
    reason TEXT NOT NULL,
    category TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    -- class the XP was earned in: class ratings count only their own events,
    -- so a student who changes class does not carry XP into the new rating
    class_id INTEGER REFERENCES classes(id),
    -- 'challenge' (approved work) or 'manual' (teacher reward); NULL for legacy
    source TEXT,
    awarded_by INTEGER REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_xp_events_user ON xp_events(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS class_staff (
    max_user_id TEXT PRIMARY KEY,
    class_id INTEGER NOT NULL REFERENCES classes(id)
);

CREATE TABLE IF NOT EXISTS school_staff (
    user_id INTEGER NOT NULL REFERENCES users(id),
    school_id INTEGER NOT NULL REFERENCES schools(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY(user_id, school_id)
);

CREATE TABLE IF NOT EXISTS class_exclusions (
    user_id INTEGER NOT NULL REFERENCES users(id),
    class_id INTEGER NOT NULL REFERENCES classes(id),
    removed_by INTEGER REFERENCES users(id),
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY(user_id, class_id)
);

-- Choosing a class from the public list is a request the class teacher (or
-- the school director) approves; codes still join at once.
CREATE TABLE IF NOT EXISTS join_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    class_id INTEGER NOT NULL REFERENCES classes(id),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending', 'approved', 'declined', 'cancelled')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    decided_at TEXT,
    decided_by INTEGER REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS activity_days (
    user_id INTEGER NOT NULL REFERENCES users(id),
    day TEXT NOT NULL,
    PRIMARY KEY(user_id, day)
);
""".replace("{USERS_COLUMNS}", USERS_COLUMNS).replace("{SCHOOLS_COLUMNS}", SCHOOLS_COLUMNS)


def school_key(name: str, city: str) -> str:
    """Case-insensitive identity of a school (SQLite lower() ignores Cyrillic)."""
    def norm(value: str) -> str:
        return " ".join(str(value).split()).casefold()

    return f"{norm(name)}|{norm(city)}"


def backfill_school_keys(conn: sqlite3.Connection) -> list[int]:
    """Fill ``norm_key`` and make it unique, so the unique index can be built.

    An old schema allowed schools whose names differ only in case or spaces
    ("Школа 1" and "школа  1" in one city). Rows are walked in id order: the
    oldest school keeps the key, every later duplicate gets ``<key>#<id>``.
    The result is deterministic and idempotent (a suffixed key is unique and
    stays as is). Returns the ids of schools whose key got a suffix.
    """
    rows = conn.execute("SELECT id, name, city, norm_key FROM schools ORDER BY id").fetchall()
    seen: set[str] = set()
    renamed: list[int] = []
    updates: list[tuple[str, int]] = []
    for row in rows:
        base = row["norm_key"] or school_key(row["name"], row["city"])
        key = base
        if key in seen:
            key = f"{base}#{row['id']}"
            renamed.append(int(row["id"]))
        seen.add(key)
        if key != row["norm_key"]:
            updates.append((key, int(row["id"])))
    # Suffixed keys first: they free the base key held by a later duplicate.
    updates.sort(key=lambda item: "#" not in item[0])
    for key, school_id in updates:
        conn.execute("UPDATE schools SET norm_key = ? WHERE id = ?", (key, school_id))
    conn.commit()
    if renamed:
        log.warning(
            "Школы с совпадающим названием и городом (без учёта регистра): id %s. "
            "Их norm_key получил суффикс #id; объедините или переименуйте их вручную.",
            ", ".join(str(i) for i in renamed),
        )
    return renamed


def connect(db_path: Path, *, check_same_thread: bool = True) -> sqlite3.Connection:
    """Open a connection.

    ``check_same_thread=False`` is for the per-request connection of the API:
    FastAPI runs a sync dependency and the sync endpoint in (possibly)
    different worker threads. The connection is still used by one request
    only and never by two threads at the same time.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=15, check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    conn.execute("PRAGMA synchronous = NORMAL")
    # SQLite lower()/LIKE ignore case for ASCII only; casefold() works for Cyrillic.
    conn.create_function(
        "casefold", 1, lambda value: value.casefold() if isinstance(value, str) else value,
        deterministic=True,
    )
    return conn


@contextmanager
def immediate(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run a multi-step change as one ``BEGIN IMMEDIATE`` transaction.

    The write lock is taken before the first read, so check-then-write
    sequences (balance, status, limits) cannot interleave with another
    request. Commits on success, rolls back on any exception. Nested use
    joins the outer transaction.
    """
    if conn.in_transaction:
        yield conn
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.rollback()
        raise
    else:
        conn.commit()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _schools_name_is_unique(conn: sqlite3.Connection) -> bool:
    """True for the legacy ``name TEXT UNIQUE`` constraint on schools."""
    for index in conn.execute("PRAGMA index_list(schools)").fetchall():
        if not index["unique"]:
            continue
        cols = [r["name"] for r in conn.execute(f"PRAGMA index_info({index['name']})")]
        if cols == ["name"]:
            return True
    return False


def _fk_violations(conn: sqlite3.Connection) -> int:
    return len(conn.execute("PRAGMA foreign_key_check").fetchall())


def _rebuild_table(
    conn: sqlite3.Connection,
    table: str,
    columns_sql: str,
    expressions: dict[str, str] | None = None,
) -> None:
    """Recreate ``table`` with a new definition (SQLite cannot ALTER a
    constraint), following https://www.sqlite.org/lang_altertable.html#otheralter:

    foreign keys off (outside a transaction), one transaction: new table,
    copy of the common columns (``expressions`` may transform a column),
    drop, rename, re-create the table's own indexes and triggers,
    ``PRAGMA foreign_key_check``, commit, foreign keys back on. The copy must
    not add foreign key violations; legacy ones that were already there do
    not block startup.
    """
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        before = _fk_violations(conn)
        conn.execute("BEGIN")
        try:
            extras = [
                row["sql"]
                for row in conn.execute(
                    "SELECT sql FROM sqlite_master WHERE tbl_name = ? "
                    "AND type IN ('index', 'trigger') AND sql IS NOT NULL",
                    (table,),
                ).fetchall()
            ]
            new = f"{table}__rebuild"
            conn.execute(f"DROP TABLE IF EXISTS {new}")
            conn.execute(f"CREATE TABLE {new} (\n{columns_sql})")
            old_cols = _columns(conn, table)
            common = [
                row["name"]
                for row in conn.execute(f"PRAGMA table_info({new})").fetchall()
                if row["name"] in old_cols
            ]
            exprs = [(expressions or {}).get(col, col) for col in common]
            conn.execute(
                f"INSERT INTO {new} ({', '.join(common)}) "
                f"SELECT {', '.join(exprs)} FROM {table}"
            )
            conn.execute(f"DROP TABLE {table}")
            conn.execute(f"ALTER TABLE {new} RENAME TO {table}")
            for sql in extras:
                conn.execute(sql)
            after = _fk_violations(conn)
            if after > before:
                raise RuntimeError(
                    f"Миграция таблицы {table}: foreign_key_check нашёл {after - before} "
                    "новых нарушений, изменения отменены"
                )
        except BaseException:
            conn.rollback()
            raise
        else:
            conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _rebuild_schools(conn: sqlite3.Connection) -> None:
    """Replace UNIQUE(name) with UNIQUE(name, city): schools of the same name
    exist in different cities."""
    _rebuild_table(
        conn, "schools", SCHOOLS_COLUMNS, {"status": "COALESCE(status, 'active')"}
    )


_ROLE_CHECK_RE = re.compile(r"CHECK\s*\(\s*role\s+IN\s*\(([^)]*)\)", re.IGNORECASE)


def _users_role_check_outdated(conn: sqlite3.Connection) -> bool:
    """True for an old ``CHECK(role IN ('student', 'teacher'))`` without
    'director': registering a school would fail with a constraint error."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'users'"
    ).fetchone()
    match = _ROLE_CHECK_RE.search(row["sql"] or "") if row else None
    return bool(match) and "'director'" not in match.group(1)


def _rebuild_users(conn: sqlite3.Connection) -> None:
    _rebuild_table(
        conn,
        "users",
        USERS_COLUMNS,
        {
            "role": "CASE WHEN role IN ('student', 'teacher', 'director') THEN role "
            "ELSE 'student' END",
            "xp": "MAX(COALESCE(xp, 0), 0)",
            "sparks": "MAX(COALESCE(sparks, 0), 0)",
            "avatar": "COALESCE(avatar, '{}')",
        },
    )


def _migrate_columns(conn: sqlite3.Connection) -> None:
    challenge_cols = _columns(conn, "challenges")
    if "subject" not in challenge_cols:
        conn.execute("ALTER TABLE challenges ADD COLUMN subject TEXT NOT NULL DEFAULT 'Общее'")
    if "proof_type" not in challenge_cols:
        conn.execute("ALTER TABLE challenges ADD COLUMN proof_type TEXT NOT NULL DEFAULT 'text'")

    event_cols = _columns(conn, "xp_events")
    if "class_id" not in event_cols:
        conn.execute("ALTER TABLE xp_events ADD COLUMN class_id INTEGER REFERENCES classes(id)")
        # Legacy events: attributed to the student's current class, once.
        conn.execute(
            "UPDATE xp_events SET class_id = "
            "(SELECT class_id FROM users WHERE users.id = xp_events.user_id) "
            "WHERE class_id IS NULL"
        )
    if "source" not in event_cols:
        conn.execute("ALTER TABLE xp_events ADD COLUMN source TEXT")
    if "awarded_by" not in event_cols:
        conn.execute("ALTER TABLE xp_events ADD COLUMN awarded_by INTEGER REFERENCES users(id)")

    completion_cols = _columns(conn, "completions")
    if "proof_url" not in completion_cols:
        conn.execute("ALTER TABLE completions ADD COLUMN proof_url TEXT NOT NULL DEFAULT ''")
    if "upload_id" not in completion_cols:
        conn.execute(
            "ALTER TABLE completions ADD COLUMN upload_id INTEGER "
            "REFERENCES uploads(id) ON DELETE SET NULL"
        )

    class_cols = _columns(conn, "classes")
    if "invite_code" not in class_cols:
        conn.execute("ALTER TABLE classes ADD COLUMN invite_code TEXT")
    if "teacher_code" not in class_cols:
        conn.execute("ALTER TABLE classes ADD COLUMN teacher_code TEXT")

    user_cols = _columns(conn, "users")
    if "school_id" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN school_id INTEGER REFERENCES schools(id)")
    if "name_locked" not in user_cols:
        # 1 = the name was typed by the person; MAX data must not overwrite it.
        conn.execute("ALTER TABLE users ADD COLUMN name_locked INTEGER NOT NULL DEFAULT 0")
    if "class_since" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN class_since TEXT")
    if "staff_detached" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN staff_detached INTEGER NOT NULL DEFAULT 0")
    if "platform_admin" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN platform_admin INTEGER NOT NULL DEFAULT 0")
        if "sandbox_admin" in user_cols:
            # The sandbox switch now uses the same column.
            conn.execute("UPDATE users SET platform_admin = sandbox_admin")
    if "blocked_at" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN blocked_at TEXT")
    if "blocked_reason" not in user_cols:
        conn.execute("ALTER TABLE users ADD COLUMN blocked_reason TEXT NOT NULL DEFAULT ''")

    school_cols = _columns(conn, "schools")
    if "status" not in school_cols:
        conn.execute("ALTER TABLE schools ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
    if "created_by" not in school_cols:
        conn.execute("ALTER TABLE schools ADD COLUMN created_by INTEGER REFERENCES users(id)")
    if "created_at" not in school_cols:
        conn.execute("ALTER TABLE schools ADD COLUMN created_at TEXT")
    if "norm_key" not in school_cols:
        conn.execute("ALTER TABLE schools ADD COLUMN norm_key TEXT")
    if "timezone" not in school_cols:
        conn.execute(
            "ALTER TABLE schools ADD COLUMN timezone TEXT NOT NULL DEFAULT 'Europe/Moscow'"
        )
    if "reject_reason" not in school_cols:
        conn.execute("ALTER TABLE schools ADD COLUMN reject_reason TEXT NOT NULL DEFAULT ''")
    conn.commit()

    if _schools_name_is_unique(conn):
        _rebuild_schools(conn)
    if _users_role_check_outdated(conn):
        _rebuild_users(conn)

    backfill_school_keys(conn)
    _create_indexes(conn)


def _create_indexes(conn: sqlite3.Connection) -> None:
    statements = [
        "CREATE INDEX IF NOT EXISTS idx_users_role_class ON users(role, class_id)",
        "CREATE INDEX IF NOT EXISTS idx_classes_school ON classes(school_id)",
        "CREATE INDEX IF NOT EXISTS idx_xp_events_created ON xp_events(created_at, user_id)",
        "CREATE INDEX IF NOT EXISTS idx_completions_user ON completions(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_xp_events_class ON xp_events(class_id, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_xp_events_manual ON xp_events(source, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_completions_challenge ON completions(challenge_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_schools_status_city ON schools(status, city)",
        "CREATE INDEX IF NOT EXISTS idx_schools_created_by ON schools(created_by)",
        "CREATE INDEX IF NOT EXISTS idx_school_staff_school ON school_staff(school_id)",
        "CREATE INDEX IF NOT EXISTS idx_class_exclusions_class ON class_exclusions(class_id, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_class_exclusions_user ON class_exclusions(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_join_requests_class ON join_requests(class_id, status, created_at)",
        "CREATE INDEX IF NOT EXISTS idx_join_requests_user ON join_requests(user_id, created_at)",
        # One active request per student.
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_join_requests_one_pending ON join_requests(user_id) "
        "WHERE status = 'pending'",
        "CREATE INDEX IF NOT EXISTS idx_completions_upload ON completions(upload_id)",
        "CREATE INDEX IF NOT EXISTS idx_activity_days_day ON activity_days(day, user_id)",
        # backfill_school_keys has made norm_key unique: a failure here is a
        # real error and must not be hidden.
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_schools_norm_key ON schools(norm_key) "
        "WHERE norm_key IS NOT NULL",
    ]
    for statement in statements:
        conn.execute(statement)
    # Codes must be unambiguous. Legacy data with duplicate codes must not
    # block startup, so these are best-effort (logged).
    for name, column in (
        ("idx_classes_invite_code", "invite_code"),
        ("idx_classes_teacher_code", "teacher_code"),
    ):
        try:
            conn.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {name} ON classes({column}) "
                f"WHERE {column} IS NOT NULL"
            )
        except sqlite3.IntegrityError:
            log.warning("Индекс %s не создан: в classes.%s есть повторы", name, column)
    conn.commit()


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
        _migrate_columns(conn)
    finally:
        conn.close()
