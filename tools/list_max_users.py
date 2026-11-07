r"""Список пользователей MAX, известных приложению.

Каждый, кто открыл мини-приложение в MAX, сохраняется с числовым MAX id.
По этому списку удобно заполнить PLATFORM_ADMIN_MAX_IDS (администраторы
платформы), DIRECTOR_MAX_IDS или TEACHER_MAX_IDS в .env.

Запуск из корня проекта:

    .\.venv\Scripts\python.exe tools\list_max_users.py          (Windows)
    .venv/bin/python tools/list_max_users.py                    (Linux)
    docker compose exec app python tools/list_max_users.py      (Docker)

База берётся из настроек (.env, APP_MODE, DATABASE_PATH). Другую базу можно
указать явно: --db путь/к/school_hero.db. Поиск по имени, username или id:
--find текст.
"""

from __future__ import annotations

import argparse
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

ROLE_LABELS = {"student": "ученик", "teacher": "педагог", "director": "директор"}


def _fix_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def main() -> int:
    _fix_console_encoding()
    parser = argparse.ArgumentParser(description="Список пользователей MAX")
    parser.add_argument("--db", help="путь к базе (по умолчанию из настроек)")
    parser.add_argument("--find", help="подстрока имени, username или MAX id")
    args = parser.parse_args()

    settings = Settings.from_env()
    db_path = Path(args.db) if args.db else settings.db_path
    if not db_path.is_absolute():
        db_path = (Path.cwd() if args.db else settings.base_dir) / db_path

    if not db_path.is_file():
        print(f"База не найдена: {db_path}")
        if not args.db:
            print(f"Режим из настроек: APP_MODE={settings.app_mode}. "
                  "Укажите боевую базу явно: --db путь/к/school_hero.db")
        return 1

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    # LIKE в SQLite не учитывает регистр только для латиницы; для кириллицы сравниваем через casefold.
    conn.create_function("cf", 1, lambda v: str(v).casefold() if v is not None else "", deterministic=True)
    try:
        cols = _columns(conn, "users")
        admin_expr = "u.platform_admin" if "platform_admin" in cols else "0"
        blocked_expr = "u.blocked_at" if "blocked_at" in cols else "NULL"
        # Школа: у ученика и педагога — через класс, у директора — через school_staff.
        has_staff = "school_staff" in {
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        director_school = (
            "(SELECT s2.name FROM school_staff ss JOIN schools s2 ON s2.id = ss.school_id "
            "WHERE ss.user_id = u.id ORDER BY ss.school_id LIMIT 1)"
            if has_staff
            else "NULL"
        )
        where = "u.max_user_id IS NOT NULL AND u.max_user_id != ''"
        params: list[str] = []
        if args.find:
            where += (
                " AND (instr(cf(u.first_name || ' ' || u.last_name), ?) > 0 "
                "OR instr(cf(u.username), ?) > 0 OR instr(cf(u.max_user_id), ?) > 0)"
            )
            params = [args.find.casefold()] * 3
        rows = conn.execute(
            f"""
            SELECT u.max_user_id, u.first_name, u.last_name, u.username, u.role,
                   {admin_expr} AS is_admin, {blocked_expr} AS blocked_at,
                   c.name AS class_name,
                   COALESCE(s.name, {director_school}) AS school_name
            FROM users u
            LEFT JOIN classes c ON c.id = u.class_id
            LEFT JOIN schools s ON s.id = c.school_id
            WHERE {where}
            ORDER BY CASE u.role WHEN 'director' THEN 0 WHEN 'teacher' THEN 1 ELSE 2 END,
                     u.first_name, u.last_name
            """,
            params,
        ).fetchall()
    finally:
        conn.close()

    env_admins = settings.platform_admin_max_ids
    print(f"База: {db_path}")
    if not rows:
        print("MAX-пользователей пока нет." if not args.find else "Никого не нашлось.")
        if not args.db and settings.app_mode != "prod":
            print(f"Сейчас APP_MODE={settings.app_mode}: в этой базе нет пользователей MAX. "
                  "Укажите боевую базу: --db путь/к/school_hero.db")
        else:
            print("Откройте мини-приложение в MAX под нужным аккаунтом и повторите.")
        return 1

    print(f"Пользователей MAX: {len(rows)}\n")
    print(f"{'MAX user id':>14}  {'Имя':<26} {'username':<16} {'роль':<9} {'школа / класс':<28} отметки")
    print("-" * 110)
    for max_user_id, first, last, username, role, is_admin, blocked_at, class_name, school_name in rows:
        name = " ".join(part for part in (first, last) if part)
        place = " / ".join(part for part in (school_name, class_name) if part) or "—"
        marks = []
        if str(max_user_id) in env_admins:
            marks.append("админ (из настроек)")
        elif is_admin:
            marks.append("админ")
        if blocked_at:
            marks.append("заблокирован")
        print(
            f"{max_user_id:>14}  {name[:26]:<26} {(username or '—')[:16]:<16} "
            f"{ROLE_LABELS.get(role, role):<9} {place[:28]:<28} {', '.join(marks)}"
        )

    print("\nЧтобы назначить роль по id, впишите его в .env (несколько — через запятую):")
    print("  PLATFORM_ADMIN_MAX_IDS=…   администратор платформы")
    print("  DIRECTOR_MAX_IDS=…         директор")
    print("  TEACHER_MAX_IDS=…          педагог (обычно проще дать код педагога класса)")
    print("Затем перезапустите сервер, а пользователь откроет приложение заново.")
    print("Администратором можно сделать и без перезапуска: вкладка «Люди» у другого администратора.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
