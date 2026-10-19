#!/usr/bin/env bash
# Fresh-install script for Ubuntu 22.04 LTS or later, on a dedicated server.
set -Eeuo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root, for example: sudo bash scripts/install-ubuntu.sh" >&2
  exit 1
fi
source /etc/os-release
if [[ "${ID:-}" != "ubuntu" ]] || dpkg --compare-versions "${VERSION_ID:-0}" lt "22.04"; then
  echo "This installer targets Ubuntu 22.04 LTS or later." >&2
  exit 1
fi

APP_DIR="/opt/ncapcheck"
APP_USER="ncapcheck"
REPO_URL="${NCAPCHECK_REPO_URL:-https://github.com/mikeehendricks/NCAPCheck.git}"
BRANCH="${NCAPCHECK_BRANCH:-main}"
DOMAIN="${DOMAIN:-}"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-}"
ENV_DIR="/etc/ncapcheck"
ENV_FILE="$ENV_DIR/ncapcheck.env"

if [[ -n "$DOMAIN" && ! "$DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]]; then
  echo "DOMAIN must be a DNS hostname (without a scheme or path)." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends git nginx python3 python3-venv python3-pip sqlite3 openssl sudo ca-certificates

if ! id -u "$APP_USER" >/dev/null 2>&1; then
  useradd --system --user-group --home-dir "$APP_DIR" --no-create-home --shell /usr/sbin/nologin "$APP_USER"
fi
install -d -o root -g "$APP_USER" -m 0750 "$APP_DIR"
install -d -o "$APP_USER" -g "$APP_USER" -m 0750 /var/lib/ncapcheck /var/log/ncapcheck /var/lib/ncapcheck/instance
install -d -o root -g "$APP_USER" -m 0750 "$ENV_DIR"

if [[ -d "$APP_DIR/.git" ]]; then
  actual_remote="$(git -C "$APP_DIR" remote get-url origin 2>/dev/null || true)"
  if [[ "$actual_remote" != "$REPO_URL" ]]; then
    echo "Existing $APP_DIR has an unexpected Git remote; refusing to overwrite it." >&2
    exit 1
  fi
elif [[ -n "$(find "$APP_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "$APP_DIR is not empty and is not an NCAPCheck Git checkout; refusing to overwrite it." >&2
  exit 1
else
  git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$APP_DIR"
fi

if [[ ! -x "$APP_DIR/venv/bin/python" ]]; then
  python3 -m venv "$APP_DIR/venv"
fi
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install --disable-pip-version-check -r "$APP_DIR/requirements-dev.txt"
chown -R root:"$APP_USER" "$APP_DIR"
chmod -R g+rX,o-rwx "$APP_DIR"

NEW_ENV=0
if [[ ! -f "$ENV_FILE" ]]; then
  NEW_ENV=1
  secret_key="$(openssl rand -hex 32)"
  encryption_key="$("$APP_DIR/venv/bin/python" -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
  setup_token="$(openssl rand -hex 24)"
  if [[ -n "$DOMAIN" && -n "$CERTBOT_EMAIL" ]]; then
    secure_cookie=true
  else
    secure_cookie=false
  fi
  cat > "$ENV_FILE" <<EOF
SECRET_KEY=$secret_key
APP_ENCRYPTION_KEY=$encryption_key
ADMIN_SETUP_TOKEN=$setup_token
DATABASE_URL=sqlite:////var/lib/ncapcheck/ncapcheck.db
INSTANCE_PATH=/var/lib/ncapcheck/instance
SESSION_COOKIE_SECURE=$secure_cookie
ENABLE_PANEL_UPDATES=true
GITHUB_REPO=mikeehendricks/NCAPCheck
SCHEDULER_INTERVAL_MINUTES=10
EOF
  chown root:"$APP_USER" "$ENV_FILE"
  chmod 0640 "$ENV_FILE"
fi

install -o root -g root -m 0644 "$APP_DIR/deploy/ncapcheck.service" /etc/systemd/system/ncapcheck.service
install -o root -g root -m 0644 "$APP_DIR/deploy/ncapcheck-worker.service" /etc/systemd/system/ncapcheck-worker.service
install -o root -g root -m 0644 "$APP_DIR/deploy/ncapcheck-update.service" /etc/systemd/system/ncapcheck-update.service
install -o root -g root -m 0750 "$APP_DIR/scripts/update-server.sh" /usr/local/sbin/ncapcheck-update
install -o root -g root -m 0750 "$APP_DIR/scripts/backup.sh" /usr/local/sbin/ncapcheck-backup
install -o root -g root -m 0440 "$APP_DIR/deploy/ncapcheck-updater.sudoers" /etc/sudoers.d/ncapcheck-updater
visudo -cf /etc/sudoers.d/ncapcheck-updater

site_domain="_"
if [[ -n "$DOMAIN" ]]; then site_domain="$DOMAIN"; fi
sed "s/__DOMAIN__/$site_domain/g" "$APP_DIR/deploy/nginx-site.conf" > /etc/nginx/sites-available/ncapcheck
ln -sfn /etc/nginx/sites-available/ncapcheck /etc/nginx/sites-enabled/ncapcheck
# This is intended for a dedicated host. Remove only Ubuntu's stock default site link.
if [[ -L /etc/nginx/sites-enabled/default ]]; then rm -f /etc/nginx/sites-enabled/default; fi
nginx -t

systemctl daemon-reload
systemctl enable --now ncapcheck.service ncapcheck-worker.service nginx.service

if [[ -n "$DOMAIN" && -n "$CERTBOT_EMAIL" ]]; then
  apt-get install -y --no-install-recommends certbot python3-certbot-nginx
  certbot --nginx --non-interactive --agree-tos --redirect --email "$CERTBOT_EMAIL" -d "$DOMAIN"
  if grep -q '^SESSION_COOKIE_SECURE=' "$ENV_FILE"; then
    sed -i 's/^SESSION_COOKIE_SECURE=.*/SESSION_COOKIE_SECURE=true/' "$ENV_FILE"
  else
    printf '\nSESSION_COOKIE_SECURE=true\n' >> "$ENV_FILE"
  fi
  chown root:"$APP_USER" "$ENV_FILE"
  chmod 0640 "$ENV_FILE"
  echo "HTTPS certificate installed for $DOMAIN."
else
  echo "WARNING: HTTPS was not configured. Do not expose login or vehicle data over public HTTP." >&2
  echo "Set DOMAIN and CERTBOT_EMAIL and rerun after DNS points to this server to request a Let's Encrypt certificate." >&2
fi

systemctl restart ncapcheck.service ncapcheck-worker.service

if [[ "$NEW_ENV" == "1" ]]; then
  admin_token="$(sed -n 's/^ADMIN_SETUP_TOKEN=//p' "$ENV_FILE")"
  if [[ -n "$DOMAIN" && -n "$CERTBOT_EMAIL" ]]; then
    admin_url="https://$DOMAIN/setup-admin"
  else
    admin_url="http://${DOMAIN:-YOUR_SERVER_ADDRESS}/setup-admin"
  fi
  echo
  echo "============================================================"
  echo "NCAPCheck installed. One-time admin setup token (save it):"
  echo "$admin_token"
  echo "Open: $admin_url"
  echo "This token is shown only on this first install. Store it securely."
  echo "============================================================"
else
  echo "NCAPCheck services updated; existing environment and encryption keys were preserved."
fi
