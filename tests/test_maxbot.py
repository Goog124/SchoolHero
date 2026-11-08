"""MAX bot webhook: all HTTP to MAX is replaced by a fake client."""

from __future__ import annotations

import logging

import pytest

from backend import maxbot
from tests.conftest import build_client, make_settings

TOKEN = "super-secret-bot-token"
SECRET = "hook-secret-0123456789abcdefghijklmnop"
HEADERS = {"X-Max-Bot-Api-Secret": SECRET}


class FakeClient:
    sent: list = []

    def __init__(self, settings=None):
        pass

    def get_me(self):
        return {"user_id": 777, "username": "school_hero_bot", "first_name": "Bot"}

    def send_message(self, user_id, text, buttons):
        FakeClient.sent.append((user_id, text, buttons))
        return {}


@pytest.fixture
def bot(tmp_path, monkeypatch):
    FakeClient.sent = []
    maxbot.reset_state()
    monkeypatch.setattr(maxbot, "get_client", lambda settings: FakeClient())
    monkeypatch.setattr(maxbot, "RETRY_DELAYS", (0, 0))
    settings = make_settings(
        tmp_path,
        app_mode="prod",
        bot_token=TOKEN,
        max_webhook_secret=SECRET,
        public_url="https://app.example.org",
    )
    client = build_client(settings)
    yield client
    client.close()
    maxbot.reset_state()


def started(user_id=42, ts=1000, payload=None):
    update = {"update_type": "bot_started", "timestamp": ts, "chat_id": 5,
              "user": {"user_id": user_id, "first_name": "A"}}
    if payload is not None:
        update["payload"] = payload
    return update


def message(user_id=42, chat_type="dialog", mid="m1", text="привет"):
    return {
        "update_type": "message_created",
        "timestamp": 2000,
        "message": {
            "sender": {"user_id": user_id, "is_bot": False},
            "recipient": {"chat_id": 5, "chat_type": chat_type, "user_id": 777},
            "body": {"mid": mid, "text": text},
        },
    }


def test_bot_started_sends_welcome_with_open_app(bot):
    r = bot.post("/api/max/webhook", json=started(payload="CLASS123"), headers=HEADERS)
    assert r.status_code == 200
    assert len(FakeClient.sent) == 1
    user_id, text, buttons = FakeClient.sent[0]
    assert user_id == 42
    assert text == maxbot.WELCOME_TEXT
    assert "CLASS123" not in text and "!" not in text
    btn = buttons[0][0]
    assert btn["type"] == "open_app"
    assert btn["web_app"] == "school_hero_bot"
    assert btn["contact_id"] == 777


@pytest.mark.parametrize("headers", [{}, {"X-Max-Bot-Api-Secret": ""},
                                     {"X-Max-Bot-Api-Secret": "wrong-secret"}])
def test_bad_secret_is_403(bot, headers):
    r = bot.post("/api/max/webhook", json=started(), headers=headers)
    assert r.status_code == 403
    assert FakeClient.sent == []


def test_no_configured_secret_is_403(tmp_path):
    settings = make_settings(tmp_path, app_mode="prod", bot_token=TOKEN)
    client = build_client(settings)
    assert client.post("/api/max/webhook", json=started(), headers=HEADERS).status_code == 403
    assert client.post("/api/max/webhook", json=started()).status_code == 403


def test_demo_mode_is_404(tmp_path):
    client = build_client(make_settings(tmp_path, max_webhook_secret=SECRET))
    assert client.post("/api/max/webhook", json=started(), headers=HEADERS).status_code == 404


def test_duplicate_update_one_greeting(bot):
    for _ in range(3):
        assert bot.post("/api/max/webhook", json=started(), headers=HEADERS).status_code == 200
    assert len(FakeClient.sent) == 1


