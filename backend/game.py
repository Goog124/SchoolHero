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
    "hat": "hat_none",
    "face": "face_none",
    "frame": "frame_wood",
}

BASIC_AVATAR = {
    "skin": "skin_light",
    "hair": "hair_short",
    "hairColor": "hair_dark",
    "outfit": "hoodie_violet",
    "accessory": "none",
    "hat": "hat_none",
    "face": "face_none",
    "frame": "frame_wood",
}

DEMO_AVATAR = {
    "skin": "skin_warm",
    "hair": "hair_curls",
    "hairColor": "hair_brown",
    "outfit": "hoodie_violet",
    "accessory": "none",
    "hat": "headphones",
    "face": "face_none",
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
    rarity: str = ""  # пусто = по уровню предмета (RARITY_BY_LEVEL)

    @property
    def rarity_id(self) -> str:
        return self.rarity or RARITY_BY_LEVEL.get(self.unlock_level, "common")

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "unlock_level": self.unlock_level,
            "price": self.price,
            "swatch": self.swatch,
            "description": self.description,
            "rarity": self.rarity_id,
        }


RARITIES = ("common", "rare", "epic", "legendary")
RARITY_BY_LEVEL = {1: "common", 2: "common", 3: "rare", 4: "epic", 5: "legendary"}
COSMETIC_TYPES = (
    "skin", "hair", "hair_color", "outfit", "hat", "face", "accessory", "frame",
)


