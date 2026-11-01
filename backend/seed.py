"""Demo content for the School Hero prototype.

The seed describes a plausible 8А class from Novgorod: classmates, a teacher,
weekly activity and three submissions waiting for review. It is intentionally
rich so the product can be evaluated without a month of real usage.
"""

from __future__ import annotations

import random
from datetime import timedelta

from .game import (
    DEFAULT_AVATAR,
    DEMO_AVATAR,
    deadline_in,
    deadline_today,
    deadline_week,
    dump_avatar,
    dump_owned,
    level_for,
    now_local,
    today_local,
    utc_sql,
)


SCHOOLS = [
    ("ГОАУ «Новгородский Кванториум»", "Великий Новгород"),
    ("Гимназия №4", "Великий Новгород"),
    ("Школа №36", "Великий Новгород"),
    ("Лицей №2", "Великий Новгород"),
    ("Гимназия №2", "Великий Новгород"),
]

CLASSES = [
    # key, school index, name, weekly goal
    ("kvant-8a", 0, "8А", 1600),
    ("kvant-8b", 0, "8Б", 1500),
    ("kvant-9a", 0, "9А", 1800),
    ("gym4-8v", 1, "8В", 1500),
    ("gym4-10a", 1, "10А", 1700),
    ("school36-9b", 2, "9Б", 1500),
    ("licey-11a", 3, "11А", 1800),
    ("gym2-7b", 4, "7Б", 1400),
]

# name, last name, class key, xp, streak, last_active_days_ago
STUDENTS = [
    ("Маргарита", "Пантелеева", "kvant-8a", 610, 12, 0),
    ("Георгий", "Сыралёв", "kvant-8a", 545, 8, 0),
    ("Пётр", "Рассадников", "kvant-8a", 480, 5, 0),
    ("Захар", "Иванов", "kvant-8a", 390, 7, 1),
    ("Софья", "Лебедева", "kvant-8a", 355, 3, 0),
    ("Артём", "Соколов", "kvant-8a", 310, 2, 2),
    ("Алиса", "Морозова", "kvant-8a", 270, 4, 0),
    ("Матвей", "Волков", "kvant-8a", 180, 1, 5),
    ("Ева", "Никитина", "kvant-8a", 140, 1, 4),
    ("Демид", "Орлов", "kvant-8a", 95, 2, 1),
    ("Варвара", "Крылова", "kvant-8a", 60, 1, 3),
    # 8Б
    ("Илья", "Фёдоров", "kvant-8b", 520, 9, 0),
    ("Ксения", "Волкова", "kvant-8b", 450, 4, 0),
    ("Тимофей", "Зайцев", "kvant-8b", 390, 3, 1),
    ("Полина", "Смирнова", "kvant-8b", 360, 5, 0),
    ("Даниил", "Кузнецов", "kvant-8b", 340, 2, 2),
    ("Анна", "Павлова", "kvant-8b", 300, 1, 3),
    # 9А
    ("Михаил", "Егоров", "kvant-9a", 980, 18, 0),
    ("Анастасия", "Кириллова", "kvant-9a", 870, 14, 0),
    ("Владислав", "Орлов", "kvant-9a", 790, 6, 1),
    ("Дарья", "Мельникова", "kvant-9a", 760, 9, 0),
    ("Кирилл", "Гусев", "kvant-9a", 720, 5, 0),
    # 8В
    ("Егор", "Никитин", "gym4-8v", 430, 6, 0),
    ("Валерия", "Соколова", "gym4-8v", 390, 4, 1),
    ("Роман", "Белов", "gym4-8v", 360, 3, 0),
    ("Кира", "Ершова", "gym4-8v", 340, 2, 2),
    ("Никита", "Комаров", "gym4-8v", 320, 1, 3),
    ("Милана", "Фомина", "gym4-8v", 300, 1, 4),
    # 10А
    ("Арсений", "Титов", "gym4-10a", 820, 11, 0),
    ("Виктория", "Зимина", "gym4-10a", 730, 8, 0),
    ("Степан", "Крылов", "gym4-10a", 690, 6, 0),
    ("Елизавета", "Дроздова", "gym4-10a", 640, 4, 1),
    ("Лев", "Соловьёв", "gym4-10a", 600, 3, 2),
    # 9Б
    ("Максим", "Лебедев", "school36-9b", 450, 7, 0),
    ("Алина", "Громова", "school36-9b", 400, 5, 0),
    ("Денис", "Воробьёв", "school36-9b", 380, 2, 1),
    ("Юлия", "Романова", "school36-9b", 350, 3, 2),
    ("Вячеслав", "Борисов", "school36-9b", 320, 1, 3),
    # 11А
    ("Андрей", "Попов", "licey-11a", 1500, 22, 0),
    ("Мария", "Ковалёва", "licey-11a", 1400, 17, 0),
    ("Фёдор", "Морозов", "licey-11a", 1300, 11, 0),
    ("Ольга", "Семёнова", "licey-11a", 1000, 8, 1),
    # 7Б
    ("Иван", "Алексеев", "gym2-7b", 350, 4, 0),
    ("Полина", "Григорьева", "gym2-7b", 320, 3, 1),
    ("Семён", "Фролов", "gym2-7b", 300, 2, 2),
    ("Арина", "Калинина", "gym2-7b", 230, 1, 4),
]

