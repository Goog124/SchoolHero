"""Platform admin panel: schools list, rejection reason, deleting a school,
user search, blocking."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import app
from backend.db import connect, init_db
from conftest import make_settings
from test_registration import (
    ADMIN_ID,
    MAX_TOKEN,
    class_codes,
    create_school,
    hdr,
    make_client,
    onboard_student,
)

DIRECTOR = 100
PUPIL = 201
PUPIL2 = 202
TEACHER = 300


@pytest.fixture
def client(tmp_path):
    c = make_client(tmp_path)
    yield c
    c.close()


def db(client):
    return connect(app.state.settings.db_path)


def state(client, user_id):
    r = client.get("/api/state", headers=hdr(user_id))
    assert r.status_code == 200, r.text
    return r.json()


def user_row(client, max_id):
    conn = db(client)
    try:
        return conn.execute("SELECT * FROM users WHERE max_user_id = ?", (str(max_id),)).fetchone()
    finally:
        conn.close()


def build_school(client, name="Гимназия №5", city="Новгород"):
    """School with a director, two pupils and a teacher; returns ids."""
    assert create_school(client, DIRECTOR, name=name, city=city).status_code == 200
    sid = state(client, DIRECTOR)["school_admin"]["schools"][0]["id"]
    # manual approval: codes work only after the admin confirmed the school
    client.post(f"/api/admin/schools/{sid}/status", json={"status": "active"}, headers=hdr(ADMIN_ID))
    codes = class_codes(client, DIRECTOR)
    onboard_student(client, PUPIL, codes["8А"]["invite_code"])
    onboard_student(client, PUPIL2, codes["8Б"]["invite_code"])
    r = client.post(
        "/api/school/join", json={"invite_code": codes["8А"]["teacher_code"]}, headers=hdr(TEACHER)
    )
    assert r.status_code == 200, r.text
    school_id = state(client, DIRECTOR)["school_admin"]["schools"][0]["id"]
    return school_id, codes


# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------


def test_admin_endpoints_hidden_from_everyone_else(client):
    school_id, _ = build_school(client)
    for uid in (PUPIL, TEACHER, DIRECTOR, 999):
        h = hdr(uid)
        assert client.get("/api/admin/schools", headers=h).status_code == 404
        assert client.get(f"/api/admin/schools/{school_id}", headers=h).status_code == 404
        assert client.get("/api/admin/users", headers=h).status_code == 404
        body = {"confirm_name": "Гимназия №5"}
        assert client.post(f"/api/admin/schools/{school_id}/delete", json=body, headers=h).status_code == 404
        assert client.post("/api/admin/users/1/block", json={"reason": "спам"}, headers=h).status_code == 404
        assert client.post("/api/admin/users/1/unblock", headers=h).status_code == 404
    # nothing happened
    assert client.get("/api/admin/schools", headers=hdr(ADMIN_ID)).json()["total"] == 1


# ---------------------------------------------------------------------------
# Schools list, filters, summary
# ---------------------------------------------------------------------------


def test_school_list_filters_search_and_counts(tmp_path):
    c = make_client(tmp_path, school_approval="manual")
    try:
        school_id, codes = build_school(c)
        assert create_school(c, 101, name="Лицей Звезда", city="Казань").status_code == 200
        admin = hdr(ADMIN_ID)

        data = c.get("/api/admin/schools", headers=admin).json()
        assert data["total"] == 2 and data["limit"] == 50 and data["has_more"] is False
        assert data["summary"]["schools"] == {"pending": 1, "active": 1, "rejected": 0, "total": 2}

        pending = c.get("/api/admin/schools?status=pending", headers=admin).json()
        assert pending["total"] == 1 and pending["items"][0]["name"] == "Лицей Звезда"
        assert c.get("/api/admin/schools?status=active", headers=admin).json()["total"] == 1
        assert c.get("/api/admin/schools?status=bogus", headers=admin).status_code == 400
        assert c.get("/api/admin/schools?status=all", headers=admin).json()["total"] == 2

        by_city = c.get("/api/admin/schools?q=казань", headers=admin).json()
        assert [s["name"] for s in by_city["items"]] == ["Лицей Звезда"]
        by_name = c.get("/api/admin/schools?q=ГИМНАЗИЯ", headers=admin).json()
        assert [s["id"] for s in by_name["items"]] == [school_id]
        assert c.get("/api/admin/schools?q=%25", headers=admin).json()["total"] == 0

        item = by_name["items"][0]
        assert item["classes"] == 2 and item["students"] == 2 and item["teachers"] == 1
        assert item["director"].startswith("Пользователь")
        assert item["status"] == "active" and item["created_at"]
        assert item["active_week"] == 0
        # pagination
        page = c.get("/api/admin/schools?limit=1", headers=admin).json()
        assert len(page["items"]) == 1 and page["has_more"] is True
        page2 = c.get("/api/admin/schools?limit=1&offset=1", headers=admin).json()
        assert page2["items"][0]["id"] != page["items"][0]["id"] and page2["has_more"] is False

        # active students over the last 7 days
        conn = db(c)
        pupil_id = user_row(c, PUPIL)["id"]
        conn.execute("INSERT INTO activity_days (user_id, day) VALUES (?, date('now'))", (pupil_id,))
        conn.execute(
            "INSERT INTO activity_days (user_id, day) VALUES (?, date('now', '-30 day'))",
            (user_row(c, PUPIL2)["id"],),
        )
        conn.commit()
        conn.close()
        item = c.get(f"/api/admin/schools?q=гимназия", headers=admin).json()["items"][0]
        assert item["active_week"] == 1
        summary = c.get("/api/admin/schools", headers=admin).json()["summary"]
        assert summary["active_students_week"] == 1
        assert summary["users"]["student"] == 3 and summary["users"]["director"] == 2
        assert summary["users"]["teacher"] == 1
    finally:
        c.close()


def test_summary_counts_pending_works(client):
    build_school(client)
    conn = db(client)
    class_id = conn.execute("SELECT id FROM classes ORDER BY id LIMIT 1").fetchone()["id"]
    conn.execute(
        "INSERT INTO challenges (class_id, title, category, xp, deadline) VALUES (?, 'Задание', 'study', 20, '2999-01-01')",
        (class_id,),
    )
    pupil_id = user_row(client, PUPIL)["id"]
    conn.execute("INSERT INTO completions (user_id, challenge_id, status) VALUES (?, 1, 'pending')", (pupil_id,))
    conn.commit()
    conn.close()
    summary = client.get("/api/admin/schools", headers=hdr(ADMIN_ID)).json()["summary"]
    assert summary["pending_works"] == 1


def test_school_detail_has_classes_without_codes(client):
    school_id, codes = build_school(client)
    data = client.get(f"/api/admin/schools/{school_id}", headers=hdr(ADMIN_ID)).json()
    names = [c["name"] for c in data["classes"]]
    assert names == ["8А", "8Б"]
    first = data["classes"][0]
    assert (first["students"], first["teachers"]) == (1, 1)
    assert len(first["teacher_names"]) == 1
    assert "invite_code" not in first and "teacher_code" not in first
    assert codes["8А"]["invite_code"] not in str(data)
    assert codes["8А"]["teacher_code"] not in str(data)
    assert client.get("/api/admin/schools/9999", headers=hdr(ADMIN_ID)).status_code == 404


# ---------------------------------------------------------------------------
# Rejection with a reason
# ---------------------------------------------------------------------------


def test_reject_with_reason_is_visible_to_director(client):
    school_id, _ = build_school(client)
    admin = hdr(ADMIN_ID)
    r = client.post(
        f"/api/admin/schools/{school_id}/status",
        json={"status": "rejected", "reason": "  Нет   такой школы  "},
        headers=admin,
    )
    assert r.status_code == 200
    school = state(client, DIRECTOR)["school_admin"]["schools"][0]
    assert school["status"] == "rejected" and school["reject_reason"] == "Нет такой школы"
    listed = client.get("/api/admin/schools?status=rejected", headers=admin).json()["items"][0]
    assert listed["reject_reason"] == "Нет такой школы"

    # without a reason it is simply empty; returning clears the old one
    client.post(f"/api/admin/schools/{school_id}/status", json={"status": "rejected"}, headers=admin)
    assert state(client, DIRECTOR)["school_admin"]["schools"][0]["reject_reason"] == ""
    client.post(f"/api/admin/schools/{school_id}/status", json={"status": "rejected", "reason": "Спам"}, headers=admin)
    client.post(f"/api/admin/schools/{school_id}/status", json={"status": "active"}, headers=admin)
    school = state(client, DIRECTOR)["school_admin"]["schools"][0]
    assert school["status"] == "active" and school["reject_reason"] == ""
    # a reason is only a reason of a rejection
    too_long = {"status": "rejected", "reason": "я" * 201}
    assert client.post(f"/api/admin/schools/{school_id}/status", json=too_long, headers=admin).status_code == 422


# ---------------------------------------------------------------------------
# Deleting a school
# ---------------------------------------------------------------------------


def seed_school_data(client):
    """Challenge, submission with a photo file, xp event, request, exclusion."""
    conn = db(client)
    settings = app.state.settings
    class_id = conn.execute("SELECT id FROM classes WHERE name = '8А'").fetchone()["id"]
    other_class = conn.execute("SELECT id FROM classes WHERE name = '8Б'").fetchone()["id"]
    pupil = user_row(client, PUPIL)["id"]
    pupil2 = user_row(client, PUPIL2)["id"]
    teacher = user_row(client, TEACHER)["id"]
    conn.execute(
        "INSERT INTO challenges (class_id, title, category, xp, deadline, proof_type) "
        "VALUES (?, 'Фото', 'study', 50, '2999-01-01', 'photo')",
        (class_id,),
    )
    challenge = conn.execute("SELECT id FROM challenges").fetchone()["id"]
    cursor = conn.execute(
        "INSERT INTO completions (user_id, challenge_id, status) VALUES (?, ?, 'approved')",
        (pupil, challenge),
    )
    completion = int(cursor.lastrowid)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    photo = settings.upload_dir / "photo-1.jpg"
    photo.write_bytes(b"\xff\xd8\xff data")
    cursor = conn.execute(
        "INSERT INTO uploads (user_id, path, content_type, size, completion_id) "
        "VALUES (?, 'photo-1.jpg', 'image/jpeg', 10, ?)",
        (pupil, completion),
    )
    conn.execute("UPDATE completions SET upload_id = ? WHERE id = ?", (cursor.lastrowid, completion))
    # photo of another, unrelated user stays
    stray = settings.upload_dir / "stray.jpg"
    stray.write_bytes(b"\xff\xd8\xff stray")
    conn.execute(
        "INSERT INTO uploads (user_id, path, content_type, size) VALUES (?, 'stray.jpg', 'image/jpeg', 5)",
        (pupil,),
    )
    conn.execute(
        "INSERT INTO xp_events (user_id, amount, reason, class_id, source) "
        "VALUES (?, 50, 'Фото', ?, 'challenge')",
        (pupil, class_id),
    )
    conn.execute("UPDATE users SET xp = 50, sparks = 77, owned = '[\"hat\"]' WHERE id = ?", (pupil,))
    conn.execute(
        "INSERT INTO class_exclusions (user_id, class_id, removed_by) VALUES (?, ?, ?)",
        (pupil2, class_id, teacher),
    )
    conn.execute("INSERT INTO join_requests (user_id, class_id) VALUES (?, ?)", (pupil2, other_class))
    conn.execute("INSERT INTO class_staff (max_user_id, class_id) VALUES ('777', ?)", (class_id,))
    conn.commit()
    conn.close()
    return photo, stray


def test_delete_school_cascades_and_keeps_users(client):
    school_id, _ = build_school(client)
    # a second school must not be touched
    assert create_school(client, 101, name="Лицей Звезда", city="Казань").status_code == 200
    photo, stray = seed_school_data(client)
    admin = hdr(ADMIN_ID)
    url = f"/api/admin/schools/{school_id}/delete"

    # the exact name is required
    bad = client.post(url, json={"confirm_name": "Другая"}, headers=admin)
    assert bad.status_code == 400 and photo.exists()
    assert client.get("/api/admin/schools", headers=admin).json()["total"] == 2

    r = client.post(url, json={"confirm_name": "  Гимназия   №5 "}, headers=admin)
    assert r.status_code == 200, r.text
    body = r.json()
    deleted = body["deleted"]
    assert deleted["classes"] == 2 and deleted["challenges"] == 1 and deleted["completions"] == 1
    assert deleted["uploads"] == 1 and deleted["files_removed"] == 1
    assert deleted["students"] == 2 and deleted["teachers"] == 1 and deleted["directors"] == 1
    assert deleted["xp_events"] == 1 and deleted["join_requests"] == 1 and deleted["exclusions"] == 1
    assert body["state"]["platform_admin"] is not None

    assert not photo.exists()
    assert stray.exists()  # not attached to this school's work

    conn = db(client)
    try:
        for table in ("challenges", "completions", "xp_events", "join_requests", "class_exclusions", "class_staff"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
        assert conn.execute("SELECT COUNT(*) FROM classes").fetchone()[0] == 2  # the other school (two classes)
        assert conn.execute("SELECT COUNT(*) FROM schools").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM school_staff").fetchone()[0] == 1
        assert conn.execute("SELECT path FROM uploads").fetchall()[0]["path"] == "stray.jpg"
        assert conn.execute("SELECT COUNT(*) FROM uploads").fetchone()[0] == 1

        pupil = user_row(client, PUPIL)
        assert pupil["class_id"] is None and pupil["role"] == "student"
        assert (pupil["xp"], pupil["sparks"], pupil["owned"]) == (50, 77, '["hat"]')
        assert user_row(client, PUPIL2)["class_id"] is None
        teacher = user_row(client, TEACHER)
        assert teacher["class_id"] is None and teacher["role"] == "teacher"
        assert teacher["staff_detached"] == 1
        director = user_row(client, DIRECTOR)
        assert director["role"] == "director" and director["school_id"] is None
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()

    s = state(client, DIRECTOR)
    assert s["school_admin"] is None and s["director"] is None
    assert s["viewer"]["role"] == "director" and s["viewer"]["school_id"] is None
    # the pupil is alive and can join another class
    pupil_state = state(client, PUPIL)
    assert pupil_state["viewer"]["class_id"] is None and pupil_state["viewer"]["xp"] == 50
    # the director can register a new school right away
    assert create_school(client, DIRECTOR, name="Новая школа", city="Москва").status_code == 200
    assert client.post(url, json={"confirm_name": "Гимназия №5"}, headers=admin).status_code == 404


def test_delete_school_without_classes(client):
    assert create_school(client, DIRECTOR, classes=("1А",)).status_code == 200
    conn = db(client)
    conn.execute("DELETE FROM classes")
    conn.commit()
    conn.close()
    sid = client.get("/api/admin/schools", headers=hdr(ADMIN_ID)).json()["items"][0]["id"]
    r = client.post(f"/api/admin/schools/{sid}/delete", json={"confirm_name": "Гимназия №5"}, headers=hdr(ADMIN_ID))
    assert r.status_code == 200 and r.json()["deleted"]["classes"] == 0


# ---------------------------------------------------------------------------
# Users and blocking
# ---------------------------------------------------------------------------


def test_user_search_and_fields(client):
    build_school(client)
    admin = hdr(ADMIN_ID)
    everyone = client.get("/api/admin/users", headers=admin).json()
    assert everyone["total"] >= 4 and everyone["limit"] == 50
    by_id = client.get(f"/api/admin/users?q={PUPIL}", headers=admin).json()
    assert [u["external_id"] for u in by_id["items"]] == [str(PUPIL)]
    u = by_id["items"][0]
    assert u["role"] == "student" and u["school"] == "Гимназия №5" and u["class_name"] == "8А"
    assert u["created_at"] and u["blocked"] is False and u["is_admin"] is False
    by_name = client.get("/api/admin/users?q=ТЕСТОВ", headers=admin).json()
    assert by_name["total"] >= 4
    assert client.get("/api/admin/users?q=нет-такого", headers=admin).json()["items"] == []
    conn = db(client)
    conn.execute("INSERT INTO activity_days (user_id, day) VALUES (?, '2026-05-04')", (user_row(client, PUPIL)["id"],))
    conn.commit()
    conn.close()
    assert client.get(f"/api/admin/users?q={PUPIL}", headers=admin).json()["items"][0]["last_active"] == "2026-05-04"
    director = client.get(f"/api/admin/users?q={DIRECTOR}", headers=admin).json()["items"][0]
    assert director["role"] == "director" and director["school"] == "Гимназия №5"


def test_block_and_unblock(client):
    build_school(client)
    admin = hdr(ADMIN_ID)
    pupil_id = user_row(client, PUPIL)["id"]

    # reason is required
    assert client.post(f"/api/admin/users/{pupil_id}/block", json={}, headers=admin).status_code == 400
    r = client.post(f"/api/admin/users/{pupil_id}/block", json={"reason": "Спам заявками"}, headers=admin)
    assert r.status_code == 200
    assert r.json()["user"]["blocked"] is True and r.json()["user"]["blocked_reason"] == "Спам заявками"

    blocked = client.get("/api/state", headers=hdr(PUPIL))
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "Доступ к приложению ограничен"
    assert blocked.headers["X-Access-Blocked"] == "1"
    assert client.post("/api/profile/name", json={"first_name": "Аа"}, headers=hdr(PUPIL)).status_code == 403
    assert client.get("/api/school/catalog", headers=hdr(PUPIL)).status_code == 403
    health = client.get("/api/health")
    assert health.status_code == 200 and health.json()["status"] == "ok"
    # others are fine
    assert client.get("/api/state", headers=hdr(PUPIL2)).status_code == 200

    only = client.get("/api/admin/users?blocked=true", headers=admin).json()
    assert [u["id"] for u in only["items"]] == [pupil_id]
    assert client.get("/api/admin/schools", headers=admin).json()["summary"]["blocked_users"] == 1

    r = client.post(f"/api/admin/users/{pupil_id}/unblock", headers=admin)
    assert r.status_code == 200 and r.json()["user"]["blocked"] is False
    assert client.get("/api/state", headers=hdr(PUPIL)).status_code == 200
    assert client.post("/api/admin/users/99999/block", json={"reason": "спам"}, headers=admin).status_code == 404


def test_cannot_block_admin_or_self(client):
    build_school(client)
    admin = hdr(ADMIN_ID)
    state(client, ADMIN_ID)
    admin_id = user_row(client, ADMIN_ID)["id"]
    r = client.post(f"/api/admin/users/{admin_id}/block", json={"reason": "тест"}, headers=admin)
    assert r.status_code == 400
    assert client.get("/api/state", headers=admin).status_code == 200

    # a second admin (listed in env) is protected as well, and a flag set
    # directly in the database does not lock an admin out
    conn = db(client)
    conn.execute("UPDATE users SET blocked_at = datetime('now') WHERE id = ?", (admin_id,))
    conn.commit()
    conn.close()
    assert client.get("/api/state", headers=admin).status_code == 200

    # self: a user who is admin only through the sandbox flag could unset it
    # and block themselves; the rule is checked before the admin rule.
    me = client.get("/api/admin/users?q=" + str(ADMIN_ID), headers=admin).json()["items"][0]
    assert me["is_self"] is True and me["is_admin"] is True


def test_blocked_user_keeps_their_data(tmp_path):
    # a blocked user keeps their data
    c = make_client(tmp_path)
    try:
        build_school(c)
        admin = hdr(ADMIN_ID)
        pid = user_row(c, PUPIL)["id"]
        c.post(f"/api/admin/users/{pid}/block", json={"reason": "тест"}, headers=admin)
        row = user_row(c, PUPIL)
        assert row["class_id"] is not None and row["blocked_at"] is not None
    finally:
        c.close()


# ---------------------------------------------------------------------------
# Sandbox
# ---------------------------------------------------------------------------


def sandbox_client(tmp_path) -> TestClient:
    settings = make_settings(tmp_path, app_mode="sandbox", default_class_id=None)
    init_db(settings.db_path)
    app.state.settings = settings
    return TestClient(app)


def sh(cid):
    return {"X-Client-Id": cid}


def test_sandbox_admin_flag_gives_access_and_blocking_works(tmp_path):
    c = sandbox_client(tmp_path)
    try:
        school = {
            "name": "Школа песочницы",
            "city": "Москва",
            "classes": [{"name": "5А", "weekly_goal": 1600}],
        }
        assert c.post("/api/school/create", json=school, headers=sh("sandbox-director")).status_code == 200
        assert c.get("/api/admin/schools", headers=sh("sandbox-user")).status_code == 404
        assert c.get("/api/state", headers=sh("sandbox-user")).status_code == 200
        # the admin checkbox of the sandbox panel
        assert c.post("/api/sandbox/admin", json={"enabled": True}, headers=sh("sandbox-user")).status_code == 200
        listing = c.get("/api/admin/schools", headers=sh("sandbox-user"))
        assert listing.status_code == 200 and listing.json()["total"] == 1
        users = c.get("/api/admin/users?q=sandbox-director", headers=sh("sandbox-user")).json()["items"]
        assert users[0]["external_id"] == "sandbox-director"

        r = c.post(f"/api/admin/users/{users[0]['id']}/block", json={"reason": "тест песочницы"}, headers=sh("sandbox-user"))
        assert r.status_code == 200
        assert c.get("/api/state", headers=sh("sandbox-director")).status_code == 403
        assert c.get("/api/health").status_code == 200

        # admin cannot block themselves; turning the flag off removes access
        me = c.get("/api/admin/users?q=sandbox-user", headers=sh("sandbox-user")).json()["items"][0]
        assert c.post(f"/api/admin/users/{me['id']}/block", json={"reason": "сам себя"}, headers=sh("sandbox-user")).status_code == 400
        c.post("/api/sandbox/admin", json={"enabled": False}, headers=sh("sandbox-user"))
        assert c.get("/api/admin/users", headers=sh("sandbox-user")).status_code == 404

        # delete the school as sandbox admin
        c.post("/api/sandbox/admin", json={"enabled": True}, headers=sh("sandbox-user"))
        sid = c.get("/api/admin/schools", headers=sh("sandbox-user")).json()["items"][0]["id"]
        r = c.post(f"/api/admin/schools/{sid}/delete", json={"confirm_name": "Школа песочницы"}, headers=sh("sandbox-user"))
        assert r.status_code == 200 and r.json()["deleted"]["classes"] == 1
    finally:
        c.close()


def test_demo_mode_has_no_admin(demo_client):
    r = demo_client.get("/api/admin/schools", headers={"X-Client-Id": "demo-test-client"})
    assert r.status_code == 404


def test_migration_adds_columns_to_old_database(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    raw = sqlite3.connect(path)
    raw.executescript(
        """
        CREATE TABLE schools (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            city TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active', UNIQUE(name, city));
        """
    )
    raw.commit()
    raw.close()
    init_db(path)
    conn = connect(path)
    try:
        assert "reject_reason" in {r["name"] for r in conn.execute("PRAGMA table_info(schools)")}
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
        assert {"blocked_at", "blocked_reason"} <= cols
    finally:
        conn.close()
