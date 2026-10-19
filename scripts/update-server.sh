#!/usr/bin/env bash
# Root-owned entry point for the admin panel's fixed systemd updater.
set -Eeuo pipefail

APP_DIR="/opt/ncapcheck"
APP_USER="ncapcheck"
BRANCH="main"
DB_PATH="/var/lib/ncapcheck/ncapcheck.db"
BACKUP_DIR="/var/backups/ncapcheck"
LOCK_FILE="/run/lock/ncapcheck-update.lock"
TEST_TMP="/tmp/ncapcheck-update-tests"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "An NCAPCheck update is already running."
  exit 0
fi

mkdir -p "$BACKUP_DIR"
chmod 0700 "$BACKUP_DIR"
if [[ -f "$DB_PATH" ]]; then
  backup="$BACKUP_DIR/ncapcheck-$(date -u +%Y%m%dT%H%M%SZ).sqlite3"
  sqlite3 "$DB_PATH" ".backup '$backup'"
  chown root:root "$backup"
  chmod 0600 "$backup"
  echo "Database backup created: $backup"
fi
find "$BACKUP_DIR" -type f -name 'ncapcheck-*.sqlite3' -mtime +30 -delete

old_commit="$(git -C "$APP_DIR" rev-parse HEAD)"
rollback() {
  echo "Update failed; restoring application revision $old_commit" >&2
  git -C "$APP_DIR" reset --hard "$old_commit" || true
  "$APP_DIR/venv/bin/pip" install --disable-pip-version-check -r "$APP_DIR/requirements.txt" || true
  chown -R root:"$APP_USER" "$APP_DIR"
  chmod -R g+rX,o-rwx "$APP_DIR"
}

if ! git -C "$APP_DIR" fetch --quiet origin "$BRANCH"; then
  echo "Could not fetch the configured GitHub branch." >&2
  exit 1
fi
if ! git -C "$APP_DIR" merge --ff-only "origin/$BRANCH"; then
  echo "Update could not be fast-forwarded." >&2
  exit 1
fi

if ! "$APP_DIR/venv/bin/pip" install --disable-pip-version-check -r "$APP_DIR/requirements-dev.txt"; then
  rollback
  exit 1
fi
if ! bash -n "$APP_DIR/scripts/install-ubuntu.sh" "$APP_DIR/scripts/update-server.sh" "$APP_DIR/scripts/backup.sh"; then
  rollback
  exit 1
fi

rm -rf "$TEST_TMP"
install -d -o "$APP_USER" -g "$APP_USER" -m 0700 "$TEST_TMP"
if ! (cd "$APP_DIR" && runuser -u "$APP_USER" -- env \
    INSTANCE_PATH="$TEST_TMP/instance" \
    PYTHONDONTWRITEBYTECODE=1 \
    "$APP_DIR/venv/bin/pytest" -q -p no:cacheprovider "$APP_DIR/tests"); then
  rollback
  exit 1
fi
rm -rf "$TEST_TMP"

# Code and venv are readable/executable by the service account but not writable.
chown -R root:"$APP_USER" "$APP_DIR"
chmod -R g+rX,o-rwx "$APP_DIR"
install -o root -g root -m 0644 "$APP_DIR/deploy/ncapcheck.service" /etc/systemd/system/ncapcheck.service
install -o root -g root -m 0644 "$APP_DIR/deploy/ncapcheck-worker.service" /etc/systemd/system/ncapcheck-worker.service
install -o root -g root -m 0644 "$APP_DIR/deploy/ncapcheck-update.service" /etc/systemd/system/ncapcheck-update.service
install -o root -g root -m 0750 "$APP_DIR/scripts/update-server.sh" /usr/local/sbin/ncapcheck-update
install -o root -g root -m 0750 "$APP_DIR/scripts/backup.sh" /usr/local/sbin/ncapcheck-backup
install -o root -g root -m 0440 "$APP_DIR/deploy/ncapcheck-updater.sudoers" /etc/sudoers.d/ncapcheck-updater
visudo -cf /etc/sudoers.d/ncapcheck-updater >/dev/null
systemctl daemon-reload
systemctl restart ncapcheck.service ncapcheck-worker.service
systemctl is-active --quiet ncapcheck.service
systemctl is-active --quiet ncapcheck-worker.service
echo "NCAPCheck update completed successfully."
