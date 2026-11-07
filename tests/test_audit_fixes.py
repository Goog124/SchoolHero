"""Regression tests for the backend audit fixes: concurrency, atomicity,
validation, limits, class-scoped counters, configuration and headers."""

from __future__ import annotations

import json
import threading
import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

import backend.service as svc
from app import app
from backend.catalog import import_catalog
from backend.config import Settings
from backend.db import connect, init_db
from backend.game import current_streak, today_local, utc_sql, now_local
from backend.security import AuthError, validate_init_data
from conftest import make_settings

ADMIN = "admin-000001"
DIRECTOR = "dir-0000001"
TEACHER = "tch-0000001"
STUDENT = "stu-0000001"
STUDENT2 = "stu-0000002"


def h(cid: str) -> dict:
    return {"X-Client-Id": cid}


@pytest.fixture
def env(tmp_path):
    settings = make_settings(
        tmp_path, app_mode="sandbox", default_class_id=None,
        platform_admin_client_ids={ADMIN},
    )
    init_db(settings.db_path)
    app.state.settings = settings
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post(
        "/api/school/create", headers=h(DIRECTOR),
        json={"name": "Школа аудита", "city": "Тула", "classes": [{"name": "7А"}, {"name": "7Б"}]},
    )
    assert r.status_code == 200, r.text
    classes = {
        c["name"]: c
        for c in client.get("/api/state", headers=h(DIRECTOR)).json()["school_admin"]["schools"][0]["classes"]
    }
    assert client.post("/api/school/join", headers=h(TEACHER),
                       json={"invite_code": classes["7А"]["teacher_code"]}).status_code == 200
    for sid in (STUDENT, STUDENT2):
        assert client.post("/api/onboarding", headers=h(sid), json={
            "first_name": "Гоша", "avatar": {}, "invite_code": classes["7А"]["invite_code"],
        }).status_code == 200
    yield {"c": client, "s": settings, "classes": classes, "school_id": r.json()["school_id"]}
    client.close()


def state(c, cid):
    r = c.get("/api/state", headers=h(cid))
    assert r.status_code == 200, r.text
    return r.json()


def new_challenge(c, title="Задание", xp=100, proof_type="text", **extra):
    r = c.post("/api/challenges", headers=h(TEACHER), json={
        "title": title, "category": "homework", "xp": xp, "kind": "daily",
        "proof_type": proof_type, **extra,
    })
    assert r.status_code == 200, r.text
    return next(x for x in state(c, STUDENT)["challenges"] if x["title"] == title)["id"]


def submit(c, ch, cid=STUDENT, proof="Сделал всё", url=""):
    return c.post(f"/api/challenges/{ch}/submit", headers=h(cid), json={"proof": proof, "proof_url": url})


def pending_id(c, cid=STUDENT):
    uid = state(c, cid)["viewer"]["id"]
    return next(p["id"] for p in state(c, TEACHER)["teacher"]["pending"] if p["student_id"] == uid)


def db(env):
    return connect(env["s"].db_path)


# --- 1. connection used across threads -------------------------------------


def test_request_connection_survives_thread_switch(env):
    """FastAPI may open the dependency in one worker thread and run the
    endpoint in another; that must not raise ProgrammingError."""
    from starlette.requests import Request

    from backend.api import _context

    scope = {"type": "http", "app": app, "headers": [], "method": "GET", "path": "/"}
    cm = _context(Request(scope), None, STUDENT)
    ctx = cm.__enter__()
    errors = []

    def use():
        try:
            svc.build_state(ctx.conn, ctx.user, ctx.settings)
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)

    t = threading.Thread(target=use)
    t.start(); t.join()
    closer = threading.Thread(target=lambda: cm.__exit__(None, None, None))
    closer.start(); closer.join()
    assert errors == []


def test_parallel_requests_do_not_fail(env):
    c = env["c"]
    ch = new_challenge(c)
    results = []

    def worker(i):
        if i % 2:
            results.append(c.get("/api/state", headers=h(STUDENT)).status_code)
        else:
            results.append(submit(c, ch).status_code)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(30)]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert 500 not in results
    assert results.count(200) >= 15


