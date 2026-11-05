#!/usr/bin/env bash
# Развёртывание School Hero в Docker на сервере с nginx (Debian/Ubuntu).
#
# Запуск на сервере от root из папки проекта (там лежат docker-compose.yml и .env):
#   sudo bash deploy/deploy-docker.sh --domain app.example.org --email you@example.com
#
# Домен выбирается по порядку: --domain (или переменная DOMAIN), затем
# PUBLIC_URL из .env, затем вопрос в терминале. Почта нужна Let's Encrypt
# (--email или LE_EMAIL), её можно не указывать.
#
# Что делает: проверяет .env, собирает образ и запускает контейнер app на
# 127.0.0.1:8000, ставит nginx-конфиг и сертификат Let's Encrypt (webroot,
# без остановки nginx), проверяет /api/health снаружи.
# Требования: Docker с плагином compose, DNS-запись домена указывает на сервер,
# открыты порты 80 и 443.
# Не запускайте одновременно с systemd-вариантом (deploy/deploy.sh): оба используют порт 8000.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN="${DOMAIN:-}"
LE_EMAIL="${LE_EMAIL:-}"

usage() { echo "Использование: sudo bash deploy/deploy-docker.sh [--domain app.example.org] [--email you@example.com]"; }
# shellcheck source=lib.sh
. "$SRC/deploy/lib.sh"
parse_args "$@"

[ "$(id -u)" -eq 0 ] || { echo "Запустите от root (sudo)"; exit 1; }
cd "$SRC"

# --- проверки -------------------------------------------------------------
command -v docker >/dev/null || { echo "Docker не установлен"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Нужен плагин docker compose (v2)"; exit 1; }
[ -f .env ] || { echo "Нет $SRC/.env (образец: .env.example)"; exit 1; }

check_env_file .env
# .env содержит токен бота: читать его должен только root (compose читает от root).
chown root:root .env
chmod 600 .env

resolve_domain .env
ensure_public_url .env

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
setup_nginx_letsencrypt "$SRC"

# --- проверка снаружи -----------------------------------------------------
sleep 2
curl -fsS "https://$DOMAIN/api/health" && echo
echo "Готово: https://$DOMAIN"
