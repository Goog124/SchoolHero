"""A director who also leads a class: teacher mode, switcher, school block."""

from __future__ import annotations

import sqlite3

import pytest

from backend.db import connect, init_db
from test_registration import (
    admin_view,
    class_codes,
    create_school,
    hdr,
    make_client,
    onboard_student,
    school_body,
)


@pytest.fixture
def client(tmp_path):
    c = make_client(tmp_path)
    yield c
    c.close()


def state(client, uid):
    return client.get("/api/state", headers=hdr(uid)).json()


def create_teaching(client, uid=100, teach="8А", **kwargs):
    body = school_body(**kwargs)
    body["teach_class"] = teach
    r = client.post("/api/school/create", json=body, headers=hdr(uid))
    assert r.status_code == 200, r.text
    return r.json()["state"]


def set_view(client, uid, view):
    return client.post("/api/profile/view", json={"view": view}, headers=hdr(uid))


TASK = {"title": "Задание классного", "description": "", "category": "help", "xp": 20, "kind": "daily"}


def test_create_school_binds_director_as_class_teacher(client):
    st = create_teaching(client)
    viewer = st["viewer"]
    assert viewer["role"] == "director"
    assert viewer["can_teach"] is True
    assert viewer["active_view"] == "director"
    cls = class_codes(client, 100)["8А"]
    assert viewer["class_id"] == cls["id"]
    assert [t["is_director"] for t in cls["teachers"]] == [True]
    assert cls["teachers"][0]["is_self"] is True
    assert class_codes(client, 100)["8Б"]["teachers"] == []
    assert st["school_admin"]["teaching_class_id"] == cls["id"]


def test_create_school_without_teach_class(client):
    assert create_school(client, 100).status_code == 200
    viewer = state(client, 100)["viewer"]
    assert viewer["can_teach"] is False and viewer["class_id"] is None
    assert viewer["active_view"] == "director"


def test_teach_class_must_be_in_new_classes(client):
    body = school_body()
    body["teach_class"] = "9Я"
    assert client.post("/api/school/create", json=body, headers=hdr(100)).status_code == 400


def test_switch_view_changes_state(client):
    create_teaching(client)
    st = state(client, 100)
    assert st["director"] is not None and st["teacher"] is None

    r = set_view(client, 100, "teacher")
    assert r.status_code == 200, r.text
    st = r.json()["state"]
    assert st["viewer"]["active_view"] == "teacher"
    assert st["viewer"]["role"] == "director"
    assert st["teacher"] is not None and st["director"] is None
    assert st["school_admin"] is not None

    st = set_view(client, 100, "director").json()["state"]
    assert st["director"] is not None and st["teacher"] is None
    assert state(client, 100)["viewer"]["active_view"] == "director"


def test_switch_unavailable_without_class(client):
    create_school(client, 100)
    assert set_view(client, 100, "teacher").status_code == 400
    onboard_student(client, 1)
    assert set_view(client, 1, "teacher").status_code == 400


def test_director_teacher_reviews_and_creates_challenge(client):
    create_teaching(client)
    cls = class_codes(client, 100)["8А"]
    onboard_student(client, 1, cls["invite_code"])
    set_view(client, 100, "teacher")

    r = client.post("/api/challenges", json=TASK, headers=hdr(100))
    assert r.status_code == 200, r.text
    ch = state(client, 1)["challenges"][0]
    assert client.post(
        f"/api/challenges/{ch['id']}/submit", json={"proof": "готово"}, headers=hdr(1)
    ).status_code == 200

    st = state(client, 100)
    assert len(st["teacher"]["pending"]) == 1
    rid = st["teacher"]["pending"][0]["id"]
    assert client.post(f"/api/reviews/{rid}", json={"action": "approve"}, headers=hdr(100)).status_code == 200
    assert state(client, 100)["teacher"]["pending"] == []


def test_other_view_pending_badge(client):
    create_teaching(client)
    cls = class_codes(client, 100)["8А"]
    onboard_student(client, 1, cls["invite_code"])
    client.post("/api/challenges", json=TASK, headers=hdr(100))
    ch = state(client, 1)["challenges"][0]
    client.post(f"/api/challenges/{ch['id']}/submit", json={"proof": "готово"}, headers=hdr(1))
    # director view: the teacher side has a work waiting
    assert state(client, 100)["viewer"]["other_view_pending"] == 1
    set_view(client, 100, "teacher")
    assert state(client, 100)["viewer"]["other_view_pending"] == 0
    # a join request to another class waits on the director side
    other = class_codes(client, 100)["8Б"]
    onboard_student(client, 2)
    r = client.post("/api/school/join", json={"class_id": other["id"]}, headers=hdr(2))
    assert r.status_code == 200, r.text
    assert state(client, 100)["viewer"]["other_view_pending"] == 1


def test_teach_endpoint_and_foreign_school(client):
    create_school(client, 100, name="Школа Альфа", classes=("5А", "5Б"))
    create_school(client, 101, name="Школа Бета", city="Москва", classes=("6А",))
    a = admin_view(client, 100)["schools"][0]
    b = admin_view(client, 101)["schools"][0]
    a_class = a["classes"][0]
    b_class = b["classes"][0]
    url = f"/api/school/{a['id']}/teach"

    assert client.post(url, json={"class_id": b_class["id"]}, headers=hdr(100)).status_code == 404
    assert client.post(url, json={"class_id": a_class["id"]}, headers=hdr(101)).status_code == 404
    onboard_student(client, 1)
    assert client.post(url, json={"class_id": a_class["id"]}, headers=hdr(1)).status_code == 404

    r = client.post(url, json={"class_id": a_class["id"]}, headers=hdr(100))
    assert r.status_code == 200, r.text
    assert r.json()["state"]["viewer"]["class_id"] == a_class["id"]
    assert r.json()["state"]["viewer"]["can_teach"] is True


def test_stop_teaching_resets_view(client):
    create_teaching(client)
    school = admin_view(client, 100)["schools"][0]
    set_view(client, 100, "teacher")
    r = client.post(f"/api/school/{school['id']}/teach", json={"class_id": None}, headers=hdr(100))
    assert r.status_code == 200, r.text
    st = r.json()["state"]
    assert st["viewer"]["can_teach"] is False
    assert st["viewer"]["active_view"] == "director"
    assert st["viewer"]["class_id"] is None
    assert st["director"] is not None
    assert all(c["teachers"] == [] for c in class_codes(client, 100).values())


def test_deleting_class_returns_director_mode(client):
    create_teaching(client)
    cls = class_codes(client, 100)["8А"]
    set_view(client, 100, "teacher")
    assert client.delete(f"/api/school/classes/{cls['id']}", headers=hdr(100)).status_code == 200
    viewer = state(client, 100)["viewer"]
    assert viewer["can_teach"] is False and viewer["active_view"] == "director"


def test_cannot_disconnect_director_teacher(client):
    create_teaching(client)
    cls = class_codes(client, 100)["8А"]
    uid = cls["teachers"][0]["id"]
    r = client.post(f"/api/school/classes/{cls['id']}/teachers/{uid}/disconnect", headers=hdr(100))
    assert r.status_code == 404
    assert state(client, 100)["viewer"]["can_teach"] is True


def test_migration_adds_active_view(tmp_path):
    path = tmp_path / "old.db"
    init_db(path)
    raw = sqlite3.connect(path)
    raw.execute("ALTER TABLE users DROP COLUMN active_view")
    raw.commit()
    raw.close()
    init_db(path)
    conn = connect(path)
    assert "active_view" in {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    conn.close()
