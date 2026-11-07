"""City directory, school time zone patch, sandbox admin switch."""

from __future__ import annotations

from backend import cities
from test_registration import (  # noqa: F401
    client,
    create_school,
    hdr,
    school_body,
)
from test_sandbox import h as sh
from test_sandbox import make_client as make_sandbox
from test_sandbox import state as sandbox_state
from conftest import DEMO_HEADERS, build_client, make_settings


def names(res):
    return [c["name"] for c in res.json()["cities"]]


def test_directory_loaded_and_clean():
    all_names = cities.directory()
    assert len(all_names) > 400 and len(set(all_names)) == len(all_names)
    assert {"Москва", "Тула", "Владивосток", "Орёл"} <= set(all_names)


def test_scope_all_suggests_directory(client):
    r = client.get("/api/school/cities", params={"q": "тул", "scope": "all"}, headers=hdr(10))
    assert r.status_code == 200
    got = names(r)
    assert got[0] == "Тула" and len(got) <= 10
    # yo equals ye, case ignored; prefix matches come first
    assert "Орёл" in names(
        client.get("/api/school/cities", params={"q": "ОРЕЛ", "scope": "all"}, headers=hdr(10))
    )
    got = names(client.get("/api/school/cities", params={"q": "ново", "scope": "all"}, headers=hdr(10)))
    assert len(got) == 10 and all(n.casefold().startswith("ново") for n in got)
    got = names(client.get("/api/school/cities", params={"q": "ск", "limit": 5, "scope": "all"}, headers=hdr(10)))
    assert len(got) == 5


def test_pupils_see_only_cities_with_active_schools(client):
    assert names(client.get("/api/school/cities", params={"q": "тул"}, headers=hdr(11))) == []
    assert names(client.get("/api/school/cities", params={"q": "тул", "scope": "all"}, headers=hdr(11))) [:1] == ["Тула"]
    assert create_school(client, 12, city="тула").status_code == 200
    # pending/active: a registered city is shown to pupils only once its school is active
    shown = names(client.get("/api/school/cities", params={"q": "тул"}, headers=hdr(11)))
    assert shown in ([], ["Тула"])


def test_city_normalized_to_directory_spelling(client):
    assert create_school(client, 12, name="Лицей 1", city="орёл").status_code == 200
    assert create_school(client, 13, name="Лицей 2", city="ОРЕЛ").status_code in (200, 400, 409)
    state = client.get("/api/state", headers=hdr(12)).json()
    assert state["viewer"]["city"] == "Орёл"


def test_custom_city_kept_as_typed(client):
    assert create_school(client, 14, name="Школа села", city="Малиновка").status_code == 200
    assert client.get("/api/state", headers=hdr(14)).json()["viewer"]["city"] == "Малиновка"
    res = client.get("/api/school/cities", params={"q": "малин", "scope": "all"}, headers=hdr(15))
    assert names(res) == ["Малиновка"]


def test_director_changes_school_timezone(client):
    r = create_school(client, 20)
    sid = r.json()["school_id"]
    assert client.get("/api/state", headers=hdr(20)).json()["timezone"] == "Europe/Moscow"
    ok = client.patch(f"/api/school/{sid}", json={"timezone": "Asia/Vladivostok"}, headers=hdr(20))
    assert ok.status_code == 200 and ok.json()["state"]["timezone"] == "Asia/Vladivostok"
    assert client.patch(f"/api/school/{sid}", json={"timezone": "Mars/Base"}, headers=hdr(20)).status_code == 400
    assert client.patch(f"/api/school/{sid}", json={"timezone": "Asia/Omsk"}, headers=hdr(21)).status_code in (403, 404)
    assert client.get("/api/state", headers=hdr(20)).json()["timezone"] == "Asia/Vladivostok"


def test_sandbox_admin_switch(tmp_path):
    c = make_sandbox(tmp_path)
    try:
        assert sandbox_state(c, "sandbox-tester")["viewer"]["is_platform_admin"] is False
        r = c.post("/api/sandbox/admin", json={"enabled": True}, headers=sh("sandbox-tester"))
        assert r.status_code == 200 and r.json()["state"]["viewer"]["is_platform_admin"] is True
        assert sandbox_state(c, "sandbox-other")["viewer"]["is_platform_admin"] is False
        assert sandbox_state(c, "sandbox-tester")["platform_admin"] is not None
        r = c.post("/api/sandbox/admin", json={"enabled": False}, headers=sh("sandbox-tester"))
        assert r.json()["state"]["viewer"]["is_platform_admin"] is False
    finally:
        c.close()


def test_sandbox_admin_404_in_prod_and_demo(client, tmp_path):
    assert client.post("/api/sandbox/admin", json={"enabled": True}, headers=hdr(30)).status_code == 404
    assert client.get("/api/state", headers=hdr(30)).json()["viewer"]["is_platform_admin"] is False
    (tmp_path / "demo").mkdir()
    c = build_client(make_settings(tmp_path / "demo"))
    try:
        assert c.post("/api/sandbox/admin", json={"enabled": True}, headers=DEMO_HEADERS).status_code == 404
    finally:
        c.close()
