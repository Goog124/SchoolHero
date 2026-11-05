"""Application settings loaded from environment variables."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

PROD_DB_NAME = "school_hero.db"
MODE_DB_NAMES = {
    "demo": "school_hero_demo.db",
    "sandbox": "school_hero_sandbox.db",
}
INIT_DATA_MAX_AGE_RANGE = (60, 86400)
WEBHOOK_SECRET_MIN = 32


def mode_db_path(app_mode: str, path: Path) -> Path:
    """Demo and sandbox never open the production database file.

    A path whose file name is the production one (for example the Docker
    image default ``DATABASE_PATH=/data/school_hero.db``) is replaced by the
    mode's own file in the same directory. A path set for the mode
    (``/data/school_hero_demo.db``) is kept as is.
    """
    name = MODE_DB_NAMES.get(app_mode)
    if name and path.name == PROD_DB_NAME:
        return path.with_name(name)
    return path


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
    public_url: str = ""
    bot_reply_interval: int = 60
    # demo binds only to loopback unless explicitly allowed (ALLOW_PUBLIC_DEMO=1)
    allow_public_demo: bool = False

    def __post_init__(self) -> None:
        if self.db_path == BASE_DIR / "data" / PROD_DB_NAME:
            object.__setattr__(self, "db_path", mode_db_path(self.app_mode, self.db_path))

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
        host = self.host.strip().lower()
        if self.demo_mode and host not in LOOPBACK_HOSTS and not self.allow_public_demo:
            raise RuntimeError(
                "APP_MODE=demo входит без подписи MAX и по умолчанию запускается только на "
                "127.0.0.1, localhost или ::1 (сейчас HOST=" + self.host + "). "
                "Для публичной витрины задайте ALLOW_PUBLIC_DEMO=1"
            )
        if (self.demo_mode or self.sandbox_mode) and self.db_path.name == PROD_DB_NAME:
            raise RuntimeError(
                f"APP_MODE={self.app_mode} не может работать с боевой базой "
                f"{PROD_DB_NAME} ({self.db_path}). Укажите DATABASE_PATH с файлом "
                f"{MODE_DB_NAMES[self.app_mode]}"
            )
        low, high = INIT_DATA_MAX_AGE_RANGE
        if not low <= int(self.init_data_max_age) <= high:
            raise RuntimeError(
                f"INIT_DATA_MAX_AGE: от {low} до {high} секунд (сейчас {self.init_data_max_age})"
            )
        if self.school_approval not in {"auto", "manual"}:
            raise RuntimeError("SCHOOL_APPROVAL должен быть 'auto' или 'manual'")
        if self.max_webhook_secret and not re.fullmatch(
            rf"[A-Za-z0-9_-]{{{WEBHOOK_SECRET_MIN},256}}", self.max_webhook_secret
        ):
            raise RuntimeError(
                f"MAX_WEBHOOK_SECRET: {WEBHOOK_SECRET_MIN}-256 символов, только латиница, "
                "цифры, - и _ (например: python -c \"import secrets; print(secrets.token_urlsafe(32))\")"
            )
        if self.app_mode == "prod" and not self.bot_token:
            raise RuntimeError("APP_MODE=prod требует MAX_BOT_TOKEN")

    @classmethod
    def from_env(cls) -> "Settings":
        app_mode = os.getenv("APP_MODE", "prod").strip().lower()
        data_dir = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
        db_name = MODE_DB_NAMES.get(app_mode, PROD_DB_NAME)
        raw_db = os.getenv("DATABASE_PATH", "").strip()
        db_path = mode_db_path(app_mode, Path(raw_db) if raw_db else data_dir / db_name)
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
            ),
            bot_reply_interval=_int_env("BOT_REPLY_INTERVAL", 60),
            allow_public_demo=_bool_env("ALLOW_PUBLIC_DEMO", False),
        )
