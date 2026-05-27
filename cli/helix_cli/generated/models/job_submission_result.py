from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="JobSubmissionResult")


@_attrs_define
class JobSubmissionResult:
    """
    Attributes:
        job_id (UUID):
        run_label (str):
        ui_url (str):
        traces_url (str):
    """

    job_id: UUID
    run_label: str
    ui_url: str
    traces_url: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        job_id = str(self.job_id)

        run_label = self.run_label

        ui_url = self.ui_url

        traces_url = self.traces_url

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "job_id": job_id,
                "run_label": run_label,
                "ui_url": ui_url,
                "traces_url": traces_url,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        job_id = UUID(d.pop("job_id"))

        run_label = d.pop("run_label")

        ui_url = d.pop("ui_url")

        traces_url = d.pop("traces_url")

        job_submission_result = cls(
            job_id=job_id,
            run_label=run_label,
            ui_url=ui_url,
            traces_url=traces_url,
        )

        job_submission_result.additional_properties = d
        return job_submission_result

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
