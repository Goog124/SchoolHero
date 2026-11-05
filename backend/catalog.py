"""Production catalog: schools, classes and teacher assignments.

The catalog is plain JSON owned by the operator (``CATALOG_FILE``). It is
applied idempotently on every start, so adding a class means editing the file
and restarting the service. ``invite_code`` is used only when a class is
created; codes of existing classes are managed in the app (re-issue) and are
not overwritten by the file. No users, scores or challenges are ever created
from it.

Format::

    {
      "schools": [
        {
          "name": "Гимназия №1",
          "city": "Москва",
          "classes": [
            {"name": "8А", "invite_code": "GYM1-8A", "weekly_goal": 1600,
             "teacher_max_ids": ["123456"]}
          ]
        }
      ]
    }
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .db import school_key


class CatalogError(RuntimeError):
    pass


def _load(path: Path) -> list[dict]:
    if not path.is_file():
        raise CatalogError(
            f"Не найден файл каталога школ: {path}. "
            "Создайте его по образцу catalog.example.json."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CatalogError(f"{path}: некорректный JSON: {exc}") from exc
    schools = data.get("schools") if isinstance(data, dict) else None
    if not isinstance(schools, list) or not schools:
        raise CatalogError(f"{path}: нужен непустой список schools")
    return schools


def import_catalog(conn: sqlite3.Connection, path: Path) -> bool:
    """Apply the optional catalog. Returns False when there is no file."""
    if not path.is_file():
        return False
    schools = _load(path)
    seen_codes: set[str] = set()
    for school in schools:
        name = str(school.get("name", "")).strip()
        city = str(school.get("city", "")).strip()
        classes = school.get("classes") or []
        if not name or not city or not classes:
            raise CatalogError("Каждая школа должна иметь name, city и classes")
        conn.execute(
            "INSERT INTO schools (name, city, norm_key, created_at) "
            "VALUES (?, ?, ?, datetime('now')) ON CONFLICT(name, city) DO NOTHING",
            (name, city, school_key(name, city)),
        )
        school_id = conn.execute(
            "SELECT id FROM schools WHERE name = ? AND city = ?", (name, city)
        ).fetchone()["id"]
        for item in classes:
            class_name = str(item.get("name", "")).strip()
            code = "".join(str(item.get("invite_code", "")).upper().split())
            goal = int(item.get("weekly_goal", 1600))
            if not class_name or not code:
                raise CatalogError(f"{name}: у класса нужны name и invite_code")
            if code in seen_codes:
                raise CatalogError(f"Повторяющийся invite_code: {code}")
            seen_codes.add(code)
            conn.execute(
                "INSERT INTO classes (school_id, name, weekly_goal, invite_code) "
                "VALUES (?, ?, ?, ?) "
                # The code is set only when the class is created: a code the
                # director re-issued in the app must survive a restart.
                "ON CONFLICT(school_id, name) DO UPDATE SET "
                "weekly_goal = excluded.weekly_goal",
                (school_id, class_name, goal, code),
            )
            class_id = conn.execute(
                "SELECT id FROM classes WHERE school_id = ? AND name = ?",
                (school_id, class_name),
            ).fetchone()["id"]
            for max_id in item.get("teacher_max_ids") or []:
                conn.execute(
                    "INSERT INTO class_staff (max_user_id, class_id) VALUES (?, ?) "
                    "ON CONFLICT(max_user_id) DO UPDATE SET class_id = excluded.class_id",
                    (str(max_id).strip(), class_id),
                )
    conn.commit()
    return True