def test_group_and_channel_messages_ignored(bot):
    for i, kind in enumerate(("chat", "channel")):
        r = bot.post("/api/max/webhook", json=message(chat_type=kind, mid=f"g{i}"), headers=HEADERS)
        assert r.status_code == 200
    assert FakeClient.sent == []


def test_dialog_message_gets_hint_and_flood_limit(bot):
    bot.post("/api/max/webhook", json=message(mid="a"), headers=HEADERS)
    bot.post("/api/max/webhook", json=message(mid="b"), headers=HEADERS)
    assert len(FakeClient.sent) == 1
    assert FakeClient.sent[0][1] == maxbot.HINT_TEXT
    bot.post("/api/max/webhook", json=message(user_id=43, mid="c"), headers=HEADERS)
    assert len(FakeClient.sent) == 2


def test_bot_messages_and_garbage_ignored(bot):
    msg = message()
    msg["message"]["sender"]["is_bot"] = True
    assert bot.post("/api/max/webhook", json=msg, headers=HEADERS).status_code == 200
    assert bot.post("/api/max/webhook", json={"update_type": "bot_started", "user": {"user_id": "x"}},
                    headers=HEADERS).status_code == 200
    assert bot.post("/api/max/webhook", json={"update_type": "other", "x": 1}, headers=HEADERS).status_code == 200
    assert bot.post("/api/max/webhook", content=b"not json", headers=HEADERS).status_code == 400
    assert bot.post("/api/max/webhook", json=[1], headers=HEADERS).status_code == 400
    assert FakeClient.sent == []


def test_oversized_body_rejected(bot):
    big = b'{"update_type":"x","pad":"' + b"a" * (maxbot.MAX_BODY_BYTES + 10) + b'"}'
    assert bot.post("/api/max/webhook", content=big, headers=HEADERS).status_code == 413


def test_token_and_secret_not_logged(bot, monkeypatch, caplog):
    class Failing(FakeClient):
        def send_message(self, *a):
            raise maxbot.MaxApiError("POST /messages: HTTP 500")

    monkeypatch.setattr(maxbot, "get_client", lambda s: Failing())
    with caplog.at_level(logging.DEBUG):
        bot.post("/api/max/webhook", json=started(user_id=99, ts=5), headers=HEADERS)
        bot.post("/api/max/webhook", json=started(), headers={"X-Max-Bot-Api-Secret": "bad"})
    assert "не удалось отправить" in caplog.text
    assert TOKEN not in caplog.text and SECRET not in caplog.text


def test_client_failure_falls_back_to_link(bot, monkeypatch):
    class NoMe(FakeClient):
        def get_me(self):
            raise maxbot.MaxApiError("GET /me: HTTP 500")

    monkeypatch.setattr(maxbot, "get_client", lambda s: NoMe())
    bot.post("/api/max/webhook", json=started(user_id=7, ts=9), headers=HEADERS)
    btn = FakeClient.sent[0][2][0][0]
    assert btn == {"type": "link", "text": maxbot.BUTTON_TEXT, "url": "https://app.example.org"}


def test_no_public_url_and_no_username_sends_text_without_keyboard(tmp_path, monkeypatch):
    class NoMe(FakeClient):
        def get_me(self):
            raise maxbot.MaxApiError("GET /me: HTTP 500")

    settings = make_settings(tmp_path, app_mode="prod", bot_token=TOKEN, max_webhook_secret=SECRET)
    assert settings.public_url == ""
    assert maxbot.build_buttons(settings, NoMe()) == []


def test_chat_command_help(bot):
    r = bot.post("/api/max/webhook", json=message(user_id=101, mid="m_help", text="/help"), headers=HEADERS)
    assert r.status_code == 200
    assert len(FakeClient.sent) == 1
    uid, reply, _ = FakeClient.sent[-1]
    assert uid == 101
    assert "Команды в чате:" in reply
    assert "/status" in reply and "/tasks" in reply
    # No emojis
    assert all(ord(c) < 0x1F000 for c in reply)


