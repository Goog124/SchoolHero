"""Removing a student from a class and keeping them out of it."""

from __future__ import annotations

import pytest

from backend.db import connect, init_db
from test_registration import class_codes, client, create_school, hdr, onboard_student  # noqa: F401

DIRECTOR, TEACHER_A, TEACHER_B, PUPIL, PUPIL2 = 100, 200, 201, 1, 2


@pytest.fixture
def school(client):  # noqa: F811
    create_school(client, DIRECTOR, name="Школа Исключений", city="Тула", classes=("8А", "8Б"))
    codes = class_codes(client, DIRECTOR)
    client.post("/api/school/join", json={"invite_code": codes["8А"]["teacher_code"]}, headers=hdr(TEACHER_A))
    client.post("/api/school/join", json={"invite_code": codes["8Б"]["teacher_code"]}, headers=hdr(TEACHER_B))
    onboard_student(client, PUPIL, codes["8А"]["invite_code"])
    onboard_student(client, PUPIL2, codes["8А"]["invite_code"])
    return codes


def state(client, uid):
    return client.get("/api/state", headers=hdr(uid)).json()


def pupil_id(client, uid=PUPIL):
    return state(client, uid)["viewer"]["id"]


def remove(client, by, student, reason=""):
    return client.post(f"/api/teacher/students/{student}/remove", json={"reason": reason}, headers=hdr(by))


def restore(client, by, student):
    return client.post(f"/api/teacher/students/{student}/restore", headers=hdr(by))


def test_teacher_removes_a_student_of_their_class(client, school):
    sid = pupil_id(client)
    client.post("/api/teacher/reward", json={"student_id": sid, "amount": 50}, headers=hdr(TEACHER_A))
    xp_before = state(client, PUPIL)["viewer"]["xp"]

    r = remove(client, TEACHER_A, sid, "Посторонний")
    assert r.status_code == 200, r.text
    teacher = r.json()["state"]["teacher"]
    assert sid not in [s["id"] for s in teacher["students"]]
    assert teacher["stats"]["students"] == 1
    assert teacher["excluded"][0]["id"] == sid and teacher["excluded"][0]["reason"] == "Посторонний"
    assert teacher["excluded"][0]["name"]

    gone = state(client, PUPIL)
    assert gone["viewer"]["class_id"] is None and gone["viewer"]["onboarded"] is True
    assert gone["viewer"]["role"] == "student"
    assert gone["viewer"]["removed_from"] == {"class_name": "8А", "school_name": "Школа Исключений"}
    assert gone["viewer"]["xp"] == xp_before  # progress is kept
    assert gone["challenges"] == [] and gone["leaderboard"]["students"] == []
    # gone from rankings and from the school numbers
    assert state(client, PUPIL2)["class_sprint"]["members"] == 1
    assert state(client, DIRECTOR)["director"]["kpi"]["total_students"] == 1
    assert [s["id"] for s in state(client, PUPIL2)["leaderboard"]["students"]] != []
    assert sid not in [s["id"] for s in state(client, PUPIL2)["leaderboard"]["students"]]


def test_pending_work_of_a_removed_student_leaves_the_queue(client, school):
    r = client.post(
        "/api/challenges",
        json={"title": "Задание класса", "description": "", "category": "help", "xp": 20, "kind": "daily"},
        headers=hdr(TEACHER_A),
    )
    assert r.status_code == 200, r.text
    ch = state(client, PUPIL)["challenges"][0]
    client.post(f"/api/challenges/{ch['id']}/submit", json={"proof": "готово"}, headers=hdr(PUPIL))
    queue = state(client, TEACHER_A)["teacher"]
    assert len(queue["pending"]) == 1
    completion_id, sid = queue["pending"][0]["id"], pupil_id(client)

    remove(client, TEACHER_A, sid)
    after = state(client, TEACHER_A)["teacher"]
    assert after["pending"] == [] and after["stats"]["pending"] == 0
    assert after["challenges"][0]["pending_count"] == 0
    # the work cannot be approved while the student is out of the class
    assert client.post(f"/api/reviews/{completion_id}", json={"action": "approve"}, headers=hdr(TEACHER_A)).status_code == 400
    # the row is kept: it is back after the student rejoins
    restore(client, TEACHER_A, sid)
    client.post("/api/school/join", json={"invite_code": school["8А"]["invite_code"]}, headers=hdr(PUPIL))
    assert len(state(client, TEACHER_A)["teacher"]["pending"]) == 1


def test_permissions(client, school):
    sid = pupil_id(client)
    assert remove(client, TEACHER_B, sid).status_code == 403      # teacher of another class
    assert remove(client, PUPIL2, sid).status_code == 403         # a student
    create_school(client, 300, name="Чужая Школа", city="Омск", classes=("8А",))
    assert remove(client, 300, sid).status_code == 403            # director of another school
    assert restore(client, TEACHER_B, sid).status_code == 404
    assert state(client, PUPIL)["viewer"]["class_id"] is not None  # nothing happened
    assert remove(client, DIRECTOR, sid, "Решение директора").status_code == 200
    assert remove(client, TEACHER_A, 99999).status_code == 404


