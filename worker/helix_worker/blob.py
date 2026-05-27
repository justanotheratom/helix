from __future__ import annotations

import io
from typing import BinaryIO

from minio import Minio

from . import settings


def _client() -> Minio:
    endpoint = settings.HELIX_BLOB_ENDPOINT.replace("http://", "").replace("https://", "")
    return Minio(
        endpoint,
        access_key=settings.HELIX_BLOB_ACCESS_KEY,
        secret_key=settings.HELIX_BLOB_SECRET_KEY,
        secure=settings.HELIX_BLOB_ENDPOINT.startswith("https://"),
    )


def ensure_bucket() -> None:
    c = _client()
    if not c.bucket_exists(settings.HELIX_BLOB_BUCKET):
        c.make_bucket(settings.HELIX_BLOB_BUCKET)


def get_bytes(key: str) -> bytes:
    obj = _client().get_object(settings.HELIX_BLOB_BUCKET, key)
    try:
        return obj.read()
    finally:
        obj.close()
        obj.release_conn()


def put_file(key: str, path: str, content_type: str = "application/octet-stream") -> None:
    ensure_bucket()
    _client().fput_object(settings.HELIX_BLOB_BUCKET, key, path, content_type=content_type)


def put_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    ensure_bucket()
    _client().put_object(
        settings.HELIX_BLOB_BUCKET, key, io.BytesIO(data), length=len(data), content_type=content_type
    )
