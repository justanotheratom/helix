import argparse
import cloudpickle
import hashlib
import json
import os
import shutil
import sys
import traceback
import yaml
from pathlib import Path
from typing import Any, Dict, List

# Path resolution is repo-agnostic (Helix). The worker runs this entrypoint
# with cwd = the consumer's base dir (programs/, api/, runtime/ live here) and
# PYTHONPATH = base : helix_runtime. We DO NOT derive the consumer root from
# __file__ (this file may live anywhere). _this_dir is added so the flat
# sibling imports (`from optimizer import …`) resolve and keep their flat
# module names — important for pickle stability of SelfContainedProgram.
_this_dir = Path(__file__).parent.resolve()          # helix_runtime dir
_base = Path(os.environ.get("HELIX_BASE_DIR", os.getcwd())).resolve()
sys.path.insert(0, str(_this_dir))
sys.path.insert(0, str(_base))

import dspy
from dotenv import load_dotenv

from optimizer import optimize_program
from config_utils import inject_config_to_env
from tracking import LatencyTracker
from image_utils import encode_image_to_base64, get_image_url
from program_loader import SelfContainedProgram, load_compiled_program
from module_loader import load_object
from data_loader import load_from_manifest
from tracing import setup_langfuse_tracing


def convert_image_path_to_dspy_image(
    image_path: str,
    config_base_dir: Path,
    image_config: Dict[str, Any] = None
) -> dspy.Image:
    """
    Convert an image file path to a dspy.Image object.

    Args:
        image_path: Relative or absolute path to image file
        config_base_dir: Base directory for resolving relative paths
        image_config: Optional image config with mode and base_url
    """
    # Resolve path relative to config directory
    full_path = Path(image_path)
    if not full_path.is_absolute():
        full_path = config_base_dir / image_path
    
    if not full_path.exists():
        raise FileNotFoundError(f"Image file not found: {full_path}")
    
    mode = (image_config or {}).get("mode", "base64")
    
    if mode == "url":
        base_url = image_config.get("base_url", "")
        # Use shared utility to generate URL
        image_url = get_image_url(full_path, base_url, config_base_dir)
        return dspy.Image(url=image_url)
    else:
        # Use shared utility to encode as base64
        image_url = encode_image_to_base64(full_path, downsample_if_needed=True, max_size_mb=3.5)
        return dspy.Image(url=image_url)


def convert_value_with_images(
    value: Any,
    config_base_dir: Path,
    image_config: Dict[str, Any] = None
) -> Any:
    """
    Recursively convert image paths in a value to dspy.Image objects.
    
    Detects image paths by checking if the string ends with common image extensions.
    """
    if isinstance(value, str):
        # Check if it's an image path
        image_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.JPG', '.JPEG', '.PNG'}
        if any(value.endswith(ext) for ext in image_extensions):
            try:
                return convert_image_path_to_dspy_image(value, config_base_dir, image_config)
            except FileNotFoundError:
                print(f"Warning: Image not found: {value}")
                return value
        return value
    elif isinstance(value, list):
        return [convert_value_with_images(item, config_base_dir, image_config) for item in value]
    elif isinstance(value, dict):
        return {k: convert_value_with_images(v, config_base_dir, image_config) for k, v in value.items()}
    else:
        return value


def resolve_lm_config_references(config: Dict[str, Any], path: str = "") -> None:
    """
    Recursively resolve string references to lm_configs throughout the config.
    
    Modifies the config dict in-place, replacing string references with actual config dicts.
    
    Args:
        config: The configuration dictionary to resolve
        path: Current path in the config (for error messages)
    """
    lm_configs = config.get('lm_configs', {})
    
    if not lm_configs:
        return
    
    def resolve_value(value: Any, current_path: str) -> Any:
        if isinstance(value, str):
            if value in lm_configs:
                return dict(lm_configs[value])
            return value
        elif isinstance(value, dict):
            resolved = {}
            for k, v in value.items():
                new_path = f"{current_path}.{k}" if current_path else k
                if k in ('lm_config', 'prompt_model_config', 'task_model_config', 'reflection_lm_config') and isinstance(v, str):
                    if v not in lm_configs:
                        raise ValueError(
                            f"lm_config reference '{v}' not found in lm_configs at {new_path}. "
                            f"Available: {list(lm_configs.keys())}"
                        )
                    resolved[k] = dict(lm_configs[v])
                else:
                    resolved[k] = resolve_value(v, new_path)
            return resolved
        elif isinstance(value, list):
            return [resolve_value(item, f"{current_path}[{i}]") for i, item in enumerate(value)]
        else:
            return value
    
    if 'program' in config and 'args' in config['program']:
        config['program']['args'] = resolve_value(config['program']['args'], 'program.args')
    
    if 'optimizer_params' in config:
        config['optimizer_params'] = resolve_value(config['optimizer_params'], 'optimizer_params')


