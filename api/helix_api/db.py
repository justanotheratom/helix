"""SQLAlchemy session + ORM models matching helix/api/db/migrations/001_initial.sql."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

from .settings import settings


engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


class Program(Base):
    __tablename__ = "programs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repo_id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (UniqueConstraint("repo_id", "name", name="uq_programs_repo_name"),)


class ProgramVersion(Base):
    __tablename__ = "program_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    program_id: Mapped[int] = mapped_column(ForeignKey("programs.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (UniqueConstraint("program_id", "version"),)
    program: Mapped[Program] = relationship()


class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    program_version_id: Mapped[int] = mapped_column(
        ForeignKey("program_versions.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (UniqueConstraint("program_version_id", "version"),)
    program_version: Mapped[ProgramVersion] = relationship()


class Split(Base):
    __tablename__ = "splits"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    __table_args__ = (UniqueConstraint("dataset_id", "version"),)
    dataset: Mapped[Dataset] = relationship()


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    repo_id: Mapped[str] = mapped_column(Text, nullable=False)
    program_version_id: Mapped[int] = mapped_column(ForeignKey("program_versions.id"), nullable=False)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id"), nullable=False)
    split_id: Mapped[int] = mapped_column(ForeignKey("splits.id"), nullable=False)
    parent_job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    config_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_blob_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    bundle_blob_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    baked_sha: Mapped[str | None] = mapped_column(Text, nullable=True)  # legacy; superseded by snapshot_id
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("snapshots.id"), nullable=True)
    helix_runtime_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    blocked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_label: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    worker_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    emitted_run_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    export_run_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint("type IN ('compile','eval')"),
        CheckConstraint("status IN ('queued','running','succeeded','failed','cancelled')"),
    )


class Artifact(Base):
    __tablename__ = "artifacts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    relative_path: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    blob_key: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mime: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Snapshot(Base):
    __tablename__ = "snapshots"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_id: Mapped[str] = mapped_column(Text, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    git_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    helix_runtime_version: Mapped[str] = mapped_column(Text, nullable=False)
    lockfile_digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_fingerprint: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_blob: Mapped[str] = mapped_column(Text, nullable=False)
    seed_state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # {oob_root: digest} — large data published as separate content-addressed
    # blobs and mounted as extra overlayfs lowerdirs (Phase 3).
    oob_blobs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    __table_args__ = (UniqueConstraint("repo_id", "digest"),)


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    worker_id: Mapped[str] = mapped_column(Text, primary_key=True)
    baked_sha: Mapped[str] = mapped_column(Text, nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LegacyCompileRunNumber(Base):
    __tablename__ = "legacy_compile_run_numbers"
    program_version_id: Mapped[int] = mapped_column(
        ForeignKey("program_versions.id", ondelete="CASCADE"), primary_key=True
    )
    next_number: Mapped[int] = mapped_column(Integer, nullable=False)


class LegacyEvalRunNumber(Base):
    __tablename__ = "legacy_eval_run_numbers"
    compile_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True
    )
    next_number: Mapped[int] = mapped_column(Integer, nullable=False)


def get_session() -> Session:
    return SessionLocal()
