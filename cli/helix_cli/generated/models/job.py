from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.job_status import JobStatus
from ..models.job_type import JobType
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.job_summary_type_0 import JobSummaryType0


T = TypeVar("T", bound="Job")


@_attrs_define
class Job:
    """
    Attributes:
        id (UUID):
        type_ (JobType):
        status (JobStatus):
        run_label (str):
        attempt (int):
        created_at (datetime.datetime):
        repo_id (None | str | Unset): trusted-local multi-repo key
        user_id (None | str | Unset): queue serialization key for the submitting user
        allow_parallel_user_jobs (bool | Unset): When true, this job may run even while another job from the same user
            is running. Default: False.
        snapshot_id (None | Unset | UUID): content-addressed snapshot the job runs against
        blocked_reason (None | str | Unset): why a 'blocked' job could not run (e.g. snapshot unavailable)
        program (None | str | Unset):
        version (None | str | Unset):
        dataset (None | str | Unset):
        split (None | str | Unset):
        parent_job_id (None | Unset | UUID):
        config_path (None | str | Unset): repo-relative path of the submitted config
        baked_sha (None | str | Unset): legacy; superseded by snapshot_id
        worker_id (None | str | Unset):
        lease_expires_at (datetime.datetime | None | Unset):
        emitted_run_number (int | None | Unset):
        export_run_number (int | None | Unset):
        started_at (datetime.datetime | None | Unset):
        ended_at (datetime.datetime | None | Unset):
        exit_code (int | None | Unset):
        summary (JobSummaryType0 | None | Unset): Final metrics parsed from the worker's status line (acc, cost, tokens,
            latency).
        ui_url (str | Unset): Absolute URL to this job in the UI
        traces_url (str | Unset): Absolute URL to the SSO trampoline that lands on this job's traces
    """

    id: UUID
    type_: JobType
    status: JobStatus
    run_label: str
    attempt: int
    created_at: datetime.datetime
    repo_id: None | str | Unset = UNSET
    user_id: None | str | Unset = UNSET
    allow_parallel_user_jobs: bool | Unset = False
    snapshot_id: None | Unset | UUID = UNSET
    blocked_reason: None | str | Unset = UNSET
    program: None | str | Unset = UNSET
    version: None | str | Unset = UNSET
    dataset: None | str | Unset = UNSET
    split: None | str | Unset = UNSET
    parent_job_id: None | Unset | UUID = UNSET
    config_path: None | str | Unset = UNSET
    baked_sha: None | str | Unset = UNSET
    worker_id: None | str | Unset = UNSET
    lease_expires_at: datetime.datetime | None | Unset = UNSET
    emitted_run_number: int | None | Unset = UNSET
    export_run_number: int | None | Unset = UNSET
    started_at: datetime.datetime | None | Unset = UNSET
    ended_at: datetime.datetime | None | Unset = UNSET
    exit_code: int | None | Unset = UNSET
    summary: JobSummaryType0 | None | Unset = UNSET
    ui_url: str | Unset = UNSET
    traces_url: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.job_summary_type_0 import JobSummaryType0

        id = str(self.id)

        type_ = self.type_.value

        status = self.status.value

        run_label = self.run_label

        attempt = self.attempt

        created_at = self.created_at.isoformat()

        repo_id: None | str | Unset
        if isinstance(self.repo_id, Unset):
            repo_id = UNSET
        else:
            repo_id = self.repo_id

        user_id: None | str | Unset
        if isinstance(self.user_id, Unset):
            user_id = UNSET
        else:
            user_id = self.user_id

        allow_parallel_user_jobs = self.allow_parallel_user_jobs

        snapshot_id: None | str | Unset
        if isinstance(self.snapshot_id, Unset):
            snapshot_id = UNSET
        elif isinstance(self.snapshot_id, UUID):
            snapshot_id = str(self.snapshot_id)
        else:
            snapshot_id = self.snapshot_id

        blocked_reason: None | str | Unset
        if isinstance(self.blocked_reason, Unset):
            blocked_reason = UNSET
        else:
            blocked_reason = self.blocked_reason

        program: None | str | Unset
        if isinstance(self.program, Unset):
            program = UNSET
        else:
            program = self.program

        version: None | str | Unset
        if isinstance(self.version, Unset):
            version = UNSET
        else:
            version = self.version

        dataset: None | str | Unset
        if isinstance(self.dataset, Unset):
            dataset = UNSET
        else:
            dataset = self.dataset

        split: None | str | Unset
        if isinstance(self.split, Unset):
            split = UNSET
        else:
            split = self.split

        parent_job_id: None | str | Unset
        if isinstance(self.parent_job_id, Unset):
            parent_job_id = UNSET
        elif isinstance(self.parent_job_id, UUID):
            parent_job_id = str(self.parent_job_id)
        else:
            parent_job_id = self.parent_job_id

        config_path: None | str | Unset
        if isinstance(self.config_path, Unset):
            config_path = UNSET
        else:
            config_path = self.config_path

        baked_sha: None | str | Unset
        if isinstance(self.baked_sha, Unset):
            baked_sha = UNSET
        else:
            baked_sha = self.baked_sha

        worker_id: None | str | Unset
        if isinstance(self.worker_id, Unset):
            worker_id = UNSET
        else:
            worker_id = self.worker_id

        lease_expires_at: None | str | Unset
        if isinstance(self.lease_expires_at, Unset):
            lease_expires_at = UNSET
        elif isinstance(self.lease_expires_at, datetime.datetime):
            lease_expires_at = self.lease_expires_at.isoformat()
        else:
            lease_expires_at = self.lease_expires_at

        emitted_run_number: int | None | Unset
        if isinstance(self.emitted_run_number, Unset):
            emitted_run_number = UNSET
        else:
            emitted_run_number = self.emitted_run_number

        export_run_number: int | None | Unset
        if isinstance(self.export_run_number, Unset):
            export_run_number = UNSET
        else:
            export_run_number = self.export_run_number

        started_at: None | str | Unset
        if isinstance(self.started_at, Unset):
            started_at = UNSET
        elif isinstance(self.started_at, datetime.datetime):
            started_at = self.started_at.isoformat()
        else:
            started_at = self.started_at

        ended_at: None | str | Unset
        if isinstance(self.ended_at, Unset):
            ended_at = UNSET
        elif isinstance(self.ended_at, datetime.datetime):
            ended_at = self.ended_at.isoformat()
        else:
            ended_at = self.ended_at

        exit_code: int | None | Unset
        if isinstance(self.exit_code, Unset):
            exit_code = UNSET
        else:
            exit_code = self.exit_code

        summary: dict[str, Any] | None | Unset
        if isinstance(self.summary, Unset):
            summary = UNSET
        elif isinstance(self.summary, JobSummaryType0):
            summary = self.summary.to_dict()
        else:
            summary = self.summary

        ui_url = self.ui_url

        traces_url = self.traces_url

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "type": type_,
                "status": status,
                "run_label": run_label,
                "attempt": attempt,
                "created_at": created_at,
            }
        )
        if repo_id is not UNSET:
            field_dict["repo_id"] = repo_id
        if user_id is not UNSET:
            field_dict["user_id"] = user_id
        if allow_parallel_user_jobs is not UNSET:
            field_dict["allow_parallel_user_jobs"] = allow_parallel_user_jobs
        if snapshot_id is not UNSET:
            field_dict["snapshot_id"] = snapshot_id
        if blocked_reason is not UNSET:
            field_dict["blocked_reason"] = blocked_reason
        if program is not UNSET:
            field_dict["program"] = program
        if version is not UNSET:
            field_dict["version"] = version
        if dataset is not UNSET:
            field_dict["dataset"] = dataset
        if split is not UNSET:
            field_dict["split"] = split
        if parent_job_id is not UNSET:
            field_dict["parent_job_id"] = parent_job_id
        if config_path is not UNSET:
            field_dict["config_path"] = config_path
        if baked_sha is not UNSET:
            field_dict["baked_sha"] = baked_sha
        if worker_id is not UNSET:
            field_dict["worker_id"] = worker_id
        if lease_expires_at is not UNSET:
            field_dict["lease_expires_at"] = lease_expires_at
        if emitted_run_number is not UNSET:
            field_dict["emitted_run_number"] = emitted_run_number
        if export_run_number is not UNSET:
            field_dict["export_run_number"] = export_run_number
        if started_at is not UNSET:
            field_dict["started_at"] = started_at
        if ended_at is not UNSET:
            field_dict["ended_at"] = ended_at
        if exit_code is not UNSET:
            field_dict["exit_code"] = exit_code
        if summary is not UNSET:
            field_dict["summary"] = summary
        if ui_url is not UNSET:
            field_dict["ui_url"] = ui_url
        if traces_url is not UNSET:
            field_dict["traces_url"] = traces_url

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.job_summary_type_0 import JobSummaryType0

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        type_ = JobType(d.pop("type"))

        status = JobStatus(d.pop("status"))

        run_label = d.pop("run_label")

        attempt = d.pop("attempt")

        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))

        def _parse_repo_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        repo_id = _parse_repo_id(d.pop("repo_id", UNSET))

        def _parse_user_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        user_id = _parse_user_id(d.pop("user_id", UNSET))

        allow_parallel_user_jobs = d.pop("allow_parallel_user_jobs", UNSET)

        def _parse_snapshot_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                snapshot_id_type_0 = UUID(data)

                return snapshot_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        snapshot_id = _parse_snapshot_id(d.pop("snapshot_id", UNSET))

        def _parse_blocked_reason(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        blocked_reason = _parse_blocked_reason(d.pop("blocked_reason", UNSET))

        def _parse_program(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        program = _parse_program(d.pop("program", UNSET))

        def _parse_version(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        version = _parse_version(d.pop("version", UNSET))

        def _parse_dataset(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        dataset = _parse_dataset(d.pop("dataset", UNSET))

        def _parse_split(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        split = _parse_split(d.pop("split", UNSET))

        def _parse_parent_job_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                parent_job_id_type_0 = UUID(data)

                return parent_job_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        parent_job_id = _parse_parent_job_id(d.pop("parent_job_id", UNSET))

        def _parse_config_path(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        config_path = _parse_config_path(d.pop("config_path", UNSET))

        def _parse_baked_sha(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        baked_sha = _parse_baked_sha(d.pop("baked_sha", UNSET))

        def _parse_worker_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        worker_id = _parse_worker_id(d.pop("worker_id", UNSET))

        def _parse_lease_expires_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                lease_expires_at_type_0 = datetime.datetime.fromisoformat(data)

                return lease_expires_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        lease_expires_at = _parse_lease_expires_at(d.pop("lease_expires_at", UNSET))

        def _parse_emitted_run_number(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        emitted_run_number = _parse_emitted_run_number(
            d.pop("emitted_run_number", UNSET)
        )

        def _parse_export_run_number(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        export_run_number = _parse_export_run_number(d.pop("export_run_number", UNSET))

        def _parse_started_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                started_at_type_0 = datetime.datetime.fromisoformat(data)

                return started_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        started_at = _parse_started_at(d.pop("started_at", UNSET))

        def _parse_ended_at(data: object) -> datetime.datetime | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                ended_at_type_0 = datetime.datetime.fromisoformat(data)

                return ended_at_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(datetime.datetime | None | Unset, data)

        ended_at = _parse_ended_at(d.pop("ended_at", UNSET))

        def _parse_exit_code(data: object) -> int | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(int | None | Unset, data)

        exit_code = _parse_exit_code(d.pop("exit_code", UNSET))

        def _parse_summary(data: object) -> JobSummaryType0 | None | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                summary_type_0 = JobSummaryType0.from_dict(data)

                return summary_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(JobSummaryType0 | None | Unset, data)

        summary = _parse_summary(d.pop("summary", UNSET))

        ui_url = d.pop("ui_url", UNSET)

        traces_url = d.pop("traces_url", UNSET)

        job = cls(
            id=id,
            type_=type_,
            status=status,
            run_label=run_label,
            attempt=attempt,
            created_at=created_at,
            repo_id=repo_id,
            user_id=user_id,
            allow_parallel_user_jobs=allow_parallel_user_jobs,
            snapshot_id=snapshot_id,
            blocked_reason=blocked_reason,
            program=program,
            version=version,
            dataset=dataset,
            split=split,
            parent_job_id=parent_job_id,
            config_path=config_path,
            baked_sha=baked_sha,
            worker_id=worker_id,
            lease_expires_at=lease_expires_at,
            emitted_run_number=emitted_run_number,
            export_run_number=export_run_number,
            started_at=started_at,
            ended_at=ended_at,
            exit_code=exit_code,
            summary=summary,
            ui_url=ui_url,
            traces_url=traces_url,
        )

        job.additional_properties = d
        return job

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
