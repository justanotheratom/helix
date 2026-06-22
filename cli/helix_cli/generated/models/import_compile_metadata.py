from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="ImportCompileMetadata")


@_attrs_define
class ImportCompileMetadata:
    """
    Attributes:
        repo_id (str): trusted-local multi-repo key
        program (str):
        version (str):
        dataset (str):
        split (str):
        emitted_run_number (int):
        results_dir_basename (str):
        user_id (None | str | Unset): queue serialization key; defaults to the authenticated client or anonymous
        compile_config_path (None | str | Unset):
    """

    repo_id: str
    program: str
    version: str
    dataset: str
    split: str
    emitted_run_number: int
    results_dir_basename: str
    user_id: None | str | Unset = UNSET
    compile_config_path: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        repo_id = self.repo_id

        program = self.program

        version = self.version

        dataset = self.dataset

        split = self.split

        emitted_run_number = self.emitted_run_number

        results_dir_basename = self.results_dir_basename

        user_id: None | str | Unset
        if isinstance(self.user_id, Unset):
            user_id = UNSET
        else:
            user_id = self.user_id

        compile_config_path: None | str | Unset
        if isinstance(self.compile_config_path, Unset):
            compile_config_path = UNSET
        else:
            compile_config_path = self.compile_config_path

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "repo_id": repo_id,
                "program": program,
                "version": version,
                "dataset": dataset,
                "split": split,
                "emitted_run_number": emitted_run_number,
                "results_dir_basename": results_dir_basename,
            }
        )
        if user_id is not UNSET:
            field_dict["user_id"] = user_id
        if compile_config_path is not UNSET:
            field_dict["compile_config_path"] = compile_config_path

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        repo_id = d.pop("repo_id")

        program = d.pop("program")

        version = d.pop("version")

        dataset = d.pop("dataset")

        split = d.pop("split")

        emitted_run_number = d.pop("emitted_run_number")

        results_dir_basename = d.pop("results_dir_basename")

        def _parse_user_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        user_id = _parse_user_id(d.pop("user_id", UNSET))

        def _parse_compile_config_path(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        compile_config_path = _parse_compile_config_path(
            d.pop("compile_config_path", UNSET)
        )

        import_compile_metadata = cls(
            repo_id=repo_id,
            program=program,
            version=version,
            dataset=dataset,
            split=split,
            emitted_run_number=emitted_run_number,
            results_dir_basename=results_dir_basename,
            user_id=user_id,
            compile_config_path=compile_config_path,
        )

        import_compile_metadata.additional_properties = d
        return import_compile_metadata

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
