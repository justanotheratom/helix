from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.eval_submission_metadata_configs_item import (
        EvalSubmissionMetadataConfigsItem,
    )


T = TypeVar("T", bound="EvalSubmissionMetadata")


@_attrs_define
class EvalSubmissionMetadata:
    """
    Attributes:
        repo_id (str): trusted-local multi-repo key
        configs (list[EvalSubmissionMetadataConfigsItem]):
        snapshot_id (None | Unset | UUID):
        snapshot_digest (None | str | Unset):
        helix_runtime_version (None | str | Unset):
        baked_sha (None | str | Unset): legacy; superseded by snapshot_id
        overlay_files (list[str] | Unset):
        inherit_bundle_from_compile_job_id (None | Unset | UUID): When set, the new eval job(s) reuse bundle_blob_key
            from the
            named compile. Used by the worker's auto-eval-chain hook so
            the eval has the same overlay as its parent compile.
    """

    repo_id: str
    configs: list[EvalSubmissionMetadataConfigsItem]
    snapshot_id: None | Unset | UUID = UNSET
    snapshot_digest: None | str | Unset = UNSET
    helix_runtime_version: None | str | Unset = UNSET
    baked_sha: None | str | Unset = UNSET
    overlay_files: list[str] | Unset = UNSET
    inherit_bundle_from_compile_job_id: None | Unset | UUID = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        repo_id = self.repo_id

        configs = []
        for configs_item_data in self.configs:
            configs_item = configs_item_data.to_dict()
            configs.append(configs_item)

        snapshot_id: None | str | Unset
        if isinstance(self.snapshot_id, Unset):
            snapshot_id = UNSET
        elif isinstance(self.snapshot_id, UUID):
            snapshot_id = str(self.snapshot_id)
        else:
            snapshot_id = self.snapshot_id

        snapshot_digest: None | str | Unset
        if isinstance(self.snapshot_digest, Unset):
            snapshot_digest = UNSET
        else:
            snapshot_digest = self.snapshot_digest

        helix_runtime_version: None | str | Unset
        if isinstance(self.helix_runtime_version, Unset):
            helix_runtime_version = UNSET
        else:
            helix_runtime_version = self.helix_runtime_version

        baked_sha: None | str | Unset
        if isinstance(self.baked_sha, Unset):
            baked_sha = UNSET
        else:
            baked_sha = self.baked_sha

        overlay_files: list[str] | Unset = UNSET
        if not isinstance(self.overlay_files, Unset):
            overlay_files = self.overlay_files

        inherit_bundle_from_compile_job_id: None | str | Unset
        if isinstance(self.inherit_bundle_from_compile_job_id, Unset):
            inherit_bundle_from_compile_job_id = UNSET
        elif isinstance(self.inherit_bundle_from_compile_job_id, UUID):
            inherit_bundle_from_compile_job_id = str(
                self.inherit_bundle_from_compile_job_id
            )
        else:
            inherit_bundle_from_compile_job_id = self.inherit_bundle_from_compile_job_id

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "repo_id": repo_id,
                "configs": configs,
            }
        )
        if snapshot_id is not UNSET:
            field_dict["snapshot_id"] = snapshot_id
        if snapshot_digest is not UNSET:
            field_dict["snapshot_digest"] = snapshot_digest
        if helix_runtime_version is not UNSET:
            field_dict["helix_runtime_version"] = helix_runtime_version
        if baked_sha is not UNSET:
            field_dict["baked_sha"] = baked_sha
        if overlay_files is not UNSET:
            field_dict["overlay_files"] = overlay_files
        if inherit_bundle_from_compile_job_id is not UNSET:
            field_dict["inherit_bundle_from_compile_job_id"] = (
                inherit_bundle_from_compile_job_id
            )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.eval_submission_metadata_configs_item import (
            EvalSubmissionMetadataConfigsItem,
        )

        d = dict(src_dict)
        repo_id = d.pop("repo_id")

        configs = []
        _configs = d.pop("configs")
        for configs_item_data in _configs:
            configs_item = EvalSubmissionMetadataConfigsItem.from_dict(
                configs_item_data
            )

            configs.append(configs_item)

        def _parse_snapshot_id(data: object) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                snapshot_id_type_0 = UUID(data)

                return snapshot_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        snapshot_id = _parse_snapshot_id(d.pop("snapshot_id", UNSET))

        def _parse_snapshot_digest(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        snapshot_digest = _parse_snapshot_digest(d.pop("snapshot_digest", UNSET))

        def _parse_helix_runtime_version(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        helix_runtime_version = _parse_helix_runtime_version(
            d.pop("helix_runtime_version", UNSET)
        )

        def _parse_baked_sha(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        baked_sha = _parse_baked_sha(d.pop("baked_sha", UNSET))

        overlay_files = cast(list[str], d.pop("overlay_files", UNSET))

        def _parse_inherit_bundle_from_compile_job_id(
            data: object,
        ) -> None | Unset | UUID:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, str):
                    raise TypeError()
                inherit_bundle_from_compile_job_id_type_0 = UUID(data)

                return inherit_bundle_from_compile_job_id_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | Unset | UUID, data)

        inherit_bundle_from_compile_job_id = _parse_inherit_bundle_from_compile_job_id(
            d.pop("inherit_bundle_from_compile_job_id", UNSET)
        )

        eval_submission_metadata = cls(
            repo_id=repo_id,
            configs=configs,
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest,
            helix_runtime_version=helix_runtime_version,
            baked_sha=baked_sha,
            overlay_files=overlay_files,
            inherit_bundle_from_compile_job_id=inherit_bundle_from_compile_job_id,
        )

        eval_submission_metadata.additional_properties = d
        return eval_submission_metadata

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
