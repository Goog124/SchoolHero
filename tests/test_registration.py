"""School registration: schools created by directors, codes, isolation."""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import app
from backend.db import connect, init_db
from conftest import MAX_TOKEN, make_settings
from test_security import sign_init_data

CODE_CHARS = set("ABCDEFGHJKMNPQRSTUVWXYZ23456789-")
ADMIN_ID = 5000


def hdr(user_id: int, name: str = "Пользователь") -> dict:
    return {
        "X-Max-Init-Data": sign_init_data(
            {"id": user_id, "first_name": name, "last_name": "Тестов"},
            bot_token=MAX_TOKEN,
        )
    }


def make_client(tmp_path, **overrides) -> TestClient:
    settings = make_settings(
        tmp_path,
        app_mode="prod",
        bot_token=MAX_TOKEN,
        default_class_id=None,
        platform_admin_max_ids={str(ADMIN_ID)},
        **overrides,
    )
    init_db(settings.db_path)  # empty production: no catalog, no demo data
    app.state.settings = settings
    return TestClient(app)


@pytest.fixture
def client(tmp_path):
    c = make_client(tmp_path)
    yield c
    c.close()


def school_body(name="Гимназия №5", city="Новгород", classes=("8А", "8Б")):
    return {
        "name": name,
        "city": city,
        "classes": [{"name": c, "weekly_goal": 1600} for c in classes],
    }


def create_school(client, user_id, **kwargs):
    return client.post("/api/school/create", json=school_body(**kwargs), headers=hdr(user_id))


def admin_view(client, user_id) -> dict:
    return client.get("/api/state", headers=hdr(user_id)).json()["school_admin"]


def class_codes(client, user_id, school_index=0) -> dict:
    return {c["name"]: c for c in admin_view(client, user_id)["schools"][school_index]["classes"]}


def onboard_student(client, user_id, class_code=None):
    body = {"first_name": "Ученик", "last_name": "Тестов", "avatar": {}}
    if class_code:
        body["invite_code"] = class_code
    r = client.post("/api/onboarding", json=body, headers=hdr(user_id))
    assert r.status_code == 200, r.text
    return r.json()["state"]


# ---------------------------------------------------------------------------


def test_empty_production_starts_without_class(client):
    state = client.get("/api/state", headers=hdr(1)).json()
    viewer = state["viewer"]
    assert viewer["class_id"] is None
    assert viewer["role"] == "student"
    assert state["challenges"] == []
    assert state["leaderboard"]["classes"] == []
    catalog = client.get("/api/school/catalog", headers=hdr(1)).json()
    assert catalog == {"cities": [], "schools": [], "classes": []}
    submit = client.post("/api/challenges/1/submit", json={"proof": "x"}, headers=hdr(1))
    assert submit.status_code in {400, 404}


def test_director_creates_school_and_gets_codes(client):
    r = create_school(client, 100)
    assert r.status_code == 200, r.text
    state = r.json()["state"]
    assert state["viewer"]["role"] == "director"
    assert state["viewer"]["class_id"] is None
    assert state["viewer"]["school_name"] == "Гимназия №5"
    assert state["director"]["kpi"]["total_classes"] == 2

    classes = class_codes(client, 100)
    assert set(classes) == {"8А", "8Б"}
    seen = set()
    for item in classes.values():
        assert len(item["invite_code"]) == 7 and len(item["teacher_code"]) == 9
        assert set(item["invite_code"]) <= CODE_CHARS
        assert set(item["teacher_code"]) <= CODE_CHARS
        seen |= {item["invite_code"], item["teacher_code"]}
    assert len(seen) == 4  # all unique

    catalog = client.get("/api/school/catalog", headers=hdr(1)).json()
    assert [s["name"] for s in catalog["schools"]] == ["Гимназия №5"]
    assert len(catalog["classes"]) == 2
    assert "invite_code" not in catalog["classes"][0]