def test_cannot_remove_staff_yourself_or_a_classless_user(client, school):
    teacher_id = state(client, TEACHER_A)["viewer"]["id"]
    assert remove(client, DIRECTOR, teacher_id).status_code == 400
    assert remove(client, TEACHER_A, teacher_id).status_code == 400
    director_id = state(client, DIRECTOR)["viewer"]["id"]
    assert remove(client, DIRECTOR, director_id).status_code == 400
    stranger = state(client, 777)["viewer"]["id"]                  # a student without a class
    assert remove(client, TEACHER_A, stranger).status_code == 400
    sid = pupil_id(client)
    assert remove(client, TEACHER_A, sid).status_code == 200
    assert remove(client, TEACHER_A, sid).status_code == 400       # already out


def test_removed_student_cannot_return_to_the_school(client, school):
    sid = pupil_id(client)
    remove(client, TEACHER_A, sid)
    cid = school["8А"]["id"]
    message = "Вы отчислены из класса этой школы"

    by_list = client.post("/api/school/join", json={"class_id": cid}, headers=hdr(PUPIL))
    assert by_list.status_code == 403 and message in by_list.json()["detail"]
    by_code = client.post("/api/school/join", json={"invite_code": school["8А"]["invite_code"]}, headers=hdr(PUPIL))
    assert by_code.status_code == 403 and message in by_code.json()["detail"]
    onboarding = client.post(
        "/api/onboarding",
        json={"first_name": "Ученик", "avatar": {}, "class_id": cid},
        headers=hdr(PUPIL),
    )
    assert onboarding.status_code == 403
    onboarding_code = client.post(
        "/api/onboarding",
        json={"first_name": "Ученик", "avatar": {}, "invite_code": school["8А"]["invite_code"]},
        headers=hdr(PUPIL),
    )
    assert onboarding_code.status_code == 403
    check = client.post("/api/school/check-code", json={"code": school['8А']['invite_code']}, headers=hdr(PUPIL)).json()
    assert check["valid"] is False and message in check["detail"]
    # the ban covers every class of the school: no request, no code
    other_list = client.post("/api/school/join", json={"class_id": school["8Б"]["id"]}, headers=hdr(PUPIL))
    assert other_list.status_code == 403
    other_code = client.post("/api/school/join", json={"invite_code": school["8Б"]["invite_code"]}, headers=hdr(PUPIL))
    assert other_code.status_code == 403
    assert state(client, PUPIL)["viewer"]["class_id"] is None
    # the classes are still listed; others can still use the code
    listed = client.get("/api/school/catalog?city=Тула", headers=hdr(PUPIL)).json()
    assert cid in [c["id"] for c in listed["classes"]]
    other = client.post("/api/school/check-code", json={"code": school['8А']['invite_code']}, headers=hdr(PUPIL2)).json()
    assert other["valid"] is True


def test_removed_student_can_join_another_school_and_restore_lifts_the_ban(client, school):
    sid = pupil_id(client)
    remove(client, TEACHER_A, sid)
    create_school(client, 300, name="Соседняя школа", city="Тула", classes=("5А",))
    neighbour = class_codes(client, 300)["5А"]
    other = client.post("/api/school/join", json={"invite_code": neighbour["invite_code"]}, headers=hdr(PUPIL))
    assert other.status_code == 200 and other.json()["state"]["viewer"]["class_name"] == "5А"
    assert other.json()["state"]["viewer"]["removed_from"] is None

    assert restore(client, TEACHER_A, sid).status_code == 200
    assert state(client, TEACHER_A)["teacher"]["excluded"] == []
    back = client.post("/api/school/join", json={"invite_code": school["8А"]["invite_code"]}, headers=hdr(PUPIL))
    assert back.status_code == 200 and back.json()["state"]["viewer"]["class_name"] == "8А"
    # restore did not move anybody by itself
    assert restore(client, TEACHER_A, sid).status_code == 404


def test_removal_declines_an_open_request_to_the_same_school(client, school):
    sid = pupil_id(client)
    r = client.post("/api/school/join", json={"class_id": school["8Б"]["id"]}, headers=hdr(PUPIL))
    assert r.status_code == 200 and r.json()["status"] == "requested"
    assert len(state(client, TEACHER_B)["teacher"]["join_requests"]) == 1
    remove(client, TEACHER_A, sid)
    assert state(client, TEACHER_B)["teacher"]["join_requests"] == []
    assert state(client, PUPIL)["viewer"]["join_request"]["status"] == "declined"


def test_teacher_code_is_not_affected_by_an_exclusion(client, school):
    sid = pupil_id(client)
    remove(client, TEACHER_A, sid)
    r = client.post("/api/school/join", json={"invite_code": school["8А"]["teacher_code"]}, headers=hdr(PUPIL))
    assert r.status_code == 200 and r.json()["state"]["viewer"]["role"] == "teacher"


def test_migration_creates_the_exclusions_table(tmp_path):
    db = tmp_path / "old.db"
    init_db(db)
    conn = connect(db)
    conn.execute("DROP TABLE class_exclusions")
    conn.commit()
    conn.close()
    init_db(db)
    init_db(db)  # idempotent
    conn = connect(db)
    try:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(class_exclusions)")}
        assert {"user_id", "class_id", "removed_by", "reason", "created_at"} <= cols
        indexes = {r["name"] for r in conn.execute("PRAGMA index_list(class_exclusions)")}
        assert "idx_class_exclusions_class" in indexes
    finally:
        conn.close()
