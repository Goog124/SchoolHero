# Сдача работы

Что входит в комплект, как его собрать и как проверяющему за несколько минут запустить и посмотреть проект.

## Оглавление

- [Состав комплекта](#состав-комплекта)
- [Как собрать комплект](#как-собрать-комплект)
- [Проверка за 5 минут](#проверка-за-5-минут)
- [Тесты](#тесты)
- [Документация](#документация)
- [Ограничения](#ограничения)

## Состав комплекта

Файлы в `dist/` после `python tools/package.py`:

| Файл | Что это |
| --- | --- |
| `school-hero-<версия>.zip` | Исходный код: всё закоммиченное в git (`git archive HEAD`) - бэкенд, фронтенд, портал, тесты, документация, Dockerfile, compose, скрипты деплоя, `.env.example` |
| `school-hero-<версия>.zip.sha256` | Контрольная сумма архива |
| `school-hero-image-<версия>.tar.gz` | Готовый Docker-образ (`docker save`), собирается, если на машине есть Docker |
| `school-hero-image-<версия>.tar.gz.sha256` | Контрольная сумма образа |

Версия - тег git на текущем коммите, иначе `<дата коммита>-<короткий хеш>`; задать вручную: `--version 1.0.0`.

В архив **не** попадают: `.env` (секреты), `data/` (базы), `static/` (сборка фронтенда, собирается в образе или командой `npm run build`), `node_modules`, `.venv`, настройки IDE. Скрипт проверяет содержимое архива и останавливается, если там нашлось что-то из этого списка.

## Как собрать комплект

Нужны git и Python 3.11+, для образа - Docker.

```bash
python tools/package.py              # архив + образ (если Docker доступен)
python tools/package.py --no-image   # только архив
```

Важно: архив собирается из последнего коммита. Незакоммиченные изменения скрипт перечислит и в архив не включит - закоммитьте их перед сборкой. Образ собирается из того же содержимого, что и архив, а не из рабочей папки. Если Docker не установлен или демон не запущен, шаг с образом пропускается с сообщением.

Проверка контрольных сумм (Linux/macOS/Git Bash):

```bash
cd dist && sha256sum -c *.sha256
```

Windows PowerShell: `Get-FileHash dist\school-hero-<версия>.zip -Algorithm SHA256` и сравнить со значением в `.sha256`.

## Проверка за 5 минут

### Вариант 1: демо в Docker (рекомендуется)

Без токена MAX и без интернета до MAX. Выдуманные школа, ученики и педагог; вход без подписи MAX; отдельная база.

Из распакованного архива:

```bash
docker compose --profile demo up -d --build demo
```

Или из готового образа без сборки:

```bash
docker load -i school-hero-image-<версия>.tar.gz
docker run --rm -p 127.0.0.1:8001:8000 -e APP_MODE=demo -e SERVE_FRONTEND=true -e DATABASE_PATH=/data/school_hero_demo.db school-hero:<версия>
```

Откройте <http://127.0.0.1:8001/>. Проверка живости: `curl http://127.0.0.1:8001/api/health` - ответ `{"status":"ok","mode":"demo"}`. Страница-портал: <http://127.0.0.1:8001/portal>.

Остановить и удалить данные демо:

```bash
docker compose --profile demo stop demo
docker volume rm school-hero_school_hero_demo_data
```

### Вариант 2: без Docker

Python 3.11+ и Node.js 20.19+ / 22.12+:

```bash
python -m venv .venv
. .venv/bin/activate            # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd frontend && npm ci && npm run build && cd ..
cp .env.example .env            # и поставьте в .env APP_MODE=demo
python app.py                   # http://127.0.0.1:8000
```

Проверка регистрации школы без MAX: `npm run sandbox`, затем <http://127.0.0.1:8010/> (см. [development.md](development.md)).

### Боевой режим (prod)

Требует токена бота MAX (`MAX_BOT_TOKEN`) и домена с HTTPS: MAX открывает мини-приложения только по HTTPS, а в `prod` вход возможен только с подписью MAX. В обычном браузере прод-версия покажет «Откройте приложение внутри MAX» - это ожидаемо. Развёртывание: [docker.md](docker.md) (Docker + nginx или Caddy) или [deploy.md](deploy.md) (systemd + nginx).

## Тесты

```bash
pip install -r requirements-dev.txt     # runtime-зависимости + pytest
python -m pytest tests -q
```

`requirements.txt` - только то, что нужно для работы (его ставят сервер и Docker-образ), `requirements-dev.txt` - плюс инструменты тестирования.

Проверка конфигурации без запуска:

```bash
docker compose config -q                 # синтаксис compose
bash -n deploy/*.sh                      # синтаксис скриптов деплоя
systemd-analyze verify deploy/school-hero.service   # на Linux с systemd
```

## Документация

| Документ | О чём |
| --- | --- |
| [README.md](../README.md) | Обзор, режимы, быстрый старт |
| [architecture.md](architecture.md) | Устройство, авторизация, схема БД, права, расчёт XP и рейтингов |
| [setup-school.md](setup-school.md) | Подключение школы |
| [roles.md](roles.md) | Ученик, педагог, директор, администратор платформы |
| [configuration.md](configuration.md) | Переменные окружения, режимы, пути данных |
| [api.md](api.md) | Справочник API |
| [bot.md](bot.md) | Бот MAX и webhook |
| [docker.md](docker.md) | Docker: compose, профили, Caddy, данные, обновление, закрепление образов |
| [deploy.md](deploy.md) | Сервер без Docker: systemd, nginx, сертификат, права, резервные копии |
| [development.md](development.md) | Разработка, песочница, тесты, пределы масштабирования |

## Ограничения

- Боевой режим работает только внутри MAX: нужен зарегистрированный бот, его токен и публичный HTTPS-домен. Без них доступны только `demo` и `sandbox`.
- `demo` и `sandbox` входят без подписи MAX и предназначены только для локального просмотра; их порты привязаны к `127.0.0.1`.
- `sandbox` в Docker не запускается (слушает только loopback), только на хосте.
- Одна база SQLite и один процесс uvicorn: рассчитано на одну или несколько школ, не на горизонтальное масштабирование (см. [development.md](development.md)).
- Резервное копирование не автоматизировано: команды в [deploy.md](deploy.md) и [docker.md](docker.md), расписание настраивается отдельно.
- Сборка образа требует доступа к Docker Hub и npm/PyPI; на машине без интернета используйте готовый `school-hero-image-<версия>.tar.gz`.