def test_student_joins_by_code_and_is_counted(client):
    create_school(client, 100)
    code = class_codes(client, 100)["8А"]["invite_code"]
    checked = client.get(f"/api/school/check-code?code={code.lower()}", headers=hdr(1)).json()
    assert checked["valid"] is True and checked["kind"] == "student"
    state = onboard_student(client, 1, code)
    assert state["viewer"]["class_name"] == "8А"
    assert state["viewer"]["school_name"] == "Гимназия №5"
    director = client.get("/api/state", headers=hdr(100)).json()["director"]
    assert director["kpi"]["total_students"] == 1


def test_cyrillic_lookalikes_in_code_are_accepted(client):
    create_school(client, 100)
    code = class_codes(client, 100)["8А"]["invite_code"]
    table = str.maketrans("ABEKMHPCTX", "АВЕКМНРСТХ")
    r = client.get(f"/api/school/check-code?code={code.translate(table)}", headers=hdr(1))
    assert r.json()["valid"] is True


def test_validation_duplicates_and_limits(client):
    assert create_school(client, 100).status_code == 200
    # Same name and city, other case and spacing: rejected for anyone.
    dup = create_school(client, 101, name="  гимназия  №5 ", city="НОВГОРОД")
    assert dup.status_code == 400
    # Same name in another city is a different school.
    assert create_school(client, 101, name="Гимназия №5", city="Москва").status_code == 200
    bad = [
        school_body(name="ab"),
        school_body(city="1"),
        school_body(classes=()),
        school_body(classes=("8А", "8а")),
        {**school_body(), "classes": [{"name": "8А", "weekly_goal": 5}]},
    ]
    for body in bad:
        assert client.post("/api/school/create", json=body, headers=hdr(102)).status_code in {400, 422}
    # Per-user cap of 3 schools.
    for i in range(2):
        assert create_school(client, 100, name=f"Школа {i + 1}").status_code == 200
    assert create_school(client, 100, name="Школа 9").status_code == 403


def test_school_creation_rate_limit(tmp_path):
    c = make_client(tmp_path, max_schools_per_user=100)
    try:
        for i in range(5):
            assert create_school(c, 100, name=f"Школа номер {i}").status_code == 200
        assert create_school(c, 100, name="Школа номер 6").status_code == 429
    finally:
        c.close()


def test_director_adds_class_and_resets_codes(client):
    create_school(client, 100)
    school_id = admin_view(client, 100)["schools"][0]["id"]
    r = client.post(f"/api/school/{school_id}/classes", json={"name": "9В", "weekly_goal": 2000}, headers=hdr(100))
    assert r.status_code == 200
    assert "9В" in class_codes(client, 100)
    dup = client.post(f"/api/school/{school_id}/classes", json={"name": "9в"}, headers=hdr(100))
    assert dup.status_code == 400

    cls = class_codes(client, 100)["9В"]
    r = client.post(f"/api/school/classes/{cls['id']}/codes", json={"kind": "teacher"}, headers=hdr(100))
    assert r.status_code == 200
    new = class_codes(client, 100)["9В"]
    assert new["teacher_code"] != cls["teacher_code"]
    assert new["invite_code"] == cls["invite_code"]
    # empty class can be removed, class with a student cannot
    onboard_student(client, 1, class_codes(client, 100)["8А"]["invite_code"])
    assert client.delete(f"/api/school/classes/{cls['id']}", headers=hdr(100)).status_code == 200
    busy = class_codes(client, 100)["8А"]["id"]
    assert client.delete(f"/api/school/classes/{busy}", headers=hdr(100)).status_code == 400


