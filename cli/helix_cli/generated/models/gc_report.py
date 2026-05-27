from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

T = TypeVar("T", bound="GcReport")


@_attrs_define
class GcReport:
    """
    Attributes:
        dry_run (bool):
        grace_hours (int):
        deleted_manifests (int):
        deleted_snapshot_blobs (int):
        deleted_orphan_bundles (int):
        snapshot_blob_keys (list[str] | Unset):
        bundle_keys (list[str] | Unset):
    """

    dry_run: bool
    grace_hours: int
    deleted_manifests: int
    deleted_snapshot_blobs: int
    deleted_orphan_bundles: int
    snapshot_blob_keys: list[str] | Unset = UNSET
    bundle_keys: list[str] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        dry_run = self.dry_run

        grace_hours = self.grace_hours

        deleted_manifests = self.deleted_manifests

        deleted_snapshot_blobs = self.deleted_snapshot_blobs

        deleted_orphan_bundles = self.deleted_orphan_bundles

        snapshot_blob_keys: list[str] | Unset = UNSET
        if not isinstance(self.snapshot_blob_keys, Unset):
            snapshot_blob_keys = self.snapshot_blob_keys

        bundle_keys: list[str] | Unset = UNSET
        if not isinstance(self.bundle_keys, Unset):
            bundle_keys = self.bundle_keys

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "dry_run": dry_run,
                "grace_hours": grace_hours,
                "deleted_manifests": deleted_manifests,
                "deleted_snapshot_blobs": deleted_snapshot_blobs,
                "deleted_orphan_bundles": deleted_orphan_bundles,
            }
        )
        if snapshot_blob_keys is not UNSET:
            field_dict["snapshot_blob_keys"] = snapshot_blob_keys
        if bundle_keys is not UNSET:
            field_dict["bundle_keys"] = bundle_keys

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        dry_run = d.pop("dry_run")

        grace_hours = d.pop("grace_hours")

        deleted_manifests = d.pop("deleted_manifests")

        deleted_snapshot_blobs = d.pop("deleted_snapshot_blobs")

        deleted_orphan_bundles = d.pop("deleted_orphan_bundles")

        snapshot_blob_keys = cast(list[str], d.pop("snapshot_blob_keys", UNSET))

        bundle_keys = cast(list[str], d.pop("bundle_keys", UNSET))

        gc_report = cls(
            dry_run=dry_run,
            grace_hours=grace_hours,
            deleted_manifests=deleted_manifests,
            deleted_snapshot_blobs=deleted_snapshot_blobs,
            deleted_orphan_bundles=deleted_orphan_bundles,
            snapshot_blob_keys=snapshot_blob_keys,
            bundle_keys=bundle_keys,
        )

        gc_report.additional_properties = d
        return gc_report

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