CURRENT_CHALLENGES = [
    {
        "title": "Домашнее задание по алгебре",
        "description": "Сдай домашку до 23:59. Педагог подтвердит выполнение в один тап.",
        "category": "homework",
        "xp": 20,
        "kind": "daily",
        "deadline": deadline_today(),
    },
    {
        "title": "Помоги однокласснику с задачей",
        "description": "Объясни тему другу или разберите задачу вместе. Напиши, кому помог.",
        "category": "help",
        "xp": 40,
        "kind": "daily",
        "deadline": deadline_today(),
    },
    {
        "title": "Кружок или секция",
        "description": "Сходи на занятие после уроков: робототехника, спорт, музыка — что угодно.",
        "category": "club",
        "xp": 30,
        "kind": "daily",
        "deadline": deadline_today(),
    },
    {
        "title": "Неделя без пропусков",
        "description": "Отмечайся каждый день и не пропускай школьные задания. Серия важнее скорости.",
        "category": "streak",
        "xp": 50,
        "kind": "weekly",
        "deadline": deadline_week(),
    },
    {
        "title": "Олимпиада по информатике",
        "description": "Школьный этап уже начался. Прикрепи результат или напиши, где участвовал.",
        "category": "olympiad",
        "xp": 100,
        "kind": "weekly",
        "deadline": deadline_week(),
    },
    {
        "title": "Доклад по истории",
        "description": "Подготовь короткий доклад о Новгородской республике к пятнице.",
        "category": "weekly",
        "xp": 50,
        "kind": "weekly",
        "deadline": deadline_in(2),
    },
    {
        "title": "Школьный хакатон «Идея»",
        "description": "Собери команду и придумай проект для школы. Участие — уже опыт.",
        "category": "event",
        "xp": 30,
        "kind": "event",
        "deadline": deadline_in(5),
    },
    {
        "title": "Помощь в школьном событии",
        "description": "Помоги организовать перемену, ярмарку или концерт. Расскажи, что сделал.",
        "category": "help",
        "xp": 40,
        "kind": "weekly",
        "deadline": deadline_week(),
    },
]

ARCHIVED_CHALLENGES = [
    ("Домашнее задание по геометрии", "homework", 20, 2),
    ("Помощь на уроке", "help", 40, 3),
    ("Разбор задач с одноклассником", "help", 40, 5),
]


