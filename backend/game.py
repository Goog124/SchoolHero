"""Game rules, cosmetics catalog and small shared helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

MSK = timezone(timedelta(hours=3))

RANKS: list[dict[str, Any]] = [
    {"level": 1, "title": "Новичок", "min_xp": 0, "next_xp": 100},
    {"level": 2, "title": "Ученик", "min_xp": 100, "next_xp": 250},
    {"level": 3, "title": "Знаток", "min_xp": 250, "next_xp": 450},
    {"level": 4, "title": "Мастер", "min_xp": 450, "next_xp": 700},
    {"level": 5, "title": "Легенда школы", "min_xp": 700, "next_xp": None},
]

XP_VALUES = {
    "homework": 20,
    "club": 30,
    "help": 40,
    "weekly": 50,
    "olympiad": 100,
    "event": 30,
    "streak": 50,
}


SUBJECTS = [
    "Алгебра",
    "Геометрия",
    "Информатика",
    "Физика",
    "Русский язык",
    "Литература",
    "История",
    "Биология",
    "Химия",
    "Английский язык",
    "Физкультура",
    "Общешкольное",
]

PROOF_TYPES = {
    "text": "Текстовый ответ",
    "link": "Ссылка на материал",
    "photo": "Фотография или скан",
}

CATEGORIES = {
    "homework": "Домашнее задание",
    "club": "Кружок или секция",
    "help": "Помощь однокласснику",
    "weekly": "Задание недели",
    "olympiad": "Олимпиада или конкурс",
    "event": "Школьное событие",
    "streak": "Серия дней",
}

KINDS = {"daily": "На сегодня", "weekly": "На неделю", "event": "Событие"}

WEEKDAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

DEFAULT_AVATAR = {
    "skin": "skin_light",
    "hair": "hair_short",
    "hairColor": "hair_dark",
    "outfit": "hoodie_violet",
    "accessory": "none",
    "frame": "frame_wood",
}

BASIC_AVATAR = {
    "skin": "skin_light",
    "hair": "hair_short",
    "hairColor": "hair_dark",
    "outfit": "hoodie_violet",
    "accessory": "none",
    "frame": "frame_wood",
}

DEMO_AVATAR = {
    "skin": "skin_warm",
    "hair": "hair_curls",
    "hairColor": "hair_brown",
    "outfit": "hoodie_violet",
    "accessory": "headphones",
    "frame": "frame_neon",
}


@dataclass(frozen=True)
class Cosmetic:
    id: str
    type: str
    name: str
    unlock_level: int = 1
    price: int = 0
    swatch: str = ""
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "unlock_level": self.unlock_level,
            "price": self.price,
            "swatch": self.swatch,
            "description": self.description,
        }


COSMETICS: list[Cosmetic] = [
    # Skin tones
    Cosmetic("skin_light", "skin", "Светлая", swatch="#f6d3b8"),
    Cosmetic("skin_warm", "skin", "Тёплая", swatch="#e8b58c"),
    Cosmetic("skin_tan", "skin", "Загорелая", swatch="#c98a5e"),
    Cosmetic("skin_deep", "skin", "Тёмная", swatch="#8d5a3d"),
    # Hair styles
    Cosmetic("hair_short", "hair", "Короткая", swatch="#6b3f2b"),
    Cosmetic("hair_curls", "hair", "Кудри", swatch="#a16207"),
    Cosmetic("hair_bob", "hair", "Каре", swatch="#7c3aed"),
    Cosmetic("hair_pony", "hair", "Хвостик", swatch="#c25a2e"),
    Cosmetic("hair_buzz", "hair", "Ёжик", swatch="#2e2038"),
    # Hair colours
    Cosmetic("hair_dark", "hair_color", "Тёмный", swatch="#2e2038"),
    Cosmetic("hair_brown", "hair_color", "Каштановый", swatch="#6b3f2b"),
    Cosmetic("hair_ginger", "hair_color", "Рыжий", swatch="#c25a2e"),
    Cosmetic("hair_blonde", "hair_color", "Золотой", swatch="#e7c56a"),
    Cosmetic("hair_violet", "hair_color", "Фиолетовый", swatch="#8b5cf6"),
    Cosmetic("hair_blue", "hair_color", "Синий", swatch="#3b82f6"),
    # Outfits
    Cosmetic(
        "hoodie_violet",
        "outfit",
        "Худи героя",
        unlock_level=1,
        swatch="#8b5cf6",
        description="Стартовый образ. Удобно и по-школьному.",
    ),
    Cosmetic(
        "hoodie_cyan",
        "outfit",
        "Спортивная толстовка",
        unlock_level=1,
        price=40,
        swatch="#22d3ee",
        description="Удобно для уроков и прогулок.",
    ),
    Cosmetic(
        "sweater_gold",
        "outfit",
        "Свитер отличника",
        unlock_level=2,
        swatch="#fbbf24",
        description="Тёплый, с полосками. Для тех, кто не пропускает.",
    ),
    Cosmetic(
        "jacket_blue",
        "outfit",
        "Куртка исследователя",
        unlock_level=2,
        swatch="#3b82f6",
        description="Для кружков, походов и школьных экспедиций.",
    ),
    Cosmetic(
        "cloak_violet",
        "outfit",
        "Клубный блейзер",
        unlock_level=3,
        swatch="#7c3aed",
        description="Для конференций, олимпиад и защиты проектов.",
    ),
    Cosmetic(
        "armor_silver",
        "outfit",
        "Фирменный жилет",
        unlock_level=4,
        swatch="#cbd5e1",
        description="Удобная форма для лабораторий и Кванториума.",
    ),
    Cosmetic(
        "suit_cosmic",
        "outfit",
        "Торжественный костюм",
        unlock_level=5,
        swatch="#f0abfc",
        description="Классический парадный стиль выпускника.",
    ),
    # Accessories
    Cosmetic("none", "accessory", "Без аксессуара", unlock_level=1, swatch="#2a1b3d"),
    Cosmetic(
        "glasses",
        "accessory",
        "Умные очки",
        unlock_level=1,
        swatch="#67e8f9",
        description="+1 к внимательности на контрольных (только для вида).",
    ),
    Cosmetic(
        "headphones",
        "accessory",
        "Наушники",
        unlock_level=2,
        swatch="#a855f7",
        description="Для фокуса и любимой музыки.",
    ),
    Cosmetic(
        "cap",
        "accessory",
        "Кепка «Квант»",
        unlock_level=2,
        price=50,
        swatch="#22d3ee",
        description="Лимитированный мерч школьного хакатона.",
    ),
    Cosmetic(
        "crown",
        "accessory",
        "Корона лидера",
        unlock_level=4,
        swatch="#fbbf24",
        description="Только для тех, кто добрался до уровня Мастера.",
    ),
    Cosmetic(
        "halo",
        "accessory",
        "Нимб легенды",
        unlock_level=5,
        swatch="#fde68a",
        description="Сияет как пятёрка за четверть.",
    ),
    # Frames
    Cosmetic("frame_wood", "frame", "Дубовая рама", unlock_level=1, swatch="#8b5a2b"),
    Cosmetic(
        "frame_neon",
        "frame",
        "Неоновая рама",
        unlock_level=2,
        swatch="#a855f7",
        description="Подсвечивает героя даже в тёмной ленте.",
    ),
    Cosmetic(
        "frame_gold",
        "frame",
        "Золотая рама",
        unlock_level=4,
        swatch="#fbbf24",
        description="Для призового места в школьном рейтинге.",
    ),
    Cosmetic(
        "frame_galaxy",
        "frame",
        "Галактическая рама",
        unlock_level=5,
        price=80,
        swatch="#818cf8",
        description="Кусочек космоса вокруг аватара.",
    ),
]

COSMETIC_BY_ID = {item.id: item for item in COSMETICS}

AVATAR_KEYS = {
    "skin": "skin",
    "hair": "hair",
    "hairColor": "hair_color",
    "outfit": "outfit",
    "accessory": "accessory",
    "frame": "frame",
}

ACHIEVEMENTS = [
    {
        "id": "first_step",
        "title": "Первый шаг",
        "description": "Получи первый подтверждённый опыт",
        "icon": "spark",
        "target": 1,
    },
    {
        "id": "helper",
        "title": "Свой среди своих",
        "description": "Помоги одноклассникам 3 раза",
        "icon": "heart",
        "target": 3,
    },
    {
        "id": "olympian",
        "title": "Олимпиец",
        "description": "Участвуй в олимпиаде или конкурсе",
        "icon": "trophy",
        "target": 1,
    },
    {
        "id": "streak7",
        "title": "Неделя силы",
        "description": "Не пропускай 7 дней подряд",
        "icon": "flame",
        "target": 7,
    },
    {
        "id": "level4",
        "title": "Мастер",
        "description": "Достигни 4 уровня",
        "icon": "star",
        "target": 4,
    },
    {
        "id": "team",
        "title": "Командный дух",
        "description": "Войди с классом в топ-3 города",
        "icon": "users",
        "target": 3,
    },
]


# ---------------------------------------------------------------------------
# Dates. Moscow has no DST, so a fixed UTC+3 offset is enough and avoids the
# missing IANA tz database on Windows.
# ---------------------------------------------------------------------------


def now_local() -> datetime:
    return datetime.now(MSK)


def today_local() -> date:
    return now_local().date()


def utc_sql(dt: datetime | None = None) -> str:
    moment = (dt or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def parse_sql_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None


def iso_utc(value: str | None) -> str | None:
    parsed = parse_sql_utc(value)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if parsed else None


def local_day(value: str | None) -> str | None:
    parsed = parse_sql_utc(value)
    return parsed.astimezone(MSK).date().isoformat() if parsed else None


def week_start_local() -> datetime:
    today = today_local()
    monday = today - timedelta(days=today.weekday())
    return datetime.combine(monday, time.min, tzinfo=MSK)


def week_start_utc_sql() -> str:
    return utc_sql(week_start_local())


def week_days() -> list[dict[str, str]]:
    start = week_start_local().date()
    today = today_local()
    labels = WEEKDAYS_SHORT
    result = []
    for offset in range(7):
        day = start + timedelta(days=offset)
        result.append(
            {
                "date": day.isoformat(),
                "label": labels[offset],
                "is_today": day == today,
                "is_future": day > today,
            }
        )
    return result


def deadline_today() -> str:
    return datetime.combine(today_local(), time(23, 59), tzinfo=MSK).isoformat()


def deadline_week() -> str:
    start = week_start_local().date()
    sunday = start + timedelta(days=6)
    return datetime.combine(sunday, time(23, 59), tzinfo=MSK).isoformat()


def deadline_in(days: int) -> str:
    day = today_local() + timedelta(days=days)
    return datetime.combine(day, time(23, 59), tzinfo=MSK).isoformat()


def is_past(iso_value: str) -> bool:
    try:
        moment = datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
    except ValueError:
        return True
    return moment < now_local()


# ---------------------------------------------------------------------------
# Levels and XP
# ---------------------------------------------------------------------------


def level_info(xp: int) -> dict[str, Any]:
    rank = RANKS[0]
    for candidate in RANKS:
        if xp >= candidate["min_xp"]:
            rank = candidate
    next_xp = rank["next_xp"]
    if next_xp is None:
        progress = 100.0
        in_level = xp - rank["min_xp"]
        for_level = 0
    else:
        progress = round(
            max(0.0, min(100.0, (xp - rank["min_xp"]) / (next_xp - rank["min_xp"]) * 100)),
            1,
        )
        in_level = xp - rank["min_xp"]
        for_level = next_xp - rank["min_xp"]
    return {
        "level": rank["level"],
        "title": rank["title"],
        "min_xp": rank["min_xp"],
        "next_xp": next_xp,
        "xp_in_level": in_level,
        "xp_for_level": for_level,
        "progress": progress,
        "is_max": next_xp is None,
    }


def level_for(xp: int) -> int:
    return int(level_info(xp)["level"])


def xp_between_levels(old_xp: int, new_xp: int) -> int:
    old_level = level_for(old_xp)
    new_level = level_for(new_xp)
    return max(0, new_level - old_level)


def earned_sparks_for_levels(count: int) -> int:
    return count * 25


# ---------------------------------------------------------------------------
# Avatar helpers
# ---------------------------------------------------------------------------


def load_avatar(raw: str | None) -> dict[str, str]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        value = {}
    avatar = dict(DEFAULT_AVATAR)
    for key in AVATAR_KEYS:
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate in COSMETIC_BY_ID:
            avatar[key] = candidate
    return avatar


def dump_avatar(avatar: dict[str, str]) -> str:
    return json.dumps(avatar, ensure_ascii=False, separators=(",", ":"))


def load_owned(raw: str | None) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    return [item for item in value if item in COSMETIC_BY_ID]


def dump_owned(items: list[str]) -> str:
    return json.dumps(sorted(set(items)), ensure_ascii=False, separators=(",", ":"))


def cosmetic_unlocked(item: Cosmetic, level: int, owned: list[str]) -> bool:
    if item.price > 0 and item.id not in owned:
        return False
    return level >= item.unlock_level


def validate_avatar_patch(
    patch: dict[str, str], level: int, owned: list[str]
) -> dict[str, str]:
    """Validate and merge an avatar patch. Raises ValueError with a human message."""
    for key, item_id in patch.items():
        expected_type = AVATAR_KEYS.get(key)
        if not expected_type:
            raise ValueError(f"Неизвестное поле образа: {key}")
        item = COSMETIC_BY_ID.get(item_id)
        if not item or item.type != expected_type:
            raise ValueError("Такого предмета нет в гардеробе")
        if not cosmetic_unlocked(item, level, owned):
            if item.price > 0 and item.id not in owned:
                raise ValueError("Сначала купи этот предмет")
            raise ValueError(f"Предмет откроется на {item.unlock_level} уровне")
    return patch


# ---------------------------------------------------------------------------
# Database helpers shared by the service layer
# ---------------------------------------------------------------------------


def mark_active(conn, user_id: int) -> int:
    """Mark today as an active day and update the streak. Returns new streak."""
    today = today_local()
    today_iso = today.isoformat()
    row = conn.execute(
        "SELECT streak, last_active_date FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if row is None:
        return 0
    last_active = row["last_active_date"]
    streak = int(row["streak"] or 0)
    if last_active == today_iso:
        pass
    elif last_active == (today - timedelta(days=1)).isoformat():
        streak += 1
    else:
        streak = 1
    conn.execute(
        "UPDATE users SET streak = ?, last_active_date = ? WHERE id = ?",
        (streak, today_iso, user_id),
    )
    conn.execute(
        "INSERT INTO activity_days (user_id, day) VALUES (?, ?) "
        "ON CONFLICT(user_id, day) DO NOTHING",
        (user_id, today_iso),
    )
    return streak


def award_xp(
    conn,
    user_id: int,
    amount: int,
    reason: str,
    category: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Add XP and an event. Returns level-up details for the recipient."""
    row = conn.execute("SELECT xp FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise ValueError("Ученик не найден")
    old_xp = int(row["xp"])
    new_xp = old_xp + int(amount)
    conn.execute("UPDATE users SET xp = ? WHERE id = ?", (new_xp, user_id))
    conn.execute(
        "INSERT INTO xp_events (user_id, amount, reason, category, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, int(amount), reason, category, created_at or utc_sql()),
    )
    levels = xp_between_levels(old_xp, new_xp)
    bonus = earned_sparks_for_levels(levels)
    if bonus:
        conn.execute(
            "UPDATE users SET sparks = sparks + ? WHERE id = ?", (bonus, user_id)
        )
    return {
        "old_xp": old_xp,
        "new_xp": new_xp,
        "level_up": levels > 0,
        "levels_gained": levels,
        "sparks_bonus": bonus,
        "level": level_info(new_xp),
    }


def streak_days(conn, user_id: int, limit: int = 7) -> list[dict[str, Any]]:
    """Return the last seven days, ending today, with activity flags."""
    today = today_local()
    dates = [today - timedelta(days=offset) for offset in range(limit - 1, -1, -1)]
    placeholders = ",".join("?" for _ in dates)
    rows = conn.execute(
        f"SELECT day FROM activity_days WHERE user_id = ? AND day IN ({placeholders})",
        (user_id, *(day.isoformat() for day in dates)),
    ).fetchall()
    active = {row["day"] for row in rows}
    result = []
    for day in dates:
        result.append(
            {
                "date": day.isoformat(),
                "label": WEEKDAYS_SHORT[day.weekday()],
                "is_today": day == today,
                "is_future": False,
                "active": day.isoformat() in active,
            }
        )
    return result


def cosmetic_state(item: Cosmetic, level: int, owned: list[str], avatar: dict[str, str]) -> dict[str, Any]:
    data = item.as_dict()
    data["owned"] = item.id in owned or (
        item.price == 0 and level >= item.unlock_level
    )
    data["unlocked"] = cosmetic_unlocked(item, level, owned)
    data["equipped"] = item.id in avatar.values()
    return data


def achievements_for(conn, user, class_rank: int | None) -> list[dict[str, Any]]:
    approved = conn.execute(
        "SELECT c.category, COUNT(*) AS n "
        "FROM completions cp JOIN challenges c ON c.id = cp.challenge_id "
        "WHERE cp.user_id = ? AND cp.status = 'approved' "
        "GROUP BY c.category",
        (user["id"],),
    ).fetchall()
    counts = {row["category"]: int(row["n"]) for row in approved}
    total = sum(counts.values())
    level = level_info(int(user["xp"]))["level"]
    streak = int(user["streak"] or 0)

    progress = {
        "first_step": total,
        "helper": counts.get("help", 0),
        "olympian": counts.get("olympiad", 0),
        "streak7": streak,
        "level4": level,
        "team": 3 if class_rank is not None and class_rank <= 3 else 0,
    }
    result = []
    for item in ACHIEVEMENTS:
        current = min(progress[item["id"]], item["target"])
        result.append(
            {
                **item,
                "progress": current,
                "unlocked": current >= item["target"],
            }
        )
    return result
