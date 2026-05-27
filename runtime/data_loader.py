"""Shared data loading utilities for DSPy programs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def load_jsonl(data_path: str) -> List[Dict[str, Any]]:
    """Load data from JSONL file."""
    examples = []
    with open(data_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                examples.append(json.loads(line))
    return examples


def load_split_manifest(manifest_path: Path) -> Dict[str, Any]:
    """Load YAML split manifest file."""
    if manifest_path.suffix not in ('.yaml', '.yml'):
        raise ValueError(f"Manifest must be YAML file (.yaml or .yml), got: {manifest_path}")

    with open(manifest_path, 'r') as f:
        content = f.read()

    return _parse_yaml_manifest(content)


def _parse_yaml_manifest(content: str) -> Dict[str, Any]:
    """Strict YAML parser for split manifest format.

    Expected format:
        source: <filename>
        train:
          - <int>
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

    The manifest must have:
    - source: path to JSONL file (relative to manifest's parent's parent directory)
    - train/val/test: lists of indices

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

    all_data = load_jsonl(str(source_path))

    if split_name == 'all':
        return all_data

    if split_name not in manifest:
        available = [k for k in manifest.keys() if k != 'source']
        raise ValueError(f"Split '{split_name}' not in manifest. Available: {available}")

    indices = manifest[split_name]
    return [all_data[i] for i in indices]
