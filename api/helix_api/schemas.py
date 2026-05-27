"""Pydantic models, kept in lock-step with helix/openapi/openapi.yaml.

Once `helix/openapi/codegen.sh` is wired, this file is replaced by
`from helix_api.generated import *` and any change to a request/response
shape goes through the YAML first.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


JobType = Literal["compile", "eval"]
JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class Error(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class WorkerHeartbeatInfo(BaseModel):
    worker_id: str
    baked_sha: str
    last_seen: datetime


class BakedShaInfo(BaseModel):
    baked_sha: str
    workers: list[WorkerHeartbeatInfo]


class Job(BaseModel):
    id: uuid.UUID
    type: JobType
    status: JobStatus
    repo_id: str | None = None
    snapshot_id: uuid.UUID | None = None
    blocked_reason: str | None = None
    program: str | None = None
    version: str | None = None
    dataset: str | None = None
    split: str | None = None
    parent_job_id: uuid.UUID | None = None
    config_path: str | None = None
    baked_sha: str | None = None
    run_label: str
    attempt: int
    worker_id: str | None = None
    lease_expires_at: datetime | None = None
    emitted_run_number: int | None = None
    export_run_number: int | None = None
    created_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    exit_code: int | None = None
    summary: dict[str, Any] | None = None
    ui_url: str
    traces_url: str


class JobSubmissionResult(BaseModel):
    job_id: uuid.UUID
    run_label: str
    ui_url: str
    traces_url: str


class CompileConfigEntry(BaseModel):
    config_path: str
    dataset: str
    split: str
    auto_eval_config_path: str | None = None


class CompileSubmissionMetadata(BaseModel):
    repo_id: str
    baked_sha: str | None = None
    snapshot_id: uuid.UUID | None = None
    snapshot_digest: str | None = None
    helix_runtime_version: str | None = None
    program: str | None = None
    version: str | None = None
    configs: list[CompileConfigEntry] = Field(min_length=1)
    overlay_files: list[str] = []


class EvalConfigEntry(BaseModel):
    config_path: str
    compile_job_id: uuid.UUID
    dataset: str | None = None
    split: str | None = None


class EvalSubmissionMetadata(BaseModel):
    repo_id: str
    baked_sha: str | None = None
    snapshot_id: uuid.UUID | None = None
    snapshot_digest: str | None = None
    helix_runtime_version: str | None = None
    configs: list[EvalConfigEntry] = Field(min_length=1)
    overlay_files: list[str] = []
    # When set, the new eval job(s) inherit bundle_blob_key from the named
    # compile job rather than the (possibly empty) multipart bundle. Used by
    # the worker's auto-eval-chain hook so the eval shares the parent's overlay.
    inherit_bundle_from_compile_job_id: uuid.UUID | None = None


class ImportCompileMetadata(BaseModel):
    repo_id: str
    program: str
    version: str
    dataset: str
    split: str
    emitted_run_number: int
    results_dir_basename: str
    compile_config_path: str | None = None


class Artifact(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    relative_path: str
    kind: str
    size_bytes: int
    sha256: str
    mime: str | None = None
    attempt: int
    created_at: datetime


class LogEvent(BaseModel):
    seq: int
    ts: datetime
    stream: Literal["stdout", "stderr"]
    line: str


class TracesUrl(BaseModel):
    url: str
    run_label: str