# --- 2. races and atomicity ---------------------------------------------------


def _two_threads(fn):
    out = []
    ths = [threading.Thread(target=lambda: out.append(fn())) for _ in range(2)]
    [t.start() for t in ths]; [t.join() for t in ths]
    return out


def test_parallel_approve_awards_once(env, monkeypatch):
    c, s = env["c"], env["s"]
    ch = new_challenge(c, xp=100)
    assert submit(c, ch).status_code == 200
    cid = pending_id(c)
    xp0 = state(c, STUDENT)["viewer"]["xp"]
    orig = svc.can_manage_class

    def slow(*a, **kw):
        r = orig(*a, **kw)
        time.sleep(0.2)
        return r

    monkeypatch.setattr(svc, "can_manage_class", slow)

    def approve():
        conn = connect(s.db_path)
        try:
            teacher = conn.execute("SELECT * FROM users WHERE client_id = ?", (TEACHER,)).fetchone()
            try:
                svc.review_completion(conn, teacher, s, cid, "approve", "")
                conn.commit()
                return "ok"
            except svc.GameError as exc:
                return exc.message
        finally:
            conn.close()

    res = _two_threads(approve)
    assert res.count("ok") == 1, res
    conn = db(env)
    try:
        uid = state(c, STUDENT)["viewer"]["id"]
        assert conn.execute("SELECT COUNT(*) FROM xp_events WHERE user_id = ?", (uid,)).fetchone()[0] == 1
    finally:
        conn.close()
    assert state(c, STUDENT)["viewer"]["xp"] == xp0 + 100


def test_parallel_buy_charges_once(env):
    c, s = env["c"], env["s"]
    conn = db(env)
    conn.execute("UPDATE users SET sparks = 45 WHERE client_id = ?", (STUDENT,))
    conn.commit(); conn.close()

    def buy():
        cn = connect(s.db_path)
        try:
            viewer = cn.execute("SELECT * FROM users WHERE client_id = ?", (STUDENT,)).fetchone()
            time.sleep(0.1)
            try:
                svc.buy_item(cn, viewer, "bowtie")  # 30 sparks
                return "ok"
            except svc.GameError as exc:
                return exc.message
        finally:
            cn.close()

    res = _two_threads(buy)
    assert res.count("ok") == 1, res
    v = state(c, STUDENT)["viewer"]
    assert v["sparks"] == 15 and "bowtie" in v["owned"]


def test_parallel_awards_lose_no_update(env):
    s = env["s"]
    conn = db(env)
    uid = conn.execute("SELECT id FROM users WHERE client_id = ?", (STUDENT,)).fetchone()[0]
    xp0 = conn.execute("SELECT xp FROM users WHERE id = ?", (uid,)).fetchone()[0]
    conn.close()

    def award():
        cn = connect(s.db_path)
        try:
            from backend.db import immediate
            from backend.game import award_xp
            with immediate(cn):
                award_xp(cn, uid, 10, "тест", "homework")
        finally:
            cn.close()

    ths = [threading.Thread(target=award) for _ in range(8)]
    [t.start() for t in ths]; [t.join() for t in ths]
    conn = db(env)
    assert conn.execute("SELECT xp FROM users WHERE id = ?", (uid,)).fetchone()[0] == xp0 + 80
    conn.close()


def test_double_submit_is_400_not_500(env):
    c = env["c"]
    ch = new_challenge(c)
    assert submit(c, ch).status_code == 200
    again = submit(c, ch)
    assert again.status_code == 400 and "на проверке" in again.json()["detail"]


# --- 3. deleting a class ------------------------------------------------------