def test_chat_command_status_and_tasks(bot):
    from backend import db
    # Insert test user and challenge into bot's db
    settings = bot.app.state.settings
    with db.connect(settings.db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO schools (id, name, city) VALUES (1, 'Школа 10', 'Москва')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO classes (id, school_id, name) VALUES (1, 1, '8А')"
        )
        conn.execute(
            "INSERT INTO users (id, max_user_id, first_name, last_name, role, class_id, school_id, xp, streak, avatar) "
            "VALUES (999, '202', 'Иван', 'Иванов', 'student', 1, 1, 120, 3, 'default')"
        )
        conn.execute(
            "INSERT INTO challenges (id, class_id, title, category, xp, deadline, active) "
            "VALUES (999, 1, 'Олимпиада по физике', 'study', 100, '2026-11-20', 1)"
        )
        conn.commit()

    # /status
    r = bot.post("/api/max/webhook", json=message(user_id=202, mid="m_stat", text="/status"), headers=HEADERS)
    assert r.status_code == 200
    assert len(FakeClient.sent) == 1
    reply = FakeClient.sent[-1][1]
    assert "Иван Иванов" in reply
    assert "8А" in reply
    assert "120 XP" in reply
    assert "3 дн." in reply
    assert all(ord(c) < 0x1F000 for c in reply)

    # /tasks
    maxbot._flood.clear()
    r = bot.post("/api/max/webhook", json=message(user_id=202, mid="m_task", text="/tasks"), headers=HEADERS)
    assert r.status_code == 200
    assert len(FakeClient.sent) == 2
    reply = FakeClient.sent[-1][1]
    assert "Олимпиада по физике" in reply
    assert "100 XP" in reply
    assert all(ord(c) < 0x1F000 for c in reply)


def test_chat_commands_can_be_disabled(tmp_path, monkeypatch):
    FakeClient.sent = []
    maxbot.reset_state()
    monkeypatch.setattr(maxbot, "get_client", lambda settings: FakeClient())
    settings = make_settings(
        tmp_path,
        app_mode="prod",
        bot_token=TOKEN,
        max_webhook_secret=SECRET,
        public_url="https://app.example.org",
        bot_chat_commands=False,
    )
    client = build_client(settings)
    r = client.post("/api/max/webhook", json=message(user_id=505, mid="m_off", text="/status"), headers=HEADERS)
    assert r.status_code == 200
    assert len(FakeClient.sent) == 1
    assert FakeClient.sent[0][1] == maxbot.HINT_TEXT
    client.close()
    maxbot.reset_state()


def test_notify_review_result(tmp_path, monkeypatch):
    FakeClient.sent = []
    settings = make_settings(tmp_path, app_mode="prod", bot_token=TOKEN)
    monkeypatch.setattr(maxbot, "get_client", lambda s: FakeClient())

    # Approved notification
    maxbot.notify_review_result(settings, 303, "Физика", "approved", xp_awarded=50, student_level=2)
    assert len(FakeClient.sent) == 1
    uid, text, _ = FakeClient.sent[0]
    assert uid == 303
    assert text == "Задание «Физика» проверено педагогом. Начислено 50 XP. Текущий уровень: 2."
    assert all(ord(c) < 0x1F000 for c in text)

    # Rejected notification with reason
    maxbot.notify_review_result(settings, 303, "Физика", "rejected", reason="Прикрепите PDF")
    assert len(FakeClient.sent) == 2
    assert FakeClient.sent[1][1] == "Задание «Физика» возвращено на доработку. Комментарий: Прикрепите PDF."

    # Notifications disabled via flag
    settings_off = make_settings(tmp_path, app_mode="prod", bot_token=TOKEN, bot_notifications_enabled=False)
    maxbot.notify_review_result(settings_off, 303, "Физика", "approved", xp_awarded=50)
    assert len(FakeClient.sent) == 2  # No new message sent
