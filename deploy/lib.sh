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

# Домен берётся по порядку: --domain / переменная DOMAIN, затем PUBLIC_URL из
# .env, затем вопрос в терминале. Имя приводится к нижнему регистру и проверяется.
resolve_domain() {
  local env_file="$1" value="${DOMAIN:-}"
  if [ -z "$value" ] && [ -f "$env_file" ]; then
    value="$(grep -E '^[[:space:]]*(export[[:space:]]+)?PUBLIC_URL=' "$env_file" | tail -1 | cut -d= -f2- | tr -d '[:space:]"'"'" || true)"
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
  current="$(grep -E '^[[:space:]]*(export[[:space:]]+)?PUBLIC_URL=' "$env_file" | tail -1 | cut -d= -f2- | tr -d '[:space:]"'"'" || true)"
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
