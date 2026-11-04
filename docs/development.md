# Разработка

Оглавление:

- [Структура репозитория](#структура-репозитория)
- [Запуск](#запуск)
- [Песочница](#песочница)
- [Демо-режим](#демо-режим)
- [Тесты](#тесты)
- [Сборка фронтенда](#сборка-фронтенда)
- [Как добавить](#как-добавить)
- [Соглашения по CSS](#соглашения-по-css)
- [Масштабирование и пределы](#масштабирование-и-пределы)

## Структура репозитория

```text
app.py                 FastAPI-приложение и запуск
backend/               api, service, registration, game, db, security, config, ratelimit, catalog, demo_seed
frontend/              React + TypeScript + Vite (src/App.tsx, screens/, components/, styles/)
static/                сборка фронтенда (создаётся npm run build, не в git)
landing/               страница-портал (/portal)
tests/                 pytest: api, registration, security, portal, sandbox
tools/                 list_max_users.py, run_sandbox.py
deploy/                deploy.sh, конфиг nginx, юнит systemd
docker/                Caddyfile
docs/                  документация
data/                  базы SQLite и catalog.json (базы не в git)
catalog.example.json   образец каталога школ
.env.example           образец настроек
package.json           скрипты dev:frontend, dev:backend, sandbox
```

Фронтенд: `src/App.tsx` - состояние, маршрутизация по вкладкам и все действия; `src/api.ts` - клиент API (заголовки `X-Max-Init-Data`/`X-Client-Id`); `src/max.ts` - обёртка над MAX Bridge; `src/types.ts` - типы состояния; `src/game.ts` - подписи категорий; `src/sandbox.ts` - тестовые пользователи песочницы; `src/screens/` - экраны; `src/components/` - общие компоненты.

## Запуск

Python 3.11+ (в Docker-образе 3.12), Node.js 20.19+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Для локальной работы в `.env` обычно `APP_MODE=demo` (токен не нужен). Для `prod` нужен `MAX_BOT_TOKEN`, и войти можно только изнутри MAX.

Бэкенд:

```powershell
python app.py          # http://127.0.0.1:8000, HOST/PORT из окружения
```

Разработка фронтенда с горячей перезагрузкой: бэкенд на :8000 и Vite на :5173, который проксирует `/api` на 8000 (`frontend/vite.config.ts`):

```powershell
python app.py
cd frontend
npm install
npm run dev            # http://127.0.0.1:5173
```

Корневые скрипты: `npm run dev:backend` (`python app.py`), `npm run dev:frontend`.

Чтобы бэкенд сам отдавал сборку, нужен `SERVE_FRONTEND=true` и собранный `static/`.

## Песочница

`APP_MODE=sandbox` - локальный режим для проверки сценария регистрации школы без MAX. Запуск (сначала собрать фронтенд, песочница раздаёт `static/`):

```powershell
cd frontend; npm run build; cd ..
npm run sandbox        # то же: python tools/run_sandbox.py
```

Открыть <http://127.0.0.1:8010/>. `tools/run_sandbox.py` выставляет `APP_MODE=sandbox`, `HOST=127.0.0.1`, `SERVE_FRONTEND=1` и порт 8010 (если не задан `PORT`); интерпретатор берётся из `.venv`.

Свойства:

- Личность определяется только по `X-Client-Id`, подпись не проверяется. Каждый id - отдельный пользователь-ученик ([architecture.md](architecture.md#определение-личности-по-режимам)).
- Панель «Песочница» вверху интерфейса: выпадающий список тестовых пользователей и кнопка «Новый пользователь». Список и активный пользователь хранятся в `localStorage` браузера (`school-hero:sandbox-users`, `school-hero:sandbox-active`); в подписи показываются «Пользователь N — Имя, роль» после регистрации (если имя осталось по умолчанию «Герой», только «Пользователь N, роль»). Рядом с панелью показана подсказка про стирание базы. Переключение пользователей позволяет играть директора, педагога и учеников в одной вкладке.
- База `data/school_hero_sandbox.db` **стирается при каждом старте** (вместе с `-wal`/`-shm`). Чтобы сохранить, `SANDBOX_KEEP_DATA=1`.
- `GET /api/health` в sandbox возвращает `boot_id`: случайное значение на каждый старт со стёртой базой; при `SANDBOX_KEEP_DATA=1` значение стабильно (хранится в `data/sandbox_boot_id` рядом с базой и обновляется, если файл базы удалён). Браузер запоминает `boot_id` (`school-hero:sandbox-boot`); если он изменился, список тестовых пользователей сбрасывается до чистого «Пользователь 1», а в панели появляется сообщение «Сервер песочницы перезапущен, тестовые пользователи сброшены».
- Данных нет: ни демо, ни каталога, `DEFAULT_CLASS_ID` отключён.
- Запуск разрешён только при `HOST` `127.0.0.1`, `localhost` или `::1`, иначе ошибка старта.
- `/api/demo/role` и `/api/demo/reset` возвращают 403, школы создаются как в боевом режиме, `verified` в состоянии `false`.
- Модерация: `SCHOOL_APPROVAL=manual` и `PLATFORM_ADMIN_CLIENT_IDS=<id>` (значение `X-Client-Id` пользователя; смотрите в `localStorage` ключ `school-hero:sandbox-users`).

Сценарий проверки регистрации:

1. Пользователь 1: «Я представляю школу» - «Новая школа», заполнить название, город, классы. Аккаунт становится директором, на вкладке «Коды» видны коды классов.
2. «Новый пользователь» (пользователь 2): «Я ученик», ввести код ученика класса, пройти шаги (имя, класс, герой).
3. «Новый пользователь» (пользователь 3): «Я представляю школу» - «Код педагога», ввести код педагога. Появится кабинет педагога этого класса.
4. Вернуться к пользователю 1 и проверить, что в сводке школы появился ученик, а у класса - педагог.
5. Проверка модерации: запустить с `SCHOOL_APPROVAL=manual` и `PLATFORM_ADMIN_CLIENT_IDS` администратора; школа не видна в каталоге, пока администратор не подтвердит её на вкладке «Заявки».

Не запускайте песочницу на сервере: см. [configuration.md](configuration.md#режимы-работы).

## Демо-режим

`APP_MODE=demo` - витрина. Что делает код:

- При старте `seed_demo_database` (`backend/demo_seed.py`) заполняет пустую базу `school_hero_demo.db`: 5 школ Великого Новгорода, 8 классов, выдуманные ученики с XP и сериями, педагог, активные и архивные задания, заявки. Если в базе уже есть школы, сид не выполняется.
- Любой валидный `X-Client-Id` даёт одного общего пользователя «Глеб Кузнецов». Его профиль заполняется функцией `seed_demo_progress` (XP 420, 120 искр, серия 6, одна заявка на проверке) при первом обращении.
- Переключатель роли `POST /api/demo/role` меняет `users.preview_role`; эффективная роль берётся из него. Для педагога используется класс по умолчанию (`DEFAULT_CLASS_ID=1`), директор видит школу этого класса.
- `POST /api/demo/reset` сбрасывает профиль зрителя к исходному.
- Панель «Демо» с кнопками ролей и «Сбросить» показывается только если `state.mode == "demo"`.
- Регистрация школы и управление классами в демо недоступны (403/404).

База демо отдельная, на боевую базу не влияет. Не публикуйте демо-режим. Модуль `demo_seed.py` импортируется всегда, но сид выполняется только при `APP_MODE=demo`.

## Тесты

Тесты используют временные базы SQLite и не трогают `data/`.

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

Файлы: `test_api.py` (демо и MAX-режим, роли, магазин, миграции), `test_registration.py` (регистрация, коды, лимиты, модерация, миграция схемы, необязательный каталог), `test_security.py` (подпись `initData`, личность), `test_portal.py` (страница-портал), `test_sandbox.py` (режим песочницы). Фикстуры - `tests/conftest.py`.

Известно: `test_portal.py::test_root_route_provides_portal_link` ожидает JSON на `GET /`, то есть `SERVE_FRONTEND=false`. `app.py` загружает `.env` при импорте, а в `.env.example` и в рабочем `.env` стоит `SERVE_FRONTEND=true` - тогда тест падает. Запускайте с `SERVE_FRONTEND=false` (в окружении или в `.env`):

```powershell
$env:SERVE_FRONTEND = "false"; .\.venv\Scripts\python.exe -m pytest tests -q
```

Тесты фронтенда в репозитории отсутствуют; типы проверяются при сборке (`tsc --noEmit`).

## Сборка фронтенда

```powershell
cd frontend
npm ci
npm run build          # tsc --noEmit && vite build, вывод в ../static (emptyOutDir)
```

Отдельная проверка типов: `npm run typecheck`. Каталог `static/` очищается при каждой сборке и не хранится в git; на сервер его нужно доставить ([deploy.md](deploy.md)).

## Как добавить

### Категорию заданий

1. `backend/game.py`: добавить пару `ключ: подпись` в `CATEGORIES` (проверка категории при создании берётся отсюда).
2. `backend/service.py`, `_director_data`: определить, к какому «направлению» относится категория. Не перечисленные категории (`else`) попадают в волонтёрство.
3. `frontend/src/types.ts`: добавить значение в `ChallengeCategory`.
4. `frontend/src/game.ts` (подпись, иконка, тон) и список `CATEGORIES` в `screens/TeacherChallengesScreen.tsx`; при необходимости подсказки в `components/ChallengeSheet.tsx`.
5. Цвет трека/направления - токены `--track-*` в `styles/app.css`, если нужен.
6. При необходимости `ACHIEVEMENTS`/`achievements_for` в `game.py`.

Словарь `XP_VALUES` в `game.py` в расчётах не используется. Допустимые награды заданий задаёт `ALLOWED_XP` в `create_challenge` и поле `xp` модели `ChallengeBody` (`backend/api.py`).

### Предмет гардероба

1. `backend/game.py`: новый `Cosmetic(id, type, name, unlock_level, price, swatch, description)` в `COSMETICS`. Типы: `skin`, `hair`, `hair_color`, `outfit`, `accessory`, `frame`. `price > 0` - покупается за искры, иначе открывается уровнем.
2. Фронтенд рисует героя из идентификаторов: добавьте отображение в `components/PixelHero.tsx` (цвета одежды и т. п.) и, если нужно, в `screens/WardrobeScreen.tsx`.
3. Сам список предметов фронтенд получает из `state.cosmetics`, дублировать его не надо. Для нового типа предмета добавьте ключ в `AVATAR_KEYS` и тип в `CosmeticType` (`types.ts`).

### Эндпоинт

1. Логика - функция в `backend/service.py` (или `registration.py`): принимает `conn`, пользователя (`viewer`), `settings`, проверяет права (`effective_role`, `can_manage_class`, `_require_director_of`), бросает `GameError(сообщение, статус)`.
2. Модель тела (pydantic) и маршрут в `backend/api.py` с `ctx: Context = Depends(get_context)`. После функции вызвать `ctx.conn.commit()` и вернуть `{"state": build_state(...)}`.
3. Если нужны новые данные в состоянии - `build_state` и тип `GameState` в `frontend/src/types.ts`.
4. Метод в `frontend/src/api.ts`, обработчик в `App.tsx` (через `mutate`), UI.
5. Тест в `tests/`, строка в [api.md](api.md).
6. Новая колонка или таблица: `SCHEMA` и `_migrate_columns` в `backend/db.py` ([architecture.md](architecture.md#миграции)).

## Соглашения по CSS

Стили лежат в `frontend/src/styles/`. Глобальные токены и базовые компоненты - `app.css` (подключается в `main.tsx`); остальные файлы подключаются экранами.

| Префикс | Файл | Область |
| --- | --- | --- |
| `st-` | `student.css` | экраны ученика |
| `tc-` | `teacher.css` | кабинет педагога и сводка директора |
| `pf-` | `profile.css` | профиль |
| `ob-` | `onboarding.css` | регистрация, мастер ученика, формы школы |
| `wd-` | `wardrobe.css` | гардероб |
| `su-` | `setup.css` | управление школой и заявки; там же панель `sb-` (песочница) |
| `pr-` | `print.css` | листы печати |

Токены - CSS-переменные на `:root` в `app.css` (`--bg-app`, `--bg-card`, `--line`, `--text-primary|secondary|muted`, `--sferum-blue`, `--ok`, `--warn`, `--danger`, `--track-*`, `--radius-*`, `--space-*`, `--tap`, `--focus-ring`). Тёмная тема переопределяет их в `:root[data-theme='dark']`. Не вводите цвета в обход токенов. Файл `portal.css` пуст; страница-портал использует `landing/styles.css`.

## Масштабирование и пределы

Реализация рассчитана на один процесс и одну базу SQLite.

- **SQLite, один писатель.** WAL позволяет параллельное чтение, запись одна; ожидание блокировки до 15 секунд (`busy_timeout`).
- **Один процесс.** `app.py` запускает `uvicorn.run` без воркеров. Не добавляйте `--workers` без доработки: лимиты в `backend/ratelimit.py` живут в памяти процесса. Перезапуск их обнуляет, а несколько процессов считают раздельно, и защита от подбора кодов и создания школ ослабляется пропорционально числу процессов.
- **Состояние собирается заново** на каждый `GET /api/state` и каждую мутацию (ответ содержит всё состояние). Рейтинги агрегируют SQL по всем классам платформы; ответ режется до 100 записей (классы и школы), но расчёт идёт по всем. У педагога выбираются все выполнения его класса.
- **Рейтинги**: топ-100 классов и школ плюс класс зрителя; список учеников - весь класс.
- **Часовой пояс** фиксирован (UTC+3), неделя считается по нему для всех школ.
- Измерений нагрузки и порогов в репозитории нет.

Когда переходить на PostgreSQL и несколько воркеров - признаки (не числа из кода):

- в журнале появляются ошибки `database is locked` / запросы ждут записи;
- время ответа `/api/state` растёт вместе с числом классов и школ;
- нужна отказоустойчивость или несколько серверов приложения;
- нужна репликация и резервное копирование без остановки.

Что потребуется: заменить `backend/db.py` и SQL, использующий особенности SQLite (`INSERT OR IGNORE`, `ON CONFLICT`, `PRAGMA`, `datetime('now')`, `REPLACE`/`UPPER` на кириллице), на слой доступа к PostgreSQL; вынести счётчики лимитов во внешнее хранилище (например, Redis) или базу; после этого можно запускать несколько воркеров.

См. также: [architecture.md](architecture.md), [configuration.md](configuration.md).
