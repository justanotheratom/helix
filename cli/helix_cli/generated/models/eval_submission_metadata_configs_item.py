from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="EvalSubmissionMetadataConfigsItem")


@_attrs_define
class EvalSubmissionMetadataConfigsItem:
    """
    Attributes:
        config_path (str):
        compile_job_id (UUID):
        dataset (None | str | Unset):
        split (None | str | Unset):
    """

    config_path: str
    compile_job_id: UUID
    dataset: None | str | Unset = UNSET
    split: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        config_path = self.config_path

        compile_job_id = str(self.compile_job_id)

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

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "config_path": config_path,
                "compile_job_id": compile_job_id,
            }
        )
        if dataset is not UNSET:
            field_dict["dataset"] = dataset
        if split is not UNSET:
            field_dict["split"] = split

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        config_path = d.pop("config_path")

        compile_job_id = UUID(d.pop("compile_job_id"))

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

        eval_submission_metadata_configs_item = cls(
            config_path=config_path,
            compile_job_id=compile_job_id,
            dataset=dataset,
            split=split,
        )

        eval_submission_metadata_configs_item.additional_properties = d
        return eval_submission_metadata_configs_item

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
