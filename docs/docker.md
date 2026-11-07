# Запуск в Docker

Весь проект собирается и запускается в Docker: образ содержит собранный фронтенд, бэкенд и страницу-портал; данные лежат в томе. Приложение слушает порт 8000 внутри контейнера и привязано к `127.0.0.1` хоста; HTTPS отдаёт nginx на хосте (основной путь для `app.example.org`) или Caddy из профиля `proxy`.

## Оглавление

- [Что входит](#что-входит)
- [Требования](#требования)
- [Быстрый старт](#быстрый-старт)
- [Деплой на сервер с nginx](#деплой-на-сервер-с-nginx)
- [Вариант с Caddy](#вариант-с-caddy)
- [Конфигурация](#конфигурация)
- [Данные, каталог школ, резервные копии](#данные-каталог-школ-резервные-копии)
- [Обновление и откат](#обновление-и-откат)
- [Бот MAX в Docker](#бот-max-в-docker)
- [Переход с systemd на Docker](#переход-с-systemd-на-docker)
- [Что не запускается в Docker](#что-не-запускается-в-docker)
- [Безопасность](#безопасность)
- [Закрепление базовых образов](#закрепление-базовых-образов)
- [Типичные проблемы](#типичные-проблемы)

## Что входит

| Файл | Назначение |
| --- | --- |
| `Dockerfile` | Две стадии. `node:22.14.0-bookworm-slim` собирает фронтенд (`npm ci`, `npm run build`). `python:3.12.10-slim-bookworm` ставит только runtime-зависимости из `requirements.txt` (pytest из `requirements-dev.txt` в образ не попадает), копирует `app.py`, `backend/`, `tools/`, `landing/`, `catalog.example.json` и собранный `static/`. Запуск `python app.py` с `umask 077` от пользователя `app` (uid 10001), порт 8000, том `/data`, `HEALTHCHECK` на `/api/health`. В образе заданы `APP_MODE=prod` и `CATALOG_FILE=/data/catalog.json`. |
| `docker-compose.yml` | Сервисы `app` (боевой), `demo` (профиль `demo`), `caddy` (профиль `proxy`). |
| `.dockerignore` | В образ не попадают `.env`, `data/`, `static/`, `tests/`, `docs/`, `deploy/`, `docker/`, `dist/`, `catalog.json`, `node_modules`, `requirements-dev.txt`, `tools/package.py`. |
| `docker/Caddyfile` | Конфиг Caddy (`caddy:2.10.0-alpine`): `{$APP_DOMAIN}`, сжатие zstd/gzip, лимит тела запроса 6 МБ, заголовки HSTS, `X-Content-Type-Options`, `Referrer-Policy`, без `Server`, `reverse_proxy app:8000`. |
| `deploy/deploy-docker.sh` | Скрипт для сервера: проверка `.env`, сборка, запуск, nginx и сертификат. |

Сервисы:

| Сервис | Профиль | Режим | Порт хоста | Том |
| --- | --- | --- | --- | --- |
| `app` | нет (запускается по умолчанию) | `prod` | `127.0.0.1:8000` | `school_hero_data` |
| `demo` | `demo` | `demo` (выдуманные данные) | `127.0.0.1:8001` | `school_hero_demo_data` |
| `caddy` | `proxy` | - | `80`, `443`, `443/udp` | `caddy_data`, `caddy_config` |

Имена томов получают префикс проекта: `school-hero_school_hero_data` и так далее.

## Требования

- Docker Engine 24 или новее и плагин Docker Compose v2 (`docker compose version`).
- Для боевого запуска: токен бота из business.max.ru в `.env` и домен с HTTPS, который указывает на сервер. MAX открывает мини-приложения только по HTTPS.

## Быстрый старт

Из корня проекта.

```bash
cp .env.example .env
```

В `.env` задайте `MAX_BOT_TOKEN` (без него `docker compose` отказывается запускать `app`). Остальные переменные описаны в [configuration.md](configuration.md).

```bash
docker compose up -d --build
```

Проверка:

```bash
docker compose ps
```

```bash
curl http://127.0.0.1:8000/api/health
```

Ответ должен быть `{"status":"ok","mode":"prod"}`, статус контейнера `healthy`. Откуда угодно, кроме MAX, прод-версия покажет экран «Откройте приложение внутри MAX»: вход возможен только с подписью MAX. `/docs`, `/redoc` и `/openapi.json` в проде отключены.

### Демо без MAX

Витрина с выдуманными школой, учениками и педагогом, своя база и свой том. Токен не нужен, `.env` не читается.

```bash
docker compose --profile demo up -d --build demo
```

Откройте <http://127.0.0.1:8001/>. Остановить и стереть данные витрины:

```bash
docker compose --profile demo down -v
```

Внимание: `down -v` удаляет все тома проекта, включая боевую базу. Если нужен только демо-том, остановите сервис `docker compose --profile demo stop demo` и удалите том `docker volume rm school-hero_school_hero_demo_data`.

## Деплой на сервер с nginx

Приложение в контейнере, nginx и сертификат Let's Encrypt на хосте. Тот же шаблон nginx (`deploy/nginx.conf.template`), что и в варианте с systemd: прокси на `127.0.0.1:8000`.

Подготовка:

1. DNS-запись `app.example.org` указывает на сервер, порты 80 и 443 открыты.
2. Проект скопирован на сервер (git clone или копирование папки), в корне лежит `.env` с `MAX_BOT_TOKEN`. Строки `APP_MODE` в `.env` быть не должно или она равна `prod`.
3. Если раньше был вариант systemd, остановите его: `systemctl disable --now school-hero` (оба используют порт 8000). Данные переносятся отдельно, см. [Переход с systemd](#переход-с-systemd-на-docker).

Запуск:

```bash
sudo bash deploy/deploy-docker.sh --domain app.example.org --email you@example.com
```

Скрипт:

1. выбирает домен (`--domain` или `DOMAIN`, затем `PUBLIC_URL` из `.env`, затем вопрос в терминале; при необходимости добавляет `PUBLIC_URL` в `.env`), проверяет Docker, `.env`, токен и отсутствие `APP_MODE` не `prod`, отказывается работать при запущенном сервисе `school-hero`;
2. выполняет `docker compose up -d --build app` и ждёт статус `healthy` (до двух минут), при неудаче печатает последние строки логов;
3. ставит nginx и certbot, получает сертификат методом webroot без остановки nginx, создаёт конфиг из `deploy/nginx.conf.template` (на сервере без IPv6 удаляет строки `listen [::]`) и перезагружает nginx; после продления сертификата nginx перезагружается автоматически;
4. проверяет `https://app.example.org/api/health`.

Повторный запуск безопасен: образ пересобирается, контейнер пересоздаётся, данные в томе сохраняются.

## Вариант с Caddy

Если nginx на хосте не нужен, Caddy сам получает и продлевает сертификат. Порты 80 и 443 на хосте должны быть свободны.

В `.env` добавьте домен без `https://`:

```bash
APP_DOMAIN=app.example.org
```

```bash
docker compose --profile proxy up -d --build
```

Caddy стартует после того, как `app` станет `healthy`. Сертификаты хранятся в томе `caddy_data`.

Заголовки и лимит тела те же, что в nginx-шаблоне. Ограничения частоты запросов в стандартной сборке Caddy нет (нужен сторонний модуль `caddy-ratelimit`); если это важно, используйте вариант с nginx на хосте.

## Конфигурация

Контейнер `app` читает `.env` (`env_file`), но значения из блока `environment` в `docker-compose.yml` важнее. Они зафиксированы и не меняются через `.env`:

| Переменная | Значение | Зачем |
| --- | --- | --- |
| `APP_MODE` | `prod` | `.env` не может включить `demo` или `sandbox` в боевом контейнере |
| `MAX_BOT_TOKEN` | из `.env`, обязательна | сборка падает с понятным сообщением, если токена нет |
| `CATALOG_FILE` | `/data/catalog.json` | необязательный начальный каталог школ |
| `HOST`, `PORT` | `0.0.0.0`, `8000` | слушать внутри контейнера |
| `STATIC_DIR` | `/app/static` | собранный фронтенд |
| `DATABASE_PATH` | `/data/school_hero.db` | база в томе |
| `SERVE_FRONTEND` | `true` | отдавать фронтенд |

Остальные переменные (`INIT_DATA_MAX_AGE`, `TEACHER_MAX_IDS`, `DIRECTOR_MAX_IDS`, `SCHOOL_APPROVAL`, `PLATFORM_ADMIN_MAX_IDS`, переменные бота и другие) берутся из `.env`; полный список с умолчаниями в [configuration.md](configuration.md). После изменения `.env` пересоздайте контейнер:

```bash
docker compose up -d app
```

Просто `restart` переменные не перечитывает.

## Данные, каталог школ, резервные копии

База SQLite лежит в томе `school-hero_school_hero_data` по пути `/data/school_hero.db` (режим WAL, рядом файлы `-wal` и `-shm`). Школы можно создавать в приложении через регистрацию директора; каталог `catalog.json` необязателен.

Положить каталог школ (корневая ФС контейнера только для чтения, поэтому файл кладётся в том через вспомогательный контейнер):

```bash
docker run --rm -v school-hero_school_hero_data:/data -v "$PWD":/src:ro alpine sh -c "cp /src/catalog.json /data/catalog.json && chown 10001:10001 /data/catalog.json && chmod 600 /data/catalog.json"
```

```bash
docker compose restart app
```

Каталог применяется при старте. Образец: `catalog.example.json`.

Фото-подтверждения хранятся в `/data/uploads` (в том же томе, `DATA_DIR/uploads`). Лимит одного фото 5 МБ.

### Резервная копия

Резервная копия должна включать и базу, и каталог `/data/uploads`; без него в работах пропадут фото.

Копия через API SQLite корректна и при работающем приложении:

```bash
docker compose exec app python -c "import sqlite3; s=sqlite3.connect('/data/school_hero.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d); d.close()"
```

```bash
docker compose cp app:/data/backup.db ./backup-$(date +%F).db
```

```bash
docker compose exec app rm /data/backup.db
```

Каталог фото копируется целиком:

```bash
docker compose cp app:/data/uploads ./uploads-$(date +%F)
```

Храните копии вне сервера.

### Восстановление

```bash
docker compose stop app
```

```bash
docker run --rm -v school-hero_school_hero_data:/data -v "$PWD":/b alpine sh -c "rm -f /data/school_hero.db-wal /data/school_hero.db-shm && cp /b/backup-2026-11-04.db /data/school_hero.db && chown 10001:10001 /data/school_hero.db"
```

```bash
docker compose up -d app
```

Подставьте имя своего файла копии.

## Обновление и откат

```bash
git pull
```

Сохраните текущий образ для отката и пересоберите:

```bash
docker tag school-hero:latest school-hero:previous
```

```bash
docker compose up -d --build app
```

Откат на предыдущий образ:

```bash
docker tag school-hero:previous school-hero:latest
```

```bash
docker compose up -d --no-build app
```

Миграции базы применяются автоматически при старте (безопасные `ALTER TABLE`). Перед обновлением сделайте резервную копию.

Полезные команды:

```bash
docker compose logs -f app
```

```bash
docker compose ps
```

```bash
docker compose down
```

`down` без `-v` останавливает и удаляет контейнеры, тома с данными остаются.

## Бот MAX в Docker

Приветствие бота и кнопка мини-приложения описаны в [bot.md](bot.md). Переменные бота берутся из `.env`. Команды управления подпиской выполняются внутри контейнера, где они читают те же переменные:

```bash
docker compose exec app python tools/max_bot.py me
```

```bash
docker compose exec app python tools/max_bot.py subscribe
```

Если запросы к API MAX падают с ошибкой проверки сертификата (платформа использует сертификат Минцифры), положите PEM-файл на хост и подключите его в контейнер файлом `docker-compose.override.yml` рядом с `docker-compose.yml`:

```yaml
services:
  app:
    environment:
      MAX_CA_BUNDLE: /certs/russian-ca.pem
    volumes:
      - ./certs/russian-ca.pem:/certs/russian-ca.pem:ro
```

Файл `certs/russian-ca.pem` должен существовать до запуска, иначе Docker создаст на его месте каталог.

## Переход с systemd на Docker

1. Остановите сервис и скопируйте базу: `systemctl disable --now school-hero`.
2. Создайте том и положите в него базу:

```bash
docker volume create school-hero_school_hero_data
```

```bash
docker run --rm -v school-hero_school_hero_data:/data -v /var/lib/school-hero:/old:ro alpine sh -c "cp /old/school_hero.db /data/ && chown 10001:10001 /data/school_hero.db"
```

3. Запустите `deploy/deploy-docker.sh`. Файл `-wal` старой базы переносить не нужно, если сервис остановлен штатно.

Каталог `/var/lib/school-hero/catalog.json`, если он был, копируется командой `docker compose cp` (см. выше).

## Что не запускается в Docker

Режим `sandbox` (песочница для проверки регистрации) в контейнер не рассчитан: он отказывается стартовать, если `HOST` не loopback, а контейнеру нужно слушать `0.0.0.0`. Песочницу запускайте на хосте: `npm run sandbox`, см. [development.md](development.md). Для показа без MAX используйте профиль `demo`.

## Безопасность

- Порты `app` и `demo` опубликованы только на `127.0.0.1`. Наружу выходит только прокси (nginx или Caddy).
- Контейнер работает от непривилегированного пользователя (uid 10001), с `no-new-privileges` и без Linux-capabilities (`cap_drop: ALL`).
- Корневая ФС `app` и `demo` только для чтения (`read_only: true`). Писать можно в том `/data` (база, каталог) и в `tmpfs` `/tmp` (64 МБ, временные файлы SQLite). Байткод Python не пишется (`PYTHONDONTWRITEBYTECODE=1`). Если в будущем приложение начнёт писать в другой каталог (например, загрузки), его нужно разместить в `/data` или добавить отдельный том.
- Ресурсы: `pids_limit: 128`, `mem_limit: 512m`. Приложение - один процесс uvicorn; при нехватке памяти контейнер будет перезапущен (`docker inspect` покажет `OOMKilled`).
- Файлы базы в томе создаются с правами 600 (`umask 077`).
- В образе нет `pytest` и прочих инструментов разработки: только `requirements.txt`.
- `.env` не попадает в образ (`.dockerignore`) и передаётся только как переменные окружения; не коммитьте его.
- Профиль `demo` принимает вход без подписи MAX. Не публикуйте его порт наружу и не запускайте на публичном сервере.
- Токен бота в логи не пишется; для логов настроена ротация (`10m` × 3 файла).

## Закрепление базовых образов

Базовые образы указаны точными тегами: `node:22.14.0-bookworm-slim`, `python:3.12.10-slim-bookworm` (в `Dockerfile`), `caddy:2.10.0-alpine` (в `docker-compose.yml`). Тег можно перезаписать в реестре, поэтому для полной повторяемости закрепите образ ещё и по digest:

```bash
docker pull python:3.12.10-slim-bookworm
docker inspect --format '{{index .RepoDigests 0}}' python:3.12.10-slim-bookworm
# python@sha256:<64 hex>
```

и впишите его рядом с тегом (тег остаётся для читаемости, решает digest):

```dockerfile
FROM python:3.12.10-slim-bookworm@sha256:<64 hex> AS runtime
```

То же для `node` и `caddy` (`image: caddy:2.10.0-alpine@sha256:...`). Digest мультиархитектурного образа (index) подходит для всех платформ. Обновление: раз в месяц или по бюллетеням безопасности меняйте тег на свежий патч-релиз той же ветки (3.12.x, 22.x, 2.x), заново получайте digest, пересобирайте `docker compose build --pull` и проверяйте `/api/health`. Frontend требует Node `^20.19` или `>=22.12` (Vite).

## Типичные проблемы

| Симптом | Причина и решение |
| --- | --- |
| `docker compose up` падает с «Задайте MAX_BOT_TOKEN в .env» | В `.env` нет токена или пустой. |
| Контейнер `unhealthy` или перезапускается | `docker compose logs app`. Частая причина: нет токена, либо `.env` испорчен. |
| `port is already allocated` (8000) | Порт занят systemd-сервисом `school-hero` или другим процессом. |
| `pip install` при сборке: `Temporary failure in name resolution` | В контейнерах сборки не работает DNS (часто WSL или VPN). Соберите с сетью хоста: `docker build --network=host -t school-hero:latest .` или `python tools/package.py --network host`. Постоянно: задайте DNS Docker в `/etc/docker/daemon.json` (`{"dns": ["1.1.1.1", "8.8.8.8"]}`) и перезапустите Docker. |
| `/portal` отдаёт 404 | Образ собран из старой версии без каталога `landing/`: пересоберите `docker compose build --no-cache app`. |
| `Read-only file system` в логах `app` | Приложение пытается писать вне `/data` и `/tmp`. Временно уберите `read_only: true` в `docker-compose.override.yml` и сообщите разработчику, какой путь нужен |
| `docker compose cp ... app:/data/...` падает с `container rootfs is marked read-only` | Корневая ФС только для чтения; копируйте в том через `docker run --rm -v school-hero_school_hero_data:/data ...` (см. «Данные») |
| Ошибка доступа к `/data` | Том создан с другим владельцем: `docker run --rm -v school-hero_school_hero_data:/data alpine chown -R 10001:10001 /data`. |
| Изменения в `.env` не применяются | Нужно пересоздать контейнер: `docker compose up -d app`. |
| `https://app.example.org` отдаёт 502 | Контейнер не запущен или не `healthy`: `docker compose ps`. |
| Сертификат не получается | DNS не указывает на сервер или порт 80 закрыт; проверьте `certbot` и `nginx -t`. |
| Проверить синтаксис compose-файла | `docker compose config` |
