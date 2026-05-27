from __future__ import annotations

import json
from collections.abc import Mapping
from io import BytesIO
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from .. import types
from ..types import File

if TYPE_CHECKING:
    from ..models.import_compile_metadata import ImportCompileMetadata


T = TypeVar("T", bound="ImportCompileSubmission")


@_attrs_define
class ImportCompileSubmission:
    """
    Attributes:
        metadata (ImportCompileMetadata):
        bundle (File): tar.gz of the entire local results-dir (excluding evals/** and helix/**)
    """

    metadata: ImportCompileMetadata
    bundle: File
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        metadata = self.metadata.to_dict()

        bundle = self.bundle.to_tuple()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "metadata": metadata,
                "bundle": bundle,
            }
        )

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

        files.append(("bundle", self.bundle.to_tuple()))

        for prop_name, prop in self.additional_properties.items():
            files.append((prop_name, (None, str(prop).encode(), "text/plain")))

        return files

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.import_compile_metadata import ImportCompileMetadata

        d = dict(src_dict)
        metadata = ImportCompileMetadata.from_dict(d.pop("metadata"))

        bundle = File(payload=BytesIO(d.pop("bundle")))

        import_compile_submission = cls(
            metadata=metadata,
            bundle=bundle,
        )

        import_compile_submission.additional_properties = d
        return import_compile_submission

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
