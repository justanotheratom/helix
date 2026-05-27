from __future__ import annotations

import json
from collections.abc import Mapping
from io import BytesIO
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from .. import types
from ..types import UNSET, File, FileTypes, Unset

if TYPE_CHECKING:
    from ..models.snapshot_meta import SnapshotMeta


T = TypeVar("T", bound="SnapshotPublish")


@_attrs_define
class SnapshotPublish:
    """
    Attributes:
        metadata (SnapshotMeta):
        tarball (File | Unset): gzip'd snapshot tar; omittable when the digest object already exists
    """

    metadata: SnapshotMeta
    tarball: File | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        metadata = self.metadata.to_dict()

        tarball: FileTypes | Unset = UNSET
        if not isinstance(self.tarball, Unset):
            tarball = self.tarball.to_tuple()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "metadata": metadata,
            }
        )
        if tarball is not UNSET:
            field_dict["tarball"] = tarball

        return field_dict

    def to_multipart(self) -> types.RequestFiles:
        files: types.RequestFiles = []

        files.append(
            (
                "metadata",
                (
                    None,
                    json.dumps(self.metadata.to_dict()).encode(),
                    "application/json",
                ),
            )
        )

        if not isinstance(self.tarball, Unset):
            files.append(("tarball", self.tarball.to_tuple()))

        for prop_name, prop in self.additional_properties.items():
            files.append((prop_name, (None, str(prop).encode(), "text/plain")))

        return files

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.snapshot_meta import SnapshotMeta

        d = dict(src_dict)
        metadata = SnapshotMeta.from_dict(d.pop("metadata"))

        _tarball = d.pop("tarball", UNSET)
        tarball: File | Unset
        if isinstance(_tarball, Unset):
            tarball = UNSET
        else:
            tarball = File(payload=BytesIO(_tarball))

        snapshot_publish = cls(
            metadata=metadata,
            tarball=tarball,
        )

        snapshot_publish.additional_properties = d
        return snapshot_publish

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