def test_delete_class_with_exclusions_and_with_history(env):
    c = env["c"]
    b = env["classes"]["7Б"]
    sid = state(c, STUDENT2)["viewer"]["id"]
    assert c.post("/api/school/join", headers=h(STUDENT2), json={"invite_code": b["invite_code"]}).status_code == 200
    assert c.post(f"/api/teacher/students/{sid}/remove", headers=h(DIRECTOR), json={}).status_code == 200
    r = c.delete(f"/api/school/classes/{b['id']}", headers=h(DIRECTOR))
    assert r.status_code == 200, r.text  # exclusions go with the class
    a = env["classes"]["7А"]
    new_challenge(c)
    r = c.delete(f"/api/school/classes/{a['id']}", headers=h(DIRECTOR))
    assert r.status_code == 400 and "удалить его нельзя" in r.json()["detail"]


# --- 4. submission validation and expired rework ------------------------------


def test_submission_validation(env):
    c = env["c"]
    text_ch = new_challenge(c, "Текст")
    link_ch = new_challenge(c, "Ссылка", proof_type="link")
    assert submit(c, text_ch, proof="  ").status_code == 400
    assert submit(c, text_ch, proof="ok").status_code == 400
    assert submit(c, text_ch, proof="x" * 1001).status_code == 400
    assert submit(c, text_ch, url="javascript:alert(1)").status_code == 400
    assert submit(c, text_ch, url="https://" + "a" * 500).status_code == 400
    r = submit(c, link_ch)
    assert r.status_code == 400 and "ссылка" in r.json()["detail"]
    assert submit(c, link_ch, url="https://example.org/work").status_code == 200
    assert submit(c, text_ch, proof="  нормально  ").status_code == 200


def test_rejected_work_after_deadline_is_expired(env):
    c = env["c"]
    ch = new_challenge(c)
    submit(c, ch)
    c.post(f"/api/reviews/{pending_id(c)}", headers=h(TEACHER), json={"action": "reject", "reason": "Нет фото"})
    item = next(x for x in state(c, STUDENT)["challenges"] if x["id"] == ch)
    assert item["status"] == "rejected"
    conn = db(env)
    conn.execute("UPDATE challenges SET deadline = ? WHERE id = ?",
                 ((now_local() - timedelta(hours=1)).isoformat(), ch))
    conn.commit(); conn.close()
    item = next(x for x in state(c, STUDENT)["challenges"] if x["id"] == ch)
    assert item["status"] == "expired" and item["reject_reason"] == "Нет фото"
    assert submit(c, ch).status_code == 400


# --- 5. batch review ---------------------------------------------------------


def test_batch_review_counts_and_errors(env):
    c = env["c"]
    ch = new_challenge(c)
    submit(c, ch)
    pid = pending_id(c)
    assert c.post("/api/reviews/batch", headers=h(TEACHER),
                  json={"completion_ids": [pid], "action": "foo"}).status_code == 422
    r = c.post("/api/reviews/batch", headers=h(TEACHER),
               json={"completion_ids": [pid, pid, 99999], "action": "approve"})
    assert r.status_code == 200, r.text
    res = r.json()["result"]
    assert res["counts"] == {"approved": 1, "rejected": 0, "failed": 1}
    assert res["errors"] == [{"id": 99999, "detail": "Заявка не найдена", "status": 404}]


# --- 6. streak ---------------------------------------------------------------


def test_streak_breaks_after_missed_day_and_staff_actions_do_not_count(env):
    c = env["c"]
    today = today_local()
    assert current_streak(5, today.isoformat()) == 5
    assert current_streak(5, (today - timedelta(days=1)).isoformat()) == 5
    assert current_streak(5, (today - timedelta(days=2)).isoformat()) == 0
    conn = db(env)
    conn.execute("UPDATE users SET streak = 5, last_active_date = ? WHERE client_id = ?",
                 ((today - timedelta(days=3)).isoformat(), STUDENT))
    conn.commit(); conn.close()
    assert state(c, STUDENT)["viewer"]["streak"] == 0
    sid = state(c, STUDENT)["viewer"]["id"]
    assert c.post("/api/teacher/reward", headers=h(TEACHER),
                  json={"student_id": sid, "amount": 50, "reason": "На уроке"}).status_code == 200
    assert state(c, STUDENT)["viewer"]["streak"] == 0  # reward is not the student's activity
    submit(c, new_challenge(c))
    assert state(c, STUDENT)["viewer"]["streak"] == 1