def _avatar_for(index: int, xp: int) -> dict[str, str]:
    level = level_for(xp)
    skins = ["skin_light", "skin_warm", "skin_tan", "skin_deep"]
    hairs = ["hair_short", "hair_curls", "hair_bob", "hair_pony", "hair_buzz"]
    hair_colors = ["hair_dark", "hair_brown", "hair_ginger", "hair_blonde", "hair_violet", "hair_blue"]
    outfits_by_level = {
        1: ["hoodie_violet", "hoodie_cyan"],
        2: ["sweater_gold", "jacket_blue", "hoodie_violet"],
        3: ["cloak_violet", "jacket_blue"],
        4: ["armor_silver", "cloak_violet"],
        5: ["suit_cosmic", "armor_silver"],
    }
    accessories_by_level = {
        1: ["none", "glasses"],
        2: ["headphones", "glasses", "none"],
        3: ["headphones", "glasses"],
        4: ["crown", "headphones"],
        5: ["halo", "crown"],
    }
    frames = ["frame_wood", "frame_neon", "frame_gold", "frame_galaxy"]
    return {
        "skin": skins[index % len(skins)],
        "hair": hairs[index % len(hairs)],
        "hairColor": hair_colors[(index * 2 + 1) % len(hair_colors)],
        "outfit": outfits_by_level[level][index % len(outfits_by_level[level])],
        "accessory": accessories_by_level[level][index % len(accessories_by_level[level])],
        "frame": frames[min(level - 1, len(frames) - 1)],
    }


def _event_reasons() -> list[tuple[str, int, str]]:
    return [
        ("Домашнее задание по алгебре", 20, "homework"),
        ("Кружок по робототехнике", 30, "club"),
        ("Помощь однокласснику", 40, "help"),
        ("Недельный челлендж", 50, "weekly"),
        ("Олимпиада по информатике", 100, "olympiad"),
        ("Школьное событие", 30, "event"),
    ]


def _insert_activity(conn, user_id: int, streak: int, last_active_days_ago: int) -> None:
    end = today_local() - timedelta(days=last_active_days_ago)
    for offset in range(max(1, min(streak, 30))):
        day = end - timedelta(days=offset)
        conn.execute(
            "INSERT OR IGNORE INTO activity_days (user_id, day) VALUES (?, ?)",
            (user_id, day.isoformat()),
        )


