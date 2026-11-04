"""End-to-end tests for the HTTP API and game rules."""

from __future__ import annotations

from conftest import (
    DEMO_HEADERS,
    MAX_TOKEN,
    challenge_by_title,
    get_state,
)
from test_security import MAX_USER, sign_init_data


def switch_role(client, role: str) -> dict:
    response = client.post(
        "/api/demo/role", json={"role": role}, headers=DEMO_HEADERS
    )
    assert response.status_code == 200, response.text
    return response.json()["state"]


def test_health_reports_demo_mode(demo_client):
    response = demo_client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "mode": "demo"}


def test_security_headers_allow_max_embedding(demo_client):
    response = demo_client.get("/api/health")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "max.ru" in response.headers["Content-Security-Policy"]
    assert "X-Frame-Options" not in response.headers


def test_state_requires_client_id(demo_client):
    assert demo_client.get("/api/state").status_code == 401
    short = demo_client.get("/api/state", headers={"X-Client-Id": "short"})
    assert short.status_code == 401
    assert "идентификатор" in short.json()["detail"]


def test_seeded_demo_state(demo_client):
    state = get_state(demo_client)
    viewer = state["viewer"]

    assert state["mode"] == "demo"
    assert state["verified"] is False
    assert state["demo_teacher_available"] is True
    assert state["teacher"] is None
    assert viewer["name"] == "Глеб Кузнецов"
    assert viewer["first_name"] == "Глеб"
    assert viewer["xp"] == 420
    assert viewer["level"]["level"] == 3
    assert viewer["level"]["title"] == "Знаток"
    assert viewer["sparks"] == 120
    assert viewer["streak"] == 6
    assert viewer["onboarded"] is True
    assert viewer["stats"] == {
        "confirmed": 3,
        "pending": 1,
        "help_count": 2,
        "weekly_xp": 150,
    }
    assert len(state["week"]) == 7
    assert len(state["challenges"]) == 8
    assert len(state["leaderboard"]["classes"]) == 8
    assert challenge_by_title(state, "Доклад по истории")["status"] == "pending"


def test_all_demo_visitors_share_one_profile(demo_client):
    first = demo_client.get(
        "/api/state", headers={"X-Client-Id": "first-browser"}
    ).json()
    second = demo_client.get(
        "/api/state", headers={"X-Client-Id": "second-browser"}
    ).json()

    assert first["viewer"]["id"] == second["viewer"]["id"]
    assert first["viewer"]["name"] == second["viewer"]["name"]


def test_submit_and_teacher_approve(demo_client):
    state = get_state(demo_client)
    challenge = challenge_by_title(state, "Домашнее задание по алгебре")

    submitted = demo_client.post(
        f"/api/challenges/{challenge['id']}/submit",
        json={"proof": "Решил все номера, проверь тетрадь."},
        headers=DEMO_HEADERS,
    )
    assert submitted.status_code == 200, submitted.text
    body = submitted.json()
    assert body["result"]["status"] == "pending"
    assert challenge_by_title(body["state"], challenge["title"])["status"] == "pending"
    assert body["state"]["viewer"]["stats"]["pending"] == 2

    repeated = demo_client.post(
        f"/api/challenges/{challenge['id']}/submit",
        json={"proof": "Ещё раз"},
        headers=DEMO_HEADERS,
    )
    assert repeated.status_code == 400
    assert "уже на проверке" in repeated.json()["detail"]

    teacher = switch_role(demo_client, "teacher")
    assert teacher["viewer"]["role"] == "teacher"
    assert teacher["viewer"]["is_teacher_preview"] is True
    assert teacher["teacher"] is not None
    assert len(teacher["teacher"]["pending"]) == 5

    pending = next(
        item
        for item in teacher["teacher"]["pending"]
        if item["is_self"] and item["title"] == challenge["title"]
    )
    approved = demo_client.post(
        f"/api/reviews/{pending['id']}",
        json={"action": "approve"},
        headers=DEMO_HEADERS,
    )
    assert approved.status_code == 200, approved.text
    result = approved.json()["result"]
    assert result["status"] == "approved"
    assert result["xp_awarded"] == 20
    assert result["level_up"] is False

    updated = approved.json()["state"]
    assert updated["viewer"]["xp"] == 440
    assert updated["viewer"]["sparks"] == 125
    assert updated["viewer"]["stats"]["confirmed"] == 4
    assert updated["viewer"]["stats"]["pending"] == 1
    assert challenge_by_title(updated, challenge["title"])["status"] == "approved"

    again = demo_client.post(
        f"/api/reviews/{pending['id']}",
        json={"action": "approve"},
        headers=DEMO_HEADERS,
    )
    assert again.status_code == 400
    assert "уже проверена" in again.json()["detail"]


