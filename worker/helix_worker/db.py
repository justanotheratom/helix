"""Direct SQL via SQLAlchemy core — the worker doesn't need ORM mapping."""
from __future__ import annotations

from sqlalchemy import create_engine

from . import settings


engine = create_engine(settings.HELIX_DATABASE_URL, pool_pre_ping=True, future=True)


def connect():
    return engine.begin()
