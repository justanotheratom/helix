from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="Artifact")


@_attrs_define
class Artifact:
    """
    Attributes:
        id (UUID):
        job_id (UUID):
        relative_path (str):
        kind (str):
        size_bytes (int):
        sha256 (str):
        attempt (int):
        created_at (datetime.datetime):
        mime (None | str | Unset):
    """

    id: UUID
    job_id: UUID
    relative_path: str
    kind: str
    size_bytes: int
    sha256: str
    attempt: int
    created_at: datetime.datetime
    mime: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = str(self.id)

        job_id = str(self.job_id)

        relative_path = self.relative_path

        kind = self.kind

        size_bytes = self.size_bytes

        sha256 = self.sha256

        attempt = self.attempt

        created_at = self.created_at.isoformat()

        mime: None | str | Unset
        if isinstance(self.mime, Unset):
            mime = UNSET
        else:
            mime = self.mime

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "job_id": job_id,
                "relative_path": relative_path,
                "kind": kind,
                "size_bytes": size_bytes,
                "sha256": sha256,
                "attempt": attempt,
                "created_at": created_at,
            }
        )
        if mime is not UNSET:
            field_dict["mime"] = mime

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        id = UUID(d.pop("id"))

        job_id = UUID(d.pop("job_id"))

        relative_path = d.pop("relative_path")

        kind = d.pop("kind")

        size_bytes = d.pop("size_bytes")

        sha256 = d.pop("sha256")

        attempt = d.pop("attempt")

        created_at = datetime.datetime.fromisoformat(d.pop("created_at"))

        def _parse_mime(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        mime = _parse_mime(d.pop("mime", UNSET))

        artifact = cls(
            id=id,
            job_id=job_id,
            relative_path=relative_path,
            kind=kind,
            size_bytes=size_bytes,
            sha256=sha256,
            attempt=attempt,
            created_at=created_at,
            mime=mime,
        )

        artifact.additional_properties = d
        return artifact

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
