# Развёртывание на сервере

Два способа развернуть сервис на сервере: **Docker** ([docker.md](docker.md), скрипт `deploy/deploy-docker.sh`) и **systemd + nginx** без Docker на Debian/Ubuntu через `deploy/deploy.sh` (этот документ). Выберите один: оба используют порт 8000.

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
- DNS: запись A (и AAAA, если есть IPv6) `app.example.org` указывает на сервер.
- Открыты порты 80 и 443. Порт 80 нужен и после выпуска сертификата: на нём продление и редирект на HTTPS.
- Порты 80/443 не заняты другим веб-сервером.
- Пакеты ставит сам скрипт: `python3 python3-venv python3-pip rsync nginx certbot curl`.
- Токен бота MAX (`MAX_BOT_TOKEN`).
- Версия nginx с директивой `http2 on;` (используется в шаблоне `deploy/nginx.conf.template`). Директиву поддерживает nginx 1.25.1 и новее; на более старых пакетах `nginx -t` завершится ошибкой, и конфиг придётся поправить (убрать `http2 on;`, добавить `http2` к `listen 443 ssl`).
- Сборка фронтенда (`static/index.html`) или Node.js 20.19+ на сервере.

Домен выбирается при запуске (см. ниже) и подставляется в шаблон `deploy/nginx.conf.template`; в репозитории домена нет. Пути зашиты в `deploy/deploy.sh`: `APP_DIR=/opt/school-hero`, `DATA_DIR=/opt/school-hero/data`, `APP_USER=schoolhero`. Общая логика (выбор домена, nginx, сертификат) вынесена в `deploy/lib.sh`.

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
SCHOOL_APPROVAL=manual
PLATFORM_ADMIN_MAX_IDS=<MAX id администраторов, подтверждающих школы>
```

Правила:

- `APP_MODE` в серверном `.env` должен быть `prod`. По документации systemd значения из `EnvironmentFile` перекрывают `Environment=` юнита, поэтому `ExecStart` запускает процесс через `/usr/bin/env APP_MODE=prod ...`: значение юнита всегда выигрывает. Кроме того, `deploy/deploy.sh` отказывается работать, если в `.env` есть `APP_MODE` не `prod`.
- Пустой `MAX_BOT_TOKEN` скрипт отклонит; сервис без токена в `prod` не стартует.
- `MAX_WEBHOOK_SECRET` либо пуст, либо не короче 32 символов (`python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`). Короткий секрет скрипт отметит предупреждением. Также предупреждения выдаются для `INIT_DATA_MAX_AGE` вне 60..86400 и для `SCHOOL_APPROVAL` не `manual`.
- `SCHOOL_APPROVAL=manual` рекомендуется для прода: при `auto` любой пользователь MAX может зарегистрировать «школу», и она сразу видна. При `manual` школы подтверждают администраторы из `PLATFORM_ADMIN_MAX_IDS`.
- **Важно.** После выкладки на пустую базу сразу откройте приложение первым сами: администратором платформы станет тот, кто первым войдёт в пустую базу (`BOOTSTRAP_FIRST_ADMIN=1`). Либо заранее задайте `PLATFORM_ADMIN_MAX_IDS` (тогда первый вход админом не делает), либо отключите это поведение `BOOTSTRAP_FIRST_ADMIN=0`. Проверить, кто администратор: вкладка «Люди» (пометка «Администратор платформы», число в сводке) или запрос `sqlite3 school_hero.db "SELECT id, max_user_id, first_name FROM users WHERE platform_admin = 1"`.
- `.env` копируется на сервер **только один раз**: если `/opt/school-hero/.env` уже есть, скрипт проверяет и использует его, а `.env` из папки проекта не трогает. Дальше правьте серверную копию.
- Права на сервере: `/opt/school-hero/.env` - владелец `root`, группа `schoolhero`, `640`. Почему не `600 root`: systemd читает `EnvironmentFile` от root, но `app.py` дополнительно загружает тот же файл через `python-dotenv` уже от пользователя `schoolhero`, и без права чтения процесс упал бы с `PermissionError`. Писать в `.env` сервис не может.
- Полный список переменных: [configuration.md](configuration.md).

### 3. Каталог школ - необязательно

`catalog.json` не нужен: школы создаёт директор ([setup-school.md](setup-school.md)). Если файл `catalog.json` лежит в корне проекта и в `/opt/school-hero/data/catalog.json` ещё нет, скрипт скопирует его (права 640). Существующий в `/opt/school-hero/data` файл не перезаписывается.

### 4. Перенести проект на сервер

Любым способом (git, `scp`, `rsync`), включая собранный `static/` и `.env`; `node_modules`, `.venv`, `data` переносить не нужно. Пример:

```bash
rsync -a --exclude node_modules --exclude .venv --exclude .git --exclude data ./ root@server:/root/school-hero-src/
```

## deploy/deploy.sh по шагам

Запуск на сервере от root из корня проекта:

```bash
cd /root/school-hero-src
sudo bash deploy/deploy.sh --domain app.example.org --email you@example.com
```

Домен выбирается по порядку: параметр `--domain` (или переменная `DOMAIN`), затем `PUBLIC_URL` из `.env`, затем вопрос в терминале. Имя проверяется: нужно доменное имя вида `app.example.org` (без `https://`, не IP-адрес), регистр приводится к нижнему. Если в `.env` нет `PUBLIC_URL`, скрипт добавит `PUBLIC_URL=https://<домен>` (он нужен боту для webhook); если он есть и отличается от выбранного домена, скрипт предупредит и ничего не изменит. `--email` (или `LE_EMAIL`) - адрес для Let's Encrypt; без него регистрация идёт без почты (`--register-unsafely-without-email`). Скрипт остановится при первой ошибке (`set -euo pipefail`).

