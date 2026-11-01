"""Application settings loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _ids_env(name: str) -> set[str]:
    raw = os.getenv(name, "")
    return {part.strip() for part in raw.split(",") if part.strip()}


@dataclass(frozen=True)
class Settings:
    base_dir: Path = BASE_DIR
    static_dir: Path = BASE_DIR / "static"
    db_path: Path = BASE_DIR / "data" / "school_hero.db"
    bot_token: str = ""
    init_data_max_age: int = 3600
    teacher_max_ids: set[str] = field(default_factory=set)
    default_class_id: int = 1

    @property
    def demo_mode(self) -> bool:
        return not self.bot_token

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
        db_path = Path(os.getenv("DATABASE_PATH", str(data_dir / "school_hero.db")))
        return cls(
            static_dir=Path(os.getenv("STATIC_DIR", str(BASE_DIR / "static"))),
            db_path=db_path,
            bot_token=os.getenv("MAX_BOT_TOKEN", "").strip(),
            init_data_max_age=_int_env("INIT_DATA_MAX_AGE", 3600),
            teacher_max_ids=_ids_env("TEACHER_MAX_IDS"),
            default_class_id=_int_env("DEFAULT_CLASS_ID", 1),
        )
