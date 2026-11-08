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
DATA_DIR="$APP_DIR/data"
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
# Серверный /opt/school-hero/.env главный: если он есть, .env из папки проекта
# не используется и не копируется. Иначе .env проекта копируется один раз.
if [ -f "$APP_DIR/.env" ]; then
  ENV_SRC="$APP_DIR/.env"
  if [ -f "$SRC/.env" ]; then echo "Есть $APP_DIR/.env — $SRC/.env не используется и не копируется."; fi
else
  ENV_SRC="$SRC/.env"
fi
[ -f "$ENV_SRC" ] || { echo "Нет .env (положите его в $SRC, образец .env.example)"; exit 1; }
echo "Использую .env: $ENV_SRC"
check_env_file "$ENV_SRC"

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
# Права:
#   /opt/school-hero          root:root, код только для чтения (сервис его не меняет);
#   /opt/school-hero/.env     root:schoolhero 640 — systemd читает его как
#                             EnvironmentFile от root, app.py ещё раз через
#                             python-dotenv от schoolhero; записать сервис не может;
#   /var/lib/school-hero      schoolhero 700, файлы внутри 600 (UMask=0077 в юните).
id "$APP_USER" >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
mkdir -p "$APP_DIR" "$DATA_DIR" /var/www/certbot
if [ -d "/var/lib/school-hero" ] && [ ! -f "$DATA_DIR/school_hero.db" ] && [ -f "/var/lib/school-hero/school_hero.db" ]; then
  echo "Перенос данных из /var/lib/school-hero в $DATA_DIR..."
  cp -a /var/lib/school-hero/* "$DATA_DIR/" 2>/dev/null || true
fi
rsync -a --delete \
  --exclude '.git' --exclude '.venv' --exclude '.idea' --exclude 'node_modules' \
  --exclude '__pycache__' --exclude '.pytest_cache' --exclude 'data' --exclude '.env' --exclude 'catalog.json' \
  --exclude '/dist' --exclude '/tests' \
  "$SRC/" "$APP_DIR/"
if [ ! -f "$APP_DIR/.env" ]; then
  install -m 640 -o root -g "$APP_USER" "$SRC/.env" "$APP_DIR/.env"
  echo "Скопирован $SRC/.env -> $APP_DIR/.env. Дальше правьте только серверную копию; локальный .env можно удалить."
fi
CATALOG_DST="$DATA_DIR/catalog.json"
# Каталог необязателен: школы можно создавать через регистрацию директора.
if [ ! -f "$CATALOG_DST" ] && [ -f "$SRC/catalog.json" ]; then
  install -m 600 -o "$APP_USER" -g "$APP_USER" "$SRC/catalog.json" "$CATALOG_DST"
fi

CA_DST="$DATA_DIR/russian_trusted_ca.pem"
if [ -f "$SRC/data/russian_trusted_ca.pem" ]; then
  install -m 644 -o "$APP_USER" -g "$APP_USER" "$SRC/data/russian_trusted_ca.pem" "$CA_DST"
fi
chown -R root:root "$APP_DIR"
chmod 755 "$APP_DIR"
chown root:"$APP_USER" "$APP_DIR/.env"
chmod 640 "$APP_DIR/.env"
chown -R "$APP_USER:$APP_USER" "$DATA_DIR"
chmod 700 "$DATA_DIR"
find "$DATA_DIR" -type d -exec chmod 700 {} +
find "$DATA_DIR" -type f -exec chmod 600 {} +
ensure_public_url "$APP_DIR/.env"

# --- Python -------------------------------------------------------------
# Окружение принадлежит root: сервис не может подменить свои зависимости.
[ -d "$APP_DIR/.venv" ] || python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip -q
# Только runtime-зависимости; pytest и прочее для разработки — requirements-dev.txt.
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt" -q
chown -R root:root "$APP_DIR/.venv"  # pip работал от root; на всякий случай

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