1. **Проверка root.** Иначе выход.
2. **`.env`.** Выбор источника (`/opt/school-hero/.env` или `<проект>/.env`), проверка, что `MAX_BOT_TOKEN` непуст.
3. **Проверка старой базы.** Если `/opt/school-hero/data/school_hero.db` существует и в `users` есть строки без `max_user_id` (остатки демо-данных или старой версии), скрипт останавливается и просит остановить сервис и удалить базу. Обход: `ALLOW_LEGACY_DB=1 sudo -E bash deploy/deploy.sh` (осознанно). Проверка выполняется через `python3` до установки пакетов.
4. **Фронтенд.** Если `static/index.html` нет, выполняет `npm ci && npm run build` (нужен npm), иначе пропускает. **Уже существующий `static/` не пересобирается** - при обновлении собирайте заново сами.
5. **Пакеты.** `apt-get update` и установка зависимостей.
6. **Пользователь и каталоги.** Системный пользователь `schoolhero` (без оболочки), `/opt/school-hero`, `/opt/school-hero/data`, `/var/www/certbot`.
7. **Копирование.** `rsync -a --delete` проекта в `/opt/school-hero`, кроме `.git`, `.venv`, `.idea`, `node_modules`, `__pycache__`, `.pytest_cache`, `data`, `.env`, `catalog.json`, `dist`, `tests`. Выкладывается и `docs/`. Данные вне `/opt`, поэтому не затрагиваются.
8. **`.env`, каталог и права.** Копирование `.env` (только если в `/opt` его нет) и необязательного `catalog.json`. Права:

   | Путь | Владелец | Права |
   | --- | --- | --- |
   | `/opt/school-hero` (код, `.venv`) | `root:root` | сервису только чтение |
   | `/opt/school-hero/.env` | `root:schoolhero` | `640` |
   | `/opt/school-hero/data` | `schoolhero:schoolhero` | `700` |
   | файлы в `/opt/school-hero/data` (база, `-wal`, `-shm`, `catalog.json`) | `schoolhero:schoolhero` | `600` |

   Новые файлы базы сервис создаёт с правами `600` (`UMask=0077` в юните).
