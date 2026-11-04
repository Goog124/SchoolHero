"""Cosmetics catalogue: data integrity, avatar slots and frontend drawing coverage."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from backend.game import (
    AVATAR_KEYS,
    COSMETIC_BY_ID,
    COSMETIC_TYPES,
    COSMETICS,
    DEFAULT_AVATAR,
    RARITIES,
    load_avatar,
    validate_avatar_patch,
)
from conftest import DEMO_HEADERS, get_state

ROOT = Path(__file__).resolve().parent.parent
COMPONENTS = ROOT / "frontend" / "src" / "components"
FRAMES_CSS = ROOT / "frontend" / "src" / "styles" / "frames.css"

# Предметы «ничего»: отдельного рисунка не требуют.
NOTHING = {"none", "hat_none", "face_none"}


def test_ids_are_unique():
    ids = [item.id for item in COSMETICS]
    assert len(ids) == len(set(ids))


def test_every_item_has_valid_fields():
    for item in COSMETICS:
        assert item.type in COSMETIC_TYPES, item.id
        assert item.name.strip(), item.id
        assert 1 <= item.unlock_level <= 5, item.id
        assert item.price >= 0, item.id
        assert item.rarity_id in RARITIES, item.id
        assert item.as_dict()["rarity"] in RARITIES


def test_every_slot_is_covered_and_has_a_default():
    assert set(AVATAR_KEYS.values()) == set(COSMETIC_TYPES)
    for key, slot in AVATAR_KEYS.items():
        default = COSMETIC_BY_ID[DEFAULT_AVATAR[key]]
        assert default.type == slot
        assert default.price == 0 and default.unlock_level == 1


def test_catalogue_size_and_cheap_start():
    new_slots = {"hat", "face"}
    assert {item.type for item in COSMETICS} >= new_slots
    assert len(COSMETICS) >= 90
    level_one = [i for i in COSMETICS if i.unlock_level == 1 and i.type not in {"skin"}]
    cheap = [i for i in COSMETICS if i.price <= 40]
    assert len(cheap) / len(COSMETICS) >= 0.4
    assert any(i.price == 0 for i in level_one)


def test_validate_patch_accepts_new_slots():
    patch = validate_avatar_patch(
        {"hat": "hat_cap", "face": "glasses_round", "accessory": "bow"}, 1, []
    )
    assert patch["hat"] == "hat_cap"


def test_validate_patch_rejects_wrong_slot_and_unknown_key():
    with pytest.raises(ValueError):
        validate_avatar_patch({"hat": "glasses_round"}, 5, [])
    with pytest.raises(ValueError):
        validate_avatar_patch({"cape": "cape"}, 5, [])


def test_validate_patch_checks_level_and_purchase():
    with pytest.raises(ValueError, match="уровне"):
        validate_avatar_patch({"hat": "hat_astro"}, 1, ["hat_astro"])
    with pytest.raises(ValueError, match="купи"):
        validate_avatar_patch({"hat": "hat_wizard"}, 3, [])
    assert validate_avatar_patch({"hat": "hat_wizard"}, 3, ["hat_wizard"])


def test_old_avatar_without_new_keys_gets_defaults():
    old = json.dumps(
        {
            "skin": "skin_warm",
            "hair": "hair_curls",
            "hairColor": "hair_brown",
            "outfit": "hoodie_violet",
            "accessory": "headphones",
            "frame": "frame_neon",
        }
    )
    avatar = load_avatar(old)
    assert avatar["hat"] == "hat_none"
    assert avatar["face"] == "face_none"
    assert avatar["accessory"] == "headphones"
    assert avatar["frame"] == "frame_neon"
    assert load_avatar(None) == DEFAULT_AVATAR
    assert load_avatar("not json") == DEFAULT_AVATAR


def test_stored_value_of_wrong_slot_falls_back_to_default():
    avatar = load_avatar(json.dumps({"hat": "glasses_round", "face": 5}))
    assert avatar["hat"] == "hat_none"
    assert avatar["face"] == "face_none"


def test_buy_and_equip_new_item(demo_client):
    state = get_state(demo_client)
    level = state["viewer"]["level"]["level"]
    assert level >= 1
    free_hat = COSMETIC_BY_ID["hat_cap"]
    equipped = demo_client.post(
        "/api/avatar/equip",
        json={"key": "hat", "item_id": free_hat.id},
        headers=DEMO_HEADERS,
    )
    assert equipped.status_code == 200, equipped.text
    assert equipped.json()["state"]["viewer"]["avatar"]["hat"] == free_hat.id

    paid = next(
        i for i in COSMETICS
        if i.type == "face" and 0 < i.price <= state["viewer"]["sparks"] and i.unlock_level <= level
    )
    not_owned = demo_client.post(
        "/api/avatar/equip", json={"key": "face", "item_id": paid.id}, headers=DEMO_HEADERS
    )
    assert not_owned.status_code == 400
    bought = demo_client.post(
        "/api/shop/buy", json={"item_id": paid.id}, headers=DEMO_HEADERS
    )
    assert bought.status_code == 200, bought.text
    again = demo_client.post(
        "/api/avatar/equip", json={"key": "face", "item_id": paid.id}, headers=DEMO_HEADERS
    )
    assert again.status_code == 200, again.text
    avatar = again.json()["state"]["viewer"]["avatar"]
    assert avatar["face"] == paid.id and avatar["hat"] == free_hat.id


def test_level_limit_for_new_item(demo_client):
    state = get_state(demo_client)
    level = state["viewer"]["level"]["level"]
    locked = next(i for i in COSMETICS if i.type == "hat" and i.unlock_level > level)
    response = demo_client.post(
        "/api/avatar/equip", json={"key": "hat", "item_id": locked.id}, headers=DEMO_HEADERS
    )
    assert response.status_code == 400
    bought = demo_client.post(
        "/api/shop/buy", json={"item_id": locked.id}, headers=DEMO_HEADERS
    )
    assert bought.status_code == 400
    assert "уровне" in bought.json()["detail"]


def test_state_exposes_new_slots_and_rarity(demo_client):
    state = get_state(demo_client)
    avatar = state["viewer"]["avatar"]
    assert "hat" in avatar and "face" in avatar
    types = {item["type"] for item in state["cosmetics"]}
    assert {"hat", "face", "accessory", "frame"} <= types
    assert all(item["rarity"] in RARITIES for item in state["cosmetics"])


def _drawing_sources() -> str:
    parts = [
        (COMPONENTS / name).read_text(encoding="utf-8")
        for name in ("PixelHero.tsx", "heroItems.tsx", "AvatarFrame.tsx")
    ]
    parts.append(FRAMES_CSS.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_every_catalogue_id_has_a_drawing():
    text = _drawing_sources()
    missing = [
        item.id
        for item in COSMETICS
        if item.id not in NOTHING and not re.search(rf"\b{re.escape(item.id)}\b", text)
    ]
    assert not missing, f"Нет рисунка во фронтенде для: {missing}"


def test_every_frame_has_its_own_style():
    css = FRAMES_CSS.read_text(encoding="utf-8")
    frames = [i.id for i in COSMETICS if i.type == "frame"]
    assert len(frames) >= 12
    for frame_id in frames:
        assert f".avatar-frame--{frame_id} " in css, frame_id
    tiles = re.findall(r"\.avatar-frame--frame_\w+ \{[^}]*?--f-tile: (url\([^\n]*\));", css)
    assert len(set(tiles)) == len(frames)
