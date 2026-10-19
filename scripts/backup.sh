#!/usr/bin/env bash
set -Eeuo pipefail
DB_PATH="/var/lib/ncapcheck/ncapcheck.db"
BACKUP_DIR="/var/backups/ncapcheck"
mkdir -p "$BACKUP_DIR"
chmod 0700 "$BACKUP_DIR"
if [[ ! -f "$DB_PATH" ]]; then
  echo "Database not found: $DB_PATH" >&2
  exit 1
fi
output="$BACKUP_DIR/ncapcheck-manual-$(date -u +%Y%m%dT%H%M%SZ).sqlite3"
sqlite3 "$DB_PATH" ".backup '$output'"
chmod 0600 "$output"
echo "Backup written to $output"