def _write_program_artifact(
    *,
    state: Dict[str, Any],
    dest_root: Path,
    source_code: str,
    class_name: str,
    config_dict: Dict[str, Any],
    source_label: str,
) -> None:
    """Write a SelfContainedProgram artifact to <dest_root>/compiled_program/.

    Used for both artifacts a compile can produce:

      dest_root = <run_dir>        - the trained program AS COMPILED (the class
                                     GEPA optimized). This is the eval artifact
                                     and source of truth: the eval config's
                                     program_inputs + metric target this class.
      dest_root = <run_dir>/deploy - the post_compile=transplant output: the
                                     trained `state` transplanted into a
                                     deploy-shaped class with matching predictor
                                     topology, which the API serves.

    Writes <dest_root>/compiled_program/{program.pkl,metadata.json} and
    <dest_root>/program.hash, then round-trip-loads to confirm the class. The
    class must subclass dspy.Module and accept `config_dict`.
    """
    out_dir = dest_root / "compiled_program"
    out_dir.mkdir(parents=True, exist_ok=True)

    wrapper = SelfContainedProgram(
        source_code=source_code,
        class_name=class_name,
        config_dict=config_dict,
        state=state,
    )

    # Pickle to bytes once; write the file and hash the same bytes to avoid
    # re-reading the artifact off disk just to compute its digest.
    pkl_bytes = cloudpickle.dumps(wrapper)
    pkl_path = out_dir / "program.pkl"
    pkl_path.write_bytes(pkl_bytes)

    (out_dir / "metadata.json").write_text(json.dumps({
        "source": source_label,
        "class_name": class_name,
        "dependency_versions": {
            "python": f"{sys.version_info.major}.{sys.version_info.minor}",
            "dspy": dspy.__version__,
            "cloudpickle": cloudpickle.__version__,
        },
    }, indent=2))

    digest = hashlib.sha256(pkl_bytes).hexdigest()
    (dest_root / "program.hash").write_text(digest)

    # Round-trip verify: the artifact must load back as the expected class.
    loaded = load_compiled_program(dest_root)
    if loaded.__class__.__name__ != class_name:
        raise AssertionError(
            f"expected {class_name}, got {loaded.__class__.__name__}"
        )
    print(f"Wrote program artifact ({class_name}) to {pkl_path}")
    print(f"program.hash {digest[:12]}…")