9. **Python.** Виртуальное окружение `/opt/school-hero/.venv` (владелец root), `pip install -r requirements.txt` - только runtime-зависимости; `pytest` лежит в `requirements-dev.txt` и на сервер не ставится.
10. **systemd.** Установка `school-hero.service`, `daemon-reload`, `enable`, `restart`.
11. **nginx и сертификат.** Если сертификата ещё нет: временный конфиг на порту 80 с `/.well-known/acme-challenge/`, `certbot certonly --webroot`. Затем из шаблона `deploy/nginx.conf.template` (подстановка `__DOMAIN__`) создаётся `/etc/nginx/conf.d/<домен>.conf`; если в системе нет IPv6 (`/proc/net/if_inet6` отсутствует), строки `listen [::]` удаляются; `nginx -t`, `reload`.
12. **Хук продления.** Создаёт `/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh` (`systemctl reload nginx`).
13. **Проверка.** Через 3 секунды `curl` на `http://127.0.0.1:8000/api/health` и `https://app.example.org/api/health`. Ответ `{"status":"ok","mode":"prod"}`.

Скрипт идемпотентен: повторный запуск - способ обновления.

## Конфигурация nginx и systemd

### `deploy/nginx.conf.template`

- Порт 80: `/.well-known/acme-challenge/` отдаётся из `/var/www/certbot`, остальное - редирект 301 на HTTPS.
- `server_tokens off` в обоих server: версия nginx не раскрывается.
- Порт 443: TLS 1.2/1.3, сертификаты `/etc/letsencrypt/live/app.example.org/`, gzip для css/js/json/svg.
- Заголовки: `Strict-Transport-Security: max-age=31536000`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin` (одноимённые заголовки приложения скрываются `proxy_hide_header`, чтобы не дублировались). `X-Frame-Options` намеренно не ставится: веб-версия MAX может открывать мини-приложение во фрейме.
- `client_max_body_size 6m` - под загрузку фото до 5 МБ. Таймауты: `client_body_timeout`/`client_header_timeout` 15 с, `send_timeout` 30 с, `proxy_connect_timeout` 5 с, `proxy_send_timeout`/`proxy_read_timeout` 60 с.
- Ограничение частоты: `limit_req_zone ... zone=school_hero_api:10m rate=10r/s` объявлена в начале файла (файлы `conf.d` подключаются внутрь `http {}`, там директива допустима). `location /api/` - `burst=40 nodelay`, сверх лимита ответ `429`. Конфиг должен быть на сервере в одном экземпляре: два файла с одной зоной (например, после смены домена остался старый `conf.d/<старый-домен>.conf`) дадут ошибку `nginx -t` «duplicate zone» - удалите старый файл.
- `location /api/` и `location /` проксируют на `http://127.0.0.1:8000` с заголовками `Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`.
- Установленная копия лежит в `/etc/nginx/conf.d/app.example.org.conf`; правки делайте в репозитории и перезапускайте скрипт, иначе они потеряются (в частности, удаление `listen [::]`).

#### Рекомендация: сервер по умолчанию

Наш конфиг не объявляет `default_server`, потому что на сервере могут быть другие сайты. Если своего сервера по умолчанию на сервере нет, nginx отвечает на запросы с чужим или пустым `Host` (сканеры, обращение по IP) первым подходящим `server`, то есть School Hero. Рекомендуется один раз добавить заглушку, например `/etc/nginx/conf.d/00-default.conf`:

```nginx
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    listen 443 ssl default_server;
    listen [::]:443 ssl default_server;
    ssl_reject_handshake on;   # nginx 1.19.4+: обрыв TLS без сертификата
    server_name _;
    server_tokens off;
    return 444;
}
```

Уберите строки `[::]`, если на сервере нет IPv6, и проверьте `nginx -t`.

### `deploy/school-hero.service`

