import os
import sys
from dataclasses import dataclass
from pathlib import Path

import cloudpickle
import dspy
from pydantic import BaseModel


@dataclass
class SelfContainedProgram:
    """Wrapper that embeds source code and recreates program at load time."""
    source_code: str
    class_name: str
    config_dict: dict
    state: dict

    def load(self):
        import types

        # Use unique module name based on class name to avoid conflicts
        module_name = f'_program_{self.class_name}'

        # Create a proper module
        module = types.ModuleType(module_name)
        module.__dict__['__builtins__'] = __builtins__

        # Register in sys.modules early so dataclass decorator can find it
        sys.modules[module_name] = module

        # Add required imports to module namespace
        exec('from __future__ import annotations', module.__dict__)
        exec('import dspy', module.__dict__)
        exec('import os', module.__dict__)
        exec('from dataclasses import dataclass', module.__dict__)
        exec('from pydantic import BaseModel, Field', module.__dict__)
        exec('from typing import Optional, Literal, List, Dict, Any, Union', module.__dict__)

        # Execute the source in the module
        exec(self.source_code, module.__dict__)

        # Rebuild models with proper namespace
        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and issubclass(obj, BaseModel) and obj is not BaseModel:
                obj.model_rebuild(_types_namespace=module.__dict__)

        # Get classes and instantiate
        ProgramClass = getattr(module, self.class_name)
        ConfigClass = getattr(module, self.class_name + 'Config')

        config = ConfigClass(**self.config_dict)
        program = ProgramClass(config=config)

        if self.state:
            program.load_state(self.state)

        return program


def find_latest_compilation(search_dir: Path) -> Path:
    """Find the latest compilation directory with a compiled_program."""
    if not search_dir.exists():
        raise FileNotFoundError(f"Results directory not found: {search_dir}")

    folders = []
    for item in search_dir.iterdir():
        if item.is_dir() and item.name.isdigit():
            folders.append(int(item.name))

    for folder_num in sorted(folders, reverse=True):
        for fmt in [f"{folder_num:04d}", f"{folder_num:05d}", str(folder_num)]:
            candidate_dir = search_dir / fmt
            if candidate_dir.exists():
                if (candidate_dir / "compile" / "compiled_program").exists():
                    return candidate_dir
                if (candidate_dir / "compiled_program").exists():
                    return candidate_dir
                break

    raise FileNotFoundError(f"No compilation with compiled_program found in {search_dir}")


def load_compiled_program(
    compilation_dir: Path,
    repo_root: Path = None
) -> dspy.Module:
    """
    Load compiled program from a compilation directory.

    Args:
        compilation_dir: Path to the compilation directory
        repo_root: Optional repo root path (unused, kept for API compatibility)

    Returns:
        Loaded DSPy module
    """
    # Determine directory structure
    if (compilation_dir / "compile" / "compiled_program").exists():
        compile_program_dir = compilation_dir / "compile" / "compiled_program"
    elif (compilation_dir / "compiled_program").exists():
        compile_program_dir = compilation_dir / "compiled_program"
    else:
        raise FileNotFoundError(f"No compiled_program found in {compilation_dir}")

    pkl_path = compile_program_dir / "program.pkl"
    if not pkl_path.exists():
        raise FileNotFoundError(f"No program.pkl found in {compile_program_dir}")

    print(f"Loading compiled program from {pkl_path}...")
    with open(pkl_path, 'rb') as f:
        obj = cloudpickle.load(f)

    # Handle self-contained wrapper (check by attribute, not isinstance, due to pickle class identity)
    if hasattr(obj, 'source_code') and hasattr(obj, 'load') and callable(obj.load):
        return obj.load()

    return obj