def _c(
    item_id: str,
    slot: str,
    name: str,
    level: int = 1,
    price: int = 0,
    swatch: str = "",
    description: str = "",
    rarity: str = "",
) -> Cosmetic:
    return Cosmetic(item_id, slot, name, level, price, swatch, description, rarity)


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
        "face",
        "Умные очки",
        unlock_level=1,
        swatch="#67e8f9",
        description="+1 к внимательности на контрольных (только для вида).",
    ),
    Cosmetic(
        "headphones",
        "hat",
        "Наушники",
        unlock_level=2,
        swatch="#a855f7",
        description="Для фокуса и любимой музыки.",
    ),
    Cosmetic(
        "cap",
        "hat",
        "Кепка «Квант»",
        unlock_level=2,
        price=50,
        swatch="#22d3ee",
        description="Лимитированный мерч школьного хакатона.",
    ),
    Cosmetic(
        "crown",
        "hat",
        "Корона лидера",
        unlock_level=4,
        swatch="#fbbf24",
        description="Только для тех, кто добрался до уровня Мастера.",
    ),
    Cosmetic(
        "halo",
        "hat",
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
        rarity="legendary",
    ),
    # ----- Расширение каталога. Чтобы добавить предмет: строка сюда + рисунок в
    # frontend/src/components/heroItems.tsx (или стиль рамки в styles/frames.css).
    # Формат: _c(id, слот, название, уровень, цена, цвет-образец[, описание[, редкость]])
    # Новые причёски и цвета волос
    _c("hair_long", "hair", "Длинные", 1, 0, "#6b3f2b"),
    _c("hair_bald", "hair", "Лысый", 1, 0, "#f0c6a3"),
    _c("hair_afro", "hair", "Афро", 2, 0, "#2e2038"),
    _c("hair_braids", "hair", "Косички", 2, 40, "#c25a2e"),
    _c("hair_mohawk", "hair", "Ирокез", 3, 70, "#8b5cf6", "Для тех, кто любит выделяться."),
    _c("hair_pink", "hair_color", "Розовый", 1, 0, "#ec4899"),
    _c("hair_white", "hair_color", "Белый", 2, 0, "#e5e7eb"),
    _c("hair_green", "hair_color", "Зелёный", 2, 30, "#22c55e"),
    _c("hair_teal", "hair_color", "Бирюзовый", 3, 40, "#14b8a6"),
    # Одежда
    _c("hoodie_red", "outfit", "Красное худи", 1, 0, "#ef4444"),
    _c("hoodie_green", "outfit", "Зелёное худи", 1, 0, "#22c55e"),
    _c("uniform_school", "outfit", "Школьная форма", 1, 0, "#1e3a8a", "Строго и аккуратно."),
    _c("tshirt_print", "outfit", "Футболка со смайлом", 1, 30, "#e2e8f0"),
    _c("tracksuit", "outfit", "Спортивный костюм", 2, 40, "#1d4ed8", "Для физкультуры и переменок."),
    _c("labcoat", "outfit", "Лабораторный халат", 2, 60, "#f1f5f9", "Для химии и физики."),
    _c("sweater_deer", "outfit", "Свитер с оленем", 2, 60, "#b91c1c", "Тёплый и праздничный."),
    _c("kimono", "outfit", "Кимоно", 3, 90, "#0e7490"),
    _c("pirate_coat", "outfit", "Пиратский камзол", 3, 90, "#7f1d1d", "Йо-хо-хо и домашнее задание."),
    _c("hero_suit", "outfit", "Костюм супергероя", 3, 100, "#2563eb", "С плащом. Для спасения оценок."),
    _c("armor_bronze", "outfit", "Бронзовая броня", 4, 120, "#b87333"),
    _c("spacesuit", "outfit", "Скафандр", 4, 140, "#e5e7eb", "К звёздам через знания."),
    _c("armor_gold", "outfit", "Золотая броня", 5, 180, "#fbbf24", "Блестящий итог года."),
    # Головные уборы
    _c("hat_none", "hat", "Без головного убора", 1, 0, "#2a1b3d"),
    _c("hat_cap", "hat", "Бейсболка", 1, 0, "#ef4444"),
    _c("hat_beanie", "hat", "Шапка-бини", 1, 0, "#14b8a6"),
    _c("hat_party", "hat", "Праздничный колпак", 2, 30, "#ec4899"),
    _c("hat_chef", "hat", "Поварской колпак", 2, 40, "#f8fafc"),
    _c("hat_cowboy", "hat", "Ковбойская шляпа", 2, 50, "#b45309"),
    _c("hat_cat", "hat", "Кошачьи ушки", 2, 60, "#6b7280"),
    _c("hat_flowers", "hat", "Цветочный венок", 3, 60, "#84cc16"),
    _c("hat_bunny", "hat", "Заячьи уши", 3, 70, "#f9a8d4"),
    _c("hat_wizard", "hat", "Колпак волшебника", 3, 90, "#6d28d9", "Звёздный колпак для зелий по химии."),
    _c("hat_pirate", "hat", "Треуголка", 4, 110, "#1f2937"),
    _c("hat_laurel", "hat", "Лавровый венок", 4, 120, "#65a30d", "Награда победителю."),
    _c("hat_astro", "hat", "Шлем астронавта", 5, 200, "#bae6fd"),
    # Лицо
    _c("face_none", "face", "Без украшений", 1, 0, "#2a1b3d"),
    _c("glasses_round", "face", "Круглые очки", 1, 0, "#67e8f9"),
    _c("mustache", "face", "Усы", 1, 30, "#2b1a12"),
    _c("shades", "face", "Солнцезащитные очки", 2, 40, "#111827"),
    _c("glasses_3d", "face", "3D-очки", 2, 50, "#ef4444"),
    _c("eyepatch", "face", "Пиратская повязка", 3, 60, "#111827"),
    _c("monocle", "face", "Монокль", 3, 70, "#fbbf24"),
    _c("mask_hero", "face", "Маска героя", 4, 100, "#dc2626"),
    _c("glasses_pixel", "face", "Пиксельные очки", 4, 120, "#111827", "Deal with it."),
    _c("vr_headset", "face", "VR-шлем", 5, 160, "#22d3ee"),
    # Аксессуары: шея, грудь, спина
    _c("scarf", "accessory", "Шарф", 1, 0, "#f472b6"),
    _c("bow", "accessory", "Бант", 1, 0, "#ec4899"),
    _c("badge", "accessory", "Значок", 1, 0, "#fbbf24"),
    _c("bowtie", "accessory", "Бабочка", 1, 30, "#dc2626"),
    _c("backpack", "accessory", "Рюкзак", 1, 40, "#16a34a"),
    _c("tie", "accessory", "Галстук", 2, 40, "#dc2626"),
    _c("necklace", "accessory", "Ожерелье", 3, 70, "#a5f3fc"),
    _c("medal", "accessory", "Медаль", 3, 80, "#fbbf24", "За победу в олимпиаде."),
    _c("cape", "accessory", "Плащ", 4, 130, "#dc2626"),
    _c("wings", "accessory", "Крылья", 5, 220, "#f8fafc", "Почти летаешь."),
    # Рамки (рисуются в styles/frames.css)
    _c("frame_checker", "frame", "Шахматная клетка", 1, 0, "#e2e8f0"),
    _c("frame_stars", "frame", "Звёздная рамка", 2, 40, "#fde047"),
    _c("frame_leaf", "frame", "Рамка из листьев", 2, 40, "#22c55e"),
    _c("frame_bolt", "frame", "Молнии", 3, 60, "#facc15"),
    _c("frame_wave", "frame", "Волны", 3, 70, "#38bdf8"),
    _c("frame_digital", "frame", "Цифровая рамка", 4, 100, "#22c55e"),
    _c("frame_flame", "frame", "Пиксельное пламя", 4, 120, "#f97316"),
    _c("frame_rainbow", "frame", "Радужная рамка", 5, 150, "#ec4899"),
]