- Запуск от `schoolhero`, рабочий каталог `/opt/school-hero`, команда `/opt/school-hero/.venv/bin/python app.py`, `Restart=on-failure` с паузой 3 с.
- `EnvironmentFile=/opt/school-hero/.env`, а также `Environment=`: `APP_MODE=prod`, `CATALOG_FILE=/opt/school-hero/data/catalog.json`, `HOST=127.0.0.1`, `PORT=8000`, `SERVE_FRONTEND=true`, `STATIC_DIR=/opt/school-hero/static`, `DATA_DIR=/opt/school-hero/data`.
- `UMask=0077`: файлы базы создаются с правами 600.
- Файловая система: `ProtectSystem=strict` (запись только в `ReadWritePaths=/opt/school-hero/data`), `ProtectHome`, `PrivateTmp`, `PrivateDevices`, `ProtectProc=invisible` (systemd 247+), `PYTHONDONTWRITEBYTECODE=1`.
- Привилегии: `NoNewPrivileges`, пустые `CapabilityBoundingSet=` и `AmbientCapabilities=`, `RestrictSUIDSGID`, `LockPersonality`, `RestrictRealtime`, `RestrictNamespaces`.
- Ядро: `ProtectKernelTunables`, `ProtectKernelModules`, `ProtectKernelLogs`, `ProtectControlGroups`, `ProtectClock`, `ProtectHostname`.
- Сеть: `RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX` - сеть нужна (порт 8000 и запросы бота к `https://platform-api2.max.ru`).
- Системные вызовы и память: `SystemCallArchitectures=native`, `SystemCallFilter=@system-service` (запрещённые вызовы получают `EPERM`), `MemoryDenyWriteExecute=true`. CPython без JIT, uvicorn, uvloop, httptools и httpx не создают исполняемую память. Если после обновления Python или зависимостей сервис падает при старте с ошибкой на `mmap`/`mprotect`, закомментируйте `MemoryDenyWriteExecute` и выполните `systemctl daemon-reload`.
- Оценка: `systemd-analyze security school-hero` (на systemd 255 - около 1.5, «OK»).
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
sudo certbot certonly --webroot -w /var/www/certbot -d app.example.org --non-interactive --agree-tos --email you@example.com
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
5. Проверьте `curl https://app.example.org/api/health` и `journalctl -u school-hero -n 50`.

