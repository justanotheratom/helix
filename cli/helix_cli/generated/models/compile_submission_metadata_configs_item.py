from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="CompileSubmissionMetadataConfigsItem")


@_attrs_define
class CompileSubmissionMetadataConfigsItem:
    """
    Attributes:
        config_path (str): repo-relative path under <overlay-root>/<p>/<v>/
        dataset (str):
        split (str):
        auto_eval_config_path (None | str | Unset): If set, auto-chain an eval against this compile on success.
    """

    config_path: str
    dataset: str
    split: str
    auto_eval_config_path: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        config_path = self.config_path

        dataset = self.dataset

        split = self.split

        auto_eval_config_path: None | str | Unset
        if isinstance(self.auto_eval_config_path, Unset):
            auto_eval_config_path = UNSET
        else:
            auto_eval_config_path = self.auto_eval_config_path

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "config_path": config_path,
                "dataset": dataset,
                "split": split,
            }
        )
        if auto_eval_config_path is not UNSET:
            field_dict["auto_eval_config_path"] = auto_eval_config_path

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        config_path = d.pop("config_path")

        dataset = d.pop("dataset")

        split = d.pop("split")

        def _parse_auto_eval_config_path(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        auto_eval_config_path = _parse_auto_eval_config_path(
            d.pop("auto_eval_config_path", UNSET)
        )

        compile_submission_metadata_configs_item = cls(
            config_path=config_path,
            dataset=dataset,
            split=split,
            auto_eval_config_path=auto_eval_config_path,
        )

        compile_submission_metadata_configs_item.additional_properties = d
        return compile_submission_metadata_configs_item

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