COSMETIC_BY_ID = {item.id: item for item in COSMETICS}

NOTHING_IDS = {"none", "hat_none", "face_none"}


def cosmetic_sort_key(item: Cosmetic) -> tuple:
    """Единый порядок предметов в гардеробе и онбординге (источник истины).

    «Ничего» первым; затем уровень открытия по возрастанию; внутри уровня
    бесплатные, затем по цене; затем редкость (обычное -> легендарное); затем
    название по алфавиту (ё как е). Статус владения не влияет, поэтому порядок
    не меняется после покупки или надевания.
    """
    return (
        item.id not in NOTHING_IDS,
        item.unlock_level,
        item.price,
        RARITIES.index(item.rarity_id),
        item.name.casefold().replace("ё", "е"),
        item.id,
    )


SORTED_COSMETICS = sorted(COSMETICS, key=cosmetic_sort_key)

# Предметы, которые в старых аватарах хранились в слоте accessory (id не менялись).
LEGACY_ACCESSORY_SLOT = {
    "glasses": "face",
    "headphones": "hat",
    "cap": "hat",
    "crown": "hat",
    "halo": "hat",
}

AVATAR_KEYS = {
    "skin": "skin",
    "hair": "hair",
    "hairColor": "hair_color",
    "outfit": "outfit",
    "hat": "hat",
    "face": "face",
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
    if not isinstance(value, dict):
        value = {}
    # Старые образы без новых слотов (hat, face) получают значения по умолчанию.
    avatar = dict(DEFAULT_AVATAR)
    for key, slot in AVATAR_KEYS.items():
        candidate = value.get(key)
        item = COSMETIC_BY_ID.get(candidate) if isinstance(candidate, str) else None
        if item is not None and item.type == slot:
            avatar[key] = candidate
    # Миграция «на лету»: раньше очки, наушники, кепка, корона и нимб лежали в
    # accessory. Переносим их в face или hat, если тот слот ещё пуст.
    legacy = value.get("accessory")
    target = LEGACY_ACCESSORY_SLOT.get(legacy) if isinstance(legacy, str) else None
    if target and avatar[target] == DEFAULT_AVATAR[target]:
        avatar[target] = legacy
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