def main():
    # Secrets normally arrive via the container env (the worker injects
    # provider keys from compose). Still honour optional .env files next to
    # the base dir for local/manual runs — best-effort, no-op if absent.
    for candidate in (_base / ".env", _base / ".env.local"):
        if candidate.exists():
            load_dotenv(str(candidate), override=True)
    
    try:
        langfuse_client = setup_langfuse_tracing()
    except RuntimeError as e:
        print(f"Langfuse tracing disabled: {e}")
        langfuse_client = None

    parser = argparse.ArgumentParser(description="Generic DSPy Compiler")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--config", type=str, help="Path to YAML configuration file")
    group.add_argument(
        "--resume",
        type=str,
        help="Resume GEPA from the specified run dir (e.g., results/####)."
    )
    args = parser.parse_args()

    run_dir = None
    if args.resume is not None:
        run_dir = Path(args.resume)
        if not run_dir.is_absolute():
            run_dir = Path.cwd() / run_dir
        if not run_dir.exists() or not run_dir.is_dir():
            print("Error: --resume must point to an existing run directory.")
            sys.exit(1)
        if run_dir.name == "gepa_logs":
            print("Error: --resume must be a run directory, not the gepa_logs directory.")
            sys.exit(1)
        if run_dir.parent.name != "results":
            print("Error: --resume must point to a run dir inside a results directory.")
            sys.exit(1)

        config_path = run_dir / "compile" / "compile.config.yaml"
        if not config_path.exists():
            print(f"Error: Compile config not found at {config_path}")
            sys.exit(1)
        config_base_dir = run_dir.parent.parent
    else:
        config_path = Path(args.config)
        if not config_path.exists():
            print(f"Error: Config file not found at {config_path}")
            sys.exit(1)
        config_base_dir = config_path.parent

    print(f"Loading config from {config_path}...")
    # Use yaml directly instead of load_config to avoid strict schema checks for now
    # (or we could point to a global schema)
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # post_compile is required (see compile.schema.yaml): every config must make
    # an explicit deploy-shape decision so we never silently ship the wrong
    # class. Enforce it here since compile.py skips full schema validation.
    pc = config.get('post_compile')
    if not isinstance(pc, dict) or pc.get('mode') not in ('identity', 'transplant'):
        raise ValueError(
            f"{config_path}: missing/invalid required `post_compile` block. "
            "Add e.g. `post_compile: {mode: identity}` (deploy the compiled "
            "class as-is) or `post_compile: {mode: transplant, deploy_program: "
            "..., deploy_class: ...}` (rebuild a deploy class from the trained "
            "state)."
        )
    if pc['mode'] == 'transplant' and not (pc.get('deploy_program') and pc.get('deploy_class')):
        raise ValueError(
            f"{config_path}: post_compile.mode=transplant requires both "
            "`deploy_program` and `deploy_class`."
        )

    # Resolve lm_config references
    try:
        resolve_lm_config_references(config)
    except ValueError as e:
        print(f"Error resolving lm_config references: {e}")
        sys.exit(1)

    # Validate config (basic check for required fields)
    # metric and data are only required if optimizer is set
    if 'program' not in config:
        print("Error: Config missing required section 'program'")
        sys.exit(1)

    opt_name = config.get("optimizer")
    if opt_name and (not config.get('metric') or not config.get('data')):
        print("Error: Config requires 'metric' and 'data' sections when optimizer is set")
        sys.exit(1)

    # Setup Results Directory (with optional GEPA resume support)
    results_base_dir = config_base_dir / "results"
    results_base_dir.mkdir(parents=True, exist_ok=True)

    opt_params = config.get("optimizer_params", {}) or {}

    if args.resume is not None:
        if opt_name != "GEPA":
            print("Error: --resume is only supported for GEPA optimizer.")
            sys.exit(1)

        log_dir_path = run_dir / "gepa_logs"
        state_path = log_dir_path / "gepa_state.bin"
        if not state_path.exists():
            print("Error: --resume run directory does not contain gepa_logs/gepa_state.bin.")
            sys.exit(1)

        opt_params["log_dir"] = str(log_dir_path)
        config["optimizer_params"] = opt_params
        print(f"Resuming GEPA run from log_dir: {opt_params['log_dir']}")

    if run_dir is None:
        # Create timestamped run directory
        # import datetime
        # timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        # Find next available folder number
        existing_folders = []
        for item in results_base_dir.iterdir():
            if item.is_dir() and item.name.isdigit():
                try:
                    existing_folders.append(int(item.name))
                except ValueError:
                    pass

        next_folder_num = max(existing_folders, default=0) + 1
        folder_name = f"{next_folder_num:04d}"

        run_dir = results_base_dir / folder_name
        run_dir.mkdir(exist_ok=True)

    print(f"Results directory: {run_dir}")

    # Save compile config early so resumes can reload it
    compile_dir = run_dir / "compile"
    compile_dir.mkdir(exist_ok=True)
    with open(compile_dir / "compile.config.yaml", "w") as f:
        yaml.dump(config, f)

    # Save program.py to compile directory
    try:
        program_module = config['program']['module']
        program_file_path = program_module.replace('.', '/') + '.py'
        program_source = Path(_base) / program_file_path
        if program_source.exists():
            shutil.copy(program_source, compile_dir / "program.py")
            print(f"Saved program.py to {compile_dir}")
    except Exception as e:
        print(f"Warning: Could not save program.py: {e}")

    # Save dataset and splits to compile directory
    try:
        data_config = config.get('data', {})
        if 'splits' in data_config:
            splits_source = config_base_dir / data_config['splits']
            if splits_source.exists():
                shutil.copy(splits_source, compile_dir / "splits.yaml")
                print(f"Saved splits.yaml to {compile_dir}")

                # Load splits manifest to get source dataset
                with open(splits_source, 'r', encoding='utf-8') as f:
                    splits_manifest = yaml.safe_load(f)
                if 'source' in splits_manifest:
                    dataset_source = splits_source.parent.parent / splits_manifest['source']
                    if dataset_source.exists():
                        shutil.copy(dataset_source, compile_dir / "dataset.jsonl")
                        print(f"Saved dataset.jsonl to {compile_dir}")
    except Exception as e:
        print(f"Warning: Could not save dataset/splits: {e}")

    # Inject env vars
    if 'env' in config:
        inject_config_to_env(config['env'], overwrite=True)
    
    # Load Program Class
    try:
        ProgramClass = load_object(config['program']['module'], config['program']['class'])
    except Exception as e:
        print(f"Error loading program class: {e}")
        sys.exit(1)
        
    # Instantiate Program
    # We assume program can be instantiated without args, or args provided in config
    program_args = config['program'].get('args', {})
    print(f"Instantiating {config['program']['class']}...")
    
    # Check for a corresponding Config class (Convention: <ClassName>Config)
    config_class_name = config['program']['class'] + "Config"
    ConfigClass = None
    try:
        ConfigClass = load_object(config['program']['module'], config_class_name)
    except (ImportError, AttributeError):
        pass
    
    if ConfigClass:
        print(f"Found config class {config_class_name}, instantiating with args...")
        try:
            config_obj = ConfigClass(**program_args)
            student = ProgramClass(config=config_obj)
        except Exception as e:
            print(f"Error instantiating program with config object: {e}")
            print("Falling back to kwargs instantiation...")
            student = ProgramClass(**program_args)
    else:
        student = ProgramClass(**program_args)
    
    # Load Metric and Data (only needed if optimizer is set)
    metric_fn = None
    trainset = []
    valset = []

    if opt_name:
        try:
            metric_fn = load_object(config['metric']['module'], config['metric']['function'])
        except Exception as e:
            print(f"Error loading metric function: {e}")
            sys.exit(1)

        # Load Data
        data_config = config['data']
        if 'splits' not in data_config:
            raise ValueError("data.splits is required")

        splits_path = config_base_dir / data_config['splits']
        if not splits_path.exists():
            raise FileNotFoundError(f"Splits manifest not found: {splits_path}")

        print(f"Loading data from manifest: {splits_path}")
        raw_train_data = load_from_manifest(splits_path, 'train')
        raw_val_data = load_from_manifest(splits_path, 'val')
        print(f"Loaded {len(raw_train_data)} train, {len(raw_val_data)} val examples")

        # Convert to DSPy Examples
        program_inputs = data_config.get('program_inputs', ['dietary_preference'])

        # Get image config for converting image paths
        image_config = config.get('program', {}).get('args', {}).get('image_config', {})
        convert_images = data_config.get('convert_images', True)

        def convert_to_examples(raw_data):
            examples = []
            for item in raw_data:
                ex_data = {}

                # Flatten input dict if program_inputs reference nested fields
                input_dict = item.get('input', {})
                if isinstance(input_dict, dict):
                    for field in program_inputs:
                        if field in input_dict:
                            val = input_dict[field]
                            if convert_images:
                                val = convert_value_with_images(val, config_base_dir, image_config)
                            ex_data[field] = val

                # Keep the output
                ex_data['output'] = item.get('output', {})

                # Legacy support for preference-validator format (where input is a simple value)
                if not any(field in ex_data for field in program_inputs):
                    for k, v in item.items():
                        if convert_images and k in ('input',):
                            ex_data[k] = convert_value_with_images(v, config_base_dir, image_config)
                        else:
                            ex_data[k] = v
                    if 'dietary_preference' not in ex_data and 'input' in ex_data:
                        ex_data['dietary_preference'] = ex_data['input']

                ex = dspy.Example(**ex_data).with_inputs(*program_inputs)
                examples.append(ex)
            return examples

        trainset = convert_to_examples(raw_train_data)
        valset = convert_to_examples(raw_val_data)

        print(f"Loaded {len(trainset)} training examples, {len(valset)} validation examples.")

    latency_tracker = LatencyTracker()
    dspy.configure(track_usage=True, callbacks=[latency_tracker])
    dspy.configure_cache(enable_disk_cache=config['cache'], enable_memory_cache=config['cache'])

    # Setup Optimizer Config
    opt_name = config['optimizer']
    opt_params = config.get('optimizer_params', {}) or {}
    compile_params = config.get('compile_params', {}) or {}
    
    # Inject metric, trainset, and valset
    opt_params['metric'] = metric_fn
    compile_params['trainset'] = trainset
    if valset:
        compile_params['valset'] = valset
    
    # Run Optimization
    if opt_name:
        print(f"Starting optimization with {opt_name}...")

        # Handle dynamic log_dir for GEPA
        if opt_params.get("log_dir") == "__auto__":
            opt_params["log_dir"] = str(run_dir / "gepa_logs")
            print(f"GEPA log directory: {opt_params['log_dir']}")

        optimizer_config = {
            "optimizer": opt_name,
            "optimizer_params": opt_params,
            "compile_params": compile_params
        }

        compiled_program = optimize_program(student, optimizer_config)
    else:
        print("No optimizer specified. Skipping compilation and using baseline program...")
        compiled_program = student
    
    if not hasattr(compiled_program, 'dump_state'):
        raise RuntimeError(
            "Compiled program does not implement dump_state(); "
            "cannot persist optimized instructions."
        )

    state = compiled_program.dump_state(json_mode=False)

    # 1) Always persist the trained program AS COMPILED to
    #    <run_dir>/compiled_program/. This is the eval artifact + source of
    #    truth: the eval config's program_inputs and metric target the compiled
    #    class, so eval MUST load this — not a transplanted deploy class.
    module_path = config['program']['module']
    if '-' in module_path or '/' in module_path:
        # Convert module notation to file path for hyphenated dirs
        source_file = Path(_base) / (module_path.replace('.', '/') + '.py')
    else:
        import importlib.util
        spec = importlib.util.find_spec(module_path)
        source_file = Path(spec.origin) if spec and spec.origin else None
    if not (source_file and source_file.exists()):
        raise FileNotFoundError(f"Could not find source file for {module_path}")
    _write_program_artifact(
        state=state,
        dest_root=run_dir,
        source_code=source_file.read_text(),
        class_name=config['program']['class'],
        config_dict=program_args,
        source_label="compile.py compiled program",
    )

    # 2) Produce the DEPLOY artifact per the required post_compile.mode.
    #    identity   -> the compiled class is itself deployable; the deploy
    #                  artifact IS <run_dir>/compiled_program/ (nothing extra).
    #    transplant -> transplant the trained state into a deploy-shaped class
    #                  with matching predictor topology, written to a SEPARATE
    #                  <run_dir>/deploy/compiled_program/. Kept distinct from the
    #                  eval artifact above because eval and serving consume
    #                  different classes. Deploy reads this; it hard-fails if the
    #                  config says transplant but this artifact is absent.
    pc = config['post_compile']
    mode = pc['mode']
    if mode == 'identity':
        print("Deploy artifact = compiled_program/ (post_compile mode=identity)")
    elif mode == 'transplant':
        deploy_program = pc['deploy_program']
        deploy_class = pc['deploy_class']
        deploy_src = (_base / deploy_program).resolve()
        if not deploy_src.is_file():
            raise FileNotFoundError(f"post_compile.deploy_program not found: {deploy_src}")
        deploy_source = deploy_src.read_text()
        if f"class {deploy_class}" not in deploy_source:
            raise ValueError(
                f"deploy program {deploy_src} does not define `class {deploy_class}`"
            )
        _write_program_artifact(
            state=state,
            dest_root=run_dir / "deploy",
            source_code=deploy_source,
            class_name=deploy_class,
            config_dict=program_args,
            source_label="compile.py post_compile (transplant)",
        )
        print("Deploy artifact = deploy/compiled_program/ (post_compile mode=transplant)")
    else:
        raise ValueError(f"Unknown post_compile.mode: {mode!r}")

    # Print compilation stats
    print("-" * 80)
    print("Compilation Stats")
    print(f"LM Calls: {latency_tracker.get_lm_call_count()}")
    print(f"Total LM Latency: {latency_tracker.get_total_lm_latency():.2f}s")
    if latency_tracker.get_lm_call_count() > 0:
        print(f"Avg LM Latency: {latency_tracker.get_average_lm_latency()*1000:.2f} ms")
    print("-" * 80)

    print(f"\nCompilation complete. Run evaluate.py to test the compiled program.")
    print(f"  uv run python3 .claude/skills/ai-utils/evaluate.py --config <eval.config.yaml> --compilation {run_dir}")
    
    # Flush traces
    if langfuse_client:
        print("Flushing traces...")
        if hasattr(langfuse_client, 'flush'):
            try:
                langfuse_client.flush()
            except Exception as e:
                print(f"Warning: Could not flush Langfuse traces: {e}")

if __name__ == "__main__":
    main()
