r"""Управление ботом MAX: me, poll, subscribe, unsubscribe, status.

Запуск из корня проекта (читает .env, токен не печатает):

    python tools/max_bot.py me
    python tools/max_bot.py poll            (Long Polling: работа с чатом без вебхука)
    python tools/max_bot.py subscribe       (Webhook: регистрация на сервере)
    python tools/max_bot.py status
    python tools/max_bot.py unsubscribe
"""

from __future__ import annotations

import secrets
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
from backend.maxbot import MaxApiError, MaxClient, UPDATE_TYPES  # noqa: E402


def _webhook_url(settings: Settings) -> str:
    return f"{settings.public_url}/api/max/webhook"


def cmd_me(client: MaxClient, settings: Settings) -> int:
    me = client.get_me()
    name = me.get("first_name") or me.get("name") or "-"
    print(f"Имя: {name}")
    print(f"Username: {me.get('username') or '(не задан)'}")
    print(f"user_id: {me.get('user_id')}")
    return 0


def cmd_status(client: MaxClient, settings: Settings) -> int:
    subs = client.get_subscriptions().get("subscriptions") or []
    if not subs:
        print("Подписок нет. Выполните: python tools/max_bot.py subscribe")
    for sub in subs:
        print(f"{sub.get('url')}  типы: {', '.join(sub.get('update_types') or []) or '-'}")
    expected = _webhook_url(settings)
    if subs and not any(s.get("url") == expected for s in subs):
        print(f"Ожидаемый адрес {expected} среди подписок не найден.")
    print(f"Секрет в .env: {'задан' if settings.max_webhook_secret else 'НЕ задан'}")
    return 0


def cmd_subscribe(client: MaxClient, settings: Settings) -> int:
    secret = settings.max_webhook_secret
    generated = False
    if not secret:
        secret = secrets.token_hex(32)  # 64 символа [0-9a-f], подходит под правила MAX
        generated = True
    url = _webhook_url(settings)
    if not url.startswith("https://"):
        print(f"PUBLIC_URL должен быть https:// (сейчас {url})")
        return 1
    result = client.subscribe(url, secret)
    if result.get("success") is False:
        print(f"MAX отклонил подписку: {result.get('message') or 'без пояснения'}")
        return 1
    print(f"Webhook зарегистрирован: {url}")
    print(f"Типы обновлений: {', '.join(UPDATE_TYPES)}")
    if generated:
        print()
        print("Секрет сгенерирован и отправлен в MAX, но в .env его ещё нет.")
        print("Добавьте в серверный .env строку и перезапустите сервис:")
        print(f"  MAX_WEBHOOK_SECRET={secret}")
        print("  systemctl restart school-hero")
        print("До этого webhook отвечает 403, приветствия не будет.")
    return 0


def cmd_unsubscribe(client: MaxClient, settings: Settings) -> int:
    url = _webhook_url(settings)
    result = client.unsubscribe(url)
    if result.get("success") is False:
        print(f"MAX не снял подписку: {result.get('message') or 'без пояснения'}")
        return 1
    print(f"Подписка снята: {url}")
    return 0


def cmd_poll(client: MaxClient, settings: Settings) -> int:
    """Long polling: опрашивает MAX API и обрабатывает сообщения в реальном времени."""
    import time
    from backend import db
    from backend.maxbot import deliver, plan_reply
    from backend.security import Identity
    from backend.service import ensure_user

    me = client.get_me()
    name = me.get("first_name") or me.get("name") or "-"
    username = me.get("username") or ""
    print(f"Бот: {name} (@{username}, id={me.get('user_id')})")
    print("Режим Long Polling запущен. Ожидание событий из чата MAX (Ctrl+C для выхода)...")

    marker = None
    while True:
        try:
            res = client.get_updates(marker=marker, timeout=25)
            updates = res.get("updates") or []
            marker = res.get("marker", marker)

            for upd in updates:
                kind = upd.get("update_type")
                user = upd.get("user")
                if not user and isinstance(upd.get("message"), dict):
                    user = upd["message"].get("sender")

                if isinstance(user, dict) and user.get("user_id") and not user.get("is_bot"):
                    uid = user["user_id"]
                    first_name = user.get("first_name") or ""
                    last_name = user.get("last_name") or ""
                    u_name = user.get("username") or ""
                    try:
                        for db_target in {settings.db_path, settings.base_dir / "data" / "school_hero.db"}:
                            if db_target.parent.exists():
                                with db.connect(db_target) as conn:
                                    identity = Identity(
                                        kind="max",
                                        max_user_id=str(uid),
                                        client_id=None,
                                        first_name=first_name,
                                        last_name=last_name,
                                        username=u_name,
                                        photo_url=user.get("avatar_url") or "",
                                        role_hint="student",
                                    )
                                    ensure_user(conn, identity, settings)
                                    conn.commit()
                    except Exception as err:
                        print(f"Ошибка сохранения пользователя {uid} в базу: {err}")

                if kind in ("bot_started", "message_created"):
                    u_label = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() if isinstance(user, dict) else str(user)
                    print(f"[{kind}] от {u_label} (user_id={user.get('user_id') if isinstance(user, dict) else '?'})")
                    plan = plan_reply(upd, settings)
                    if plan:
                        target_id, text = plan
                        print(f"-> Ответ: {text[:60].replace(chr(10), ' ')}...")
                        deliver(settings, target_id, text)

        except KeyboardInterrupt:
            print("\nLong Polling остановлен.")
            return 0
        except Exception as exc:
            print(f"Ошибка получения обновлений: {exc}")
            time.sleep(3)


COMMANDS = {
    "me": cmd_me,
    "subscribe": cmd_subscribe,
    "status": cmd_status,
    "unsubscribe": cmd_unsubscribe,
    "poll": cmd_poll,
}


def _fix_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str]) -> int:
    _fix_console_encoding()
    if len(argv) != 2 or argv[1] not in COMMANDS:
        print(__doc__)
        return 2
    settings = Settings.from_env()
    if not settings.bot_token:
        print("В .env не задан MAX_BOT_TOKEN")
        return 1
    if argv[1] in ("subscribe", "status", "unsubscribe") and not settings.public_url:
        print("В .env не задан PUBLIC_URL (например https://app.example.org)")
        return 1
    try:
        client = MaxClient(settings)
        return COMMANDS[argv[1]](client, settings)
    except MaxApiError as exc:
        print(f"Ошибка API: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
