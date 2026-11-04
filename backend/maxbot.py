"""MAX bot: webhook receiver and a small API client.

Behaviour: on ``bot_started`` the bot greets the user and offers a button that
opens the mini app; on a message in a direct dialog it replies with a short
hint and the same button (at most once per interval per user).

API facts come from dev.max.ru (see docs/bot.md): token in the
``Authorization`` header, ``X-Max-Bot-Api-Secret`` on incoming webhooks,
``POST /messages?user_id=...`` with an ``inline_keyboard`` attachment and an
``open_app`` button.
"""

from __future__ import annotations

import hmac
import json
import logging
import threading
import time
from collections import OrderedDict
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from .config import Settings

log = logging.getLogger("schoolhero.maxbot")

SECRET_HEADER = "X-Max-Bot-Api-Secret"
MAX_BODY_BYTES = 64 * 1024
UPDATE_TYPES = ["bot_started", "message_created"]

WELCOME_TEXT = (
    "Школьный герой — задания, рейтинг класса и проверка педагогом. "
    "Откройте приложение, чтобы начать."
)
HINT_TEXT = "Школьный герой работает в приложении. Откройте его кнопкой ниже."
BUTTON_TEXT = "Открыть приложение"

SEND_ATTEMPTS = 3
RETRY_DELAYS = (1.0, 3.0)
HTTP_TIMEOUT = 10.0

router = APIRouter()


class MaxApiError(Exception):
    """API call failed. The message never contains the token."""


class MaxClient:
    def __init__(self, settings: Settings):
        base = settings.max_api_base.rstrip("/")
        if not base.startswith("https://"):
            raise MaxApiError("MAX_API_BASE должен начинаться с https://")
        self._base = base
        self._token = settings.bot_token
        self._verify: Any = settings.max_ca_bundle or True

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> Any:
        if not self._token:
            raise MaxApiError("MAX_BOT_TOKEN не задан")
        try:
            response = httpx.request(
                method,
                self._base + path,
                params=params,
                json=json_body,
                headers={"Authorization": self._token},
                timeout=HTTP_TIMEOUT,
                verify=self._verify,
                follow_redirects=False,
            )
        except httpx.HTTPError as exc:
            # Only the exception class: its text may echo request details.
            raise MaxApiError(f"{method} {path}: {type(exc).__name__}") from None
        if response.status_code >= 400:
            err = MaxApiError(f"{method} {path}: HTTP {response.status_code}")
            err.status = response.status_code  # type: ignore[attr-defined]
            raise err
        try:
            return response.json()
        except ValueError:
            return {}

    def get_me(self) -> dict:
        return self._request("GET", "/me")

    def send_message(self, user_id: int, text: str, buttons: list[list[dict]]) -> dict:
        body: dict[str, Any] = {"text": text}
        if buttons:
            body["attachments"] = [
                {"type": "inline_keyboard", "payload": {"buttons": buttons}}
            ]
        return self._request("POST", "/messages", params={"user_id": user_id}, json_body=body)

    def get_subscriptions(self) -> dict:
        return self._request("GET", "/subscriptions")

    def subscribe(self, url: str, secret: str) -> dict:
        body: dict[str, Any] = {"url": url, "update_types": UPDATE_TYPES}
        if secret:
            body["secret"] = secret
        return self._request("POST", "/subscriptions", json_body=body)

    def unsubscribe(self, url: str) -> dict:
        return self._request("DELETE", "/subscriptions", params={"url": url})


def get_client(settings: Settings) -> MaxClient:
    """Factory; tests replace it with a fake."""
    return MaxClient(settings)


class _TTLSet:
    """Small in-memory TTL map for idempotency and flood control."""

    def __init__(self, ttl: float, limit: int = 20000):
        self.ttl = ttl
        self.limit = limit
        self._data: OrderedDict[Any, float] = OrderedDict()
        self._lock = threading.Lock()

    def seen_or_add(self, key: Any, ttl: float | None = None) -> bool:
        """True if key is still fresh; otherwise record it and return False."""
        now = time.monotonic()
        ttl = self.ttl if ttl is None else ttl
        with self._lock:
            expires = self._data.get(key)
            if expires is not None and expires > now:
                return True
            self._data[key] = now + ttl
            self._data.move_to_end(key)
            while len(self._data) > self.limit:
                self._data.popitem(last=False)
            return False

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


_updates = _TTLSet(ttl=24 * 3600)
_flood = _TTLSet(ttl=60)
_bot_cache: dict[str, Any] = {}


def reset_state() -> None:
    _updates.clear()
    _flood.clear()
    _bot_cache.clear()


