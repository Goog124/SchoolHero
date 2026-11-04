# Развёртывание на сервере

Основной путь для `m.ospab.org` - **systemd + nginx** на Debian/Ubuntu через `deploy/deploy.sh`. Вариант с Docker описан отдельно в [конце документа](#вариант-docker).

Оглавление:

- [Требования](#требования)
- [Подготовка](#подготовка)
- [deploy/deploy.sh по шагам](#deploydeploysh-по-шагам)
- [Конфигурация nginx и systemd](#конфигурация-nginx-и-systemd)
- [Сертификат: получение и продление](#сертификат-получение-и-продление)
- [Обновление версии](#обновление-версии)
- [Резервное копирование и восстановление](#резервное-копирование-и-восстановление)
- [Логи и проверка](#логи-и-проверка)
- [Типичные проблемы](#типичные-проблемы)
- [Вариант Docker](#вариант-docker)

## Требования

- Сервер Debian/Ubuntu с root-доступом (скрипт использует `apt-get`, `systemctl`).
- DNS: запись A (и AAAA, если есть IPv6) `m.ospab.org` указывает на сервер.
- Открыты порты 80 и 443. Порт 80 нужен и после выпуска сертификата: на нём продление и редирект на HTTPS.
- Порты 80/443 не заняты другим веб-сервером.
- Пакеты ставит сам скрипт: `python3 python3-venv python3-pip rsync nginx certbot curl`.
- Токен бота MAX (`MAX_BOT_TOKEN`).
- Версия nginx с директивой `http2 on;` (используется в `deploy/m.ospab.org.conf`). Директиву поддерживает nginx 1.25.1 и новее; на более старых пакетах `nginx -t` завершится ошибкой, и конфиг придётся поправить (убрать `http2 on;`, добавить `http2` к `listen 443 ssl`).
- Сборка фронтенда (`static/index.html`) или Node.js 20.19+ на сервере.

Домен и пути зашиты в `deploy/deploy.sh` (`DOMAIN`, `APP_DIR=/opt/school-hero`, `DATA_DIR=/var/lib/school-hero`, `APP_USER=schoolhero`) и в `deploy/m.ospab.org.conf`. Для другого домена правьте оба файла и переименуйте конфиг: скрипт берёт `deploy/$DOMAIN.conf`.

## Подготовка

### 1. Собрать фронтенд

`static/` исключён из git, поэтому собирается на вашей машине (или на сервере, если там есть npm):

```bash
cd frontend
npm ci
npm run build      # пишет в ../static
```

### 2. Подготовить `.env`

Скопируйте `.env.example` в `.env` и задайте минимум:

```text
APP_MODE=prod
MAX_BOT_TOKEN=<токен бота>
SCHOOL_APPROVAL=auto
PLATFORM_ADMIN_MAX_IDS=<MAX id администраторов, если нужно>
```

Правила:

- `APP_MODE` в серверном `.env` должен быть `prod`. По документации systemd значения из `EnvironmentFile` перекрывают `Environment=` юнита, и `APP_MODE=demo` или `sandbox` в `.env` включит режим без проверки подписи на публичном домене. Скрипт этого не проверяет.
- Пустой `MAX_BOT_TOKEN` скрипт отклонит; сервис без токена в `prod` не стартует.
- Готовый `.env` скрипт берёт из `/opt/school-hero/.env` (если уже есть), иначе из корня проекта, и ставит права 600.
- Полный список переменных: [configuration.md](configuration.md).

### 3. Каталог школ - необязательно

`catalog.json` не нужен: школы создаёт директор ([setup-school.md](setup-school.md)). Если файл `catalog.json` лежит в корне проекта и в `/var/lib/school-hero/catalog.json` ещё нет, скрипт скопирует его (права 640). Существующий в `/var/lib/school-hero` файл не перезаписывается.

### 4. Перенести проект на сервер

Любым способом (git, `scp`, `rsync`), включая собранный `static/` и `.env`; `node_modules`, `.venv`, `data` переносить не нужно. Пример:

```bash
rsync -a --exclude node_modules --exclude .venv --exclude .git --exclude data ./ root@server:/root/school-hero-src/
```

## deploy/deploy.sh по шагам

Запуск на сервере от root из корня проекта:

```bash
cd /root/school-hero-src
sudo LE_EMAIL=you@example.com bash deploy/deploy.sh
```

`LE_EMAIL` - адрес для Let's Encrypt; без него регистрация идёт без почты (`--register-unsafely-without-email`). Скрипт остановится при первой ошибке (`set -euo pipefail`).

1. **Проверка root.** Иначе выход.
2. **`.env`.** Выбор источника (`/opt/school-hero/.env` или `<проект>/.env`), проверка, что `MAX_BOT_TOKEN` непуст.
3. **Проверка старой базы.** Если `/var/lib/school-hero/school_hero.db` существует и в `users` есть строки без `max_user_id` (остатки демо-данных или старой версии), скрипт останавливается и просит остановить сервис и удалить базу. Обход: `ALLOW_LEGACY_DB=1 sudo -E bash deploy/deploy.sh` (осознанно). Проверка выполняется через `python3` до установки пакетов.
4. **Фронтенд.** Если `static/index.html` нет, выполняет `npm ci && npm run build` (нужен npm), иначе пропускает. **Уже существующий `static/` не пересобирается** - при обновлении собирайте заново сами.
5. **Пакеты.** `apt-get update` и установка зависимостей.
6. **Пользователь и каталоги.** Системный пользователь `schoolhero` (без оболочки), `/opt/school-hero`, `/var/lib/school-hero`, `/var/www/certbot`.
7. **Копирование.** `rsync -a --delete` проекта в `/opt/school-hero`, кроме `.git`, `.venv`, `.idea`, `node_modules`, `__pycache__`, `.pytest_cache`, `data`, `.env`, `catalog.json`. Выкладывается и `docs/`. Данные вне `/opt`, поэтому не затрагиваются.
8. **`.env` и каталог.** Копирование `.env` (если в `/opt` его нет), необязательного `catalog.json`; владелец `schoolhero`; права `.env` 600.
9. **Python.** Виртуальное окружение `/opt/school-hero/.venv`, `pip install -r requirements.txt`.
10. **systemd.** Установка `school-hero.service`, `daemon-reload`, `enable`, `restart`.
11. **nginx и сертификат.** Если сертификата ещё нет: временный конфиг на порту 80 с `/.well-known/acme-challenge/`, `certbot certonly --webroot`. Затем установка `deploy/m.ospab.org.conf` в `/etc/nginx/conf.d/`; если в системе нет IPv6 (`/proc/net/if_inet6` отсутствует), строки `listen [::]` удаляются; `nginx -t`, `reload`.
12. **Хук продления.** Создаёт `/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh` (`systemctl reload nginx`).
13. **Проверка.** Через 3 секунды `curl` на `http://127.0.0.1:8000/api/health` и `https://m.ospab.org/api/health`. Ответ `{"status":"ok","mode":"prod"}`.

Скрипт идемпотентен: повторный запуск - способ обновления.

## Конфигурация nginx и systemd

### `deploy/m.ospab.org.conf`

- Порт 80: `/.well-known/acme-challenge/` отдаётся из `/var/www/certbot`, остальное - редирект 301 на HTTPS.
- Порт 443: TLS 1.2/1.3, сертификаты `/etc/letsencrypt/live/m.ospab.org/`, HSTS (`max-age=31536000`), `client_max_body_size 2m`, gzip для css/js/json/svg.
- `location /` проксирует на `http://127.0.0.1:8000` с заголовками `Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`, таймаут чтения 60 с.
- Установленная копия лежит в `/etc/nginx/conf.d/m.ospab.org.conf`; правки делайте в репозитории и перезапускайте скрипт, иначе они потеряются (в частности, удаление `listen [::]`).

### `deploy/school-hero.service`

- Запуск от `schoolhero`, рабочий каталог `/opt/school-hero`, команда `/opt/school-hero/.venv/bin/python app.py`, `Restart=on-failure` с паузой 3 с.
- `EnvironmentFile=/opt/school-hero/.env`, а также `Environment=`: `APP_MODE=prod`, `CATALOG_FILE=/var/lib/school-hero/catalog.json`, `HOST=127.0.0.1`, `PORT=8000`, `SERVE_FRONTEND=true`, `STATIC_DIR=/opt/school-hero/static`, `DATA_DIR=/var/lib/school-hero`.
- Усиление: `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`, `ProtectHome`, запись разрешена только в `/var/lib/school-hero`.
- Один процесс uvicorn без `--workers`; это важно из-за лимитов в памяти ([development.md](development.md#масштабирование-и-пределы)).

Управление:

```bash
sudo systemctl status school-hero
sudo systemctl restart school-hero
sudo systemctl stop school-hero
```

## Сертификат: получение и продление

Первый выпуск делает `deploy.sh` методом webroot (nginx остаётся запущенным). Вручную то же:

```bash
sudo certbot certonly --webroot -w /var/www/certbot -d m.ospab.org --non-interactive --agree-tos --email you@example.com
```

Продление: пакет certbot ставит `certbot.timer`; проверка:

```bash
systemctl list-timers | grep certbot
sudo certbot renew --dry-run
```

После продления хук из `renewal-hooks/deploy/` перезагружает nginx. Для продления порт 80 должен быть доступен снаружи и `/.well-known/acme-challenge/` - отдаваться из `/var/www/certbot`.

## Обновление версии

1. Соберите фронтенд заново (`cd frontend && npm ci && npm run build`).
2. Сделайте резервную копию базы ([ниже](#резервное-копирование-и-восстановление)).
3. Перенесите новую версию проекта на сервер (см. «Подготовка», шаг 4). `.env` в `/opt/school-hero` не перезаписывается.
4. Запустите `sudo bash deploy/deploy.sh`.
5. Проверьте `curl https://m.ospab.org/api/health` и `journalctl -u school-hero -n 50`.

Схема базы мигрирует сама при старте ([architecture.md](architecture.md#миграции)); откатить миграцию нельзя - только вернуть копию.

## Резервное копирование и восстановление

База работает в режиме WAL: рядом с `school_hero.db` лежат `-wal` и `-shm`. Простое копирование одного `.db` при работающем сервисе может дать неполную копию. Копируйте средствами SQLite.

Команда `sqlite3` не ставится скриптом: `sudo apt-get install sqlite3`. Копию делайте от имени `schoolhero`, чтобы не создать файлы базы с владельцем root.

```bash
sudo install -d -o schoolhero -g schoolhero /var/lib/school-hero/backups
sudo -u schoolhero sqlite3 /var/lib/school-hero/school_hero.db \
  ".backup '/var/lib/school-hero/backups/school_hero-$(date +%F).db'"
```

Без `sqlite3` то же средствами Python:

```bash
sudo -u schoolhero python3 - <<'PY'
import sqlite3, datetime
src = sqlite3.connect("/var/lib/school-hero/school_hero.db")
dst = sqlite3.connect(f"/var/lib/school-hero/backups/school_hero-{datetime.date.today()}.db")
src.backup(dst)
dst.close(); src.close()
PY
```

Альтернатива - остановить сервис и скопировать файл вместе с `-wal` и `-shm`.

Восстановление:

```bash
sudo systemctl stop school-hero
sudo rm -f /var/lib/school-hero/school_hero.db-wal /var/lib/school-hero/school_hero.db-shm
sudo cp /var/lib/school-hero/backups/school_hero-ГГГГ-ММ-ДД.db /var/lib/school-hero/school_hero.db
sudo chown schoolhero:schoolhero /var/lib/school-hero/school_hero.db
sudo systemctl start school-hero
```

Копии храните вне сервера. Расписания резервного копирования в проекте нет; настройте cron/systemd-timer сами. Сохраняйте также `.env` (там токен бота) и `catalog.json`, если используется.

## Логи и проверка

Сервис пишет в stdout/stderr, журнал - в journald:

```bash
sudo journalctl -u school-hero -n 100 --no-pager
sudo journalctl -u school-hero -f
sudo tail -n 50 /var/log/nginx/error.log
```

Проверки:

```bash
curl -s http://127.0.0.1:8000/api/health        # напрямую в сервис
curl -s https://m.ospab.org/api/health          # через nginx
sudo nginx -t
```

`/api/health` не требует авторизации и возвращает `status` и `mode`. В боевой среде `mode` должен быть `prod`.

## Типичные проблемы

| Симптом | Причина и решение |
| --- | --- |
| `nginx -t` падает на `listen [::]:...` | Сервер без IPv6. Скрипт удаляет такие строки автоматически; при ручной правке удалите `listen [::]:80;` и `listen [::]:443 ssl;` |
| `nginx -t` падает на `http2 on` | nginx старше 1.25.1. См. требования |
| 502 Bad Gateway от nginx | Сервис не запущен или падает. `systemctl status school-hero`, `journalctl -u school-hero -n 100`, `curl http://127.0.0.1:8000/api/health` |
| Сервис перезапускается по кругу, в журнале `APP_MODE=prod требует MAX_BOT_TOKEN` | Токен в `.env` пуст. Заполните `MAX_BOT_TOKEN` и `systemctl restart school-hero` |
| В журнале `APP_MODE должен быть ...` / `SCHOOL_APPROVAL должен быть ...` | Опечатка в значении переменной |
| В журнале `CatalogError` | Повреждён `catalog.json`; исправьте или удалите файл |
| Certbot: порт 80 занят (при `--standalone`) | Скрипт использует webroot и порт не занимает. Для ручного `--standalone` остановите nginx или другой процесс (`ss -ltnp \| grep ':80 '`); лучше используйте `--webroot` |
| Certbot не проходит проверку | DNS не указывает на сервер, порт 80 закрыт, либо временный конфиг не загрузился (`nginx -t`) |
| Скрипт: «найдено пользователей без MAX id» | В базе остатки демо-данных. `systemctl stop school-hero; rm /var/lib/school-hero/school_hero.db*`, затем снова скрипт. Для осознанного пропуска `ALLOW_LEGACY_DB=1` |
| Приложение открывается, но в `/api/health` `mode` не `prod` | В серверном `.env` другой `APP_MODE`. Исправьте и перезапустите сервис |
| Все запросы возвращают 401 «Данные MAX устарели» | Приложение открыто дольше `INIT_DATA_MAX_AGE` (по умолчанию 1 час), либо расходятся часы сервера и клиента. Откройте приложение заново, проверьте время сервера (`timedatectl`) |
| Интерфейс показывает «Откройте приложение внутри MAX» | В `prod` приложение работает только внутри MAX, в обычном браузере вход невозможен |
| `GET /` отдаёт JSON `schoolhero-api` | `SERVE_FRONTEND` не включён |
| `GET /` отдаёт 503 «Frontend is not built» | В `STATIC_DIR` нет `index.html`; соберите фронтенд и перезапустите скрипт |
| `/portal` возвращает 404 в Docker | Каталог `landing/` не копируется в образ |

## Вариант Docker

Не является основным путём для `m.ospab.org`; описывает файлы `Dockerfile`, `docker-compose.yml`, `docker/Caddyfile`.

`Dockerfile` - двухстадийная сборка: на Node 22 собирается фронтенд, на `python:3.12-slim` запускается `python app.py` от пользователя `app` (uid 10001), порт 8000, том `/data`, `HEALTHCHECK` на `/api/health`.

`docker-compose.yml`:

- Сервис `app`: `APP_MODE=prod`, `MAX_BOT_TOKEN` берётся из `.env` (если пуст - compose не стартует), база `/data/school_hero.db`, каталог `/data/catalog.json`, `SERVE_FRONTEND=true`. Порт публикуется только на `127.0.0.1:8000`. Данные в томе `school_hero_data`.
- Сервис `caddy` (профиль `proxy`): `caddy:2-alpine`, порты 80, 443, 443/udp, конфиг `docker/Caddyfile` (`{$APP_DOMAIN}` с `reverse_proxy app:8000`), домен из `APP_DOMAIN` (по умолчанию `school-hero.example.com`), сертификаты Caddy получает сам. Запускается после того, как `app` здоров.

Запуск без прокси (за собственным reverse proxy на хосте):

```bash
cp .env.example .env          # заполните MAX_BOT_TOKEN, остальное по необходимости
docker compose up -d --build
```

С Caddy:

```bash
echo 'APP_DOMAIN=m.example.org' >> .env
docker compose --profile proxy up -d --build
```

Каталог школ необязателен; при необходимости: `docker compose cp catalog.json app:/data/catalog.json` и `docker compose restart app`.

Логи и проверка:

```bash
docker compose logs -f app
docker compose ps
```

Резервная копия базы (в образе нет утилиты `sqlite3`, используйте Python):

```bash
docker compose exec app python -c "import sqlite3; s=sqlite3.connect('/data/school_hero.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d); d.close()"
docker compose cp app:/data/backup.db ./backup.db
```

Различия с systemd-вариантом: образ не содержит `landing/` (нет `/portal`), в нём нет `deploy.sh`-проверки старой базы, а тесты и `.env` в образ не попадают (`.dockerignore`).

См. также: [configuration.md](configuration.md), [development.md](development.md).