def test_reject_returns_submission_to_student(demo_client):
    challenge = challenge_by_title(
        get_state(demo_client), "Кружок или секция"
    )
    demo_client.post(
        f"/api/challenges/{challenge['id']}/submit",
        json={"proof": "Ходил на робототехнику."},
        headers=DEMO_HEADERS,
    )
    teacher = switch_role(demo_client, "teacher")
    pending = next(
        item
        for item in teacher["teacher"]["pending"]
        if item["is_self"] and item["title"] == challenge["title"]
    )

    rejected = demo_client.post(
        f"/api/reviews/{pending['id']}",
        json={"action": "reject", "reason": "Нужна фотография с занятия."},
        headers=DEMO_HEADERS,
    )
    assert rejected.status_code == 200, rejected.text
    result = rejected.json()["result"]
    assert result["status"] == "rejected"
    assert result["xp_awarded"] == 0

    updated = rejected.json()["state"]
    item = challenge_by_title(updated, challenge["title"])
    assert item["status"] == "rejected"
    assert item["reject_reason"] == "Нужна фотография с занятия."
    assert updated["viewer"]["xp"] == 420

    back_to_student = switch_role(demo_client, "student")
    assert back_to_student["viewer"]["role"] == "student"
    item = challenge_by_title(back_to_student, challenge["title"])
    assert item["status"] == "rejected"

    resubmitted = demo_client.post(
        f"/api/challenges/{challenge['id']}/submit",
        json={"proof": "Фото прикрепил в чате класса."},
        headers=DEMO_HEADERS,
    )
    assert resubmitted.status_code == 200
    assert (
        challenge_by_title(resubmitted.json()["state"], challenge["title"])["status"]
        == "pending"
    )


