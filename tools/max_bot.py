r"""Управление ботом MAX: me, subscribe, unsubscribe, status.

Запуск из корня проекта (читает .env, токен не печатает):

    python tools/max_bot.py me
    python tools/max_bot.py subscribe
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


COMMANDS = {
    "me": cmd_me,
    "subscribe": cmd_subscribe,
    "status": cmd_status,
    "unsubscribe": cmd_unsubscribe,
}


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in COMMANDS:
        print(__doc__)
        return 2
    settings = Settings.from_env()
    if not settings.bot_token:
        print("В .env не задан MAX_BOT_TOKEN")
        return 1
    try:
        client = MaxClient(settings)
        return COMMANDS[argv[1]](client, settings)
    except MaxApiError as exc:
        print(f"Ошибка API: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