# --- 7. manual XP limits, own work -------------------------------------------


def test_manual_reward_limits_and_reason(env):
    c = env["c"]
    sid = state(c, STUDENT)["viewer"]["id"]
    body = {"student_id": sid, "amount": 300, "reason": "Олимпиада"}
    assert c.post("/api/teacher/reward", headers=h(TEACHER),
                  json={"student_id": sid, "amount": 50}).status_code == 422
    assert c.post("/api/teacher/reward", headers=h(TEACHER),
                  json={**body, "reason": "   "}).status_code in {400, 422}
    assert c.post("/api/teacher/reward", headers=h(TEACHER), json=body).status_code == 200
    r = c.post("/api/teacher/reward", headers=h(DIRECTOR), json={**body, "amount": 10})
    assert r.status_code == 400 and "300 XP в день" in r.json()["detail"]
    # teacher's own daily cap
    monkey = svc.MANUAL_XP_PER_TEACHER_DAY
    svc.MANUAL_XP_PER_TEACHER_DAY = 350
    try:
        sid2 = state(c, STUDENT2)["viewer"]["id"]
        r = c.post("/api/teacher/reward", headers=h(TEACHER), json={"student_id": sid2, "amount": 100, "reason": "Ещё"})
        assert r.status_code == 400 and "педагога" in r.json()["detail"]
    finally:
        svc.MANUAL_XP_PER_TEACHER_DAY = monkey


def test_staff_cannot_review_own_or_staff_work(env):
    c = env["c"]
    ch = new_challenge(c)
    conn = db(env)
    tid = conn.execute("SELECT id FROM users WHERE client_id = ?", (TEACHER,)).fetchone()[0]
    did = conn.execute("SELECT id FROM users WHERE client_id = ?", (DIRECTOR,)).fetchone()[0]
    cur = conn.execute("INSERT INTO completions (user_id, challenge_id, status, proof) VALUES (?, ?, 'pending', 'моя')", (tid, ch))
    own = cur.lastrowid
    conn.commit(); conn.close()
    r = c.post(f"/api/reviews/{own}", headers=h(TEACHER), json={"action": "approve"})
    assert r.status_code == 403 and "собственную" in r.json()["detail"]
    r = c.post(f"/api/reviews/{own}", headers=h(DIRECTOR), json={"action": "approve"})
    assert r.status_code == 403 and "учеников" in r.json()["detail"]
    assert did


# --- 8. counters after a class change ----------------------------------------


def test_class_change_keeps_xp_out_of_new_class_rating(env):
    c = env["c"]
    a, b = env["classes"]["7А"], env["classes"]["7Б"]
    ch = new_challenge(c, xp=100)
    submit(c, ch)
    c.post(f"/api/reviews/{pending_id(c)}", headers=h(TEACHER), json={"action": "approve"})
    ch2 = new_challenge(c, "Второе")
    submit(c, ch2)  # pending in 7А
    assert c.post("/api/school/join", headers=h(STUDENT), json={"invite_code": b["invite_code"]}).status_code == 200
    v = state(c, STUDENT)
    assert v["viewer"]["xp"] >= 100  # XP stays with the student
    assert v["viewer"]["stats"]["pending"] == 0  # 7А work is not pending in 7Б
    classes = {e["id"]: e for e in v["leaderboard"]["classes"]}
    assert classes[b["id"]]["xp"] == 0 and classes[b["id"]]["weekly_xp"] == 0
    assert classes[a["id"]]["xp"] == 100
    assert v["viewer"]["weekly_xp"] == 0


