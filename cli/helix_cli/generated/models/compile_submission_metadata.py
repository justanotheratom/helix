from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.compile_submission_metadata_configs_item import (
        CompileSubmissionMetadataConfigsItem,
    )


T = TypeVar("T", bound="CompileSubmissionMetadata")


@_attrs_define
class CompileSubmissionMetadata:
    """
    Attributes:
        repo_id (str): trusted-local multi-repo key
        configs (list[CompileSubmissionMetadataConfigsItem]):
        user_id (None | str | Unset): queue serialization key; defaults to the authenticated client or anonymous
        snapshot_id (None | Unset | UUID): published snapshot the job runs against
        snapshot_digest (None | str | Unset):
        helix_runtime_version (None | str | Unset): consumer's required helix-runtime version spec
        baked_sha (None | str | Unset): legacy; superseded by snapshot_id
        program (None | str | Unset): override; otherwise inferred from config path
        version (None | str | Unset):
        overlay_files (list[str] | Unset):
    """

    repo_id: str
    configs: list[CompileSubmissionMetadataConfigsItem]
    user_id: None | str | Unset = UNSET
    snapshot_id: None | Unset | UUID = UNSET
    snapshot_digest: None | str | Unset = UNSET
    helix_runtime_version: None | str | Unset = UNSET
    baked_sha: None | str | Unset = UNSET
    program: None | str | Unset = UNSET
    version: None | str | Unset = UNSET
    overlay_files: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        repo_id = self.repo_id

        configs = []
        for configs_item_data in self.configs:
            configs_item = configs_item_data.to_dict()
            configs.append(configs_item)

        user_id: None | str | Unset
        if isinstance(self.user_id, Unset):
            user_id = UNSET
        else:
            user_id = self.user_id

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

        program: None | str | Unset
        if isinstance(self.program, Unset):
            program = UNSET
        else:
            program = self.program

        version: None | str | Unset
        if isinstance(self.version, Unset):
            version = UNSET
        else:
            version = self.version

        overlay_files: list[str] | Unset = UNSET
        if not isinstance(self.overlay_files, Unset):
            overlay_files = self.overlay_files

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "repo_id": repo_id,
                "configs": configs,
            }
        )
        if user_id is not UNSET:
            field_dict["user_id"] = user_id
        if snapshot_id is not UNSET:
            field_dict["snapshot_id"] = snapshot_id
        if snapshot_digest is not UNSET:
            field_dict["snapshot_digest"] = snapshot_digest
        if helix_runtime_version is not UNSET:
            field_dict["helix_runtime_version"] = helix_runtime_version
        if baked_sha is not UNSET:
            field_dict["baked_sha"] = baked_sha
        if program is not UNSET:
            field_dict["program"] = program
        if version is not UNSET:
            field_dict["version"] = version
        if overlay_files is not UNSET:
            field_dict["overlay_files"] = overlay_files

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.compile_submission_metadata_configs_item import (
            CompileSubmissionMetadataConfigsItem,
        )

        d = dict(src_dict)
        repo_id = d.pop("repo_id")

        configs = []
        _configs = d.pop("configs")
        for configs_item_data in _configs:
            configs_item = CompileSubmissionMetadataConfigsItem.from_dict(
                configs_item_data
            )

            configs.append(configs_item)

        def _parse_user_id(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        user_id = _parse_user_id(d.pop("user_id", UNSET))

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

        def _parse_program(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        program = _parse_program(d.pop("program", UNSET))

        def _parse_version(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        version = _parse_version(d.pop("version", UNSET))

        overlay_files = cast(list[str], d.pop("overlay_files", UNSET))

        compile_submission_metadata = cls(
            repo_id=repo_id,
            configs=configs,
            user_id=user_id,
            snapshot_id=snapshot_id,
            snapshot_digest=snapshot_digest,
            helix_runtime_version=helix_runtime_version,
            baked_sha=baked_sha,
            program=program,
            version=version,
            overlay_files=overlay_files,
        )

        compile_submission_metadata.additional_properties = d
        return compile_submission_metadata

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
