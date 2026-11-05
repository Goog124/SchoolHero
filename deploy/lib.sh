#!/usr/bin/env bash
# Общие функции для deploy.sh и deploy-docker.sh. Не запускается сам.
# shellcheck shell=bash

DOMAIN_RE='^([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$'

# Разбор аргументов: --domain <имя>, --email <адрес>. Остальное — ошибка.
parse_args() {
  while [ $# -gt 0 ]; do
    case "$1" in
      --domain) DOMAIN="${2:-}"; shift 2 ;;
      --email) LE_EMAIL="${2:-}"; shift 2 ;;
      -h|--help) usage; exit 0 ;;
      *) echo "Неизвестный аргумент: $1"; usage; exit 2 ;;
    esac
  done
}

# Значение переменной из .env (последняя строка KEY=..., без кавычек и пробелов).
env_value() {
  local env_file="$1" key="$2"
  grep -E "^[[:space:]]*(export[[:space:]]+)?${key}=" "$env_file" | tail -1 | cut -d= -f2- | tr -d '[:space:]"'"'" || true
}

# Проверка серверного .env перед запуском. Ошибки останавливают деплой,
# сомнительные значения дают предупреждение.
check_env_file() {
  local env_file="$1" token mode secret max_age
  token="$(env_value "$env_file" MAX_BOT_TOKEN)"
  if [ -z "$token" ]; then
    echo "В $env_file нет строки MAX_BOT_TOKEN=... или она пуста — прод без токена запускать нельзя"
    exit 1
  fi

  # Режимы demo и sandbox входят без подписи MAX: на сервере их быть не должно.
  if grep -Eq '^[[:space:]]*(export[[:space:]]+)?APP_MODE=' "$env_file"; then
    mode="$(env_value "$env_file" APP_MODE)"
    if [ "$mode" != "prod" ]; then
      echo "В $env_file указан APP_MODE=$mode. На сервере допустим только prod: удалите эту строку или поставьте APP_MODE=prod."
      exit 1
    fi
  fi

  # Секрет webhook: пусто (бот без webhook) или не короче 32 символов.
  secret="$(env_value "$env_file" MAX_WEBHOOK_SECRET)"
  if [ -n "$secret" ] && [ "${#secret}" -lt 32 ]; then
    echo "Внимание: MAX_WEBHOOK_SECRET в $env_file короче 32 символов (${#secret})."
    echo "  Сгенерируйте новый: python3 -c 'import secrets; print(secrets.token_urlsafe(32))'"
    echo "  и заново подпишите webhook (docs/bot.md). Приложение может отказаться стартовать с коротким секретом."
  fi

  max_age="$(env_value "$env_file" INIT_DATA_MAX_AGE)"
  if [ -n "$max_age" ]; then
    if ! printf '%s' "$max_age" | grep -Eq '^[0-9]+$' || [ "$max_age" -lt 60 ] || [ "$max_age" -gt 86400 ]; then
      echo "Внимание: INIT_DATA_MAX_AGE=$max_age вне диапазона 60..86400 секунд."
    fi
  fi

  if [ "$(env_value "$env_file" SCHOOL_APPROVAL)" != "manual" ]; then
    echo "Замечание: SCHOOL_APPROVAL не manual — любая зарегистрированная школа видна сразу. Для прода рекомендуется manual (см. .env.example)."
  fi
}

# Домен берётся по порядку: --domain / переменная DOMAIN, затем PUBLIC_URL из
# .env, затем вопрос в терминале. Имя приводится к нижнему регистру и проверяется.
resolve_domain() {
  local env_file="$1" value="${DOMAIN:-}"
  if [ -z "$value" ] && [ -f "$env_file" ]; then
    value="$(env_value "$env_file" PUBLIC_URL)"
    value="${value#http://}"; value="${value#https://}"; value="${value%%/*}"
  fi
  if [ -z "$value" ] && [ -t 0 ]; then
    read -r -p "Домен, на котором будет работать сервис (например app.example.org): " value
  fi
  value="$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]')"
  if [ -z "$value" ]; then
    echo "Не указан домен. Передайте --domain app.example.org, переменную DOMAIN или PUBLIC_URL в .env."
    exit 1
  fi
  if ! printf '%s' "$value" | grep -Eq "$DOMAIN_RE"; then
    echo "Некорректное имя домена: $value (нужно имя вида app.example.org, не IP-адрес и не URL)"
    exit 1
  fi
  DOMAIN="$value"
  echo "Домен: $DOMAIN"
}

# PUBLIC_URL нужен боту (адрес webhook). Добавляем, если его нет; если он
# отличается от выбранного домена — предупреждаем и ничего не меняем.
ensure_public_url() {
  local env_file="$1" current
  current="$(env_value "$env_file" PUBLIC_URL)"
  if [ -z "$current" ]; then
    printf '\nPUBLIC_URL=https://%s\n' "$DOMAIN" >> "$env_file"
    echo "В $env_file добавлено PUBLIC_URL=https://$DOMAIN"
  elif [ "${current%/}" != "https://$DOMAIN" ]; then
    echo "Внимание: в $env_file PUBLIC_URL=$current, а выбран домен $DOMAIN. Проверьте, что это намеренно."
  fi
}

# nginx + сертификат Let's Encrypt (webroot, без остановки nginx).
setup_nginx_letsencrypt() {
  local src="$1" conf="/etc/nginx/conf.d/$DOMAIN.conf" email_args
  export DEBIAN_FRONTEND=noninteractive
  apt-get install -y nginx certbot curl >/dev/null
  mkdir -p /var/www/certbot

  if [ ! -d "/etc/letsencrypt/live/$DOMAIN" ]; then
    # Временный HTTP-конфиг только для проверки домена.
    cat > "$conf" <<NGX
server {
    listen 80;
    server_name $DOMAIN;
    server_tokens off;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 404; }
}
NGX
    nginx -t && systemctl reload nginx
    if [ -n "${LE_EMAIL:-}" ]; then email_args=(--email "$LE_EMAIL"); else email_args=(--register-unsafely-without-email); fi
    certbot certonly --webroot -w /var/www/certbot -d "$DOMAIN" \
      --non-interactive --agree-tos "${email_args[@]}"
  fi

  sed "s/__DOMAIN__/$DOMAIN/g" "$src/deploy/nginx.conf.template" > "$conf"
  chmod 644 "$conf"
  # На сервере без IPv6 директива listen [::] валит nginx.
  if [ ! -e /proc/net/if_inet6 ]; then sed -i '/listen \[::\]/d' "$conf"; fi
  nginx -t
  systemctl reload nginx
  # certbot.timer (ставится пакетом) продлевает сертификат; после продления перезагружаем nginx.
  mkdir -p /etc/letsencrypt/renewal-hooks/deploy
  printf '#!/bin/sh\nsystemctl reload nginx\n' > /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
  chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
}
