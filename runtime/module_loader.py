"""Dynamic module loading utilities."""
from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any


def get_repo_root() -> Path:
    """The consumer base dir (PYTHONPATH root), repo-agnostic.

    The worker runs entrypoints with cwd = base dir and sets HELIX_BASE_DIR.
    Not derived from __file__ — this module may live anywhere (helix_runtime).
    """
    return Path(os.environ.get("HELIX_BASE_DIR", os.getcwd())).resolve()


def load_object(module_path_or_name: str, object_name: str, repo_root: Path = None) -> Any:
    """
    Dynamically load a class or function from a module or file path.

    Args:
        module_path_or_name: Either a dotted module path (e.g., 'programs.utils.foo')
                            or a file path (e.g., 'programs/utils/foo.py')
        object_name: Name of the class or function to load
        repo_root: Optional repo root for resolving relative paths

    Returns:
        The loaded object

    Raises:
        ImportError: If the module or object cannot be loaded
    """
    if repo_root is None:
        repo_root = get_repo_root()

    # Handle path-like strings or strings with hyphens (which can't be standard modules)
    if '/' in module_path_or_name or module_path_or_name.endswith('.py') or '-' in module_path_or_name:
        # Convert dot notation with hyphens to path if needed
        if not ('/' in module_path_or_name or module_path_or_name.endswith('.py')):
            file_path_str = module_path_or_name.replace('.', '/') + '.py'
        else:
            file_path_str = module_path_or_name

        file_path = Path(file_path_str)
        if not file_path.is_absolute():
            file_path = repo_root / file_path

        if not file_path.exists():
            # Try alternative paths
            if Path(file_path_str).exists():
                file_path = Path(file_path_str)
            elif (repo_root / file_path_str).exists():
                file_path = repo_root / file_path_str

        if not file_path.exists():
            raise ImportError(f"File not found: {file_path} (derived from {module_path_or_name})")

        module_name = file_path.stem
        try:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                return getattr(module, object_name)
        except Exception as e:
            raise ImportError(f"Failed to load {object_name} from {file_path}: {e}")

    # Standard import
    try:
        module = importlib.import_module(module_path_or_name)
        return getattr(module, object_name)
    except (ImportError, AttributeError) as e:
        raise ImportError(f"Could not load {object_name} from {module_path_or_name}: {e}")
