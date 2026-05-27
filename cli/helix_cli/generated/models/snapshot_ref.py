from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="SnapshotRef")


@_attrs_define
class SnapshotRef:
    """
    Attributes:
        snapshot_id (UUID):
        digest (str):
        existed (bool): true if this (repo_id,digest) already had a manifest
    """

    snapshot_id: UUID
    digest: str
    existed: bool
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        snapshot_id = str(self.snapshot_id)

        digest = self.digest

        existed = self.existed

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "snapshot_id": snapshot_id,
                "digest": digest,
                "existed": existed,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        snapshot_id = UUID(d.pop("snapshot_id"))

        digest = d.pop("digest")

        existed = d.pop("existed")

        snapshot_ref = cls(
            snapshot_id=snapshot_id,
            digest=digest,
            existed=existed,
        )

        snapshot_ref.additional_properties = d
        return snapshot_ref

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