def test_archived_task_pending_is_shown_and_counted(env):
    c = env["c"]
    ch = new_challenge(c)
    submit(c, ch)
    assert c.post(f"/api/challenges/{ch}/archive", headers=h(TEACHER)).status_code == 200
    t = state(c, TEACHER)["teacher"]
    sid = state(c, STUDENT)["viewer"]["id"]
    assert len(t["pending"]) == 1
    assert next(s for s in t["students"] if s["id"] == sid)["pending_count"] == 1


def test_migration_adds_class_id_to_events(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    init_db(path)
    raw = sqlite3.connect(path)
    raw.executescript(
        "DROP TABLE xp_events;"
        "CREATE TABLE xp_events (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, amount INTEGER NOT NULL, reason TEXT NOT NULL, category TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')));"
        "INSERT INTO schools (id, name, city) VALUES (1, 'Ш', 'Г');"
        "INSERT INTO classes (id, school_id, name) VALUES (7, 1, '7А');"
        "INSERT INTO users (id, class_id, first_name, avatar) VALUES (1, 7, 'И', '{}');"
        "INSERT INTO xp_events (user_id, amount, reason) VALUES (1, 20, 'x');"
    )
    raw.commit(); raw.close()
    init_db(path)
    conn = connect(path)
    try:
        row = conn.execute("SELECT class_id, source FROM xp_events").fetchone()
        assert row["class_id"] == 7 and row["source"] is None
    finally:
        conn.close()


# --- 9. low-level security and configuration ---------------------------------


def test_non_ascii_hash_is_auth_error():
    with pytest.raises(AuthError):
        validate_init_data("auth_date=1&hash=ффф", "token", 3600)
    with pytest.raises(AuthError):
        validate_init_data("auth_date=1&hash=" + "é" * 64, "token", 3600)


def test_non_ascii_hash_over_http_is_401(tmp_path):
    settings = make_settings(tmp_path, app_mode="prod", bot_token="t")
    init_db(settings.db_path)
    app.state.settings = settings
    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/api/state", headers={"X-Max-Init-Data": "auth_date=1&hash=%D0%B9"})
    assert r.status_code == 401
    c.close()


def test_huge_ids_are_422(env):
    c = env["c"]
    big = 99999999999999999999999
    assert c.post(f"/api/challenges/{big}/submit", headers=h(STUDENT), json={"proof": "abc"}).status_code == 422
    assert c.post(f"/api/reviews/{big}", headers=h(TEACHER), json={"action": "approve"}).status_code == 422
    assert c.post("/api/teacher/reward", headers=h(TEACHER),
                  json={"student_id": big, "amount": 10, "reason": "abc"}).status_code == 422
    assert c.post("/api/reviews/batch", headers=h(TEACHER),
                  json={"completion_ids": [big], "action": "approve"}).status_code == 422
    assert c.get(f"/api/school/catalog?offset={big}", headers=h(STUDENT)).status_code == 422


def test_check_code_is_post(env):
    c = env["c"]
    code = env["classes"]["7А"]["invite_code"]
    r = c.post("/api/school/check-code", headers=h("someone-0001"), json={"code": code})
    assert r.status_code == 200 and r.json()["valid"] is True
    assert c.get(f"/api/school/check-code?code={code}", headers=h("someone-0001")).status_code in {404, 405}


def test_settings_validation(tmp_path):
    ok = dict(app_mode="prod", bot_token="t", db_path=tmp_path / "school_hero.db")
    Settings(**ok).validate()
    for age in (10, 86401):
        with pytest.raises(RuntimeError):
            Settings(**ok, init_data_max_age=age).validate()
    with pytest.raises(RuntimeError):
        Settings(**ok, max_webhook_secret="short-secret").validate()
    Settings(**ok, max_webhook_secret="a" * 32).validate()
    # demo: loopback only unless allowed; never the production database
    demo = dict(app_mode="demo", db_path=tmp_path / "school_hero_demo.db")
    Settings(**demo).validate()
    with pytest.raises(RuntimeError):
        Settings(**demo, host="0.0.0.0").validate()
    Settings(**demo, host="0.0.0.0", allow_public_demo=True).validate()
    for mode in ("demo", "sandbox"):
        with pytest.raises(RuntimeError):
            Settings(app_mode=mode, db_path=tmp_path / "school_hero.db").validate()
    assert Settings(app_mode="sandbox").db_path.name == "school_hero_sandbox.db"


def test_from_env_never_points_demo_at_prod_db(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "school_hero.db"))  # Docker image default
    for mode, name in (("demo", "school_hero_demo.db"), ("sandbox", "school_hero_sandbox.db"), ("prod", "school_hero.db")):
        monkeypatch.setenv("APP_MODE", mode)
        assert Settings.from_env().db_path == tmp_path / name
    monkeypatch.setenv("APP_MODE", "demo")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "school_hero_demo.db"))  # docker demo profile
    assert Settings.from_env().db_path == tmp_path / "school_hero_demo.db"


