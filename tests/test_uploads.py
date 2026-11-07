"""Photo proof: upload rules, access, attaching to a submission."""

from __future__ import annotations

import pytest

from backend import uploads as uploads_mod
from backend.db import connect
from test_registration import class_codes, client, create_school, hdr, onboard_student  # noqa: F401

DIRECTOR, TEACHER, OTHER_TEACHER, PUPIL, PUPIL2, STRANGER = 100, 200, 201, 1, 2, 3

JPEG = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"0" * 64
PNG = bytes([0x89]) + b"PNG\r\n\x1a\n" + b"0" * 64
WEBP = b"RIFF\x10\x00\x00\x00WEBP" + b"0" * 32


def post_photo(client, uid, data=JPEG, ctype="image/jpeg"):
    return client.post("/api/uploads", content=data, headers={**hdr(uid), "Content-Type": ctype})


@pytest.fixture
def school(client):  # noqa: F811
    create_school(client, DIRECTOR, name="Школа Фото", city="Тверь", classes=("8А", "8Б"))
    codes = class_codes(client, DIRECTOR)
    client.post("/api/school/join", json={"invite_code": codes["8А"]["teacher_code"]}, headers=hdr(TEACHER))
    client.post("/api/school/join", json={"invite_code": codes["8Б"]["teacher_code"]}, headers=hdr(OTHER_TEACHER))
    onboard_student(client, PUPIL, codes["8А"]["invite_code"])
    onboard_student(client, PUPIL2, codes["8А"]["invite_code"])
    return codes


def make_challenge(client, proof_type="photo"):
    r = client.post(
        "/api/challenges",
        json={"title": "Тетрадь", "category": "homework", "xp": 20, "kind": "daily", "proof_type": proof_type},
        headers=hdr(TEACHER),
    )
    assert r.status_code == 200, r.text
    state = client.get("/api/state", headers=hdr(PUPIL)).json()
    return next(c["id"] for c in state["challenges"] if c["title"] == "Тетрадь")


def submit(client, uid, cid, **extra):
    return client.post(
        f"/api/challenges/{cid}/submit", json={"proof": "Сделано", **extra}, headers=hdr(uid)
    )


def test_upload_ok_formats_and_file_mode(client, school):
    for data, ctype in ((JPEG, "image/jpeg"), (PNG, "image/png"), (WEBP, "image/webp")):
        r = post_photo(client, PUPIL, data, ctype)
        assert r.status_code == 200, r.text
    settings = client.app.state.settings
    files = list(settings.upload_dir.iterdir())
    assert len(files) == 3 and {f.suffix for f in files} == {".jpg", ".png", ".webp"}


def test_size_limit_413(client, school, monkeypatch):
    monkeypatch.setattr(uploads_mod, "MAX_UPLOAD_BYTES", 1000)
    r = post_photo(client, PUPIL, JPEG + b"0" * 2000)
    assert r.status_code == 413
    settings = client.app.state.settings
    assert not settings.upload_dir.exists() or not list(settings.upload_dir.iterdir())


def test_type_and_spoofing_rejected(client, school):
    assert post_photo(client, PUPIL, JPEG, "image/gif").status_code == 415
    assert post_photo(client, PUPIL, JPEG, "text/html").status_code == 415
    # PNG bytes declared as JPEG and plain text declared as an image
    assert post_photo(client, PUPIL, PNG, "image/jpeg").status_code == 415
    assert post_photo(client, PUPIL, b"<html>hello</html>", "image/png").status_code == 415
    assert post_photo(client, PUPIL, b"", "image/png").status_code == 400
    settings = client.app.state.settings
    assert not settings.upload_dir.exists() or not list(settings.upload_dir.iterdir())


def test_only_student_with_class_uploads(client, school):
    assert post_photo(client, TEACHER).status_code == 403
    assert post_photo(client, DIRECTOR).status_code == 403
    assert post_photo(client, STRANGER).status_code == 403  # no class


def test_access_rights(client, school):
    cid = make_challenge(client)
    up = post_photo(client, PUPIL).json()["id"]
    # unattached: only the author
    assert client.get(f"/api/uploads/{up}", headers=hdr(PUPIL)).status_code == 200
    assert client.get(f"/api/uploads/{up}", headers=hdr(TEACHER)).status_code == 404
    assert submit(client, PUPIL, cid, upload_id=up).status_code == 200
    ok = client.get(f"/api/uploads/{up}", headers=hdr(TEACHER))
    assert ok.status_code == 200 and ok.content == JPEG
    assert ok.headers["content-type"] == "image/jpeg"
    assert ok.headers["cache-control"] == "private, no-store"
    assert ok.headers["x-content-type-options"] == "nosniff"
    assert ok.headers["content-disposition"] == "inline"
    assert client.get(f"/api/uploads/{up}", headers=hdr(DIRECTOR)).status_code == 200
    assert client.get(f"/api/uploads/{up}", headers=hdr(PUPIL)).status_code == 200
    for outsider in (PUPIL2, OTHER_TEACHER, STRANGER):
        assert client.get(f"/api/uploads/{up}", headers=hdr(outsider)).status_code == 404
    assert client.get("/api/uploads/9999", headers=hdr(PUPIL)).status_code == 404
    # pending item for the teacher carries the id
    pending = client.get("/api/state", headers=hdr(TEACHER)).json()["teacher"]["pending"]
    assert pending[0]["upload_id"] == up


def test_photo_required_and_binding(client, school):
    cid = make_challenge(client)
    assert submit(client, PUPIL, cid).status_code == 400  # photo is required
    up = post_photo(client, PUPIL).json()["id"]
    foreign = post_photo(client, PUPIL2).json()["id"]
    assert submit(client, PUPIL, cid, upload_id=foreign).status_code == 400  # not own
    assert submit(client, PUPIL, cid, upload_id=up).status_code == 200


def test_upload_cannot_be_bound_twice(client, school):
    cid = make_challenge(client)
    up = post_photo(client, PUPIL).json()["id"]
    assert submit(client, PUPIL, cid, upload_id=up).status_code == 200
    r = client.post(
        "/api/challenges", json={"title": "Второе", "category": "homework", "xp": 20,
                                 "kind": "daily", "proof_type": "text"}, headers=hdr(TEACHER))
    assert r.status_code == 200
    state = client.get("/api/state", headers=hdr(PUPIL)).json()
    second = next(c["id"] for c in state["challenges"] if c["title"] == "Второе")
    again = submit(client, PUPIL, second, upload_id=up)
    assert again.status_code == 400
    # optional for non-photo types
    assert submit(client, PUPIL, second).status_code == 200


def test_daily_limit(client, school, monkeypatch):
    monkeypatch.setattr(uploads_mod, "MAX_UPLOADS_PER_DAY", 3)
    for _ in range(3):
        assert post_photo(client, PUPIL).status_code == 200
    assert post_photo(client, PUPIL).status_code == 429
    assert post_photo(client, PUPIL2).status_code == 200  # per student


def test_orphans_are_removed(client, school):
    up = post_photo(client, PUPIL).json()["id"]
    settings = client.app.state.settings
    conn = connect(settings.db_path)
    try:
        assert uploads_mod.cleanup_orphan_uploads(conn, settings) == 0
        conn.execute("UPDATE uploads SET created_at = datetime('now', '-2 days')")
        conn.commit()
        assert uploads_mod.cleanup_orphan_uploads(conn, settings) == 1
        assert conn.execute("SELECT COUNT(*) FROM uploads").fetchone()[0] == 0
    finally:
        conn.close()
    assert list(settings.upload_dir.iterdir()) == []
    assert up