def test_teacher_code_makes_teacher_of_that_class(client):
    create_school(client, 100)
    codes = class_codes(client, 100)["8Б"]
    wrong = client.post("/api/school/join", json={"invite_code": "ZZZ-ZZZ"}, headers=hdr(200))
    assert wrong.status_code == 404
    r = client.post("/api/school/join", json={"invite_code": codes["teacher_code"]}, headers=hdr(200))
    assert r.status_code == 200, r.text
    state = r.json()["state"]
    assert state["viewer"]["role"] == "teacher"
    assert state["viewer"]["class_name"] == "8Б"
    assert state["teacher"] is not None
    # the teacher is listed in the director's panel
    assert class_codes(client, 100)["8Б"]["teachers"]
    # a student code never grants the teacher role
    s = client.post("/api/school/join", json={"invite_code": codes["invite_code"]}, headers=hdr(201))
    assert s.json()["state"]["viewer"]["role"] == "student"
    # a student cannot be moved by a teacher; a director cannot become teacher
    d = client.post("/api/school/join", json={"invite_code": codes["teacher_code"]}, headers=hdr(100))
    assert d.status_code == 400
    # teachers keep their class and role on the next request
    again = client.get("/api/state", headers=hdr(200)).json()
    assert again["viewer"]["role"] == "teacher" and again["viewer"]["class_name"] == "8Б"


def test_failed_code_attempts_are_limited(client):
    for _ in range(20):
        client.get("/api/school/check-code?code=NOPE", headers=hdr(300))
    r = client.get("/api/school/check-code?code=NOPE", headers=hdr(300))
    assert r.status_code == 429


def _challenge_and_submission(client, director_id, class_id, student_id):
    r = client.post(
        "/api/challenges",
        json={"title": "Задание школы", "description": "", "category": "help",
              "xp": 20, "kind": "daily", "class_id": class_id},
        headers=hdr(director_id),
    )
    assert r.status_code == 200, r.text
    challenge = client.get("/api/state", headers=hdr(student_id)).json()["challenges"][0]
    sub = client.post(f"/api/challenges/{challenge['id']}/submit", json={"proof": "готово"}, headers=hdr(student_id))
    assert sub.status_code == 200, sub.text
    return challenge["id"]


def test_directors_cannot_touch_other_schools(client):
    create_school(client, 100, name="Школа Альфа", classes=("5А", "5Б"))
    create_school(client, 101, name="Школа Бета", city="Москва", classes=("6А",))
    a = admin_view(client, 100)["schools"][0]
    b = admin_view(client, 101)["schools"][0]
    a_class = next(c for c in a["classes"] if c["name"] == "5А")
    onboard_student(client, 1, a_class["invite_code"])
    cid = _challenge_and_submission(client, 100, a_class["id"], 1)
    state_a = client.get("/api/state", headers=hdr(100)).json()
    assert state_a["director"]["kpi"]["total_students"] == 1

    # B sees none of A's people or classes
    state_b = client.get("/api/state", headers=hdr(101)).json()
    assert state_b["director"]["kpi"]["total_students"] == 0
    assert [c["name"] for c in state_b["director"]["classes"]] == ["6А"]
    assert state_b["school_admin"]["schools"][0]["id"] == b["id"]
    assert len(state_b["school_admin"]["schools"]) == 1

    pending = state_a["director"]
    assert pending is not None
    completions = client.get("/api/state", headers=hdr(100)).json()
    assert completions["director"]["kpi"]["total_classes"] == 2

    h = hdr(101)
    assert client.post(f"/api/school/{a['id']}/classes", json={"name": "9А"}, headers=h).status_code == 404
    assert client.post(f"/api/school/{a['id']}/select", headers=h).status_code == 404
    assert client.post(f"/api/school/classes/{a_class['id']}/codes", json={"kind": "student"}, headers=h).status_code == 404
    assert client.delete(f"/api/school/classes/{a_class['id']}", headers=h).status_code == 404
    forged = client.post(
        "/api/challenges",
        json={"title": "Чужой класс", "description": "", "category": "help",
              "xp": 20, "kind": "daily", "class_id": a_class["id"]},
        headers=h,
    )
    assert forged.status_code == 403
    student_id = client.get("/api/state", headers=hdr(1)).json()["viewer"]["id"]
    assert client.post("/api/teacher/reward", json={"student_id": student_id, "amount": 50}, headers=h).status_code == 403
    review_ids = client.get("/api/state", headers=hdr(100)).json()
    assert review_ids is not None
    r = client.post("/api/reviews/1", json={"action": "approve"}, headers=h)
    assert r.status_code == 403
    # the owner can do all of it
    assert client.post("/api/reviews/1", json={"action": "approve"}, headers=hdr(100)).status_code == 200
    assert cid


