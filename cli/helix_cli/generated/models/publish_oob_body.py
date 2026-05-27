from __future__ import annotations

from collections.abc import Mapping
from io import BytesIO
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from .. import types
from ..types import UNSET, File, FileTypes, Unset

T = TypeVar("T", bound="PublishOobBody")


@_attrs_define
class PublishOobBody:
    """
    Attributes:
        digest (str):
        tarball (File | Unset):
    """

    digest: str
    tarball: File | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        digest = self.digest

        tarball: FileTypes | Unset = UNSET
        if not isinstance(self.tarball, Unset):
            tarball = self.tarball.to_tuple()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "digest": digest,
            }
        )
        if tarball is not UNSET:
            field_dict["tarball"] = tarball

        return field_dict

    def to_multipart(self) -> types.RequestFiles:
        files: types.RequestFiles = []

        files.append(("digest", (None, str(self.digest).encode(), "text/plain")))

        if not isinstance(self.tarball, Unset):
            files.append(("tarball", self.tarball.to_tuple()))

        for prop_name, prop in self.additional_properties.items():
            files.append((prop_name, (None, str(prop).encode(), "text/plain")))

        return files

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        digest = d.pop("digest")

        _tarball = d.pop("tarball", UNSET)
        tarball: File | Unset
        if isinstance(_tarball, Unset):
            tarball = UNSET
        else:
            tarball = File(payload=BytesIO(_tarball))

        publish_oob_body = cls(
            digest=digest,
            tarball=tarball,
        )

        publish_oob_body.additional_properties = d
        return publish_oob_body

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
