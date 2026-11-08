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

HELP_TEXT = (
    "Школьный герой: справка\n\n"
    "Команды в чате:\n"
    "/status — информация о профиле, уровне и серии\n"
    "/tasks — список актуальных заданий класса\n"
    "/help — справка по командам\n\n"
    "Для сдачи отчётов и кастомизации персонажа откройте приложение кнопкой ниже."
)

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
        verify: Any = settings.max_ca_bundle or True
        if isinstance(verify, str) and verify.lower() in ("insecure", "0", "false", "off", "no"):
            verify = False
        self._verify: Any = verify

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

    def get_updates(self, marker: int | None = None, timeout: int = 25, limit: int = 100) -> dict:
        params: dict[str, Any] = {"timeout": timeout, "limit": limit}
        if marker is not None:
            params["marker"] = marker
        return self._request("GET", "/updates", params=params)


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


def deliver(
    settings: Settings,
    user_id: int,
    text: str,
    buttons: list[list[dict]] | None = None,
) -> None:
    """Send text + app button with a timeout and a few retries (runs in background)."""
    try:
        client = get_client(settings)
    except MaxApiError as exc:
        log.error("бот MAX не настроен: %s", exc)
        return
    last: Exception | None = None
    for attempt in range(SEND_ATTEMPTS):
        try:
            btns = build_buttons(settings, client) if buttons is None else buttons
            client.send_message(user_id, text, btns)
            return
        except MaxApiError as exc:
            last = exc
            status = getattr(exc, "status", None)
            retryable = status is None or status == 429 or status >= 500
            if not retryable or attempt == SEND_ATTEMPTS - 1:
                break
            time.sleep(RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)])
    log.error("не удалось отправить сообщение боту MAX: %s", last)


def _format_status(max_user_id: int, settings: Settings) -> str:
    try:
        from . import db
        with db.connect(settings.db_path) as conn:
            row = conn.execute(
                """
                SELECT u.*, c.name AS class_name, s.name AS school_name
                FROM users u
                LEFT JOIN classes c ON c.id = u.class_id
                LEFT JOIN schools s ON s.id = u.school_id
                WHERE u.max_user_id = ?
                """,
                (str(max_user_id),),
            ).fetchone()
            if not row:
                return (
                    "Школьный герой: профиль\n\n"
                    "Пользователь не найден в системе. Откройте приложение кнопкой ниже для входа."
                )

            role_titles = {"student": "ученик", "teacher": "педагог", "director": "директор"}
            role_name = role_titles.get(row["role"], row["role"])
            name = f"{row['first_name']} {row['last_name']}".strip()
            class_name = row["class_name"] or "без привязки к классу"
            school_name = row["school_name"] or "школа не указана"

            lines = [
                "Школьный герой: профиль",
                "",
                f"Пользователь: {name}",
                f"Роль: {role_name}",
                f"Класс: {class_name}",
                f"Школа: {school_name}",
            ]
            if row["role"] == "student":
                from .game import level_for
                level = level_for(int(row["xp"]))
                lines.extend([
                    f"Уровень: {level} ({row['xp']} XP)",
                    f"Серия активности: {row['streak']} дн.",
                ])
            return "\n".join(lines)
    except Exception as exc:
        log.warning("Ошибка получения статуса для бота: %s", exc)
        return HINT_TEXT


def _format_tasks(max_user_id: int, settings: Settings) -> str:
    try:
        from . import db
        with db.connect(settings.db_path) as conn:
            user = conn.execute(
                "SELECT id, class_id FROM users WHERE max_user_id = ?",
                (str(max_user_id),),
            ).fetchone()
            if not user or not user["class_id"]:
                return (
                    "Школьный герой: задания\n\n"
                    "Для просмотра заданий войдите в приложение и выберите класс."
                )

            tasks = conn.execute(
                "SELECT title, xp, deadline FROM challenges "
                "WHERE class_id = ? AND active = 1 ORDER BY id DESC LIMIT 5",
                (user["class_id"],),
            ).fetchall()
            if not tasks:
                return (
                    "Школьный герой: актуальные задания\n\n"
                    "Сейчас нет активных заданий для вашего класса."
                )

            lines = ["Школьный герой: актуальные задания", ""]
            for i, t in enumerate(tasks, 1):
                deadline_str = f" (срок: {t['deadline'][:10]})" if t["deadline"] else ""
                lines.append(f"{i}. {t['title']} — {t['xp']} XP{deadline_str}")
            return "\n".join(lines)
    except Exception as exc:
        log.warning("Ошибка получения заданий для бота: %s", exc)
        return HINT_TEXT


def handle_command(user_id: int, text: str, settings: Settings) -> str | None:
    """Handle text commands if enabled. Returns reply text or None for standard hint."""
    if not settings.bot_chat_commands:
        return None
    cleaned = text.strip()
    first_word = cleaned.split()[0].lower() if cleaned else ""

    if first_word in {"/status", "/профиль", "статус", "профиль"}:
        return _format_status(user_id, settings)
    if first_word in {"/tasks", "/задания", "задания"}:
        return _format_tasks(user_id, settings)
    if first_word in {"/help", "/помощь", "помощь"}:
        return HELP_TEXT
    return None


def notify_user(
    settings: Settings,
    max_user_id: str | int | None,
    text: str,
    buttons: list[list[dict]] | None = None,
) -> None:
    """Send notification to MAX chat if notifications are enabled."""
    if not settings.bot_notifications_enabled or not settings.bot_token or not max_user_id:
        return
    try:
        uid = int(str(max_user_id).strip())
    except (ValueError, TypeError):
        return
    deliver(settings, uid, text, buttons=buttons)


def notify_review_result(
    settings: Settings,
    student_max_id: str | int | None,
    challenge_title: str,
    status: str,
    xp_awarded: int = 0,
    student_level: int = 1,
    reason: str = "",
) -> None:
    """Send verification result notification to a student."""
    if not settings.bot_notifications_enabled or not student_max_id:
        return
    title = (challenge_title or "").strip()
    if status == "approved":
        text = (
            f"Задание «{title}» проверено педагогом. "
            f"Начислено {xp_awarded} XP. Текущий уровень: {student_level}."
        )
    elif status == "rejected":
        if reason.strip():
            text = f"Задание «{title}» возвращено на доработку. Комментарий: {reason.strip()}."
        else:
            text = f"Задание «{title}» отклонено педагогом."
    else:
        return
    notify_user(settings, student_max_id, text)


def notify_teacher_submission(
    settings: Settings,
    teacher_max_id: str | int | None,
    student_name: str,
    class_name: str,
    challenge_title: str,
) -> None:
    """Send new submission notification to a teacher."""
    if not settings.bot_notifications_enabled or not teacher_max_id:
        return
    text = (
        f"Новый ответ на проверку: {student_name.strip()}, класс {class_name.strip()}. "
        f"Задание: «{challenge_title.strip()}»."
    )
    notify_user(settings, teacher_max_id, text)


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

        reply_text = None
        if isinstance(body, dict):
            text = (body.get("text") or "").strip()
            if text and settings.bot_chat_commands:
                reply_text = handle_command(user_id, text, settings)
        if not reply_text:
            reply_text = HINT_TEXT
        return user_id, reply_text
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