Схема базы мигрирует сама при старте ([architecture.md](architecture.md#миграции)); откатить миграцию нельзя - только вернуть копию.

## Резервное копирование и восстановление

База работает в режиме WAL: рядом с `school_hero.db` лежат `-wal` и `-shm`. Простое копирование одного `.db` при работающем сервисе может дать неполную копию. Копируйте средствами SQLite.

Команда `sqlite3` не ставится скриптом: `sudo apt-get install sqlite3`. Копию делайте от имени `schoolhero`, чтобы не создать файлы базы с владельцем root.

```bash
sudo install -d -m 700 -o schoolhero -g schoolhero /opt/school-hero/data/backups
sudo -u schoolhero sqlite3 /opt/school-hero/data/school_hero.db \
  ".backup '/opt/school-hero/data/backups/school_hero-$(date +%F).db'"
```

Без `sqlite3` то же средствами Python:

```bash
sudo -u schoolhero python3 - <<'PY'
import sqlite3, datetime
src = sqlite3.connect("/opt/school-hero/data/school_hero.db")
dst = sqlite3.connect(f"/opt/school-hero/data/backups/school_hero-{datetime.date.today()}.db")
src.backup(dst)
dst.close(); src.close()
PY
```

Альтернатива - остановить сервис и скопировать файл вместе с `-wal` и `-shm`.

Восстановление:

```bash
sudo systemctl stop school-hero
sudo rm -f /opt/school-hero/data/school_hero.db-wal /opt/school-hero/data/school_hero.db-shm
sudo cp /opt/school-hero/data/backups/school_hero-ГГГГ-ММ-ДД.db /opt/school-hero/data/school_hero.db
sudo chown schoolhero:schoolhero /opt/school-hero/data/school_hero.db
sudo systemctl start school-hero
```

Фото-подтверждения лежат в каталоге `uploads` рядом с базой (`/opt/school-hero/data/uploads`, то есть `DATA_DIR/uploads`); резервная копия должна включать и его, например `sudo tar -C /opt/school-hero/data -czf uploads-$(date +%F).tar.gz uploads`. Восстанавливайте каталог с владельцем `schoolhero`.

Копии храните вне сервера. Расписания резервного копирования в проекте нет; настройте cron/systemd-timer сами. Сохраняйте также `.env` (там токен бота) и `catalog.json`, если используется.

## Бот MAX

После деплоя настройте приветствие бота: [bot.md](bot.md). Кратко: `MAX_WEBHOOK_SECRET` в `/opt/school-hero/.env`, `systemctl restart school-hero`, `python tools/max_bot.py subscribe`. Webhook должен быть доступен снаружи по HTTPS на порту 443 (nginx уже так настроен).

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
curl -s https://app.example.org/api/health          # через nginx
sudo nginx -t
```

`/api/health` не требует авторизации и возвращает `status` и `mode`. В боевой среде `mode` должен быть `prod`.

## Типичные проблемы

| Симптом | Причина и решение |
| --- | --- |
| `nginx -t` падает на `listen [::]:...` | Сервер без IPv6. Скрипт удаляет такие строки автоматически; при ручной правке удалите `listen [::]:80;` и `listen [::]:443 ssl;` |
| `nginx -t` падает на `http2 on` | nginx старше 1.25.1. См. требования |
| `nginx -t`: `duplicate zone "school_hero_api"` | В `conf.d` два конфига School Hero (например, от старого домена). Оставьте один |
| Клиенты получают 429 | Сработал лимит `/api/` (10 запросов/с, всплеск 40 с одного IP). Если много пользователей за одним NAT (школьная сеть), поднимите `rate`/`burst` в шаблоне |
| Сервис падает сразу, в журнале `status=31/SYS` | Системный вызов вне `@system-service` или запрет `MemoryDenyWriteExecute`: см. раздел про юнит |
| В журнале `PermissionError` на `/opt/school-hero/.env` | Права `.env` изменены вручную. Нужно `root:schoolhero 640`: `chown root:schoolhero /opt/school-hero/.env; chmod 640 /opt/school-hero/.env` |
| 502 Bad Gateway от nginx | Сервис не запущен или падает. `systemctl status school-hero`, `journalctl -u school-hero -n 100`, `curl http://127.0.0.1:8000/api/health` |
| Сервис перезапускается по кругу, в журнале `APP_MODE=prod требует MAX_BOT_TOKEN` | Токен в `.env` пуст. Заполните `MAX_BOT_TOKEN` и `systemctl restart school-hero` |
| В журнале `APP_MODE должен быть ...` / `SCHOOL_APPROVAL должен быть ...` | Опечатка в значении переменной |
| В журнале `CatalogError` | Повреждён `catalog.json`; исправьте или удалите файл |
| Certbot: порт 80 занят (при `--standalone`) | Скрипт использует webroot и порт не занимает. Для ручного `--standalone` остановите nginx или другой процесс (`ss -ltnp \| grep ':80 '`); лучше используйте `--webroot` |
| Certbot не проходит проверку | DNS не указывает на сервер, порт 80 закрыт, либо временный конфиг не загрузился (`nginx -t`) |
| Скрипт: «найдено пользователей без MAX id» | В базе остатки демо-данных. `systemctl stop school-hero; rm /opt/school-hero/data/school_hero.db*`, затем снова скрипт. Для осознанного пропуска `ALLOW_LEGACY_DB=1` |
| Приложение открывается, но в `/api/health` `mode` не `prod` | В серверном `.env` другой `APP_MODE`. Исправьте и перезапустите сервис |
| Все запросы возвращают 401 «Данные MAX устарели» | Приложение открыто дольше `INIT_DATA_MAX_AGE` (по умолчанию 24 часа), либо расходятся часы сервера и клиента. Откройте приложение заново, проверьте время сервера (`timedatectl`) |
| Интерфейс показывает «Откройте приложение внутри MAX» | В `prod` приложение работает только внутри MAX, в обычном браузере вход невозможен |
| `GET /` отдаёт JSON `schoolhero-api` | `SERVE_FRONTEND` не включён |
| `GET /` отдаёт 503 «Frontend is not built» | В `STATIC_DIR` нет `index.html`; соберите фронтенд и перезапустите скрипт |

## Вариант Docker

Описан отдельно: [docker.md](docker.md) (compose, профили, скрипт `deploy/deploy-docker.sh`, резервные копии, обновление, бот, переход с systemd). Образ содержит и страницу `/portal`. Не запускайте оба варианта одновременно: оба используют порт 8000.
