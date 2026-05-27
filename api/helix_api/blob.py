"""Thin minio wrapper for Helix blob storage."""
from __future__ import annotations

import io
from typing import BinaryIO

from minio import Minio
from minio.error import S3Error

from .settings import settings


def _client() -> Minio:
    endpoint = settings.blob_endpoint.replace("http://", "").replace("https://", "")
    return Minio(
        endpoint,
        access_key=settings.blob_access_key,
        secret_key=settings.blob_secret_key,
        secure=settings.blob_endpoint.startswith("https://"),
    )


def ensure_bucket() -> None:
    c = _client()
    if not c.bucket_exists(settings.blob_bucket):
        c.make_bucket(settings.blob_bucket)


def put_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    ensure_bucket()
    _client().put_object(
        settings.blob_bucket,
        key,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )


def put_stream(key: str, fp: BinaryIO, length: int, content_type: str = "application/octet-stream") -> None:
    ensure_bucket()
    _client().put_object(settings.blob_bucket, key, fp, length=length, content_type=content_type)


def get_object_stream(key: str):
    return _client().get_object(settings.blob_bucket, key)


def stat(key: str):
    try:
        return _client().stat_object(settings.blob_bucket, key)
    except S3Error:
        return None


def list_objects(prefix: str):
    """Yield minio Object entries under `prefix` (recursive)."""
    return _client().list_objects(settings.blob_bucket, prefix=prefix, recursive=True)


def remove_object(key: str) -> None:
    _client().remove_object(settings.blob_bucket, key)
