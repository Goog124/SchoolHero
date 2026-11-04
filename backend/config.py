"""Application settings loaded from environment variables."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _ids_env(name: str) -> set[str]:
    raw = os.getenv(name, "")
    return {part.strip() for part in raw.split(",") if part.strip()}


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    base_dir: Path = BASE_DIR
    static_dir: Path = BASE_DIR / "static"
    db_path: Path = BASE_DIR / "data" / "school_hero.db"
    bot_token: str = ""
    init_data_max_age: int = 86400
    teacher_max_ids: set[str] = field(default_factory=set)
    director_max_ids: set[str] = field(default_factory=set)
    default_class_id: int | None = None
    serve_frontend: bool = False
    app_mode: str = "prod"  # prod | demo | sandbox
    host: str = "127.0.0.1"
    sandbox_wipe: bool = False
    platform_admin_client_ids: set[str] = field(default_factory=set)
    catalog_file: Path = BASE_DIR / "data" / "catalog.json"
    school_approval: str = "auto"  # auto | manual
    platform_admin_max_ids: set[str] = field(default_factory=set)
    max_schools_per_user: int = 3
    # MAX bot (webhook + приветствие)
    max_api_base: str = "https://platform-api2.max.ru"
    max_webhook_secret: str = ""
    max_bot_username: str = ""
    max_ca_bundle: str = ""
    public_url: str = "https://m.ospab.org"
    bot_reply_interval: int = 60

    @property
    def demo_mode(self) -> bool:
        return self.app_mode == "demo"

    @property
    def sandbox_mode(self) -> bool:
        return self.app_mode == "sandbox"

    def validate(self) -> None:
        """Fail at startup instead of running half-configured."""
        if self.app_mode not in {"prod", "demo", "sandbox"}:
            raise RuntimeError("APP_MODE должен быть 'prod', 'demo' или 'sandbox'")
        if self.sandbox_mode and self.host.strip().lower() not in LOOPBACK_HOSTS:
            raise RuntimeError(
                "APP_MODE=sandbox входит без подписи MAX и запускается только на "
                "127.0.0.1, localhost или ::1 (сейчас HOST=" + self.host + ")"
            )
        if self.school_approval not in {"auto", "manual"}:
            raise RuntimeError("SCHOOL_APPROVAL должен быть 'auto' или 'manual'")
        if self.max_webhook_secret and not re.fullmatch(
            r"[A-Za-z0-9_-]{5,256}", self.max_webhook_secret
        ):
            raise RuntimeError(
                "MAX_WEBHOOK_SECRET: 5-256 символов, только латиница, цифры, - и _"
            )
        if self.app_mode == "prod" and not self.bot_token:
            raise RuntimeError("APP_MODE=prod требует MAX_BOT_TOKEN")

    @classmethod
    def from_env(cls) -> "Settings":
        app_mode = os.getenv("APP_MODE", "prod").strip().lower()
        data_dir = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
        db_name = {
            "demo": "school_hero_demo.db",
            "sandbox": "school_hero_sandbox.db",
        }.get(app_mode, "school_hero.db")
        db_path = Path(os.getenv("DATABASE_PATH", str(data_dir / db_name)))
        return cls(
            app_mode=app_mode,
            host=os.getenv("HOST", "127.0.0.1").strip() or "127.0.0.1",
            sandbox_wipe=_bool_env("SANDBOX_WIPE", False),
            platform_admin_client_ids=_ids_env("PLATFORM_ADMIN_CLIENT_IDS"),
            catalog_file=Path(os.getenv("CATALOG_FILE", str(data_dir / "catalog.json"))),
            static_dir=Path(os.getenv("STATIC_DIR", str(BASE_DIR / "static"))),
            db_path=db_path,
            bot_token=os.getenv("MAX_BOT_TOKEN", "").strip(),
            init_data_max_age=_int_env("INIT_DATA_MAX_AGE", 86400),
            teacher_max_ids=_ids_env("TEACHER_MAX_IDS"),
            director_max_ids=_ids_env("DIRECTOR_MAX_IDS"),
            # In prod a new user has no class until they pick one; the default
            # class exists only for the demo (or when set explicitly).
            default_class_id=(
                None
                if app_mode == "sandbox"
                else _int_env("DEFAULT_CLASS_ID", 1 if app_mode == "demo" else 0) or None
            ),
            school_approval=os.getenv("SCHOOL_APPROVAL", "auto").strip().lower() or "auto",
            platform_admin_max_ids=_ids_env("PLATFORM_ADMIN_MAX_IDS"),
            serve_frontend=_bool_env("SERVE_FRONTEND", False),
            max_api_base=(
                os.getenv("MAX_API_BASE", "").strip().rstrip("/")
                or "https://platform-api2.max.ru"
            ),
            max_webhook_secret=os.getenv("MAX_WEBHOOK_SECRET", "").strip(),
            max_bot_username=os.getenv("MAX_BOT_USERNAME", "").strip().lstrip("@"),
            max_ca_bundle=os.getenv("MAX_CA_BUNDLE", "").strip(),
            public_url=(
                os.getenv("PUBLIC_URL", "").strip().rstrip("/")
                or os.getenv("MINIAPP_URL", "").strip().rstrip("/")
                or "https://m.ospab.org"
            ),
            bot_reply_interval=_int_env("BOT_REPLY_INTERVAL", 60),
        )