def _seed_events(conn, user_id: int, xp: int, rng: random.Random) -> None:
    if xp <= 0:
        return
    weekly_target = max(20, min(170, xp // 4 + 10))
    today_index = today_local().weekday()
    reasons = _event_reasons()
    remaining = weekly_target
    created_events = 0
    while remaining > 0 and created_events < 4:
        reason, amount, category = reasons[rng.randrange(len(reasons))]
        if amount > remaining and remaining < 20:
            break
        day_offset = rng.randint(0, max(0, today_index))
        moment = now_local() - timedelta(
            days=day_offset, hours=rng.randint(0, 8), minutes=rng.randint(0, 59)
        )
        conn.execute(
            "INSERT INTO xp_events (user_id, amount, reason, category, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, reason, category, utc_sql(moment)),
        )
        remaining -= amount
        created_events += 1


def seed_database(conn) -> None:
    exists = conn.execute("SELECT COUNT(*) AS n FROM schools").fetchone()["n"]
    if exists:
        return

    school_ids: list[int] = []
    for name, city in SCHOOLS:
        cursor = conn.execute(
            "INSERT INTO schools (name, city) VALUES (?, ?)", (name, city)
        )
        school_ids.append(int(cursor.lastrowid))

    class_ids: dict[str, int] = {}
    for key, school_index, name, goal in CLASSES:
        cursor = conn.execute(
            "INSERT INTO classes (school_id, name, weekly_goal) VALUES (?, ?, ?)",
            (school_ids[school_index], name, goal),
        )
        class_ids[key] = int(cursor.lastrowid)

    user_ids: dict[str, int] = {}
    rng = random.Random(42)
    for index, (first, last, class_key, xp, streak, last_seen) in enumerate(STUDENTS):
        avatar = _avatar_for(index, xp)
        cursor = conn.execute(
            """
            INSERT INTO users
                (first_name, last_name, username, role, class_id, xp, sparks,
                 streak, last_active_date, avatar, owned, onboarded)
            VALUES (?, ?, ?, 'student', ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                first,
                last,
                f"{first.lower()}_{last.lower()}",
                class_ids[class_key],
                xp,
                20 + (xp // 50) * 5,
                streak,
                (today_local() - timedelta(days=last_seen)).isoformat(),
                dump_avatar(avatar),
                dump_owned([]),
            ),
        )
        user_ids[f"{first} {last}"] = int(cursor.lastrowid)
        _insert_activity(conn, int(cursor.lastrowid), streak, last_seen)
        _seed_events(conn, int(cursor.lastrowid), xp, rng)

    teacher_cursor = conn.execute(
        """
        INSERT INTO users
            (first_name, last_name, username, role, class_id, xp, sparks,
             streak, last_active_date, avatar, owned, onboarded)
        VALUES ('Константин', 'Зверев', 'teacher_zverev', 'teacher', ?, 0, 0,
                0, NULL, ?, '[]', 1)
        """,
        (class_ids["kvant-8a"], dump_avatar(DEFAULT_AVATAR)),
    )
    teacher_id = int(teacher_cursor.lastrowid)

    current_ids: dict[str, int] = {}
    for item in CURRENT_CHALLENGES:
        cursor = conn.execute(
            """
            INSERT INTO challenges
                (class_id, title, description, category, xp, kind, deadline,
                 created_by, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                class_ids["kvant-8a"],
                item["title"],
                item["description"],
                item["category"],
                item["xp"],
                item["kind"],
                item["deadline"],
                teacher_id,
            ),
        )
        current_ids[item["title"]] = int(cursor.lastrowid)

    archived_ids: dict[str, int] = {}
    for title, category, xp, days_ago in ARCHIVED_CHALLENGES:
        deadline = (now_local() - timedelta(days=days_ago - 1)).isoformat()
        cursor = conn.execute(
            """
            INSERT INTO challenges
                (class_id, title, description, category, xp, kind, deadline,
                 created_by, active)
            VALUES (?, ?, 'Архивное задание демо-класса', ?, ?, 'weekly', ?, ?, 0)
            """,
            (class_ids["kvant-8a"], title, category, xp, deadline, teacher_id),
        )
        archived_ids[title] = int(cursor.lastrowid)

    # A few students have already completed the visible challenges. Their XP is
    # already reflected in users.xp; these rows only make participant counts real.
    participant_map = {
        "Домашнее задание по алгебре": ["Маргарита Пантелеева", "Георгий Сыралёв", "Софья Лебедева", "Артём Соколов", "Алиса Морозова"],
        "Неделя без пропусков": ["Маргарита Пантелеева", "Георгий Сыралёв", "Захар Иванов"],
        "Олимпиада по информатике": [],
        "Доклад по истории": [],
    }
    for title, names in participant_map.items():
        for name in names:
            conn.execute(
                "INSERT OR IGNORE INTO completions "
                "(user_id, challenge_id, status, proof, created_at, reviewed_at, reviewed_by) "
                "VALUES (?, ?, 'approved', 'Подтверждено в демо-классе', ?, ?, ?)",
                (
                    user_ids[name],
                    current_ids[title],
                    utc_sql(now_local() - timedelta(days=1)),
                    utc_sql(now_local() - timedelta(hours=20)),
                    teacher_id,
                ),
            )

    # Three submissions waiting for the teacher. This powers the one-tap review.
    pending = [
        (
            "Маргарита Пантелеева",
            "Олимпиада по информатике",
            "Призёр школьного этапа, диплом №42. Решение задачи про графы.",
            2,
        ),
        (
            "Пётр Рассадников",
            "Помоги однокласснику с задачей",
            "Разобрали геометрию с Демидом, он сдал самостоятельную на 4.",
            5,
        ),
        (
            "Ева Никитина",
            "Кружок или секция",
            "Записалась в школьный театр, первое занятие прошло сегодня.",
            26,
        ),
    ]
    for name, title, proof, hours_ago in pending:
        moment = now_local() - timedelta(hours=hours_ago)
        conn.execute(
            "INSERT INTO completions "
            "(user_id, challenge_id, status, proof, created_at) "
            "VALUES (?, ?, 'pending', ?, ?)",
            (user_ids[name], current_ids[title], proof, utc_sql(moment)),
        )

    # Archived history for the demo viewer is inserted per viewer by
    # seed_demo_progress(); the challenge ids are looked up by title.
    conn.commit()


def seed_demo_progress(conn, user_id: int, class_id: int) -> None:
    """Give a freshly created demo viewer a lived-in profile."""
    now = now_local()
    archived = {
        row["title"]: row["id"]
        for row in conn.execute(
            "SELECT id, title FROM challenges WHERE active = 0 AND class_id = ?",
            (class_id,),
        ).fetchall()
    }
    teacher = conn.execute(
        "SELECT id FROM users WHERE role = 'teacher' AND class_id = ? LIMIT 1",
        (class_id,),
    ).fetchone()
    teacher_id = int(teacher["id"]) if teacher else None

    weekday_index = today_local().weekday()
    history = [
        ("Домашнее задание по геометрии", 2, 20, "Домашнее задание по геометрии"),
        ("Помощь на уроке", 3, 40, "Помощь на уроке"),
        ("Разбор задач с одноклассником", 5, 40, "Разбор задач с одноклассником"),
    ]
    for title, days_ago, xp, reason in history:
        challenge_id = archived.get(title)
        if not challenge_id:
            continue
        moment = now - timedelta(days=days_ago)
        conn.execute(
            "INSERT OR IGNORE INTO completions "
            "(user_id, challenge_id, status, proof, created_at, reviewed_at, reviewed_by) "
            "VALUES (?, ?, 'approved', 'Демо-достижение', ?, ?, ?)",
            (
                user_id,
                challenge_id,
                utc_sql(moment),
                utc_sql(moment + timedelta(hours=2)),
                teacher_id,
            ),
        )
        category = "homework" if xp == 20 else "help"
        # Keep demo XP inside the current week even when today is Monday.
        event_moment = now - timedelta(
            days=min(days_ago, weekday_index), hours=1 + xp % 5
        )
        conn.execute(
            "INSERT INTO xp_events (user_id, amount, reason, category, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, xp, reason, category, utc_sql(event_moment)),
        )

    # One extra weekly XP event, visible in the feed.
    weekly_moment = now - timedelta(days=min(1, weekday_index), hours=3)
    conn.execute(
        "INSERT INTO xp_events (user_id, amount, reason, category, created_at) "
        "VALUES (?, 50, 'Недельный челлендж', 'weekly', ?)",
        (user_id, utc_sql(weekly_moment)),
    )

    # A submission that is currently waiting for the teacher.
    report = conn.execute(
        "SELECT id FROM challenges WHERE title = 'Доклад по истории' AND active = 1 LIMIT 1"
    ).fetchone()
    if report:
        conn.execute(
            "INSERT OR IGNORE INTO completions "
            "(user_id, challenge_id, status, proof, created_at) "
            "VALUES (?, ?, 'pending', 'Прочитал главу 5, выписал даты и подготовил план доклада.', ?)",
            (user_id, int(report["id"]), utc_sql(now - timedelta(hours=3))),
        )

    # Six-day streak, with today active.
    for offset in range(6):
        day = today_local() - timedelta(days=offset)
        conn.execute(
            "INSERT OR IGNORE INTO activity_days (user_id, day) VALUES (?, ?)",
            (user_id, day.isoformat()),
        )

    conn.execute(
        """
        UPDATE users SET
            xp = 420,
            sparks = 120,
            streak = 6,
            last_active_date = ?,
            avatar = ?,
            owned = ?,
            onboarded = 1
        WHERE id = ?
        """,
        (
            today_local().isoformat(),
            dump_avatar(DEMO_AVATAR),
            dump_owned(["hoodie_cyan"]),
            user_id,
        ),
    )
    conn.commit()
