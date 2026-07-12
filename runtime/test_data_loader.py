from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runtime.data_loader import load_from_manifest


class StableIdSplitManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.data = self.root / "data"
        self.splits = self.data / "splits"
        self.splits.mkdir(parents=True)
        self.dataset = self.data / "examples.jsonl"
        self.manifest = self.splits / "examples_001.yaml"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_dataset(self, sample_ids: list[str]) -> None:
        self.dataset.write_text(
            "".join(
                json.dumps({"id": sample_id, "value": sample_id.upper()}) + "\n"
                for sample_id in sample_ids
            ),
            encoding="utf-8",
        )

    def write_v2_manifest(
        self,
        *,
        train: list[str] | None = None,
        val: list[str] | None = None,
        test: list[str] | None = None,
    ) -> None:
        partitions = {
            "train": train or [],
            "val": val or [],
            "test": test or [],
        }
        lines = [
            "schema_version: helix-splits/v2",
            "source: examples.jsonl",
            "id_field: id",
        ]
        for name, sample_ids in partitions.items():
            if sample_ids:
                lines.append(f"{name}:")
                lines.extend(f"    - {sample_id}" for sample_id in sample_ids)
            else:
                lines.append(f"{name}: []")
        self.manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_v2_split_selection_is_invariant_to_source_order(self) -> None:
        self.write_dataset(["a", "b", "c"])
        self.write_v2_manifest(train=["b"], val=["a"], test=["c"])

        first = load_from_manifest(self.manifest, "train")
        self.write_dataset(["c", "a", "b"])
        second = load_from_manifest(self.manifest, "train")

        self.assertEqual(first, [{"id": "b", "value": "B"}])
        self.assertEqual(second, first)

    def test_v2_rejects_duplicate_source_ids(self) -> None:
        self.write_dataset(["a", "a"])
        self.write_v2_manifest(train=["a"])

        with self.assertRaisesRegex(ValueError, "Duplicate dataset ID 'a'"):
            load_from_manifest(self.manifest, "train")

    def test_v2_rejects_unknown_split_ids(self) -> None:
        self.write_dataset(["a"])
        self.write_v2_manifest(train=["missing"], val=["a"])

        with self.assertRaisesRegex(ValueError, "unknown dataset ID 'missing'"):
            load_from_manifest(self.manifest, "train")

    def test_v2_rejects_cross_partition_duplicates(self) -> None:
        self.write_dataset(["a"])
        self.write_v2_manifest(train=["a"], val=["a"])

        with self.assertRaisesRegex(ValueError, "appears more than once"):
            load_from_manifest(self.manifest, "train")

    def test_v2_rejects_unassigned_source_records(self) -> None:
        self.write_dataset(["a", "b"])
        self.write_v2_manifest(train=["a"])

        with self.assertRaisesRegex(ValueError, "does not assign 1 dataset record"):
            load_from_manifest(self.manifest, "train")

    def test_legacy_integer_manifest_remains_supported(self) -> None:
        self.write_dataset(["a", "b"])
        self.manifest.write_text(
            "source: examples.jsonl\ntrain:\n    - 1\nval:\n    - 0\n",
            encoding="utf-8",
        )

        self.assertEqual(
            load_from_manifest(self.manifest, "train"),
            [{"id": "b", "value": "B"}],
        )


if __name__ == "__main__":
    unittest.main()
