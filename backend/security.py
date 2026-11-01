"""MAX Bridge initData validation and request identity.

The browser value ``window.WebApp.initDataUnsafe`` is convenient but is not
signed. Only the raw ``initData`` string is ever trusted here.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from .config import Settings


CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
DEMO_CLIENT_ID = "demo-viewer"
DEMO_FIRST_NAME = "Глеб"
DEMO_LAST_NAME = "Кузнецов"
DEMO_USERNAME = "gleb"


class AuthError(Exception):
    """Raised when a request cannot be attributed to a trusted identity."""


@dataclass(frozen=True)
class Identity:
    kind: str  # "max" | "demo"
    max_user_id: str | None
    client_id: str | None
    first_name: str
    last_name: str
    username: str
    photo_url: str
    role_hint: str  # "student" | "teacher"


def validate_init_data(init_data: str, bot_token: str, max_age: int) -> dict[str, str]:
    """Validate raw ``WebApp.initData`` and return its fields.

    secret = HMAC_SHA256("WebAppData", bot_token)
    hash   = HMAC_SHA256(secret, sorted("key=value") joined with "\\n")
    """
    if not init_data:
        raise AuthError("Не переданы данные авторизации MAX")
    if not bot_token:
        raise AuthError("Сервер не настроен для проверки MAX initData")

    pairs = parse_qsl(init_data, keep_blank_values=True)
    hashes = [value for key, value in pairs if key == "hash"]
    if len(hashes) != 1:
        raise AuthError("Некорректная подпись MAX")

    received_hash = hashes[0].lower()
    data_check_string = "\n".join(
        sorted(f"{key}={value}" for key, value in pairs if key != "hash")
    )
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256
    ).digest()
    computed_hash = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise AuthError("Подпись MAX не совпадает")

    values = dict(pairs)
    try:
        auth_date = int(values["auth_date"])
    except (KeyError, ValueError) as exc:
        raise AuthError("В данных MAX нет корректного auth_date") from exc

    now = int(time.time())
    if auth_date > now + 60:
        raise AuthError("Данные MAX выданы в будущем")
    if now - auth_date > max_age:
        raise AuthError("Данные MAX устарели, откройте приложение заново")

    return values


def identity_from_request(
    init_data: str | None, client_id: str | None, settings: Settings
) -> Identity:
    if settings.bot_token:
        values = validate_init_data(
            init_data or "", settings.bot_token, settings.init_data_max_age
        )
        try:
            user = json.loads(values.get("user", "{}"))
            user_id = int(user["id"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AuthError("В данных MAX нет пользователя") from exc

        max_user_id = str(user_id)
        return Identity(
            kind="max",
            max_user_id=max_user_id,
            client_id=None,
            first_name=str(user.get("first_name") or "Герой")[:64],
            last_name=str(user.get("last_name") or "")[:64],
            username=str(user.get("username") or "")[:64],
            photo_url=str(user.get("photo_url") or "")[:512],
            role_hint=(
                "teacher" if max_user_id in settings.teacher_max_ids else "student"
            ),
        )

    if not client_id or not CLIENT_ID_RE.fullmatch(client_id):
        raise AuthError("Нет корректного идентификатора демо-клиента")
    # Browser demo has no identity provider. All visitors share one lived-in
    # demo profile so repeated visits do not flood the class leaderboard with
    # clones of the same student.
    return Identity(
        kind="demo",
        max_user_id=None,
        client_id=DEMO_CLIENT_ID,
        first_name=DEMO_FIRST_NAME,
        last_name=DEMO_LAST_NAME,
        username=DEMO_USERNAME,
        photo_url="",
        role_hint="student",
    )
