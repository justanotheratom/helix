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
    from ..models.eval_submission_metadata import EvalSubmissionMetadata


T = TypeVar("T", bound="EvalSubmission")


@_attrs_define
class EvalSubmission:
    """
    Attributes:
        metadata (EvalSubmissionMetadata):
        bundle (File):
    """

    metadata: EvalSubmissionMetadata
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
        from ..models.eval_submission_metadata import EvalSubmissionMetadata

        d = dict(src_dict)
        metadata = EvalSubmissionMetadata.from_dict(d.pop("metadata"))

        bundle = File(payload=BytesIO(d.pop("bundle")))

        eval_submission = cls(
            metadata=metadata,
            bundle=bundle,
        )

        eval_submission.additional_properties = d
        return eval_submission

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
