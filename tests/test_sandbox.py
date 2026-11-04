"""APP_MODE=sandbox: empty database, one user per client id, real roles."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app as app_module
from app import app
from backend.config import Settings
from backend.db import connect, init_db
from conftest import make_settings


def h(client_id: str) -> dict:
    return {"X-Client-Id": client_id}


def make_client(tmp_path, **overrides) -> TestClient:
    settings = make_settings(tmp_path, app_mode="sandbox", default_class_id=None, **overrides)
    init_db(settings.db_path)
    app.state.settings = settings
    return TestClient(app)


@pytest.fixture
def client(tmp_path):
    c = make_client(tmp_path)
    yield c
    c.close()


def state(client, cid):
    r = client.get("/api/state", headers=h(cid))
    assert r.status_code == 200, r.text
    return r.json()


def test_each_client_id_is_a_separate_user(client):
    a, b = state(client, "sandbox-user-a"), state(client, "sandbox-user-b")
    assert client.get("/api/health").json()["mode"] == "sandbox"
    assert a["mode"] == "sandbox" and a["verified"] is False
    assert a["viewer"]["id"] != b["viewer"]["id"]
    assert state(client, "sandbox-user-a")["viewer"]["id"] == a["viewer"]["id"]


def test_new_user_starts_empty_like_prod(client):
    s = state(client, "sandbox-user-a")
    assert s["viewer"]["role"] == "student"
    assert s["viewer"]["class_id"] is None
    assert s["viewer"]["onboarded"] is False
    assert s["challenges"] == [] and s["leaderboard"]["classes"] == []
    catalog = client.get("/api/school/catalog", headers=h("sandbox-user-a")).json()
    assert (catalog["cities"], catalog["schools"], catalog["classes"]) == ([], [], [])


def test_invalid_or_missing_client_id_is_rejected(client):
    assert client.get("/api/state").status_code == 401
    assert client.get("/api/state", headers=h("short")).status_code == 401


def test_demo_endpoints_are_forbidden(client):
    assert client.post("/api/demo/role", json={"role": "teacher"}, headers=h("sandbox-user-a")).status_code == 403
    assert client.post("/api/demo/reset", headers=h("sandbox-user-a")).status_code == 403


def test_full_registration_path(client):
    director = "sandbox-director"
    r = client.post(
        "/api/school/create",
        json={"name": "Лицей Песочница", "city": "Новгород",
              "classes": [{"name": "7А", "weekly_goal": 1600}]},
        headers=h(director),
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"]["viewer"]["role"] == "director"
    cls = state(client, director)["school_admin"]["schools"][0]["classes"][0]

    pupil = "sandbox-pupil-1"
    r = client.post(
        "/api/onboarding",
        json={"first_name": "Ученик", "last_name": "Первый", "avatar": {}, "invite_code": cls["invite_code"]},
        headers=h(pupil),
    )
    assert r.status_code == 200, r.text
    viewer = r.json()["state"]["viewer"]
    assert viewer["role"] == "student" and viewer["class_name"] == "7А"

    teacher = "sandbox-teacher"
    r = client.post("/api/school/join", json={"invite_code": cls["teacher_code"]}, headers=h(teacher))
    assert r.status_code == 200, r.text
    t = r.json()["state"]
    assert t["viewer"]["role"] == "teacher" and t["viewer"]["class_name"] == "7А"
    assert t["teacher"] is not None

    d = state(client, director)
    assert d["director"]["kpi"]["total_students"] == 1
    assert d["school_admin"]["schools"][0]["classes"][0]["teachers"]
    # a role never leaks between users
    assert state(client, pupil)["viewer"]["role"] == "student"


def test_platform_admin_by_client_id(tmp_path):
    c = make_client(
        tmp_path,
        school_approval="manual",
        platform_admin_client_ids={"sandbox-admin"},
    )
    try:
        r = c.post(
            "/api/school/create",
            json={"name": "Школа на проверке", "city": "Москва",
                  "classes": [{"name": "5А", "weekly_goal": 1600}]},
            headers=h("sandbox-director"),
        )
        assert r.status_code == 200
        assert c.get("/api/school/catalog", headers=h("sandbox-pupil-1")).json()["schools"] == []
        assert state(c, "sandbox-director")["platform_admin"] is None
        pending = state(c, "sandbox-admin")["platform_admin"]["pending"]
        assert len(pending) == 1
        ok = c.post(f"/api/admin/schools/{pending[0]['id']}/status", json={"status": "active"}, headers=h("sandbox-admin"))
        assert ok.status_code == 200
        assert len(c.get("/api/school/catalog", headers=h("sandbox-pupil-1")).json()["schools"]) == 1
    finally:
        c.close()


def test_sandbox_refuses_non_loopback_host():
    for host in ("0.0.0.0", "192.168.1.5", "example.com"):
        with pytest.raises(RuntimeError):
            Settings(app_mode="sandbox", host=host).validate()
    for host in ("127.0.0.1", "localhost", "::1"):
        Settings(app_mode="sandbox", host=host).validate()  # no token needed


def test_from_env_sandbox_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_MODE", "sandbox")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DEFAULT_CLASS_ID", "1")
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    monkeypatch.delenv("HOST", raising=False)
    s = Settings.from_env()
    assert s.sandbox_mode and not s.demo_mode
    assert s.db_path.name == "school_hero_sandbox.db"
    assert s.default_class_id is None
    assert s.sandbox_keep_data is False
    s.validate()


def test_database_is_wiped_on_start_unless_kept(tmp_path, monkeypatch):
    settings = make_settings(tmp_path, app_mode="sandbox", default_class_id=None)
    monkeypatch.setattr(app_module, "settings", settings)
    app.state.settings = settings

    def run_once() -> int:
        with TestClient(app) as c:
            assert c.get("/api/school/catalog", headers=h("sandbox-wipe-1")).json()["schools"] == []
            c.post(
                "/api/school/create",
                json={"name": "Школа для очистки", "city": "Тула",
                      "classes": [{"name": "5А", "weekly_goal": 1600}]},
                headers=h("sandbox-wipe-1"),
            )
        conn = connect(settings.db_path)
        try:
            return conn.execute("SELECT COUNT(*) FROM schools").fetchone()[0]
        finally:
            conn.close()

    assert run_once() == 1
    # second start: file is deleted, then one school is created again
    assert run_once() == 1
    kept = make_settings(tmp_path, app_mode="sandbox", default_class_id=None, sandbox_keep_data=True)
    monkeypatch.setattr(app_module, "settings", kept)
    app.state.settings = kept
    with TestClient(app) as c:
        assert c.get("/api/school/catalog", headers=h("sandbox-wipe-1")).json()["schools"]


def test_health_boot_id_changes_when_database_is_wiped(tmp_path, monkeypatch):
    settings = make_settings(tmp_path, app_mode="sandbox", default_class_id=None)
    monkeypatch.setattr(app_module, "settings", settings)
    app.state.settings = settings

    def boot() -> str:
        with TestClient(app) as c:
            data = c.get("/api/health").json()
        assert data["mode"] == "sandbox"
        return data["boot_id"]

    first, second = boot(), boot()
    assert first and second and first != second


def test_health_boot_id_is_stable_with_keep_data(tmp_path, monkeypatch):
    settings = make_settings(
        tmp_path, app_mode="sandbox", default_class_id=None, sandbox_keep_data=True
    )
    monkeypatch.setattr(app_module, "settings", settings)
    app.state.settings = settings

    def boot() -> str:
        with TestClient(app) as c:
            return c.get("/api/health").json()["boot_id"]

    first = boot()
    assert boot() == first
    # a deleted database means the remembered users are gone: new id
    for suffix in ("", "-wal", "-shm"):
        (tmp_path / f"test.db{suffix}").unlink(missing_ok=True)
    assert boot() != first


def test_health_has_no_boot_id_outside_sandbox(tmp_path):
    settings = make_settings(tmp_path, app_mode="prod", bot_token="t")
    app.state.settings = settings
    c = TestClient(app)  # no lifespan: module settings are not touched
    assert "boot_id" not in c.get("/api/health").json()
    c.close()
