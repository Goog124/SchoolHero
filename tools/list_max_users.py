r"""List MAX users known to the app.

Every user who opens the mini app inside MAX is stored with their numeric
MAX user id. Use this list to fill TEACHER_MAX_IDS.

Usage (from the project root):

    .\.venv\Scripts\python.exe tools\list_max_users.py
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from backend.config import Settings  # noqa: E402


def main() -> int:
    settings = Settings.from_env()
    db_path = settings.db_path
    if not db_path.is_absolute():
        db_path = settings.base_dir / db_path

    if not db_path.is_file():
        print(f"База не найдена: {db_path}")
        print("Сначала запустите приложение и откройте мини-апп в MAX.")
        return 1

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT max_user_id, first_name, last_name, username, role
            FROM users
            WHERE max_user_id IS NOT NULL AND max_user_id != ''
            ORDER BY (role = 'teacher') DESC, first_name, last_name
            """
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        print(f"База: {db_path}")
        print("MAX-пользователей пока нет.")
        print("Откройте мини-приложение в MAX под нужным аккаунтом и повторите.")
        return 1

    print(f"База: {db_path}\n")
    print(f"{'MAX user id':>14}  {'Имя':<28} {'username':<18} роль")
    print("-" * 76)
    for max_user_id, first_name, last_name, username, role in rows:
        name = " ".join(part for part in (first_name, last_name) if part)
        role_label = "педагог" if role == "teacher" else "ученик"
        print(
            f"{max_user_id:>14}  {name[:28]:<28} "
            f"{(username or '—')[:18]:<18} {role_label}"
        )

    print("\nСкопируйте нужные id в .env, через запятую:")
    print("TEACHER_MAX_IDS=123456789,987654321")
    print("Затем перезапустите сервер — педагог откроет приложение заново.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
