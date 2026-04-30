#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="/lzcapp/document/usstock-backups"
LOG_DIR="${HOME}/logs"
DATE="$(date +%F)"
BACKUP_FILE="${BACKUP_DIR}/usstock-${DATE}.sql.gz"
LOG_FILE="${LOG_DIR}/weekly-backup-${DATE}.log"

mkdir -p "$BACKUP_DIR" "$LOG_DIR"

write_alert_log() {
  local severity="$1"
  local message="$2"

  if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "DATABASE_URL not set; skip alert_log write: ${severity} ${message}"
    return 0
  fi

  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
    -c "INSERT INTO alert_log (job_name, trade_date, severity, category, message)
        VALUES ('weekly_backup', CURRENT_DATE, '${severity}', 'backup', \$\$${message}\$\$);" \
    >/dev/null
}

{
  echo "=== weekly backup start $(date -u -Iseconds) ==="
  if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "DATABASE_URL is required for weekly_backup.sh" >&2
    exit 1
  fi

  pg_dump "$DATABASE_URL" | gzip -c > "$BACKUP_FILE"
  find "$BACKUP_DIR" -name "usstock-*.sql.gz" -type f -mtime +7 -delete
  if ! write_alert_log "INFO" "weekly backup completed: ${BACKUP_FILE}"; then
    echo "alert_log write failed after successful backup"
  fi
  echo "backup written: ${BACKUP_FILE}"
  echo "=== weekly backup end $(date -u -Iseconds) ==="
} 2>&1 | tee -a "$LOG_FILE"