def test_teacher_can_confirm_classmate(demo_client):
    teacher = switch_role(demo_client, "teacher")
    pending = next(
        item for item in teacher["teacher"]["pending"] if not item["is_self"]
    )
    before = next(
        student
        for student in teacher["teacher"]["students"]
        if student["id"] == pending["student_id"]
    )

    approved = demo_client.post(
        f"/api/reviews/{pending['id']}",
        json={"action": "approve"},
        headers=DEMO_HEADERS,
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["result"]["xp_awarded"] == pending["xp"]
    after = next(
        student
        for student in approved.json()["state"]["teacher"]["students"]
        if student["id"] == pending["student_id"]
    )
    assert after["xp"] == before["xp"] + pending["xp"]


def test_student_cannot_review_or_create(demo_client):
    teacher = switch_role(demo_client, "teacher")
    pending = teacher["teacher"]["pending"][0]
    switch_role(demo_client, "student")

    review = demo_client.post(
        f"/api/reviews/{pending['id']}",
        json={"action": "approve"},
        headers=DEMO_HEADERS,
    )
    assert review.status_code == 403
    assert "педагог" in review.json()["detail"]

    create = demo_client.post(
        "/api/challenges",
        json={
            "title": "Новое задание",
            "description": "",
            "category": "help",
            "xp": 20,
            "kind": "daily",
        },
        headers=DEMO_HEADERS,
    )
    assert create.status_code == 403


def test_buy_and_equip_cosmetic(demo_client):
    bought = demo_client.post(
        "/api/shop/buy", json={"item_id": "cap"}, headers=DEMO_HEADERS
    )
    assert bought.status_code == 200, bought.text
    state = bought.json()["state"]
    assert state["viewer"]["sparks"] == 70
    assert "cap" in state["viewer"]["owned"]

    duplicate = demo_client.post(
        "/api/shop/buy", json={"item_id": "cap"}, headers=DEMO_HEADERS
    )
    assert duplicate.status_code == 400
    assert "уже куплен" in duplicate.json()["detail"]

    equipped = demo_client.post(
        "/api/avatar/equip",
        json={"key": "accessory", "item_id": "cap"},
        headers=DEMO_HEADERS,
    )
    assert equipped.status_code == 200, equipped.text
    assert equipped.json()["state"]["viewer"]["avatar"]["accessory"] == "cap"

    locked = demo_client.post(
        "/api/avatar/equip",
        json={"key": "accessory", "item_id": "halo"},
        headers=DEMO_HEADERS,
    )
    assert locked.status_code == 400
    assert "5" in locked.json()["detail"]

    expensive = demo_client.post(
        "/api/shop/buy", json={"item_id": "frame_galaxy"}, headers=DEMO_HEADERS
    )
    assert expensive.status_code == 400
    assert "уровне" in expensive.json()["detail"]


def test_teacher_creates_and_archives_challenge(demo_client):
    switch_role(demo_client, "teacher")
    created = demo_client.post(
        "/api/challenges",
        json={
            "title": "Помощь на школьной ярмарке",
            "description": "Помоги с оформлением стенда.",
            "category": "help",
            "xp": 40,
            "kind": "event",
            "deadline": "",
        },
        headers=DEMO_HEADERS,
    )
    assert created.status_code == 200, created.text
    state = created.json()["state"]
    challenge = challenge_by_title(state, "Помощь на школьной ярмарке")
    assert challenge["xp"] == 40
    assert challenge["kind"] == "event"
    assert challenge["status"] == "available"

    archived = demo_client.post(
        f"/api/challenges/{challenge['id']}/archive", headers=DEMO_HEADERS
    )
    assert archived.status_code == 200
    assert all(
        item["id"] != challenge["id"]
        for item in archived.json()["state"]["challenges"]
    )

    def post_xp(value):
        return demo_client.post(
            "/api/challenges",
            json={"title": "Задание с наградой", "description": "", "category": "help",
                  "xp": value, "kind": "daily"},
            headers=DEMO_HEADERS,
        )

    # One rule everywhere: any integer 10..300 (the API schema and the service agree).
    assert post_xp(55).status_code == 200
    assert post_xp(10).status_code == 200
    assert post_xp(300).status_code == 200
    for bad in (9, 301, 500, 0, -20):
        assert post_xp(bad).status_code in {400, 422}, bad
    reward = demo_client.post("/api/teacher/reward", json={"student_id": 1, "amount": 301}, headers=DEMO_HEADERS)
    assert reward.status_code in {400, 422}

    missing = demo_client.post(
        "/api/challenges/999999/archive", headers=DEMO_HEADERS
    )
    assert missing.status_code == 404


def test_onboarding_normalizes_name_and_avatar(demo_client):
    saved = demo_client.post(
        "/api/onboarding",
        json={
            "first_name": "  Иван   Петров  ",
            "avatar": {"skin": "skin_tan", "hair": "hair_curls"},
        },
        headers=DEMO_HEADERS,
    )
    assert saved.status_code == 200, saved.text
    viewer = saved.json()["state"]["viewer"]
    assert viewer["first_name"] == "Иван"
    assert viewer["onboarded"] is True
    assert viewer["avatar"]["skin"] == "skin_tan"
    assert viewer["avatar"]["hair"] == "hair_curls"
    assert viewer["avatar"]["outfit"] == "hoodie_violet"

    bad_name = demo_client.post(
        "/api/onboarding",
        json={"first_name": "   ", "avatar": {}},
        headers=DEMO_HEADERS,
    )
    assert bad_name.status_code == 400

    bad_avatar = demo_client.post(
        "/api/onboarding",
        json={"first_name": "Иван", "avatar": {"skin": "skin_hacker"}},
        headers=DEMO_HEADERS,
    )
    assert bad_avatar.status_code == 400
    assert "гардеробе" in bad_avatar.json()["detail"]


def test_reset_restores_pristine_demo_profile(demo_client):
    demo_client.post(
        "/api/onboarding",
        json={"first_name": "Тестовый Герой", "avatar": {"skin": "skin_deep"}},
        headers=DEMO_HEADERS,
    )
    demo_client.post(
        "/api/shop/buy", json={"item_id": "cap"}, headers=DEMO_HEADERS
    )
    demo_client.post(
        "/api/avatar/equip",
        json={"key": "accessory", "item_id": "cap"},
        headers=DEMO_HEADERS,
    )
    challenge = challenge_by_title(
        get_state(demo_client), "Кружок или секция"
    )
    demo_client.post(
        f"/api/challenges/{challenge['id']}/submit",
        json={"proof": "Записался в театр."},
        headers=DEMO_HEADERS,
    )
    switch_role(demo_client, "teacher")

    reset = demo_client.post("/api/demo/reset", headers=DEMO_HEADERS)
    assert reset.status_code == 200, reset.text
    state = reset.json()["state"]
    viewer = state["viewer"]

    assert viewer["first_name"] == "Глеб"
    assert viewer["last_name"] == "Кузнецов"
    assert viewer["username"] == "gleb"
    assert viewer["xp"] == 420
    assert viewer["sparks"] == 120
    assert viewer["streak"] == 6
    assert viewer["role"] == "student"
    assert viewer["onboarded"] is True
    assert viewer["avatar"]["accessory"] == "headphones"
    assert viewer["owned"] == ["hoodie_cyan"]
    assert viewer["stats"] == {
        "confirmed": 3,
        "pending": 1,
        "help_count": 2,
        "weekly_xp": 150,
    }
    assert state["teacher"] is None
    assert challenge_by_title(state, "Доклад по истории")["status"] == "pending"
    assert all(
        item["title"] != challenge["title"]
        or item["status"] != "pending"
        for item in state["challenges"]
    )


def test_demo_role_validation(demo_client):
    invalid = demo_client.post(
        "/api/demo/role", json={"role": "admin"}, headers=DEMO_HEADERS
    )
    assert invalid.status_code == 400


def test_max_mode_requires_valid_init_data(max_client):
    assert max_client.get("/api/health").json()["mode"] == "prod"
    assert max_client.get("/api/state").status_code == 401
    assert (
        max_client.get(
            "/api/state", headers={"X-Max-Init-Data": "auth_date=1&hash=bad"}
        ).status_code
        == 401
    )

    init_data = sign_init_data(MAX_USER, bot_token=MAX_TOKEN)
    response = max_client.get(
        "/api/state", headers={"X-Max-Init-Data": init_data}
    )
    assert response.status_code == 200, response.text
    state = response.json()
    assert state["mode"] == "prod"
    assert state["verified"] is True
    assert state["viewer"]["name"] == "Алиса Морозова"
    assert state["viewer"]["role"] == "student"
    assert state["viewer"]["onboarded"] is False
    assert state["demo_teacher_available"] is False


def test_max_teacher_gets_cabinet(max_client):
    teacher_user = {
        "id": 9001,
        "first_name": "Константин",
        "last_name": "Зверев",
        "username": "zverev",
    }
    init_data = sign_init_data(teacher_user, bot_token=MAX_TOKEN)
    response = max_client.get(
        "/api/state", headers={"X-Max-Init-Data": init_data}
    )
    assert response.status_code == 200, response.text
    state = response.json()
    assert state["viewer"]["role"] == "teacher"
    assert state["teacher"] is not None
    assert len(state["teacher"]["pending"]) == 3
    assert state["viewer"]["is_teacher_preview"] is False

    demo_switch = max_client.post(
        "/api/demo/role",
        json={"role": "student"},
        headers={"X-Max-Init-Data": init_data},
    )
    assert demo_switch.status_code == 403

    reset = max_client.post(
        "/api/demo/reset", headers={"X-Max-Init-Data": init_data}
    )
    assert reset.status_code == 403


def test_max_student_cannot_use_teacher_endpoints(max_client):
    init_data = sign_init_data(MAX_USER, bot_token=MAX_TOKEN)
    headers = {"X-Max-Init-Data": init_data}

    create = max_client.post(
        "/api/challenges",
        json={
            "title": "Задание от ученика",
            "description": "",
            "category": "help",
            "xp": 20,
            "kind": "daily",
        },
        headers=headers,
    )
    assert create.status_code == 403

    state = max_client.get("/api/state", headers=headers).json()
    pending_id = state["viewer"]["stats"]["pending"]
    assert pending_id == 0
    review = max_client.post(
        "/api/reviews/1", json={"action": "approve"}, headers=headers
    )
    assert review.status_code == 403

def test_director_role_and_batch_review(demo_client):
    director_state = switch_role(demo_client, "director")
    assert director_state["viewer"]["role"] == "director"
    assert director_state["director"] is not None
    kpi = director_state["director"]["kpi"]
    assert kpi["total_students"] > 0
    assert len(director_state["director"]["grades"]) > 0
    assert "directions" in director_state["director"]

    # Teacher switch and batch approve
    teacher_state = switch_role(demo_client, "teacher")
    pending = teacher_state["teacher"]["pending"]
    assert len(pending) >= 2
    ids = [pending[0]["id"], pending[1]["id"]]
    batch_resp = demo_client.post(
        "/api/reviews/batch",
        json={"completion_ids": ids, "action": "approve"},
        headers=DEMO_HEADERS,
    )
    assert batch_resp.status_code == 200
    res = batch_resp.json()["result"]
    assert res["approved"] == 2
    assert len(res["results"]) == 2


def test_teacher_reward_student(demo_client):
    switch_role(demo_client, "teacher")
    state = demo_client.get("/api/state", headers=DEMO_HEADERS).json()
    student = state["teacher"]["students"][0]
    initial_xp = student["xp"]
    resp = demo_client.post(
        "/api/teacher/reward",
        json={"student_id": student["id"], "amount": 50, "reason": "Активность на уроке математики"},
        headers=DEMO_HEADERS,
    )
    assert resp.status_code == 200
    updated_state = resp.json()["state"]
    updated_student = next(s for s in updated_state["teacher"]["students"] if s["id"] == student["id"])
    assert updated_student["xp"] == initial_xp + 50
    assert "recent_works" in updated_student
    assert "subject_stats" in updated_student



def test_school_check_code_and_catalog(demo_client):
    # Test valid code KVANT-8A
    resp = demo_client.get("/api/school/check-code?code=KVANT-8A", headers=DEMO_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["class_name"] == "8А"
    assert "Кванториум" in data["school_name"]
    assert data["teacher_name"] == "Константин Зверев"

    # Test invalid code
    bad_resp = demo_client.get("/api/school/check-code?code=NONEXISTENT", headers=DEMO_HEADERS)
    assert bad_resp.status_code == 200
    assert bad_resp.json()["valid"] is False

    # Test catalog
    cat_resp = demo_client.get("/api/school/catalog", headers=DEMO_HEADERS)
    assert cat_resp.status_code == 200
    cat_data = cat_resp.json()
    assert "Великий Новгород" in cat_data["cities"]
    assert len(cat_data["schools"]) >= 5
    assert len(cat_data["classes"]) >= 8

    # Test join class
    join_resp = demo_client.post("/api/school/join", json={"invite_code": "KVANT-8A"}, headers=DEMO_HEADERS)
    assert join_resp.status_code == 200
    assert join_resp.json()["state"]["viewer"]["class_name"] == "8А"

    # Test onboarding with last_name and invite_code
    onboard_resp = demo_client.post(
        "/api/onboarding",
        json={
            "first_name": "Сергей",
            "last_name": "Иванов",
            "invite_code": "KVANT-8A",
            "avatar": {"skin": "skin_warm", "hair": "hair_short"},
        },
        headers=DEMO_HEADERS,
    )
    assert onboard_resp.status_code == 200
    viewer = onboard_resp.json()["state"]["viewer"]
    assert viewer["first_name"] == "Сергей"
    assert viewer["last_name"] == "Иванов"
    assert viewer["class_name"] == "8А"
    assert viewer["onboarded"] is True


def test_demo_mode_cannot_be_enabled_by_empty_token(tmp_path):
    from backend.config import Settings

    settings = Settings(app_mode="prod", bot_token="")
    assert not settings.demo_mode
    try:
        settings.validate()
    except RuntimeError:
        pass
    else:
        raise AssertionError("prod without token must fail")


def test_prod_catalog_creates_no_users(tmp_path):
    import json

    from backend.catalog import import_catalog
    from backend.db import connect, init_db

    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "schools": [
                    {
                        "name": "Школа 1",
                        "city": "Город",
                        "classes": [
                            {"name": "5А", "invite_code": "S1-5A", "teacher_max_ids": ["42"]}
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    db = tmp_path / "prod.db"
    init_db(db)
    conn = connect(db)
    try:
        import_catalog(conn, catalog)
        import_catalog(conn, catalog)  # idempotent
        assert conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 0
        assert conn.execute("SELECT COUNT(*) AS n FROM classes").fetchone()["n"] == 1
        assert conn.execute("SELECT COUNT(*) AS n FROM challenges").fetchone()["n"] == 0
        assert conn.execute("SELECT class_id FROM class_staff WHERE max_user_id='42'").fetchone()
    finally:
        conn.close()


def test_staff_cannot_use_hero_or_shop():
    import sqlite3

    from backend.service import GameError, buy_item, equip_item

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    staff = conn.execute("SELECT 'teacher' AS role, NULL AS preview_role").fetchone()
    for call in (lambda: buy_item(conn, staff, "x"), lambda: equip_item(conn, staff, "hair", "x")):
        try:
            call()
        except GameError as exc:
            assert exc.status == 403
        else:
            raise AssertionError("staff must not use hero or shop")
