#!/usr/bin/env bash
# Развёртывание School Hero на сервере с nginx (Debian/Ubuntu) без Docker.
#
# Запуск на сервере от root, из распакованной папки проекта:
#   sudo bash deploy/deploy.sh --domain app.example.org --email you@example.com
#
# Домен выбирается по порядку: --domain (или переменная DOMAIN), затем
# PUBLIC_URL из .env, затем вопрос в терминале. Почта нужна Let's Encrypt
# (--email или LE_EMAIL), её можно не указывать.
#
# Требования: DNS-запись домена указывает на этот сервер, открыты 80 и 443,
# в .env заполнен MAX_BOT_TOKEN, собран фронтенд (static/index.html)
# либо на сервере есть Node.js >= 20.19.
set -euo pipefail

APP_DIR="/opt/school-hero"
DATA_DIR="/var/lib/school-hero"
APP_USER="schoolhero"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN="${DOMAIN:-}"
LE_EMAIL="${LE_EMAIL:-}"

usage() { echo "Использование: sudo bash deploy/deploy.sh [--domain app.example.org] [--email you@example.com]"; }
# shellcheck source=lib.sh
. "$SRC/deploy/lib.sh"
parse_args "$@"

[ "$(id -u)" -eq 0 ] || { echo "Запустите от root (sudo)"; exit 1; }

# --- .env ---------------------------------------------------------------
if [ -f "$APP_DIR/.env" ]; then ENV_SRC="$APP_DIR/.env"; else ENV_SRC="$SRC/.env"; fi
[ -f "$ENV_SRC" ] || { echo "Нет .env (положите его в $SRC)"; exit 1; }
echo "Использую .env: $ENV_SRC"
TOKEN="$(grep -E '^[[:space:]]*(export[[:space:]]+)?MAX_BOT_TOKEN=' "$ENV_SRC" | head -1 | cut -d= -f2- | tr -d '[:space:]"'"'" || true)"
[ -n "$TOKEN" ] || { echo "В $ENV_SRC нет строки MAX_BOT_TOKEN=... или она пуста — прод без токена запускать нельзя"; exit 1; }

# Режимы demo и sandbox входят без подписи MAX: на сервере их быть не должно.
MODE_LINE="$(grep -E '^[[:space:]]*(export[[:space:]]+)?APP_MODE=' "$ENV_SRC" | tail -1 || true)"
if [ -n "$MODE_LINE" ]; then
  MODE_VAL="$(printf '%s' "$MODE_LINE" | cut -d= -f2- | tr -d '[:space:]"'"'")"
  if [ "$MODE_VAL" != "prod" ]; then
    echo "В $ENV_SRC указан APP_MODE=$MODE_VAL. На сервере допустим только prod: удалите эту строку или поставьте APP_MODE=prod."
    exit 1
  fi
fi

resolve_domain "$ENV_SRC"

# --- проверка старой базы -------------------------------------------------
# В боевой базе у каждого пользователя есть MAX id. Пользователи без него
# остались от старой версии с выдуманными данными.
DB="$DATA_DIR/school_hero.db"
if [ -f "$DB" ] && [ "${ALLOW_LEGACY_DB:-0}" != "1" ]; then
  FAKE="$(python3 - "$DB" <<'PY' 2>/dev/null || echo 0
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
print(c.execute("SELECT COUNT(*) FROM users WHERE max_user_id IS NULL").fetchone()[0])
PY
)"
  if [ "${FAKE:-0}" != "0" ]; then
    echo "В $DB найдено пользователей без MAX id: $FAKE (остатки демо-данных)."
    echo "Остановите сервис и удалите базу: systemctl stop school-hero; rm $DB*"
    echo "Если это осознанно, запустите с ALLOW_LEGACY_DB=1."
    exit 1
  fi
fi

# --- фронтенд -----------------------------------------------------------
if [ ! -f "$SRC/static/index.html" ]; then
  command -v npm >/dev/null || { echo "Нет static/ и нет npm. Соберите фронтенд локально (npm run build) и скопируйте static/"; exit 1; }
  (cd "$SRC/frontend" && npm ci && npm run build)
fi

# --- пакеты -------------------------------------------------------------
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip rsync curl

# --- пользователь и каталоги ---------------------------------------------
id "$APP_USER" >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
mkdir -p "$APP_DIR" "$DATA_DIR" /var/www/certbot
rsync -a --delete \
  --exclude '.git' --exclude '.venv' --exclude '.idea' --exclude 'node_modules' \
  --exclude '__pycache__' --exclude '.pytest_cache' --exclude 'data' --exclude '.env' --exclude 'catalog.json' \
  "$SRC/" "$APP_DIR/"
[ -f "$APP_DIR/.env" ] || install -m 600 "$SRC/.env" "$APP_DIR/.env"
CATALOG_DST="$DATA_DIR/catalog.json"
# Каталог необязателен: школы можно создавать через регистрацию директора.
if [ ! -f "$CATALOG_DST" ] && [ -f "$SRC/catalog.json" ]; then install -m 640 "$SRC/catalog.json" "$CATALOG_DST"; fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR" "$DATA_DIR"
chmod 600 "$APP_DIR/.env"
ensure_public_url "$APP_DIR/.env"

# --- Python -------------------------------------------------------------
[ -d "$APP_DIR/.venv" ] || python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip -q
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt" -q
chown -R "$APP_USER:$APP_USER" "$APP_DIR/.venv"

# --- systemd ------------------------------------------------------------
install -m 644 "$SRC/deploy/school-hero.service" /etc/systemd/system/school-hero.service
systemctl daemon-reload
systemctl enable school-hero
systemctl restart school-hero

# --- nginx + Let's Encrypt ----------------------------------------------
setup_nginx_letsencrypt "$SRC"

# --- проверка -----------------------------------------------------------
sleep 3
curl -fsS http://127.0.0.1:8000/api/health && echo
curl -fsS "https://$DOMAIN/api/health" && echo
echo "Готово: https://$DOMAIN"
