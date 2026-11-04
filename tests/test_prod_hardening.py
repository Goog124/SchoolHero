"""Production hardening: API docs are not published in prod."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

SCRIPT = """
import sys
from fastapi.testclient import TestClient
import app as a
c = TestClient(a.app)
print(",".join(str(c.get(p).status_code) for p in ("/docs", "/redoc", "/openapi.json", "/api/health")))
"""


def statuses(tmp_path, **env) -> list[str]:
    full = {k: v for k, v in os.environ.items() if k not in {"APP_MODE", "SERVE_FRONTEND"}}
    full.update(DATA_DIR=str(tmp_path), MAX_BOT_TOKEN="t", **env)
    out = subprocess.run(
        [sys.executable, "-c", SCRIPT], cwd=ROOT, env=full,
        capture_output=True, text=True, timeout=60, check=True,
    )
    return out.stdout.strip().splitlines()[-1].split(",")


@pytest.mark.parametrize("serve_frontend", ["false", "true"])
def test_docs_are_hidden_in_prod(tmp_path, serve_frontend):
    assert statuses(tmp_path, APP_MODE="prod", SERVE_FRONTEND=serve_frontend) == ["404", "404", "404", "200"]


@pytest.mark.parametrize("mode", ["demo", "sandbox"])
def test_docs_stay_available_outside_prod(tmp_path, mode):
    assert statuses(tmp_path, APP_MODE=mode) == ["200", "200", "200", "200"]
