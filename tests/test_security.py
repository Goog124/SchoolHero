"""Tests for MAX initData validation and demo identity."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from backend.security import (
    DEMO_CLIENT_ID,
    DEMO_FIRST_NAME,
    AuthError,
    identity_from_request,
    validate_init_data,
)
from conftest import make_settings

BOT_TOKEN = "test-bot-token"


def sign_init_data(
    user: dict,
    *,
    bot_token: str = BOT_TOKEN,
    auth_date: int | None = None,
    extra: dict[str, str] | None = None,
) -> str:
    fields = {
        "auth_date": str(int(time.time()) if auth_date is None else auth_date),
        "query_id": "AAH-test-query",
        "user": json.dumps(user, ensure_ascii=False, separators=(",", ":")),
    }
    if extra:
        fields.update(extra)
    check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(fields.items())
    )
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256
    ).digest()
    fields["hash"] = hmac.new(
        secret_key, check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return urlencode(fields)


MAX_USER = {
    "id": 7001,
    "first_name": "Алиса",
    "last_name": "Морозова",
    "username": "alice",
    "photo_url": "https://example.test/alice.png",
}


def test_valid_signature_is_accepted():
    init_data = sign_init_data(MAX_USER)

    values = validate_init_data(init_data, BOT_TOKEN, max_age=3600)

    assert values["query_id"] == "AAH-test-query"
    assert json.loads(values["user"])["id"] == 7001


def test_tampered_payload_is_rejected():
    init_data = sign_init_data(MAX_USER)
    tampered = init_data.replace("7001", "7002")

    with pytest.raises(AuthError, match="Подпись"):
        validate_init_data(tampered, BOT_TOKEN, max_age=3600)


def test_wrong_bot_token_is_rejected():
    init_data = sign_init_data(MAX_USER)

    with pytest.raises(AuthError, match="Подпись"):
        validate_init_data(init_data, "another-token", max_age=3600)


def test_missing_hash_is_rejected():
    with pytest.raises(AuthError, match="подпись"):
        validate_init_data("auth_date=1&user=%7B%7D", BOT_TOKEN, max_age=3600)


def test_empty_init_data_is_rejected():
    with pytest.raises(AuthError):
        validate_init_data("", BOT_TOKEN, max_age=3600)


def test_missing_bot_token_configuration_is_rejected():
    with pytest.raises(AuthError, match="не настроен"):
        validate_init_data(sign_init_data(MAX_USER), "", max_age=3600)


def test_expired_init_data_is_rejected():
    init_data = sign_init_data(MAX_USER, auth_date=int(time.time()) - 4000)

    with pytest.raises(AuthError, match="устарели"):
        validate_init_data(init_data, BOT_TOKEN, max_age=3600)


def test_future_init_data_is_rejected():
    init_data = sign_init_data(MAX_USER, auth_date=int(time.time()) + 120)

    with pytest.raises(AuthError, match="будущем"):
        validate_init_data(init_data, BOT_TOKEN, max_age=3600)


def test_auth_date_is_required():
    fields = {
        "query_id": "AAH-test-query",
        "user": json.dumps(MAX_USER, separators=(",", ":")),
    }
    check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret_key = hmac.new(
        b"WebAppData", BOT_TOKEN.encode("utf-8"), hashlib.sha256
    ).digest()
    fields["hash"] = hmac.new(
        secret_key, check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    with pytest.raises(AuthError, match="auth_date"):
        validate_init_data(urlencode(fields), BOT_TOKEN, max_age=3600)


def test_identity_from_signed_user(tmp_path):
    settings = make_settings(tmp_path, app_mode="prod", bot_token=BOT_TOKEN)

    identity = identity_from_request(sign_init_data(MAX_USER), None, settings)

    assert identity.kind == "max"
    assert identity.max_user_id == "7001"
    assert identity.first_name == "Алиса"
    assert identity.last_name == "Морозова"
    assert identity.username == "alice"
    assert identity.role_hint == "student"


def test_teacher_id_gets_teacher_hint(tmp_path):
    settings = make_settings(
        tmp_path, app_mode="prod", bot_token=BOT_TOKEN, teacher_max_ids={"7001"}
    )

    identity = identity_from_request(sign_init_data(MAX_USER), None, settings)

    assert identity.role_hint == "teacher"


def test_signed_payload_without_user_is_rejected(tmp_path):
    settings = make_settings(tmp_path, app_mode="prod", bot_token=BOT_TOKEN)
    init_data = sign_init_data({"first_name": "Без id"})

    with pytest.raises(AuthError, match="нет пользователя"):
        identity_from_request(init_data, None, settings)


def test_demo_identity_requires_valid_client_id(tmp_path):
    settings = make_settings(tmp_path)

    for bad_client in (None, "", "short", "x" * 65, "bad client!"):
        with pytest.raises(AuthError):
            identity_from_request(None, bad_client, settings)


def test_demo_identity_is_shared_and_fixed(tmp_path):
    settings = make_settings(tmp_path)

    first = identity_from_request(None, "first-browser", settings)
    second = identity_from_request(None, "second-browser", settings)

    assert first == second
    assert first.kind == "demo"
    assert first.client_id == DEMO_CLIENT_ID
    assert first.first_name == DEMO_FIRST_NAME
    assert first.role_hint == "student"


def test_demo_mode_ignores_init_data(tmp_path):
    settings = make_settings(tmp_path)

    identity = identity_from_request(sign_init_data(MAX_USER), "demo-client-1", settings)

    assert identity.kind == "demo"
    assert identity.max_user_id is None
