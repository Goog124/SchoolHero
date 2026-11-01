"""Shared fixtures for backend tests.

Every test gets a throwaway SQLite database, so the seeded demo data and the
real ``data/school_hero.db`` are never touched.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app  # noqa: E402
from backend.config import Settings  # noqa: E402
from backend.db import connect, init_db  # noqa: E402
from backend.seed import seed_database  # noqa: E402

DEMO_HEADERS = {"X-Client-Id": "demo-test-client"}
MAX_TOKEN = "test-bot-token"


def make_settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "base_dir": ROOT,
        "static_dir": ROOT / "static",
        "db_path": tmp_path / "test.db",
        "bot_token": "",
        "init_data_max_age": 3600,
        "teacher_max_ids": set(),
        "default_class_id": 1,
    }
    values.update(overrides)
    return Settings(**values)


def build_client(settings: Settings) -> TestClient:
    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        seed_database(conn)
    finally:
        conn.close()
    # TestClient only runs the app lifespan when used as a context manager.
    # We seed explicitly above so the module-level demo database is untouched.
    app.state.settings = settings
    return TestClient(app)


@pytest.fixture
def demo_settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def demo_client(demo_settings: Settings):
    client = build_client(demo_settings)
    yield client
    client.close()


@pytest.fixture
def max_settings(tmp_path: Path) -> Settings:
    return make_settings(
        tmp_path,
        bot_token=MAX_TOKEN,
        teacher_max_ids={"9001"},
    )


@pytest.fixture
def max_client(max_settings: Settings):
    client = build_client(max_settings)
    yield client
    client.close()


def get_state(client: TestClient) -> dict:
    response = client.get("/api/state", headers=DEMO_HEADERS)
    assert response.status_code == 200, response.text
    return response.json()


def challenge_by_title(state: dict, title: str) -> dict:
    return next(item for item in state["challenges"] if item["title"] == title)
