# Школьный герой

Мини-приложение для MAX. Ученик получает опыт (XP) за задания, олимпиады, кружки и помощь одноклассникам, растёт в уровнях и рейтингах класса и школы. Педагог создаёт задания и подтверждает выполнение, директор регистрирует школу, раздаёт коды классов и видит сводку по школе.

Технологии: Python 3.11+, FastAPI, SQLite; React, TypeScript, Vite. Вход - подписанный `initData` из MAX (HMAC-SHA256).

## Режимы (`APP_MODE`)

| Режим | Назначение | Вход | База |
| --- | --- | --- | --- |
| `prod` (по умолчанию) | боевой сервер; нужен `MAX_BOT_TOKEN` | подписанный `initData` | `school_hero.db` |
| `demo` | витрина с выдуманными данными, только локально | `X-Client-Id`, общий профиль | `school_hero_demo.db` |
| `sandbox` | локальная проверка регистрации школы, база стирается при старте, только loopback | `X-Client-Id`, каждый id - отдельный пользователь | `school_hero_sandbox.db` |

Пустой токен режим не переключает: `prod` без `MAX_BOT_TOKEN` не стартует. Подробности: [docs/configuration.md](docs/configuration.md).

## Быстрый старт (локально)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

cd frontend
npm ci
npm run build
cd ..

Copy-Item .env.example .env     # для показа поставьте APP_MODE=demo
python app.py                   # http://127.0.0.1:8000
```

Проверка регистрации школы без MAX: `npm run sandbox` (после сборки фронтенда), открыть <http://127.0.0.1:8010/>.

Тесты:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

Развёртывание на `m.ospab.org` (systemd + nginx): `sudo LE_EMAIL=you@example.com bash deploy/deploy.sh`, подробности в [docs/deploy.md](docs/deploy.md).

## Документация

- [docs/architecture.md](docs/architecture.md) - устройство, авторизация, схема БД, права, расчёт XP и рейтингов, ограничения
- [docs/setup-school.md](docs/setup-school.md) - подключение школы: регистрация директора, коды, подтверждение, лимиты
- [docs/roles.md](docs/roles.md) - что делают ученик, педагог, директор, администратор платформы; печать и PDF
- [docs/deploy.md](docs/deploy.md) - сервер, nginx, systemd, сертификат, резервные копии, Docker
- [docs/configuration.md](docs/configuration.md) - все переменные окружения, режимы, пути данных
- [docs/api.md](docs/api.md) - справочник API
- [docs/development.md](docs/development.md) - разработка, песочница, тесты, соглашения, пределы масштабирования

## Структура

```text
app.py        точка входа FastAPI
backend/      API, логика, база, авторизация
frontend/     React-интерфейс (сборка в static/)
landing/      страница-портал (/portal)
deploy/       deploy.sh, nginx, systemd
docker/       Caddyfile
tools/        list_max_users.py, run_sandbox.py
tests/        pytest
docs/         документация
```
