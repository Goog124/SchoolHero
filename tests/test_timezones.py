"""School time zones: "today", weeks, deadlines, streak days, daily limits."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend import game
from backend.db import connect, init_db
from test_registration import class_codes, client, create_school, hdr, school_body  # noqa: F401

VLAD, MSK_ZONE = "Asia/Vladivostok", "Europe/Moscow"
# Sunday 23:00 in Moscow, already Monday 06:00 in Vladivostok.
INSTANT = datetime(2026, 11, 1, 20, 0, tzinfo=timezone.utc)


@pytest.fixture
def frozen(monkeypatch):
    monkeypatch.setattr(game, "now_local", lambda tz=None: INSTANT.astimezone(game.get_tz(tz)))


def test_deadline_today_follows_school_zone(frozen):
    assert game.deadline_today(MSK_ZONE) == "2026-11-01T23:59:00+03:00"
    assert game.deadline_today(VLAD) == "2026-11-02T23:59:00+10:00"
    assert game.deadline_today() == game.deadline_today(MSK_ZONE)  # no school: Moscow
    assert game.deadline_week(VLAD) == "2026-11-08T23:59:00+10:00"
    assert game.deadline_week(MSK_ZONE) == "2026-11-01T23:59:00+03:00"


def test_week_boundary(frozen):
    assert game.week_start_local(MSK_ZONE).date().isoformat() == "2026-10-26"
    assert game.week_start_local(VLAD).date().isoformat() == "2026-11-02"
    assert game.week_start_utc_sql(VLAD) == "2026-11-01 14:00:00"
    assert game.week_start_utc_sql(MSK_ZONE) == "2026-10-25 21:00:00"
    assert [d["date"] for d in game.week_days(VLAD)][0] == "2026-11-02"


def test_daily_limit_boundary(frozen):
    assert game.day_start_utc_sql(VLAD) == "2026-11-01 14:00:00"
    assert game.day_start_utc_sql(MSK_ZONE) == "2026-10-31 21:00:00"


def test_streak_day_depends_on_zone(frozen, tmp_path):
    init_db(tmp_path / "t.db")
    conn = connect(tmp_path / "t.db")
    try:
        for uid in (1, 2):
            conn.execute(
                "INSERT INTO users (id, first_name, avatar, streak, last_active_date) "
                "VALUES (?, 'A', '{}', 1, '2026-11-01')",
                (uid,),
            )
        assert game.mark_active(conn, 1, VLAD) == 2  # it is already Nov 2 there
        assert game.mark_active(conn, 2, MSK_ZONE) == 1  # still Nov 1 in Moscow
        assert game.current_streak(1, "2026-10-30", VLAD) == 0
        assert game.current_streak(1, "2026-10-31", MSK_ZONE) == 1
    finally:
        conn.close()


def test_normalize_and_options():
    assert game.normalize_timezone("Mars/Base") == MSK_ZONE
    assert game.normalize_timezone(VLAD) == VLAD
    ids = [o["id"] for o in game.timezone_options()]
    assert VLAD in ids and MSK_ZONE in ids


def test_register_school_with_timezone_and_change(client):  # noqa: F811
    body = school_body()
    body["timezone"] = VLAD
    r = client.post("/api/school/create", json=body, headers=hdr(100))
    assert r.status_code == 200, r.text
    state = r.json()["state"]
    assert state["timezone"] == VLAD and state["today"]
    assert VLAD in [o["id"] for o in state["timezones"]]
    school = state["school_admin"]["schools"][0]
    assert school["timezone"] == VLAD

    bad = school_body(name="Другая школа")
    bad["timezone"] = "Mars/Base"
    assert client.post("/api/school/create", json=bad, headers=hdr(101)).status_code == 400
    default = client.post("/api/school/create", json=school_body(name="Третья школа"), headers=hdr(102))
    assert default.json()["state"]["timezone"] == MSK_ZONE

    sid = school["id"]
    assert client.patch(f"/api/school/{sid}", json={"timezone": "Mars/Base"}, headers=hdr(100)).status_code == 400
    assert client.patch(f"/api/school/{sid}", json={"timezone": "Asia/Omsk"}, headers=hdr(102)).status_code == 404
    changed = client.patch(f"/api/school/{sid}", json={"timezone": "Asia/Omsk"}, headers=hdr(100))
    assert changed.status_code == 200 and changed.json()["state"]["timezone"] == "Asia/Omsk"


def test_challenge_deadline_uses_school_zone(client):  # noqa: F811
    body = school_body()
    body["timezone"] = VLAD
    client.post("/api/school/create", json=body, headers=hdr(100))
    r = client.post(
        "/api/challenges",
        json={"title": "На сегодня", "category": "homework", "xp": 20, "kind": "daily",
              "class_id": class_codes(client, 100)["8А"]["id"]},
        headers=hdr(100),
    )
    assert r.status_code == 200, r.text
    challenges = client.get("/api/state", headers=hdr(100)).json()
    cid = class_codes(client, 100)["8А"]["id"]
    conn = connect(client.app.state.settings.db_path)
    try:
        deadline = conn.execute("SELECT deadline FROM challenges WHERE class_id = ?", (cid,)).fetchone()[0]
    finally:
        conn.close()
    assert deadline.endswith("T23:59:00+10:00") and deadline == game.deadline_today(VLAD)
    assert challenges