def test_catalog_restart_keeps_reissued_code(tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps({"schools": [{"name": "Кат", "city": "Тверь",
                                             "classes": [{"name": "8А", "invite_code": "GYM1-8A"}]}]}), encoding="utf-8")
    init_db(tmp_path / "c.db")
    conn = connect(tmp_path / "c.db")
    try:
        import_catalog(conn, path)
        conn.execute("UPDATE classes SET invite_code = 'NEW-CODE'"); conn.commit()
        import_catalog(conn, path)
        assert conn.execute("SELECT invite_code FROM classes").fetchone()[0] == "NEW-CODE"
    finally:
        conn.close()


# --- 11. headers --------------------------------------------------------------


def test_content_security_policy(env):
    headers = env["c"].get("/api/health").headers
    csp = headers["Content-Security-Policy"]
    for part in ("default-src 'self'", "script-src 'self' https://st.max.ru", "object-src 'none'",
                 "base-uri 'self'", "img-src 'self' data: blob: https:", "frame-ancestors 'self' https://max.ru"):
        assert part in csp
    assert "X-Frame-Options" not in headers
    assert "camera=()" in headers["Permissions-Policy"]


# --- 13. director --------------------------------------------------------------


def test_class_grade_and_empty_leading_parallel(env):
    assert svc.class_grade("10-1") == "10"
    assert svc.class_grade("11А") == "11"
    assert svc.class_grade("Спецгруппа") is None
    conn = db(env)
    conn.execute("UPDATE users SET class_id = NULL WHERE role = 'student'"); conn.commit(); conn.close()
    kpi = state(env["c"], DIRECTOR)["director"]["kpi"]
    assert kpi["total_students"] == 0 and kpi["leading_grade"] is None


# --- 14. rejected school -------------------------------------------------------


def test_rejected_school_is_read_only_until_restored(env):
    c, sid = env["c"], env["school_id"]
    a = env["classes"]["7А"]
    assert c.post(f"/api/admin/schools/{sid}/status", headers=h(ADMIN), json={"status": "rejected"}).status_code == 200
    r = c.post(f"/api/school/{sid}/classes", headers=h(DIRECTOR), json={"name": "9А"})
    assert r.status_code == 403 and "отклонена" in r.json()["detail"]
    assert c.post(f"/api/school/classes/{a['id']}/codes", headers=h(DIRECTOR), json={"kind": "student"}).status_code == 403
    assert c.post("/api/school/join", headers=h("new-student-1"), json={"invite_code": a["invite_code"]}).status_code == 404
    r = c.post("/api/challenges", headers=h(TEACHER), json={"title": "Нельзя", "category": "homework", "xp": 10, "kind": "daily"})
    assert r.status_code == 403
    assert state(c, DIRECTOR)["viewer"]["school_status"] == "rejected"
    assert c.post(f"/api/admin/schools/{sid}/status", headers=h(ADMIN), json={"status": "active"}).status_code == 200
    assert c.post(f"/api/school/{sid}/classes", headers=h(DIRECTOR), json={"name": "9А"}).status_code == 200
    assert c.post("/api/school/join", headers=h("new-student-1"), json={"invite_code": a["invite_code"]}).status_code == 200