def _bot_identity(settings: Settings, client: MaxClient) -> tuple[str, int | None]:
    """Bot username (and user id, if known), from config or cached GET /me."""
    username = settings.max_bot_username or _bot_cache.get("username", "")
    user_id = _bot_cache.get("user_id")
    if username and (settings.max_bot_username or user_id is not None):
        return username, user_id
    me = client.get_me()
    username = settings.max_bot_username or str(me.get("username") or "")
    uid = me.get("user_id")
    user_id = uid if isinstance(uid, int) and not isinstance(uid, bool) else None
    if username:
        _bot_cache["username"] = username
    if user_id is not None:
        _bot_cache["user_id"] = user_id
    return username, user_id


def build_buttons(settings: Settings, client: MaxClient) -> list[list[dict]]:
    """open_app button; falls back to a plain link if the username is unknown."""
    try:
        username, bot_id = _bot_identity(settings, client)
    except MaxApiError as exc:
        log.warning("GET /me не удался (%s), кнопка будет ссылкой", exc)
        username, bot_id = "", None
    if username:
        button: dict[str, Any] = {
            "type": "open_app",
            "text": BUTTON_TEXT,
            "web_app": username,
        }
        if bot_id is not None:
            button["contact_id"] = bot_id
        return [[button]]
    if not settings.public_url:
        # Нет ни username бота, ни PUBLIC_URL: отправляем текст без кнопки.
        return []
    return [[{"type": "link", "text": BUTTON_TEXT, "url": settings.public_url}]]


def deliver(settings: Settings, user_id: int, text: str) -> None:
    """Send text + app button with a timeout and a few retries (runs in background)."""
    try:
        client = get_client(settings)
    except MaxApiError as exc:
        log.error("бот MAX не настроен: %s", exc)
        return
    last: Exception | None = None
    for attempt in range(SEND_ATTEMPTS):
        try:
            buttons = build_buttons(settings, client)
            client.send_message(user_id, text, buttons)
            return
        except MaxApiError as exc:
            last = exc
            status = getattr(exc, "status", None)
            retryable = status is None or status == 429 or status >= 500
            if not retryable or attempt == SEND_ATTEMPTS - 1:
                break
            time.sleep(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)])
    log.error("не удалось отправить сообщение боту MAX: %s", last)


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def plan_reply(update: dict, settings: Settings) -> tuple[int, str] | None:
    """Decide what to send for an update: (user_id, text) or None. Pure apart from caches."""
    kind = update.get("update_type")
    if kind == "bot_started":
        user = update.get("user")
        user_id = _as_int(user.get("user_id")) if isinstance(user, dict) else None
        if user_id is None:
            return None
        # payload (deep link data) is deliberately ignored.
        key = ("started", user_id, update.get("timestamp"))
        if _updates.seen_or_add(key):
            return None
        _flood.seen_or_add(user_id, ttl=settings.bot_reply_interval)
        return user_id, WELCOME_TEXT

    if kind == "message_created":
        message = update.get("message")
        if not isinstance(message, dict):
            return None
        recipient = message.get("recipient")
        if not isinstance(recipient, dict) or recipient.get("chat_type") != "dialog":
            return None
        sender = message.get("sender")
        if not isinstance(sender, dict) or sender.get("is_bot"):
            return None
        user_id = _as_int(sender.get("user_id"))
        if user_id is None:
            return None
        body = message.get("body")
        mid = body.get("mid") if isinstance(body, dict) else None
        key = ("msg", mid) if isinstance(mid, str) and mid else (
            "msg", user_id, update.get("timestamp"), message.get("timestamp")
        )
        if _updates.seen_or_add(key):
            return None
        if _flood.seen_or_add(user_id, ttl=settings.bot_reply_interval):
            return None
        return user_id, HINT_TEXT
    return None


@router.post("/api/max/webhook", include_in_schema=False)
async def max_webhook(request: Request, background: BackgroundTasks) -> dict:
    settings: Settings = request.app.state.settings
    if settings.app_mode != "prod" or not settings.bot_token:
        raise HTTPException(status_code=404, detail="Not found")

    expected = settings.max_webhook_secret
    received = request.headers.get(SECRET_HEADER, "")
    if not expected or not hmac.compare_digest(
        received.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(status_code=403, detail="Forbidden")

    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Payload too large")
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Payload too large")
    try:
        update = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="Bad request") from None
    if not isinstance(update, dict):
        raise HTTPException(status_code=400, detail="Bad request")

    plan = plan_reply(update, settings)
    if plan:
        user_id, text = plan
        background.add_task(deliver, settings, user_id, text)
    return {"ok": True}
