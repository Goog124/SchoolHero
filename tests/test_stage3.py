"""Stage 3 audit fixes: one list of subjects, deadline labels, demo reset."""

from __future__ import annotations

from datetime import timedelta

from backend.db import connect
from backend.game import SUBJECTS, today_local
from backend.service import term_label
from conftest import DEMO_HEADERS, get_state


def switch_role(client, role: str) -> dict:
    response = client.post("/api/demo/role", json={"role": role}, headers=DEMO_HEADERS)
    assert response.status_code == 200, response.text
    return response.json()["state"]


def create(client, **extra):
    payload = {
        "title": "Проверочное задание",
        "description": "",
        "category": "homework",
        "xp": 30,
        "kind": "weekly",
        "deadline": (today_local() + timedelta(days=3)).isoformat(),
    }
    payload.update(extra)
    return client.post("/api/challenges", json=payload, headers=DEMO_HEADERS)


def find(state: dict, title: str) -> dict:
    return next(c for c in state["teacher"]["challenges"] if c["title"] == title)


# --- subjects ---------------------------------------------------------------


def test_state_sends_subjects_to_staff_only(demo_client):
    assert get_state(demo_client)["subjects"] == []
    teacher = switch_role(demo_client, "teacher")
    assert teacher["subjects"] == SUBJECTS
    director = switch_role(demo_client, "director")
    assert director["subjects"] == SUBJECTS


def test_listed_subject_is_accepted_and_normalized(demo_client):
    switch_role(demo_client, "teacher")
    response = create(demo_client, title="Задание по физике", subject="  физика ")
    assert response.status_code == 200, response.text
    assert find(response.json()["state"], "Задание по физике")["subject"] == "Физика"


def test_unknown_subject_is_rejected(demo_client):
    switch_role(demo_client, "teacher")
    response = create(demo_client, subject="Астрология")
    assert response.status_code == 400
    assert "предмет" in response.json()["detail"].lower()


def test_other_subject_uses_own_text(demo_client):
    switch_role(demo_client, "teacher")
    ok = create(demo_client, title="Робототехника", subject="Другое", subject_other="Робототехника")
    assert ok.status_code == 200, ok.text
    assert find(ok.json()["state"], "Робототехника")["subject"] == "Робототехника"

    # Own text equal to a listed subject is stored as the listed one.
    same = create(demo_client, title="Своя химия", subject="Другое", subject_other="химия")
    assert find(same.json()["state"], "Своя химия")["subject"] == "Химия"

    empty = create(demo_client, title="Без названия", subject="Другое", subject_other=" ")
    assert empty.status_code == 400


def test_no_subject_defaults_to_general(demo_client):
    switch_role(demo_client, "teacher")
    response = create(demo_client, title="Общее задание", subject="")
    assert response.status_code == 200, response.text
    assert find(response.json()["state"], "Общее задание")["subject"] == "Общее"


# --- deadline labels ----------------------------------------------------------


def test_term_label_follows_deadline():
    today = today_local()
    assert term_label(f"{today.isoformat()}T23:59:00+03:00") == "На сегодня"
    far = today + timedelta(days=20)
    assert term_label(f"{far.isoformat()}T23:59:00+03:00").startswith("До ")
    assert term_label(f"{far.isoformat()}T23:59:00+03:00") != "До конца недели"
    past = today - timedelta(days=1)
    assert term_label(f"{past.isoformat()}T23:59:00+03:00") == "Срок прошёл"
    sunday = today + timedelta(days=6 - today.weekday())
    if sunday != today:
        assert term_label(f"{sunday.isoformat()}T23:59:00+03:00") == "До конца недели"
    assert term_label("") == ""


def test_daily_kind_with_far_deadline_is_not_labelled_today(demo_client):
    switch_role(demo_client, "teacher")
    far = (today_local() + timedelta(days=10)).isoformat()
    response = create(demo_client, title="Долгое задание", kind="daily", deadline=far)
    assert response.status_code == 200, response.text
    assert find(response.json()["state"], "Долгое задание")["kind_label"] != "На сегодня"


def test_kind_without_date_gets_matching_deadline(demo_client):
    switch_role(demo_client, "teacher")
    response = create(demo_client, title="Сегодняшнее", kind="daily", deadline="")
    assert response.status_code == 200, response.text
    item = find(response.json()["state"], "Сегодняшнее")
    assert item["deadline"].startswith(today_local().isoformat())
    assert item["kind_label"] == "На сегодня"


# --- demo reset -----------------------------------------------------------------


def test_reset_demo_without_class_returns_to_default_class(demo_client, demo_settings):
    viewer_id = get_state(demo_client)["viewer"]["id"]
    conn = connect(demo_settings.db_path)
    try:
        conn.execute("UPDATE users SET class_id = NULL WHERE id = ?", (viewer_id,))
        conn.commit()
    finally:
        conn.close()
    assert get_state(demo_client)["viewer"]["class_id"] is None

    reset = demo_client.post("/api/demo/reset", headers=DEMO_HEADERS)
    assert reset.status_code == 200, reset.text
    viewer = reset.json()["state"]["viewer"]
    assert viewer["class_id"] == demo_settings.default_class_id
    assert viewer["onboarded"] is True
    assert viewer["role"] == "student"


def test_reset_demo_returns_from_another_class(demo_client, demo_settings):
    conn = connect(demo_settings.db_path)
    try:
        other = conn.execute(
            "SELECT id FROM classes WHERE id != ? ORDER BY id LIMIT 1",
            (demo_settings.default_class_id,),
        ).fetchone()
        viewer_id = get_state(demo_client)["viewer"]["id"]
        if other is not None:
            conn.execute("UPDATE users SET class_id = ? WHERE id = ?", (other["id"], viewer_id))
            conn.commit()
    finally:
        conn.close()

    reset = demo_client.post("/api/demo/reset", headers=DEMO_HEADERS)
    assert reset.status_code == 200, reset.text
    assert reset.json()["state"]["viewer"]["class_id"] == demo_settings.default_class_id


def test_demo_role_switch_and_reset_cycle(demo_client):
    teacher = switch_role(demo_client, "teacher")
    assert teacher["teacher"] is not None
    director = switch_role(demo_client, "director")
    assert director["director"] is not None
    reset = demo_client.post("/api/demo/reset", headers=DEMO_HEADERS)
    assert reset.status_code == 200, reset.text
    state = reset.json()["state"]
    assert state["viewer"]["role"] == "student"
    assert state["teacher"] is None
    assert state["director"] is None
