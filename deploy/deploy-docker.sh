#!/usr/bin/env bash
# Развёртывание School Hero в Docker на сервере с nginx (Debian/Ubuntu), домен m.ospab.org.
#
# Запуск на сервере от root из папки проекта (там лежат docker-compose.yml и .env):
#   sudo LE_EMAIL=you@example.com bash deploy/deploy-docker.sh
#
# Что делает: проверяет .env, собирает образ и запускает контейнер app на
# 127.0.0.1:8000, ставит nginx-конфиг и сертификат Let's Encrypt (webroot,
# без остановки nginx), проверяет /api/health снаружи.
# Требования: Docker с плагином compose, DNS m.ospab.org -> сервер, порты 80 и 443.
# Не запускайте одновременно с systemd-вариантом (deploy/deploy.sh): оба используют порт 8000.
set -euo pipefail

DOMAIN="m.ospab.org"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LE_EMAIL="${LE_EMAIL:-}"

[ "$(id -u)" -eq 0 ] || { echo "Запустите от root (sudo)"; exit 1; }
cd "$SRC"

# --- проверки -------------------------------------------------------------
command -v docker >/dev/null || { echo "Docker не установлен"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Нужен плагин docker compose (v2)"; exit 1; }
[ -f .env ] || { echo "Нет $SRC/.env (образец: .env.example)"; exit 1; }

TOKEN="$(grep -E '^[[:space:]]*(export[[:space:]]+)?MAX_BOT_TOKEN=' .env | head -1 | cut -d= -f2- | tr -d '[:space:]"'"'" || true)"
[ -n "$TOKEN" ] || { echo "В .env нет MAX_BOT_TOKEN или он пуст — прод без токена запускать нельзя"; exit 1; }

if grep -Eq '^[[:space:]]*(export[[:space:]]+)?APP_MODE=' .env \
   && ! grep -Eq '^[[:space:]]*(export[[:space:]]+)?APP_MODE=[[:space:]]*"?prod"?[[:space:]]*$' .env; then
  echo "В .env задан APP_MODE не prod. Уберите строку или поставьте prod."
  exit 1
fi

if systemctl is-active --quiet school-hero 2>/dev/null; then
  echo "Работает systemd-сервис school-hero и занимает порт 8000."
  echo "Остановите его: systemctl disable --now school-hero (данные: /var/lib/school-hero/school_hero.db)."
  exit 1
fi

[ -f static/index.html ] || echo "Папки static/ нет — это нормально: фронтенд собирается внутри образа."

# --- сборка и запуск ------------------------------------------------------
docker compose up -d --build app

echo "Жду, пока контейнер станет healthy…"
CID="$(docker compose ps -q app)"
for _ in $(seq 1 60); do
  STATUS="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$CID" 2>/dev/null || echo none)"
  [ "$STATUS" = "healthy" ] && break
  sleep 2
done
if [ "${STATUS:-}" != "healthy" ]; then
  echo "Контейнер не стал healthy (статус: ${STATUS:-?}). Логи:"
  docker compose logs --tail 40 app
  exit 1
fi
curl -fsS http://127.0.0.1:8000/api/health && echo

# --- nginx + Let's Encrypt ------------------------------------------------
apt-get install -y nginx certbot curl >/dev/null
mkdir -p /var/www/certbot
CONF="/etc/nginx/conf.d/$DOMAIN.conf"
if [ ! -d "/etc/letsencrypt/live/$DOMAIN" ]; then
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
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
printf '#!/bin/sh\nsystemctl reload nginx\n' > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh

# --- проверка снаружи -----------------------------------------------------
sleep 2
curl -fsS "https://$DOMAIN/api/health" && echo
echo "Готово: https://$DOMAIN"
