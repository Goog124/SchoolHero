"""Start the sandbox: empty database on every run, loopback only, no Docker.

    npm run sandbox            (from the project root)
    python tools/run_sandbox.py

Environment: PORT (default 8010), SANDBOX_KEEP_DATA=1 keeps the database,
SCHOOL_APPROVAL=manual and PLATFORM_ADMIN_CLIENT_IDS=<ids> to try moderation.
Serves the built frontend from static/ (run `npm run build` in frontend/ first).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def venv_python() -> str:
    for rel in (".venv/Scripts/python.exe", ".venv/bin/python"):
        candidate = ROOT / rel
        if candidate.is_file():
            return str(candidate)
    return sys.executable


def main() -> int:
    env = dict(os.environ)
    env.update({"APP_MODE": "sandbox", "HOST": "127.0.0.1", "SERVE_FRONTEND": "1"})
    env.setdefault("PORT", "8010")
    print(f"Sandbox: http://127.0.0.1:{env['PORT']}/  (database is wiped on every start)")
    return subprocess.call([venv_python(), str(ROOT / "app.py")], cwd=ROOT, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
