#!/usr/bin/env bash
set -euo pipefail

DATE="${1:-$(date -u -d 'yesterday' +%Y-%m-%d)}"
LOG_DIR="${HOME}/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/daily-${DATE}.log"

cd "${HOME}/us-stock-research"

{
  echo "=== usstock daily $DATE start $(date -u -Iseconds) ==="
  uv run --package usstock-data       usstock-data daily        --as-of "$DATE"
  uv run --package usstock-analytics  usstock-analytics themes-score --date "$DATE"
  uv run --package usstock-analytics  usstock-analytics a-pool signals --date "$DATE"
  uv run --package usstock-analytics  usstock-analytics signals --date "$DATE"
  uv run --package usstock-reports    usstock-reports daily     --date "$DATE"
  echo "=== usstock daily $DATE end $(date -u -Iseconds) ==="
} 2>&1 | tee -a "$LOG_FILE"
