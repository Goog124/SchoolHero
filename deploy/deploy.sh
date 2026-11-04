#!/usr/bin/env bash
# Развёртывание School Hero на сервере с nginx (Debian/Ubuntu), домен m.ospab.org.
#
# Запуск на сервере от root, из распакованной папки проекта:
#   sudo LE_EMAIL=you@example.com bash deploy/deploy.sh
#
# Требования: DNS A/AAAA m.ospab.org -> этот сервер, открыты 80 и 443,
# в .env заполнен MAX_BOT_TOKEN, собран фронтенд (static/index.html)
# либо на сервере есть Node.js >= 20.19.
set -euo pipefail

DOMAIN="m.ospab.org"
APP_DIR="/opt/school-hero"
DATA_DIR="/var/lib/school-hero"
APP_USER="schoolhero"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LE_EMAIL="${LE_EMAIL:-}"

[ "$(id -u)" -eq 0 ] || { echo "Запустите от root (sudo)"; exit 1; }

# --- .env ---------------------------------------------------------------
if [ -f "$APP_DIR/.env" ]; then ENV_SRC="$APP_DIR/.env"; else ENV_SRC="$SRC/.env"; fi
[ -f "$ENV_SRC" ] || { echo "Нет .env (положите его в $SRC)"; exit 1; }
echo "Использую .env: $ENV_SRC"
TOKEN="$(grep -E '^[[:space:]]*(export[[:space:]]+)?MAX_BOT_TOKEN=' "$ENV_SRC" | head -1 | cut -d= -f2- | tr -d '[:space:]"'"'" || true)"
[ -n "$TOKEN" ] || { echo "В $ENV_SRC нет строки MAX_BOT_TOKEN=... или она пуста — прод без токена запускать нельзя"; exit 1; }

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
apt-get install -y python3 python3-venv python3-pip rsync nginx certbot curl

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
CONF="/etc/nginx/conf.d/$DOMAIN.conf"
if [ ! -d "/etc/letsencrypt/live/$DOMAIN" ]; then
  # Временный HTTP-конфиг только для проверки домена.
  cat > "$CONF" <<NGX
server {
    listen 80;
    server_name $DOMAIN;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 404; }
}
NGX
  nginx -t && systemctl reload nginx
  if [ -n "$LE_EMAIL" ]; then EMAIL_ARGS=(--email "$LE_EMAIL"); else EMAIL_ARGS=(--register-unsafely-without-email); fi
  certbot certonly --webroot -w /var/www/certbot -d "$DOMAIN" \
    --non-interactive --agree-tos "${EMAIL_ARGS[@]}"
fi

install -m 644 "$SRC/deploy/$DOMAIN.conf" "$CONF"
# На сервере без IPv6 директива listen [::] валит nginx.
if [ ! -e /proc/net/if_inet6 ]; then sed -i '/listen \[::\]/d' "$CONF"; fi
nginx -t
systemctl reload nginx
# certbot.timer (ставится пакетом) продлевает сертификат; перезагружаем nginx после продления.
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
printf '#!/bin/sh\nsystemctl reload nginx\n' > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh

# --- проверка -----------------------------------------------------------
sleep 3
curl -fsS http://127.0.0.1:8000/api/health && echo
curl -fsS "https://$DOMAIN/api/health" && echo
echo "Готово: https://$DOMAIN"
