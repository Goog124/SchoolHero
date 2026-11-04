"""SQLite connection, schema and migrations."""

from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schools (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_by INTEGER REFERENCES users(id),
    created_at TEXT,
    norm_key TEXT,
    UNIQUE(name, city)
);

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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    xp INTEGER NOT NULL DEFAULT 0 CHECK(xp >= 0),
    sparks INTEGER NOT NULL DEFAULT 0 CHECK(sparks >= 0),
    streak INTEGER NOT NULL DEFAULT 0,
    last_active_date TEXT,
    avatar TEXT NOT NULL,
    owned TEXT NOT NULL DEFAULT '[]',
    onboarded INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

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
    UNIQUE(user_id, challenge_id)
);

CREATE INDEX IF NOT EXISTS idx_completions_status ON completions(status, created_at);

CREATE TABLE IF NOT EXISTS xp_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    amount INTEGER NOT NULL,
    reason TEXT NOT NULL,
    category TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
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

CREATE TABLE IF NOT EXISTS activity_days (
    user_id INTEGER NOT NULL REFERENCES users(id),
    day TEXT NOT NULL,
    PRIMARY KEY(user_id, day)
);
"""


def school_key(name: str, city: str) -> str:
    """Case-insensitive identity of a school (SQLite lower() ignores Cyrillic)."""
    def norm(value: str) -> str:
        return " ".join(str(value).split()).casefold()

    return f"{norm(name)}|{norm(city)}"


def backfill_school_keys(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT id, name, city FROM schools WHERE norm_key IS NULL"
    ).fetchall()
    for row in rows:
        try:
            conn.execute(
                "UPDATE schools SET norm_key = ? WHERE id = ?",
                (school_key(row["name"], row["city"]), row["id"]),
            )
        except sqlite3.IntegrityError:
            pass  # legacy duplicate: leave NULL, the unique index skips NULLs
    conn.commit()


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=15)
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


def _rebuild_schools(conn: sqlite3.Connection) -> None:
    """Replace UNIQUE(name) with UNIQUE(name, city): schools of the same name
    exist in different cities."""
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.executescript(
            """
            BEGIN;
            CREATE TABLE schools_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                city TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                created_by INTEGER REFERENCES users(id),
                created_at TEXT,
                norm_key TEXT,
                UNIQUE(name, city)
            );
            INSERT INTO schools_new (id, name, city, status, created_by, created_at, norm_key)
                SELECT id, name, city, COALESCE(status, 'active'), created_by, created_at, norm_key
                FROM schools;
            DROP TABLE schools;
            ALTER TABLE schools_new RENAME TO schools;
            COMMIT;
            """
        )
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _migrate_columns(conn: sqlite3.Connection) -> None:
    challenge_cols = _columns(conn, "challenges")
    if "subject" not in challenge_cols:
        conn.execute("ALTER TABLE challenges ADD COLUMN subject TEXT NOT NULL DEFAULT 'Общее'")
    if "proof_type" not in challenge_cols:
        conn.execute("ALTER TABLE challenges ADD COLUMN proof_type TEXT NOT NULL DEFAULT 'text'")

    if "proof_url" not in _columns(conn, "completions"):
        conn.execute("ALTER TABLE completions ADD COLUMN proof_url TEXT NOT NULL DEFAULT ''")

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

    school_cols = _columns(conn, "schools")
    if "status" not in school_cols:
        conn.execute("ALTER TABLE schools ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
    if "created_by" not in school_cols:
        conn.execute("ALTER TABLE schools ADD COLUMN created_by INTEGER REFERENCES users(id)")
    if "created_at" not in school_cols:
        conn.execute("ALTER TABLE schools ADD COLUMN created_at TEXT")
    if "norm_key" not in school_cols:
        conn.execute("ALTER TABLE schools ADD COLUMN norm_key TEXT")
    conn.commit()

    if _schools_name_is_unique(conn):
        _rebuild_schools(conn)

    backfill_school_keys(conn)
    _create_indexes(conn)


def _create_indexes(conn: sqlite3.Connection) -> None:
    statements = [
        "CREATE INDEX IF NOT EXISTS idx_users_role_class ON users(role, class_id)",
        "CREATE INDEX IF NOT EXISTS idx_classes_school ON classes(school_id)",
        "CREATE INDEX IF NOT EXISTS idx_xp_events_created ON xp_events(created_at, user_id)",
        "CREATE INDEX IF NOT EXISTS idx_completions_user ON completions(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_completions_challenge ON completions(challenge_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_schools_status_city ON schools(status, city)",
        "CREATE INDEX IF NOT EXISTS idx_schools_created_by ON schools(created_by)",
        "CREATE INDEX IF NOT EXISTS idx_school_staff_school ON school_staff(school_id)",
        # Codes must be unambiguous. Legacy data with duplicates must not
        # block startup, so these are best-effort.
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_classes_invite_code ON classes(invite_code) "
        "WHERE invite_code IS NOT NULL",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_classes_teacher_code ON classes(teacher_code) "
        "WHERE teacher_code IS NOT NULL",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_schools_norm_key ON schools(norm_key) "
        "WHERE norm_key IS NOT NULL",
    ]
    for statement in statements:
        try:
            conn.execute(statement)
        except sqlite3.IntegrityError:
            pass
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
