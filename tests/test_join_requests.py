"""Joining a class from the public list is a request a teacher approves;
a student code joins at once. Directors can disconnect teachers."""

from __future__ import annotations

import pytest

from backend.db import connect
from test_registration import (  # noqa: F401
    ADMIN_ID,
    class_codes,
    client,
    create_school,
    hdr,
    make_client,
    onboard_student,
)

DIRECTOR, OTHER_DIRECTOR, TEACHER_A, TEACHER_B = 100, 300, 200, 201
PUPIL, PUPIL2, MEMBER = 1, 2, 3


@pytest.fixture
def school(client):  # noqa: F811
    create_school(client, DIRECTOR, name="Школа Заявок", city="Тула", classes=("5А", "5Б"))
    codes = class_codes(client, DIRECTOR)
    client.post("/api/school/join", json={"invite_code": codes["5А"]["teacher_code"]}, headers=hdr(TEACHER_A))
    client.post("/api/school/join", json={"invite_code": codes["5Б"]["teacher_code"]}, headers=hdr(TEACHER_B))
    onboard_student(client, MEMBER, codes["5А"]["invite_code"])  # someone already in 5А
    return codes


def state(client, uid):
    r = client.get("/api/state", headers=hdr(uid))
    assert r.status_code == 200, r.text
    return r.json()


def ask(client, uid, class_id):
    return client.post("/api/school/join", json={"class_id": class_id}, headers=hdr(uid))


def decide(client, uid, request_id, action):
    return client.post(f"/api/join-requests/{request_id}", json={"action": action}, headers=hdr(uid))


def teacher_requests(client, uid=TEACHER_A):
    return state(client, uid)["teacher"]["join_requests"]