def test_class_student_cannot_manage_schools(client):
    create_school(client, 100)
    school = admin_view(client, 100)["schools"][0]
    assert client.post(f"/api/school/{school['id']}/classes", json={"name": "9А"}, headers=hdr(1)).status_code == 404
    assert client.post("/api/admin/schools/1/status", json={"status": "active"}, headers=hdr(1)).status_code == 403


def test_director_classes_match_class_entry(client):
    create_school(client, 100, classes=("5А", "5Б", "6А"))
    onboard_student(client, 1, class_codes(client, 100)["5А"]["invite_code"])
    director = client.get("/api/state", headers=hdr(100)).json()["director"]
    assert len(director["classes"]) == 3
    for entry in director["classes"]:
        for key in ("xp", "weekly_xp", "members", "goal", "progress", "rank"):
            assert isinstance(entry[key], (int, float)), key
        assert entry["goal"] == 1600
    empty = next(c for c in director["classes"] if c["name"] == "6А")
    assert (empty["members"], empty["xp"], empty["weekly_xp"]) == (0, 0, 0)
    assert sorted(c["rank"] for c in director["classes"]) == [1, 2, 3]


def test_manual_approval_hides_school_until_confirmed(tmp_path):
    c = make_client(tmp_path, school_approval="manual")
    try:
        assert create_school(c, 100).status_code == 200
        state = c.get("/api/state", headers=hdr(100)).json()
        assert state["school_admin"]["schools"][0]["status"] == "pending"
        school_id = state["school_admin"]["schools"][0]["id"]
        code = class_codes(c, 100)["8А"]["invite_code"]

        assert c.get("/api/school/catalog", headers=hdr(1)).json()["schools"] == []
        assert c.get(f"/api/school/check-code?code={code}", headers=hdr(1)).json()["valid"] is False
        class_id = class_codes(c, 100)["8А"]["id"]
        assert c.post("/api/school/join", json={"class_id": class_id}, headers=hdr(1)).status_code == 404
        # not visible in cross-school rankings either
        lb = c.get("/api/state", headers=hdr(1)).json()["leaderboard"]
        assert lb["schools"] == []

        # only a platform admin can moderate
        assert c.post(f"/api/admin/schools/{school_id}/status", json={"status": "active"}, headers=hdr(100)).status_code == 403
        assert c.get("/api/state", headers=hdr(100)).json()["platform_admin"] is None
        admin_state = c.get("/api/state", headers=hdr(ADMIN_ID)).json()
        assert [p["id"] for p in admin_state["platform_admin"]["pending"]] == [school_id]
        r = c.post(f"/api/admin/schools/{school_id}/status", json={"status": "active"}, headers=hdr(ADMIN_ID))
        assert r.status_code == 200
        assert r.json()["state"]["platform_admin"]["pending"] == []

        assert len(c.get("/api/school/catalog", headers=hdr(1)).json()["schools"]) == 1
        assert c.get(f"/api/school/check-code?code={code}", headers=hdr(1)).json()["valid"] is True
    finally:
        c.close()


def test_rejected_school_stays_hidden_and_frees_the_quota(tmp_path):
    c = make_client(tmp_path, school_approval="manual", max_schools_per_user=1)
    try:
        create_school(c, 100)
        sid = admin_view(c, 100)["schools"][0]["id"]
        assert create_school(c, 100, name="Другая школа").status_code == 403
        c.post(f"/api/admin/schools/{sid}/status", json={"status": "rejected"}, headers=hdr(ADMIN_ID))
        assert c.get("/api/school/catalog", headers=hdr(1)).json()["schools"] == []
        assert create_school(c, 100, name="Другая школа").status_code == 200
    finally:
        c.close()


