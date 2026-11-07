"""Migrations of old databases: duplicate school keys, users CHECK without 'director'."""

from __future__ import annotations

import sqlite3

from backend.db import connect, init_db

OLD_USERS = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT, max_user_id TEXT UNIQUE, client_id TEXT UNIQUE,
    first_name TEXT NOT NULL, last_name TEXT NOT NULL DEFAULT '', username TEXT NOT NULL DEFAULT '',
    photo_url TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'student' CHECK(role IN ('student', 'teacher')),
    preview_role TEXT, class_id INTEGER REFERENCES classes(id),
    xp INTEGER NOT NULL DEFAULT 0, sparks INTEGER NOT NULL DEFAULT 0, streak INTEGER NOT NULL DEFAULT 0,
    last_active_date TEXT, avatar TEXT NOT NULL, owned TEXT NOT NULL DEFAULT '[]',
    onboarded INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_users_class ON users(class_id);
"""


def make_old(path, extra=""):
    raw = sqlite3.connect(path)
    raw.executescript(
        """
        CREATE TABLE schools (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            city TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active',
            created_by INTEGER, created_at TEXT, norm_key TEXT, UNIQUE(name, city));
        CREATE TABLE classes (id INTEGER PRIMARY KEY AUTOINCREMENT,
            school_id INTEGER NOT NULL REFERENCES schools(id), name TEXT NOT NULL,
            weekly_goal INTEGER NOT NULL DEFAULT 1600, invite_code TEXT, teacher_code TEXT,
            UNIQUE(school_id, name));
        """
        + OLD_USERS
        + extra
    )
    raw.commit()
    raw.close()


def test_duplicate_school_keys_get_deterministic_suffix_and_index(tmp_path):
    db = tmp_path / "dup.db"
    make_old(
        db,
        """
        INSERT INTO schools (name, city) VALUES ('Школа 1', 'Москва');
        INSERT INTO schools (name, city) VALUES ('школа  1', 'москва');
        INSERT INTO schools (name, city) VALUES ('ШКОЛА 1', 'Москва ');
        INSERT INTO schools (name, city) VALUES ('Школа 2', 'Москва');
        """,
    )
    init_db(db)
    first = _keys(db)
    init_db(db)  # idempotent
    assert _keys(db) == first
    assert first[0] == "школа 1|москва" or "|" in first[0]
    assert first[1] == f"{first[0]}#2" and first[2] == f"{first[0]}#3"
    assert len(set(first)) == 4
    conn = connect(db)
    try:
        names = {r["name"] for r in conn.execute("PRAGMA index_list(schools)")}
        assert "idx_schools_norm_key" in names
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


def _keys(db):
    conn = connect(db)
    try:
        return [r[0] for r in conn.execute("SELECT norm_key FROM schools ORDER BY id")]
    finally:
        conn.close()


def test_users_check_without_director_is_rebuilt(tmp_path):
    db = tmp_path / "old_users.db"
    make_old(
        db,
        """
        INSERT INTO schools (name, city) VALUES ('Школа 1', 'Москва');
        INSERT INTO classes (school_id, name) VALUES (1, '8А');
        INSERT INTO users (max_user_id, first_name, avatar, class_id, xp, role)
            VALUES ('1', 'Иван', '{"hair":"a"}', 1, 120, 'student');
        INSERT INTO users (max_user_id, first_name, avatar, class_id, role)
            VALUES ('2', 'Анна', '{}', 1, 'teacher');
        CREATE TABLE fk_probe (id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id));
        INSERT INTO fk_probe (user_id) VALUES (1);
        """,
    )
    init_db(db)
    init_db(db)
    conn = connect(db)
    try:
        conn.execute("UPDATE users SET role = 'director' WHERE id = 2")  # CHECK now allows it
        rows = conn.execute("SELECT id, first_name, role, xp, avatar, class_id FROM users ORDER BY id").fetchall()
        assert [(r["id"], r["first_name"], r["xp"], r["class_id"]) for r in rows] == [
            (1, "Иван", 120, 1),
            (2, "Анна", 0, 1),
        ]
        assert rows[0]["avatar"] == '{"hair":"a"}' and rows[1]["role"] == "director"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM fk_probe").fetchone()[0] == 1
        index_names = {r["name"] for r in conn.execute("PRAGMA index_list(users)")}
        assert "idx_users_class" in index_names
        assert not [t for t in conn.execute("SELECT name FROM sqlite_master WHERE name LIKE '%__rebuild'")]
    finally:
        conn.close()
