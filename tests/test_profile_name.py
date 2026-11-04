"""Names of teachers and directors: asked when missing, typed names are kept."""

from __future__ import annotations

import pytest

from conftest import MAX_TOKEN
from test_registration import class_codes, client  # noqa: F401
from test_security import sign_init_data


def hdr_named(user_id: int, first=None, last=None) -> dict:
    """initData whose user has no name (MAX may omit it) or the given one."""
    user = {"id": user_id}
    if first:
        user["first_name"] = first
    if last:
        user["last_name"] = last
    return {"X-Max-Init-Data": sign_init_data(user, bot_token=MAX_TOKEN)}


def viewer(client, headers) -> dict:
    return client.get("/api/state", headers=headers).json()["viewer"]


def set_name(client, headers, **body):
    return client.post("/api/profile/name", json=body, headers=headers)


def test_new_director_and_teacher_need_a_name_student_never(client):
    director = hdr_named(100)
    r = client.post(
        "/api/school/create",
        json={"name": "Школа Имён", "city": "Тверь", "classes": [{"name": "5А"}]},
        headers=director,
    )
    assert r.status_code == 200, r.text
    v = r.json()["state"]["viewer"]
    assert v["role"] == "director" and v["first_name"] == "Герой" and v["needs_name"] is True

    teacher_code = class_codes(client, 100)["5А"]["teacher_code"]
    teacher = hdr_named(101)
    r = client.post("/api/school/join", json={"invite_code": teacher_code}, headers=teacher)
    assert r.json()["state"]["viewer"]["needs_name"] is True

    # a pupil is asked by the onboarding itself, so the flag is always false
    pupil = hdr_named(102)
    assert viewer(client, pupil)["first_name"] == "Герой"
    assert viewer(client, pupil)["needs_name"] is False

    # staff with a name from MAX are not asked
    named = hdr_named(103, "Ольга", "Смирнова")
    client.post("/api/school/join", json={"invite_code": teacher_code}, headers=named)
    assert viewer(client, named)["needs_name"] is False


def test_staff_can_set_and_change_the_name(client):
    director = hdr_named(100)
    client.post(
        "/api/school/create",
        json={"name": "Школа Номер Ноль", "city": "Омск", "classes": [{"name": "5А"}]},
        headers=director,
    )
    assert viewer(client, director)["needs_name"] is True
    r = set_name(client, director, first_name="Анна", last_name="Иванова-Петрова")
    assert r.status_code == 200, r.text
    v = r.json()["state"]["viewer"]
    assert (v["first_name"], v["last_name"], v["name"]) == ("Анна", "Иванова-Петрова", "Анна Иванова-Петрова")
    assert v["needs_name"] is False
    again = set_name(client, director, first_name="Мария", last_name="Орлова")
    assert again.json()["state"]["viewer"]["name"] == "Мария Орлова"


def test_single_field_full_name_is_split(client):
    director = hdr_named(100)
    client.post(
        "/api/school/create",
        json={"name": "Школа Один", "city": "Омск", "classes": [{"name": "5А"}]},
        headers=director,
    )
    v = set_name(client, director, first_name="Анна Иванова").json()["state"]["viewer"]
    assert (v["first_name"], v["last_name"]) == ("Анна", "Иванова")


def test_max_name_does_not_overwrite_a_typed_one(client):
    director = hdr_named(100)
    client.post(
        "/api/school/create",
        json={"name": "Школа Два", "city": "Омск", "classes": [{"name": "5А"}]},
        headers=director,
    )
    set_name(client, director, first_name="Анна", last_name="Иванова")
    # MAX starts to send its own name for the same user: still the typed one
    changed = hdr_named(100, "Чужое", "Имя")
    v = viewer(client, changed)
    assert (v["first_name"], v["last_name"]) == ("Анна", "Иванова")
    # a name nobody typed is still refreshed from MAX
    other = hdr_named(200, "Первое", "Имя")
    assert viewer(client, other)["first_name"] == "Первое"
    assert viewer(client, hdr_named(200, "Второе", "Имя"))["first_name"] == "Второе"


@pytest.mark.parametrize(
    "body",
    [
        {"first_name": "А"},
        {"first_name": "Ан" * 13},
        {"first_name": "Анна1"},
        {"first_name": "Анна", "last_name": "Иванов<script>"},
        {"first_name": "  "},
        {"first_name": "Анна", "last_name": "И" * 33},
    ],
)
def test_name_validation(client, body):
    director = hdr_named(100)
    client.post(
        "/api/school/create",
        json={"name": "Школа Три", "city": "Омск", "classes": [{"name": "5А"}]},
        headers=director,
    )
    assert set_name(client, director, **body).status_code in {400, 422}
    assert viewer(client, director)["first_name"] == "Герой"


def test_name_endpoint_requires_auth(client):
    assert client.post("/api/profile/name", json={"first_name": "Анна"}).status_code == 401


def test_onboarding_name_is_kept_against_max_updates(client):
    pupil = hdr_named(300, "Старое", "Имя")
    client.post("/api/onboarding", json={"first_name": "Сергей", "last_name": "Иванов", "avatar": {}}, headers=pupil)
    assert viewer(client, hdr_named(300, "Новое", "Имя"))["first_name"] == "Сергей"
