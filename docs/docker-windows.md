# Docker на Windows без WSL

Как собрать и запустить проект в Docker на Windows без WSL: Docker Desktop с движком Hyper-V, все команды в PowerShell. Общее описание образа, сервисов и данных — в [docker.md](docker.md).

## Оглавление

- [Требования](#требования)
- [Установка Docker Desktop с Hyper-V](#установка-docker-desktop-с-hyper-v)
- [Подготовка проекта](#подготовка-проекта)
- [Демо без токена и без MAX](#демо-без-токена-и-без-max)
- [Боевой режим локально](#боевой-режим-локально)
- [Сборка образа и комплекта для сдачи](#сборка-образа-и-комплекта-для-сдачи)
- [Данные и резервная копия](#данные-и-резервная-копия)
- [Остановка и очистка](#остановка-и-очистка)
- [Типичные проблемы](#типичные-проблемы)

## Требования

- Windows 10/11 **Pro, Enterprise или Education**. В редакции Home нет Hyper-V: там Docker Desktop работает только через WSL 2.
- Включённая виртуализация в BIOS/UEFI (Intel VT-x или AMD-V).
- Docker Desktop.
- Git for Windows и Python 3.11+ — только для сборки комплекта на сдачу (`tools/package.py`). Для запуска через `docker compose` они не нужны.

## Установка Docker Desktop с Hyper-V

1. Включите Hyper-V в PowerShell **от имени администратора** и перезагрузите компьютер:

```powershell
Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V -All
```

2. Установите Docker Desktop с docker.com. В установщике **снимите** флажок «Use WSL 2 instead of Hyper-V» (если он есть).
3. Если Docker Desktop уже установлен с WSL 2: Settings → General → снимите «Use the WSL 2 based engine» → Apply & restart.
4. Убедитесь, что Docker работает с Linux-контейнерами (по умолчанию так и есть; в меню значка Docker в трее не должно быть пункта «Switch to Linux containers…»).
5. Проверка в обычном PowerShell:

```powershell
docker version
```

```powershell
docker compose version
```

Обе команды должны ответить без ошибок; `Server` в выводе `docker version` должен быть `linux`.

## Подготовка проекта

Все команды — в PowerShell из корня проекта (папка с `docker-compose.yml`):

```powershell
cd D:\path\to\schoolhero-custom
```

Создайте `.env` из образца:

```powershell
Copy-Item .env.example .env
```

Для демо `.env` не нужен, но файл должен существовать, иначе `docker compose` откажется работать с сервисом `app`. Для боевого режима откройте `.env` в редакторе и задайте `MAX_BOT_TOKEN` (остальные переменные — в [configuration.md](configuration.md)).

Переносы строк: в репозитории есть `.gitattributes`, который держит `*.sh`, `*.service`, `*.conf` с LF. Если вы получили проект не через git, а архивом и редактировали скрипты в Windows-редакторе, проверьте, что редактор не заменил LF на CRLF — для Docker-сборки это не важно, а для деплой-скриптов на Linux-сервере важно.

## Демо без токена и без MAX

Витрина с выдуманными школой, учениками и педагогом. Вход без подписи MAX, поэтому порт открыт только на `127.0.0.1`.

```powershell
docker compose --profile demo up -d --build demo
```

Первая сборка занимает несколько минут: скачиваются образы Node и Python, собирается фронтенд, ставятся зависимости.

Проверка:

```powershell
docker compose --profile demo ps
```

Статус должен стать `healthy` (через 15–30 секунд после старта). Откройте <http://127.0.0.1:8001/>.

## Боевой режим локально

```powershell
docker compose up -d --build
```

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

Ответ `status: ok, mode: prod`. В обычном браузере боевой режим покажет экран «Откройте приложение внутри MAX» — вход только с подписью MAX; это ожидаемо. Для проверки интерфейса используйте демо или песочницу (песочница в Docker не запускается, см. [docker.md](docker.md#что-не-запускается-в-docker)).

Логи:

```powershell
docker compose logs -f app
```

## Сборка образа и комплекта для сдачи

Только образ:

```powershell
docker build -t school-hero:latest .
```

Комплект на сдачу (zip из последнего коммита, образ из того же коммита и контрольные суммы в `dist\`). Нужны Git for Windows и Python:

```powershell
python tools/package.py
```

Если при сборке `pip install` падает с `Temporary failure in name resolution`, см. [Типичные проблемы](#типичные-проблемы).

Сохранить уже собранный образ в файл и загрузить на другой машине:

```powershell
docker save school-hero:latest -o school-hero-image.tar
```

```powershell
docker load -i school-hero-image.tar
```

## Данные и резервная копия

База и фото лежат в томах Docker (`school-hero_school_hero_data`, для демо `school-hero_school_hero_demo_data`), а не в папке проекта. Список томов:

```powershell
docker volume ls
```

Резервная копия боевой базы (копия через API SQLite корректна и при работающем приложении):

```powershell
docker compose exec app python -c "import sqlite3; s=sqlite3.connect('/data/school_hero.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d); d.close()"
```

```powershell
docker compose cp app:/data/backup.db .\backup.db
```

Фото работ лежат в `/data/uploads` того же тома. Подробнее о восстановлении и обновлении — в [docker.md](docker.md#данные-каталог-школ-резервные-копии).

## Остановка и очистка

Остановить, данные сохранятся:

```powershell
docker compose --profile demo stop demo
```

```powershell
docker compose down
```

Удалить контейнеры **и все тома проекта** (боевая и демо-база будут стёрты):

```powershell
docker compose --profile demo down -v
```

## Типичные проблемы

| Симптом | Причина и решение |
| --- | --- |
| Docker Desktop не запускается: «Hardware assisted virtualization… not enabled» | Виртуализация выключена в BIOS/UEFI. Включите Intel VT-x / AMD-V. |
| В настройках нет переключателя WSL 2 / Hyper-V, Docker требует WSL | Редакция Windows Home: Hyper-V недоступен, нужен WSL 2. |
| `docker compose up` падает с «Задайте MAX_BOT_TOKEN в .env» | Для боевого режима в `.env` нужен токен. Для показа используйте профиль `demo`. |
| `env file ... .env not found` | Создайте `.env`: `Copy-Item .env.example .env`. |
| `pip install` при сборке: `Temporary failure in name resolution` | В контейнерах сборки не работает DNS (часто из-за VPN или прокси). Выключите VPN и повторите. Если не помогло: Docker Desktop → Settings → Docker Engine, добавьте в JSON `"dns": ["1.1.1.1", "8.8.8.8"]`, Apply & restart. Разово: `docker build --network=host -t school-hero:latest .` или `python tools/package.py --network host`. |
| `port is already allocated` (8000 или 8001) | Порт занят, например локально запущенным `python app.py`. Остановите его или смените порт в `docker-compose.yml` (левая часть `127.0.0.1:8000:8000`). |
| Контейнер `unhealthy` или перезапускается | `docker compose logs app` — чаще всего нет токена или испорчен `.env`. |
| Команды вида `VAR=value команда` не работают | Это синтаксис bash. В PowerShell переменные задаются так: `$env:VAR = "value"; команда`. |
| После изменения `.env` ничего не поменялось | Пересоздайте контейнер: `docker compose up -d app` (просто `restart` переменные не перечитывает). |
