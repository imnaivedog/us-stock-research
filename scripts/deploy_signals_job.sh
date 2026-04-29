#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-naive-usstock-live}"
REGION="${REGION:-us-central1}"
IMAGE="${IMAGE:-us-central1-docker.pkg.dev/naive-usstock-live/us-stock-repo/publisher:latest}"
RUNNER_SA="${RUNNER_SA:-scheduler-sa@naive-usstock-live.iam.gserviceaccount.com}"

gcloud run jobs deploy signals-daily-job \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --image "${IMAGE}" \
  --set-env-vars PYTHONPATH=/app/src:/app,PYTHONUNBUFFERED=1 \
  --set-secrets DATABASE_URL=postgres-url:latest,FMP_API_KEY=fmp-key:latest \
  --command python \
  --args -m,signals.orchestrate \
  --max-retries 1 \
  --task-timeout 30m

gcloud scheduler jobs create http signals-daily-trigger \
  --project "${PROJECT_ID}" \
  --location "${REGION}" \
  --schedule "0 22 * * 2-6" \
  --time-zone UTC \
  --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/signals-daily-job:run" \
  --http-method POST \
  --oauth-service-account-email "${RUNNER_SA}" \
  || gcloud scheduler jobs update http signals-daily-trigger \
    --project "${PROJECT_ID}" \
    --location "${REGION}" \
    --schedule "0 22 * * 2-6" \
    --time-zone UTC \
    --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/signals-daily-job:run" \
    --http-method POST \
    --oauth-service-account-email "${RUNNER_SA}"
