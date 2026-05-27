from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.snapshot_meta_oob_blobs import SnapshotMetaOobBlobs
    from ..models.snapshot_meta_seed_state import SnapshotMetaSeedState


T = TypeVar("T", bound="SnapshotMeta")


@_attrs_define
class SnapshotMeta:
    """
    Attributes:
        repo_id (str):
        digest (str): sha256 of the uncompressed canonical tar
        helix_runtime_version (str):
        config_blob (str): the resolved .helix.toml (authoritative for the job)
        git_sha (None | str | Unset):
        lockfile_digest (None | str | Unset):
        base_fingerprint (None | str | Unset):
        seed_state (SnapshotMetaSeedState | Unset): max legacy run number per <program>/<version>
        oob_blobs (SnapshotMetaOobBlobs | Unset): {out_of_band root: blob digest} mounted as extra lowerdirs
    """

    repo_id: str
    digest: str
    helix_runtime_version: str
    config_blob: str
    git_sha: None | str | Unset = UNSET
    lockfile_digest: None | str | Unset = UNSET
    base_fingerprint: None | str | Unset = UNSET
    seed_state: SnapshotMetaSeedState | Unset = UNSET
    oob_blobs: SnapshotMetaOobBlobs | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        repo_id = self.repo_id

        digest = self.digest

        helix_runtime_version = self.helix_runtime_version

        config_blob = self.config_blob

        git_sha: None | str | Unset
        if isinstance(self.git_sha, Unset):
            git_sha = UNSET
        else:
            git_sha = self.git_sha

        lockfile_digest: None | str | Unset
        if isinstance(self.lockfile_digest, Unset):
            lockfile_digest = UNSET
        else:
            lockfile_digest = self.lockfile_digest

        base_fingerprint: None | str | Unset
        if isinstance(self.base_fingerprint, Unset):
            base_fingerprint = UNSET
        else:
            base_fingerprint = self.base_fingerprint

        seed_state: dict[str, Any] | Unset = UNSET
        if not isinstance(self.seed_state, Unset):
            seed_state = self.seed_state.to_dict()

        oob_blobs: dict[str, Any] | Unset = UNSET
        if not isinstance(self.oob_blobs, Unset):
            oob_blobs = self.oob_blobs.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "repo_id": repo_id,
                "digest": digest,
                "helix_runtime_version": helix_runtime_version,
                "config_blob": config_blob,
            }
        )
        if git_sha is not UNSET:
            field_dict["git_sha"] = git_sha
        if lockfile_digest is not UNSET:
            field_dict["lockfile_digest"] = lockfile_digest
        if base_fingerprint is not UNSET:
            field_dict["base_fingerprint"] = base_fingerprint
        if seed_state is not UNSET:
            field_dict["seed_state"] = seed_state
        if oob_blobs is not UNSET:
            field_dict["oob_blobs"] = oob_blobs

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.snapshot_meta_oob_blobs import SnapshotMetaOobBlobs
        from ..models.snapshot_meta_seed_state import SnapshotMetaSeedState

        d = dict(src_dict)
        repo_id = d.pop("repo_id")

        digest = d.pop("digest")

        helix_runtime_version = d.pop("helix_runtime_version")

        config_blob = d.pop("config_blob")

        def _parse_git_sha(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        git_sha = _parse_git_sha(d.pop("git_sha", UNSET))

        def _parse_lockfile_digest(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        lockfile_digest = _parse_lockfile_digest(d.pop("lockfile_digest", UNSET))

        def _parse_base_fingerprint(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(None | str | Unset, data)

        base_fingerprint = _parse_base_fingerprint(d.pop("base_fingerprint", UNSET))

        _seed_state = d.pop("seed_state", UNSET)
        seed_state: SnapshotMetaSeedState | Unset
        if isinstance(_seed_state, Unset):
            seed_state = UNSET
        else:
            seed_state = SnapshotMetaSeedState.from_dict(_seed_state)

        _oob_blobs = d.pop("oob_blobs", UNSET)
        oob_blobs: SnapshotMetaOobBlobs | Unset
        if isinstance(_oob_blobs, Unset):
            oob_blobs = UNSET
        else:
            oob_blobs = SnapshotMetaOobBlobs.from_dict(_oob_blobs)

        snapshot_meta = cls(
            repo_id=repo_id,
            digest=digest,
            helix_runtime_version=helix_runtime_version,
            config_blob=config_blob,
            git_sha=git_sha,
            lockfile_digest=lockfile_digest,
            base_fingerprint=base_fingerprint,
            seed_state=seed_state,
            oob_blobs=oob_blobs,
        )

        snapshot_meta.additional_properties = d
        return snapshot_meta

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
