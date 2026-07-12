"""Shared data loading utilities for DSPy programs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import yaml


def load_jsonl(data_path: str) -> List[Dict[str, Any]]:
    """Load data from JSONL file."""
    examples = []
    with open(data_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                examples.append(json.loads(line))
    return examples


def load_yaml_documents(data_path: str) -> List[Dict[str, Any]]:
    """Load a multi-document YAML dataset."""
    docs = list(yaml.safe_load_all(Path(data_path).read_text(encoding="utf-8")))
    return [doc for doc in docs if doc]


def yaml_document_to_jsonl_row(doc: Dict[str, Any]) -> Dict[str, Any]:
    if "inputs" not in doc:
        row = dict(doc)
        product_details = row.get("product_details")
        if isinstance(product_details, dict):
            row["product_details"] = json.dumps(product_details, ensure_ascii=False)
        return row

    product_details = doc["inputs"]["product_details"]
    if isinstance(product_details, dict):
        product_details = json.dumps(product_details, ensure_ascii=False)

    outputs = doc.get("outputs")
    if outputs is None:
        return {
            "product_details": product_details,
            "explanation_of_fixes": [],
            "result": None,
            "categories": doc.get("categories") or {},
        }

    return {
        "product_details": product_details,
        "explanation_of_fixes": outputs.get("explanation_of_fixes") or [],
        "result": outputs["result"],
        "categories": doc.get("categories") or {},
    }


def load_dataset(data_path: str) -> List[Dict[str, Any]]:
    path = Path(data_path)
    if path.suffix in (".yaml", ".yml"):
        return [yaml_document_to_jsonl_row(doc) for doc in load_yaml_documents(data_path)]
    return load_jsonl(data_path)


def load_split_manifest(manifest_path: Path) -> Dict[str, Any]:
    """Load YAML split manifest file."""
    if manifest_path.suffix not in ('.yaml', '.yml'):
        raise ValueError(f"Manifest must be YAML file (.yaml or .yml), got: {manifest_path}")

    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = yaml.safe_load(f)

    if not isinstance(manifest, dict):
        raise ValueError(f"Split manifest must be a mapping: {manifest_path}")

    schema_version = manifest.get('schema_version')
    if schema_version is None:
        allowed_keys = {'source', 'train', 'val', 'test'}
    elif schema_version == 'helix-splits/v2':
        allowed_keys = {
            'schema_version', 'source', 'id_field', 'train', 'val', 'test'
        }
    else:
        raise ValueError(
            f"Unsupported split manifest schema_version {schema_version!r} "
            f"in {manifest_path}"
        )
    unknown = set(manifest) - allowed_keys
    if unknown:
        raise ValueError(f"Unknown split manifest keys {sorted(unknown)} in {manifest_path}")

    if 'source' not in manifest or not manifest['source']:
        raise ValueError(f"Missing required 'source' key in {manifest_path}")

    if schema_version == 'helix-splits/v2':
        id_field = manifest.get('id_field')
        if not isinstance(id_field, str) or not id_field.strip():
            raise ValueError(
                f"Split manifest id_field must be a non-empty string in {manifest_path}"
            )
        missing_partitions = [
            key for key in ('train', 'val', 'test') if key not in manifest
        ]
        if missing_partitions:
            raise ValueError(
                f"Split manifest missing partition(s) {missing_partitions} in {manifest_path}"
            )

    for key in ('train', 'val', 'test'):
        if key not in manifest:
            continue
        values = manifest[key]
        if not isinstance(values, list):
            raise ValueError(f"Split manifest {key} must be a list in {manifest_path}")
        if schema_version == 'helix-splits/v2':
            invalid = [value for value in values if not isinstance(value, str) or not value]
            if invalid:
                raise ValueError(
                    f"Split manifest {key} must contain non-empty string IDs in "
                    f"{manifest_path}; invalid value(s): {invalid[:3]}"
                )
        else:
            manifest[key] = [int(v) for v in values]

    return manifest


def _records_by_id(
    records: List[Dict[str, Any]], manifest: Dict[str, Any], manifest_path: Path
) -> Dict[str, Dict[str, Any]]:
    id_field = manifest['id_field']
    records_by_id: Dict[str, Dict[str, Any]] = {}
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(
                f"Dataset record {index} must be a mapping to use ID-based splits"
            )
        sample_id = record.get(id_field)
        if not isinstance(sample_id, str) or not sample_id:
            raise ValueError(
                f"Dataset record {index} has no non-empty string {id_field!r} "
                f"required by {manifest_path}"
            )
        if sample_id in records_by_id:
            raise ValueError(
                f"Duplicate dataset ID {sample_id!r} for id_field {id_field!r}"
            )
        records_by_id[sample_id] = record

    owner_by_id: Dict[str, str] = {}
    for partition in ('train', 'val', 'test'):
        for sample_id in manifest[partition]:
            previous_owner = owner_by_id.get(sample_id)
            if previous_owner is not None:
                raise ValueError(
                    f"Dataset ID {sample_id!r} appears more than once across split "
                    f"partitions ({previous_owner}, {partition})"
                )
            if sample_id not in records_by_id:
                raise ValueError(
                    f"Split partition {partition} references unknown dataset ID "
                    f"{sample_id!r}"
                )
            owner_by_id[sample_id] = partition

    unassigned = set(records_by_id) - set(owner_by_id)
    if unassigned:
        preview = sorted(unassigned)[:5]
        raise ValueError(
            f"ID-based split manifest does not assign {len(unassigned)} dataset "
            f"record(s), including {preview}"
        )
    return records_by_id


def _parse_yaml_manifest(content: str) -> Dict[str, Any]:
    """Strict YAML parser for split manifest format.

    Deprecated: prefer load_split_manifest(), which uses yaml.safe_load.
    Kept for tests that exercise the legacy strict format.

    Expected shape::

        source: <filename>
        train:
          - <int>
        val:
          - <int>
        test:
          - <int>

    Only allows: source (string), train/val/test (lists of integers).
    Fails on any deviation from this exact format.
    """
    manifest = {}
    lines = content.rstrip().split('\n')
    current_list_key = None
    allowed_keys = {'source', 'train', 'val', 'test'}

    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue

        # List item: must be exactly "  - <integer>"
        if stripped.startswith('-'):
            if current_list_key is None:
                raise ValueError(f"Line {line_num}: List item found without preceding train/val/test key")
            if not line.startswith('  - '):
                raise ValueError(f"Line {line_num}: List items must be indented with exactly 2 spaces and '- '")
            value = stripped[1:].strip()
            if not value.isdigit():
                raise ValueError(f"Line {line_num}: List items must be integers, got '{value}'")
            manifest[current_list_key].append(int(value))
            continue

        # Key-value pair: must be "key: value" (no leading spaces for top-level keys)
        if ':' in stripped:
            if line and (line[0] == ' ' or line[0] == '\t'):
                raise ValueError(f"Line {line_num}: Top-level keys must not be indented")

            key, value = stripped.split(':', 1)
            key = key.strip()
            value = value.strip()

            if key not in allowed_keys:
                raise ValueError(f"Line {line_num}: Unknown key '{key}'. Allowed keys: {allowed_keys}")

            if key == 'source':
                if key in manifest:
                    raise ValueError(f"Line {line_num}: Duplicate 'source' key")
                if not value:
                    raise ValueError(f"Line {line_num}: 'source' must have a value")
                manifest[key] = value
                current_list_key = None
            elif key in {'train', 'val', 'test'}:
                if key in manifest:
                    raise ValueError(f"Line {line_num}: Duplicate '{key}' key")
                if value:
                    raise ValueError(f"Line {line_num}: '{key}' must be followed by list items, not inline value")
                manifest[key] = []
                current_list_key = key
            else:
                raise ValueError(f"Line {line_num}: Unexpected key '{key}'")
        else:
            if line.startswith(' '):
                raise ValueError(f"Line {line_num}: Unexpected indented line: '{line}'")
            raise ValueError(f"Line {line_num}: Invalid format: '{line}'")

    if 'source' not in manifest:
        raise ValueError("Missing required 'source' key")

    return manifest


def load_from_manifest(manifest_path: Path, split_name: str) -> List[Dict[str, Any]]:
    """
    Load data for a specific split from a self-contained manifest.

    Args:
        manifest_path: Path to YAML manifest with source + train/val/test
        split_name: 'train', 'val', 'test', or 'all'

    A legacy manifest contains integer indices. A ``helix-splits/v2`` manifest
    contains stable string IDs and names the source record field with ``id_field``.

    Directory structure expected:
        data/
            001.jsonl           <- source file
            splits/
                001_002.yaml    <- manifest with "source: 001.jsonl"
    """
    manifest = load_split_manifest(manifest_path)

    # Source path is relative to manifest's parent's parent (e.g., data/splits/ -> data/)
    source_path = manifest_path.parent.parent / manifest['source']
    if not source_path.exists():
        raise FileNotFoundError(f"Source file not found: {source_path}")

    all_data = load_dataset(str(source_path))

    records_by_id = None
    if manifest.get('schema_version') == 'helix-splits/v2':
        records_by_id = _records_by_id(all_data, manifest, manifest_path)

    if split_name == 'all':
        return all_data

    if split_name not in manifest:
        available = [k for k in manifest.keys() if k != 'source']
        raise ValueError(f"Split '{split_name}' not in manifest. Available: {available}")

    references = manifest[split_name]
    if records_by_id is not None:
        return [records_by_id[sample_id] for sample_id in references]
    return [all_data[index] for index in references]