def test_catalog_filters_by_city_and_query(client):
    create_school(client, 100, name="Лицей Альфа", city="Новгород")
    create_school(client, 101, name="Школа Бета", city="Москва")
    h = hdr(1)
    only = client.get("/api/school/catalog?only_cities=true", headers=h).json()
    assert only["cities"] == ["Москва", "Новгород"] and only["schools"] == []
    by_city = client.get("/api/school/catalog?city=Москва", headers=h).json()
    assert [s["name"] for s in by_city["schools"]] == ["Школа Бета"]
    assert all(c["school_id"] == by_city["schools"][0]["id"] for c in by_city["classes"])
    found = client.get("/api/school/catalog?q=ЛИЦЕЙ", headers=h).json()
    assert [s["name"] for s in found["schools"]] == ["Лицей Альфа"]


def test_env_teacher_role_is_not_downgrading_a_registered_director(tmp_path):
    c = make_client(tmp_path, teacher_max_ids={"100"})
    try:
        create_school(c, 100)
        assert c.get("/api/state", headers=hdr(100)).json()["viewer"]["role"] == "director"
    finally:
        c.close()


def test_migration_adds_columns_and_relaxes_school_name(tmp_path):
    db = tmp_path / "legacy.db"
    raw = sqlite3.connect(db)
    raw.executescript(
        """
        CREATE TABLE schools (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, city TEXT NOT NULL);
        CREATE TABLE classes (id INTEGER PRIMARY KEY AUTOINCREMENT, school_id INTEGER NOT NULL REFERENCES schools(id),
            name TEXT NOT NULL, weekly_goal INTEGER NOT NULL DEFAULT 1600, invite_code TEXT, UNIQUE(school_id, name));
        CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, max_user_id TEXT UNIQUE, client_id TEXT UNIQUE,
            first_name TEXT NOT NULL, last_name TEXT NOT NULL DEFAULT '', username TEXT NOT NULL DEFAULT '',
            photo_url TEXT NOT NULL DEFAULT '', role TEXT NOT NULL DEFAULT 'student', preview_role TEXT,
            class_id INTEGER REFERENCES classes(id), xp INTEGER NOT NULL DEFAULT 0, sparks INTEGER NOT NULL DEFAULT 0,
            streak INTEGER NOT NULL DEFAULT 0, last_active_date TEXT, avatar TEXT NOT NULL,
            owned TEXT NOT NULL DEFAULT '[]', onboarded INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT (datetime('now')));
        INSERT INTO schools (name, city) VALUES ('Школа 1', 'Москва');
        INSERT INTO classes (school_id, name, invite_code) VALUES (1, '8А', 'OLD-8A');
        INSERT INTO users (max_user_id, first_name, avatar, class_id) VALUES ('1', 'Иван', '{}', 1);
        """
    )
    raw.commit()
    raw.close()

    init_db(db)
    init_db(db)  # idempotent
    conn = connect(db)
    try:
        school_cols = {r["name"] for r in conn.execute("PRAGMA table_info(schools)")}
        assert {"status", "created_by", "norm_key"} <= school_cols
        assert "teacher_code" in {r["name"] for r in conn.execute("PRAGMA table_info(classes)")}
        assert "school_id" in {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
        assert conn.execute("SELECT status, norm_key FROM schools").fetchone()["status"] == "active"
        conn.execute("INSERT INTO schools (name, city) VALUES ('Школа 1', 'Казань')")  # same name, other city
        assert conn.execute("SELECT invite_code FROM classes WHERE id = 1").fetchone()[0] == "OLD-8A"
        assert conn.execute("SELECT class_id FROM users").fetchone()[0] == 1
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        conn.close()


def test_catalog_file_is_optional(tmp_path):
    from backend.catalog import import_catalog

    init_db(tmp_path / "x.db")
    conn = connect(tmp_path / "x.db")
    try:
        assert import_catalog(conn, tmp_path / "missing.json") is False
        assert conn.execute("SELECT COUNT(*) FROM schools").fetchone()[0] == 0
    finally:
        conn.close()