def test_list_choice_files_a_request_and_shows_nothing_of_the_class(client, school):
    r = ask(client, PUPIL, school["5А"]["id"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "requested" and body["request"]["class_name"] == "5А"
    s = body["state"]
    assert s["viewer"]["class_id"] is None
    assert s["viewer"]["join_request"]["status"] == "pending"
    assert s["viewer"]["join_request"]["school_name"] == "Школа Заявок"
    # nothing of the class leaks while the request waits
    assert s["leaderboard"]["students"] == [] and s["feed"] == [] and s["challenges"] == []
    reqs = teacher_requests(client)
    assert len(reqs) == 1 and reqs[0]["class_name"] == "5А" and reqs[0]["name"]
    assert teacher_requests(client, TEACHER_B) == []


def test_onboarding_with_a_class_from_the_list_files_a_request(client, school):
    r = client.post(
        "/api/onboarding",
        json={"first_name": "Новый", "last_name": "Ученик", "avatar": {}, "class_id": school["5А"]["id"]},
        headers=hdr(PUPIL),
    )
    assert r.status_code == 200, r.text
    v = r.json()["state"]["viewer"]
    assert v["onboarded"] is True and v["class_id"] is None
    assert v["join_request"]["status"] == "pending"


def test_teacher_approves_and_the_student_is_in(client, school):
    rid = ask(client, PUPIL, school["5А"]["id"]).json()["request"]["id"]
    r = decide(client, TEACHER_A, rid, "approve")
    assert r.status_code == 200, r.text
    assert r.json()["result"]["status"] == "approved"
    assert r.json()["state"]["teacher"]["join_requests"] == []
    v = state(client, PUPIL)["viewer"]
    assert v["class_name"] == "5А" and v["join_request"] is None
    assert decide(client, TEACHER_A, rid, "approve").status_code == 409  # already decided


def test_declined_request_is_shown_and_another_class_can_be_asked(client, school):
    rid = ask(client, PUPIL, school["5А"]["id"]).json()["request"]["id"]
    assert decide(client, TEACHER_A, rid, "decline").status_code == 200
    v = state(client, PUPIL)["viewer"]
    assert v["class_id"] is None and v["join_request"]["status"] == "declined"
    again = ask(client, PUPIL, school["5Б"]["id"])
    assert again.status_code == 200 and again.json()["state"]["viewer"]["join_request"]["class_name"] == "5Б"


def test_cancel_and_one_active_request(client, school):
    assert client.post("/api/join-requests/cancel", headers=hdr(PUPIL)).status_code == 404
    first = ask(client, PUPIL, school["5А"]["id"])
    assert ask(client, PUPIL, school["5А"]["id"]).json()["request"]["id"] == first.json()["request"]["id"]
    other = ask(client, PUPIL, school["5Б"]["id"])
    assert other.status_code == 409 and "5А" in other.json()["detail"]
    r = client.post("/api/join-requests/cancel", headers=hdr(PUPIL))
    assert r.status_code == 200 and r.json()["state"]["viewer"]["join_request"] is None
    assert teacher_requests(client) == []
    assert ask(client, PUPIL, school["5Б"]["id"]).status_code == 200


def test_at_most_five_requests_a_day(client, school):
    for _ in range(5):
        assert ask(client, PUPIL, school["5А"]["id"]).status_code == 200
        client.post("/api/join-requests/cancel", headers=hdr(PUPIL))
    sixth = ask(client, PUPIL, school["5Б"]["id"])
    assert sixth.status_code == 429


def test_only_the_class_teacher_or_school_director_decide(client, school):
    rid = ask(client, PUPIL, school["5А"]["id"]).json()["request"]["id"]
    create_school(client, OTHER_DIRECTOR, name="Чужая школа", city="Омск", classes=("6А",))
    for outsider in (TEACHER_B, OTHER_DIRECTOR, MEMBER, PUPIL):
        assert decide(client, outsider, rid, "approve").status_code == 404, outsider
    other_admin = state(client, OTHER_DIRECTOR)["school_admin"]
    assert other_admin["join_requests"] == []
    own = state(client, DIRECTOR)["school_admin"]["join_requests"]
    assert [r["id"] for r in own] == [rid] and own[0]["class_name"] == "5А"
    assert decide(client, DIRECTOR, rid, "approve").status_code == 200
    assert state(client, PUPIL)["viewer"]["class_name"] == "5А"


def test_code_still_joins_at_once_and_closes_the_request(client, school):
    ask(client, PUPIL, school["5А"]["id"])
    r = client.post("/api/school/join", json={"invite_code": school["5Б"]["invite_code"]}, headers=hdr(PUPIL))
    assert r.status_code == 200 and r.json()["status"] == "joined"
    v = r.json()["state"]["viewer"]
    assert v["class_name"] == "5Б" and v["join_request"] is None
    assert teacher_requests(client) == []


def test_a_member_changes_class_only_through_a_request_or_a_code(client, school):
    r = ask(client, MEMBER, school["5Б"]["id"])
    assert r.status_code == 200 and r.json()["state"]["viewer"]["class_name"] == "5А"  # stays
    rid = r.json()["request"]["id"]
    assert decide(client, TEACHER_B, rid, "approve").status_code == 200
    assert state(client, MEMBER)["viewer"]["class_name"] == "5Б"
    assert ask(client, MEMBER, school["5Б"]["id"]).status_code == 400  # already there


def test_excluded_student_cannot_ask_any_class_of_the_school(client, school):
    sid = state(client, MEMBER)["viewer"]["id"]
    client.post(f"/api/teacher/students/{sid}/remove", json={}, headers=hdr(TEACHER_A))
    for cls in ("5А", "5Б"):
        r = ask(client, MEMBER, school[cls]["id"])
        assert r.status_code == 403 and "отчислены" in r.json()["detail"]


def test_staff_cannot_file_requests(client, school):
    assert ask(client, TEACHER_A, school["5Б"]["id"]).status_code == 403
    assert ask(client, DIRECTOR, school["5Б"]["id"]).status_code == 403


# --- disconnecting teachers --------------------------------------------------


def teacher_list(client, cls="5А"):
    return class_codes(client, DIRECTOR)[cls]["teachers"]


def test_director_disconnects_a_teacher(client, school):
    teachers = teacher_list(client)
    assert len(teachers) == 1 and teachers[0]["name"] and teachers[0]["since"]
    tid, cid = teachers[0]["id"], school["5А"]["id"]
    url = f"/api/school/classes/{cid}/teachers/{tid}/disconnect"
    assert client.post(url, headers=hdr(TEACHER_B)).status_code == 404
    create_school(client, OTHER_DIRECTOR, name="Чужая школа", city="Омск", classes=("6А",))
    assert client.post(url, headers=hdr(OTHER_DIRECTOR)).status_code == 404
    r = client.post(url, headers=hdr(DIRECTOR))
    assert r.status_code == 200, r.text
    assert teacher_list(client) == []
    t = state(client, TEACHER_A)
    assert t["viewer"]["role"] == "teacher" and t["viewer"]["class_id"] is None and t["teacher"] is None
    # the old code was not changed, so the director decides by reissuing it;
    # with a new one the teacher can join again
    assert client.post(url, headers=hdr(DIRECTOR)).status_code == 404
    again = client.post("/api/school/join", json={"invite_code": school["5А"]["teacher_code"]}, headers=hdr(TEACHER_A))
    assert again.status_code == 200 and again.json()["state"]["viewer"]["class_name"] == "5А"


def test_reissuing_the_teacher_code_can_disconnect_everyone(client, school):
    cid = school["5А"]["id"]
    keep = client.post(f"/api/school/classes/{cid}/codes", json={"kind": "teacher"}, headers=hdr(DIRECTOR))
    assert keep.status_code == 200 and len(teacher_list(client)) == 1
    drop = client.post(
        f"/api/school/classes/{cid}/codes",
        json={"kind": "teacher", "disconnect_teachers": True},
        headers=hdr(DIRECTOR),
    )
    assert drop.status_code == 200 and teacher_list(client) == []
    assert state(client, TEACHER_A)["viewer"]["class_id"] is None
    assert len(teacher_list(client, "5Б")) == 1  # other classes untouched
    old = client.post("/api/school/join", json={"invite_code": school["5А"]["teacher_code"]}, headers=hdr(TEACHER_A))
    assert old.status_code == 404


def test_env_teacher_stays_disconnected(tmp_path):
    c = make_client(tmp_path, teacher_max_ids={"777"})
    try:
        create_school(c, DIRECTOR, name="Школа Каталога", city="Тула", classes=("7А",))
        cid = class_codes(c, DIRECTOR)["7А"]["id"]
        conn = connect(tmp_path / "test.db")
        conn.execute("INSERT INTO class_staff (max_user_id, class_id) VALUES ('777', ?)", (cid,))
        conn.commit()
        conn.close()
        assert state(c, 777)["viewer"]["class_name"] == "7А"
        tid = class_codes(c, DIRECTOR)["7А"]["teachers"][0]["id"]
        assert c.post(f"/api/school/classes/{cid}/teachers/{tid}/disconnect", headers=hdr(DIRECTOR)).status_code == 200
        again = state(c, 777)["viewer"]  # next login: not re-attached by the env list
        assert again["role"] == "teacher" and again["class_id"] is None
    finally:
        c.close()


# --- platform admin ----------------------------------------------------------


def test_admin_sees_rejected_schools_and_can_restore(tmp_path):
    c = make_client(tmp_path, school_approval="manual")
    try:
        create_school(c, DIRECTOR, name="Школа на проверке", city="Тула", classes=("5А",))
        sid = state(c, ADMIN_ID)["platform_admin"]["pending"][0]["id"]
        c.post(f"/api/admin/schools/{sid}/status", json={"status": "rejected"}, headers=hdr(ADMIN_ID))
        admin = state(c, ADMIN_ID)["platform_admin"]
        assert admin["pending"] == [] and [s["id"] for s in admin["rejected"]] == [sid]
        c.post(f"/api/admin/schools/{sid}/status", json={"status": "active"}, headers=hdr(ADMIN_ID))
        assert state(c, ADMIN_ID)["platform_admin"]["rejected"] == []
    finally:
        c.close()


def test_migration_adds_the_requests_table_and_columns(tmp_path):
    from backend.db import init_db

    db = tmp_path / "old.db"
    init_db(db)
    conn = connect(db)
    conn.execute("DROP TABLE join_requests")
    conn.commit()
    conn.close()
    init_db(db)
    conn = connect(db)
    try:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(join_requests)")}
        assert {"user_id", "class_id", "status", "created_at", "decided_at", "decided_by"} <= cols
        user_cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
        assert {"class_since", "staff_detached"} <= user_cols
        indexes = {r["name"] for r in conn.execute("PRAGMA index_list(join_requests)")}
        assert "idx_join_requests_one_pending" in indexes
    finally:
        conn.close()
