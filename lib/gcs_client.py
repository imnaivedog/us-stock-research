from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from google.cloud import storage
from pydantic_settings import BaseSettings, SettingsConfigDict


class GCSSettings(BaseSettings):
    gcp_project_id: str = "naive-usstock-live"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


def upload_dir(local_path: str | Path, gcs_uri: str) -> list[str]:
    local_root = Path(local_path)
    if not local_root.exists():
        raise FileNotFoundError(local_root)
    parsed = urlparse(gcs_uri)
    if parsed.scheme != "gs" or not parsed.netloc:
        raise ValueError(f"Expected gs:// URI, got {gcs_uri}")

    bucket_name = parsed.netloc
    prefix = parsed.path.lstrip("/")
    if prefix and not prefix.endswith("/"):
        prefix += "/"

    client = storage.Client(project=GCSSettings().gcp_project_id)
    bucket = client.bucket(bucket_name)
    uploaded: list[str] = []
    for file_path in sorted(path for path in local_root.rglob("*") if path.is_file()):
        relative = file_path.relative_to(local_root).as_posix()
        blob_name = f"{prefix}{relative}"
        bucket.blob(blob_name).upload_from_filename(str(file_path))
        uploaded.append(f"gs://{bucket_name}/{blob_name}")
    return uploaded


def upload_file(local_path: str | Path, gcs_uri: str) -> str:
    file_path = Path(local_path)
    if not file_path.exists():
        raise FileNotFoundError(file_path)
    parsed = urlparse(gcs_uri)
    if parsed.scheme != "gs" or not parsed.netloc or not parsed.path.strip("/"):
        raise ValueError(f"Expected gs://bucket/path URI, got {gcs_uri}")

    bucket_name = parsed.netloc
    blob_name = parsed.path.lstrip("/")
    client = storage.Client(project=GCSSettings().gcp_project_id)
    bucket = client.bucket(bucket_name)
    bucket.blob(blob_name).upload_from_filename(str(file_path))
    return f"gs://{bucket_name}/{blob_name}"
