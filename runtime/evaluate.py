import argparse
import json
import os
import shutil
import statistics
import sys
import time
import yaml
from pathlib import Path
from typing import Any, Dict, List, Set

# Repo-agnostic path resolution (Helix). cwd = consumer base dir;
# PYTHONPATH = base : helix_runtime. _this_dir keeps flat sibling imports
# resolving with their flat module names (pickle stability).
_this_dir = Path(__file__).parent.resolve()          # helix_runtime dir
_base = Path(os.environ.get("HELIX_BASE_DIR", os.getcwd())).resolve()
sys.path.insert(0, str(_this_dir))
sys.path.insert(0, str(_base))

import dspy
from dotenv import load_dotenv

from llm_pricing import calculate_cost
from config_utils import inject_config_to_env
from tracking import LatencyTracker, aggregate_usage, calculate_cost_from_usage
from compile import convert_raw_data_to_examples, resolve_program_inputs
from program_loader import find_latest_compilation, load_compiled_program
from module_loader import load_object
from data_loader import load_from_manifest
from tracing import setup_langfuse_tracing


class TrackingModule:
    """Wrapper to track tokens, latency, and costs for any DSPy module.

    Note: This intentionally does NOT inherit from dspy.Module because inheriting
    from dspy.Module breaks the usage tracking - get_lm_usage() returns None when
    the prediction passes through a dspy.Module wrapper.
    """

    def __init__(self, module: dspy.Module,
                 example_stats: Dict[int, Dict[str, Any]], total_stats: Dict[str, Any]):
        self.module = module
        self.example_stats = example_stats
        self.total_stats = total_stats
        self._example_index = 0

    def __call__(self, **kwargs):
        idx = self._example_index
        self._example_index += 1


        start_time = time.time()
        prediction = self.module(**kwargs)
        latency = time.time() - start_time

        example_input_tokens = 0
        example_output_tokens = 0
        cost = 0.0

        usage_data = prediction.get_lm_usage()
        if usage_data:
            aggregated = aggregate_usage(usage_data)
            example_input_tokens = aggregated["prompt_tokens"]
            example_output_tokens = aggregated["completion_tokens"]
            cost = calculate_cost_from_usage(usage_data)

        self.example_stats[idx] = {
            'latency': latency,
            'cost': cost,
            'tokens': {'input': example_input_tokens, 'output': example_output_tokens},
            'error': None,
            'prediction': str(prediction)
        }

        self.total_stats['total_input_tokens'] += example_input_tokens
        self.total_stats['total_output_tokens'] += example_output_tokens
        self.total_stats['latencies'].append(latency)
        self.total_stats['total_cost'] += cost

        return prediction


def create_evaluation_metric(results_file: Path, example_stats: Dict[int, Dict[str, Any]],
                             base_metric_fn: Any) -> Any:
    """Create a metric function that wraps the user metric and saves stats."""
    example_index = [0]

    def metric(example: dspy.Example, prediction: Any, trace=None) -> float:
        idx = example_index[0]
        example_index[0] += 1

        stats = example_stats.get(idx, {})

        try:
            score = base_metric_fn(example, prediction, trace)
        except Exception as e:
            print(f"Error in metric calculation: {e}")
            score = 0.0

        result_entry = {
            "example_idx": idx,
            "score": score,
            "latency": stats.get('latency', 0.0),
            "cost": stats.get('cost', 0.0),
            "tokens": stats.get('tokens', {'input': 0, 'output': 0}),
            "error": stats.get('error'),
            "prediction": stats.get('prediction')
        }

        with open(results_file, 'a') as f:
            f.write(json.dumps(result_entry) + '\n')

        return score

    return metric


def load_existing_results(results_file: Path) -> Dict[str, Any]:
    """Load existing results from results.jsonl for resumability."""
    completed_indices: Set[int] = set()
    scores: List[float] = []
    latencies: List[float] = []
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0.0

    if results_file.exists():
        with open(results_file, 'r') as f:
            for line in f:
                if line.strip():
                    entry = json.loads(line)
                    idx = entry.get('example_idx')
                    if idx is not None:
                        completed_indices.add(idx)
                        scores.append(entry.get('score', 0.0))
                        latencies.append(entry.get('latency', 0.0))
                        tokens = entry.get('tokens', {})
                        total_input_tokens += tokens.get('input', 0)
                        total_output_tokens += tokens.get('output', 0)
                        total_cost += entry.get('cost', 0.0)

    return {
        'completed_indices': completed_indices,
        'scores': scores,
        'latencies': latencies,
        'total_input_tokens': total_input_tokens,
        'total_output_tokens': total_output_tokens,
        'total_cost': total_cost,
    }


def format_latency_stats(latencies: List[float]) -> str:
    """Format latency statistics (avg, median, variance) in ms."""
    if not latencies:
        return "N/A"
    avg = statistics.mean(latencies) * 1000
    median = statistics.median(latencies) * 1000
    if len(latencies) >= 2:
        var = statistics.variance(latencies) * 1000000  # Convert to ms^2
        return f"avg={avg:.0f}ms, med={median:.0f}ms, var={var:.0f}ms²"
    return f"avg={avg:.0f}ms, med={median:.0f}ms"


def print_progress(
    completed: int,
    total: int,
    scores: List[float],
    latencies: List[float],
    total_input_tokens: int,
    total_output_tokens: int,
    total_cost: float,
    start_time: float
):
    """Print evaluation progress with running statistics."""
    elapsed = time.time() - start_time
    if completed > 0:
        eta = (elapsed / completed) * (total - completed)
        eta_str = f"{eta:.0f}s" if eta < 60 else f"{eta/60:.1f}m"
    else:
        eta_str = "N/A"

    accuracy = sum(scores) / len(scores) * 100 if scores else 0
    total_tokens = total_input_tokens + total_output_tokens
    latency_stats = format_latency_stats(latencies)

    print(
        f"\r[{completed}/{total}] "
        f"Acc: {accuracy:.1f}% | "
        f"Tokens: {total_tokens:,} (in:{total_input_tokens:,}/out:{total_output_tokens:,}) | "
        f"Cost: ${total_cost:.4f} | "
        f"Latency: {latency_stats} | "
        f"ETA: {eta_str}",
        end="", flush=True
    )


def main():
    # Secrets normally arrive via container env; honour optional .env files
    # next to the base dir for local/manual runs (best-effort).
    for candidate in (_base / ".env", _base / ".env.local"):
        if candidate.exists():
            load_dotenv(candidate, override=True)

    try:
        langfuse_client = setup_langfuse_tracing()
    except RuntimeError as e:
        print(f"Langfuse tracing disabled: {e}")
        langfuse_client = None

    parser = argparse.ArgumentParser(description="DSPy Program Evaluator")
    parser.add_argument("--config", type=str, required=True, help="Path to eval.config.yaml")
    parser.add_argument("--compilation", type=str, help="Path to compilation directory (auto-detects latest if not specified)")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: Config file not found at {config_path}")
        sys.exit(1)

    print(f"Loading config from {config_path}...")
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # Validate required config sections
    if 'metric' not in config:
        print("Error: Config missing required section 'metric'")
        sys.exit(1)
    if 'data' not in config:
        print("Error: Config missing required section 'data'")
        sys.exit(1)

    # Inject env vars
    if 'env' in config:
        inject_config_to_env(config['env'], overwrite=True)

    # Find compilation directory
    if args.compilation:
        compilation_dir = Path(args.compilation)
        if not compilation_dir.exists():
            print(f"Error: Compilation directory not found: {compilation_dir}")
            sys.exit(1)
    else:
        # Auto-detect from config directory's results folder
        search_dir = config_path.parent / "results"
        try:
            compilation_dir = find_latest_compilation(search_dir)
            print(f"Auto-detected compilation: {compilation_dir}")
        except FileNotFoundError as e:
            print(f"Error: {e}")
            print("Specify --compilation to provide a compilation directory.")
            sys.exit(1)

    # Setup eval output directory: {compilation}/evals/XXXX/
    evals_base_dir = compilation_dir / "evals"
    evals_base_dir.mkdir(parents=True, exist_ok=True)

    existing_folders = []
    for item in evals_base_dir.iterdir():
        if item.is_dir() and item.name.isdigit():
            try:
                existing_folders.append(int(item.name))
            except ValueError:
                pass

    next_folder_num = max(existing_folders, default=0) + 1
    eval_dir = evals_base_dir / f"{next_folder_num:04d}"
    eval_dir.mkdir(exist_ok=True)

    print(f"Eval output directory: {eval_dir}")

    # Save eval config copy
    shutil.copy(config_path, eval_dir / "eval.config.yaml")

    # Reject misleading config sections. The program (class, module, args, LM)
    # is fully baked into the compiled artifact at compile time; eval-time
    # overrides via `program:` were silently ignored, which made cross-model
    # eval configs lie about which model actually ran. Fail loud instead.
    if 'program' in config:
        print(
            "Error: eval.config.yaml must not contain a `program:` block. "
            "The compiled program (class, module, lm_config) is loaded from "
            "<compilation>/compiled_program/program.pkl. "
            "Remove the `program:` section."
        )
        sys.exit(1)

    # Save metrics.py to eval directory
    try:
        metric_module = config['metric']['module']
        # Convert a module path to its source file path.
        metric_file_path = metric_module.replace('.', '/') + '.py'
        metric_source = Path(_base) / metric_file_path
        if metric_source.exists():
            shutil.copy(metric_source, eval_dir / "metrics.py")
            print(f"Saved metrics.py to {eval_dir}")
    except Exception as e:
        print(f"Warning: Could not save metrics.py: {e}")

    # Save program.py to eval directory by extracting the source code embedded
    # in the compiled program pickle (the authoritative source as of compile
    # time). Avoids reading the live program file, which may have drifted.
    try:
        import cloudpickle as _cp
        _pkl = compilation_dir / "compiled_program" / "program.pkl"
        if not _pkl.exists():
            _pkl = compilation_dir / "compile" / "compiled_program" / "program.pkl"
        if _pkl.exists():
            with open(_pkl, 'rb') as f:
                _wrap = _cp.load(f)
            _src = getattr(_wrap, 'source_code', None)
            if _src:
                (eval_dir / "program.py").write_text(_src)
                print(f"Saved program.py to {eval_dir}")
    except Exception as e:
        print(f"Warning: Could not save program.py: {e}")

    # Save dataset and splits to eval directory
    try:
        data_config = config['data']
        # Save splits file
        if 'splits' in data_config:
            splits_source = config_path.parent / data_config['splits']
            if splits_source.exists():
                shutil.copy(splits_source, eval_dir / "splits.yaml")
                print(f"Saved splits.yaml to {eval_dir}")

            # Load splits manifest to get source dataset
            with open(splits_source, 'r', encoding='utf-8') as f:
                splits_manifest = yaml.safe_load(f)
            if 'source' in splits_manifest:
                # Dataset is relative to splits file directory
                dataset_source = splits_source.parent.parent / splits_manifest['source']
                if dataset_source.exists():
                    shutil.copy(dataset_source, eval_dir / "dataset.jsonl")
                    print(f"Saved dataset.jsonl to {eval_dir}")
    except Exception as e:
        print(f"Warning: Could not save dataset/splits: {e}")

    # Load compiled program directly
    print(f"Loading compiled program from {compilation_dir}...")
    try:
        program = load_compiled_program(compilation_dir)
        loaded_model = getattr(program, 'model', '<unknown>')
        loaded_api_base = getattr(program, 'api_base', None)
        print(
            f"Loaded compiled program. model={loaded_model}"
            + (f" api_base={loaded_api_base}" if loaded_api_base else "")
        )
    except Exception as e:
        print(f"Error loading compiled program: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Load Metric
    try:
        metric_fn = load_object(config['metric']['module'], config['metric']['function'])
    except Exception as e:
        print(f"Error loading metric function: {e}")
        sys.exit(1)

    # Initialize metric with args if provided
    metric_args = config['metric'].get('args', {})
    if metric_args:
        metric_module = config['metric']['module']
        if 'judge_lm_config' in metric_args:
            judge_config = metric_args['judge_lm_config']
            # Resolve lm_config reference if it's a string
            if isinstance(judge_config, str):
                lm_configs = config.get('lm_configs', {})
                if judge_config in lm_configs:
                    judge_config = dict(lm_configs[judge_config])
                else:
                    raise ValueError(f"judge_lm_config '{judge_config}' not found in lm_configs")
            try:
                init_fn = load_object(metric_module, 'init_judge')
                init_fn(judge_config)
                print(f"Initialized judge LM from config")
            except (ImportError, AttributeError):
                pass

    # Load Data
    data_config = config['data']
    if 'splits' not in data_config:
        raise ValueError("data.splits is required")

    splits_path = config_path.parent / data_config['splits']
    if not splits_path.exists():
        raise FileNotFoundError(f"Splits manifest not found: {splits_path}")

    split_name = data_config.get('split_name', 'test')
    print(f"Loading '{split_name}' from manifest: {splits_path}")
    raw_data = load_from_manifest(splits_path, split_name)
    print(f"Loaded {len(raw_data)} examples")

    # Convert to DSPy Examples
    program_inputs = resolve_program_inputs(data_config)
    
    # Get image config for converting image paths (from compile config if available)
    image_config = data_config.get('image_config', {})
    convert_images = data_config.get('convert_images', True)

    dataset = convert_raw_data_to_examples(
        raw_data, data_config, config_path.parent, image_config, convert_images
    )

    print(f"Loaded {len(dataset)} examples.")

    if 'cache' not in config:
        raise ValueError("Config must have 'cache' in config")

    print(f"Configuring global cache: {config['cache']}")
    dspy.configure_cache(enable_disk_cache=config['cache'], enable_memory_cache=config['cache'])

    latency_tracker = LatencyTracker()
    dspy.configure(track_usage=True, callbacks=[latency_tracker])

    # Setup Tracking
    total_stats = {
        'total_input_tokens': 0,
        'total_output_tokens': 0,
        'total_cost': 0.0,
        'latencies': []
    }
    example_stats = {}

    wrapped_program = TrackingModule(
        module=program,
        example_stats=example_stats,
        total_stats=total_stats
    )

    results_file = eval_dir / "results.jsonl"

    # Check for existing results (resumability)
    existing = load_existing_results(results_file)
    completed_indices = existing['completed_indices']
    scores = existing['scores']
    all_latencies = existing['latencies']
    total_stats['total_input_tokens'] = existing['total_input_tokens']
    total_stats['total_output_tokens'] = existing['total_output_tokens']
    total_stats['total_cost'] = existing['total_cost']

    if completed_indices:
        print(f"Resuming evaluation: {len(completed_indices)} examples already completed.")

    print(f"Starting evaluation on {len(dataset)} examples...")
    start_time = time.time()

    # Manual evaluation loop with progress display
    for idx, example in enumerate(dataset):
        if idx in completed_indices:
            continue

        # Extract inputs for the program
        inputs = {field: getattr(example, field) for field in program_inputs}

        # Run prediction with tracking
        try:
            wrapped_program._example_index = idx
            prediction = wrapped_program(**inputs)

            # Calculate score
            metric_result = metric_fn(example, prediction, None)
            # Handle metrics that return Prediction objects (e.g., gepa_feedback_metric)
            if hasattr(metric_result, 'score'):
                score = float(metric_result.score)
                feedback = getattr(metric_result, 'feedback', None)
            else:
                score = float(metric_result)
                feedback = None
        except Exception as e:
            print(f"\nError on example {idx}: {e}")
            score = 0.0
            feedback = None
            example_stats[idx] = {
                'latency': 0.0,
                'cost': 0.0,
                'tokens': {'input': 0, 'output': 0},
                'error': str(e),
                'prediction': None
            }

        scores.append(score)
        stats = example_stats.get(idx, {})
        latency = stats.get('latency', 0.0)
        all_latencies.append(latency)

        # Write result to file
        result_entry = {
            "example_idx": idx,
            "score": score,
            "feedback": feedback,
            "latency": stats.get('latency', 0.0),
            "cost": stats.get('cost', 0.0),
            "tokens": stats.get('tokens', {'input': 0, 'output': 0}),
            "error": stats.get('error'),
            "prediction": stats.get('prediction')
        }
        with open(results_file, 'a') as f:
            f.write(json.dumps(result_entry) + '\n')

        # Print progress
        print_progress(
            completed=len(scores),
            total=len(dataset),
            scores=scores,
            latencies=all_latencies,
            total_input_tokens=total_stats['total_input_tokens'],
            total_output_tokens=total_stats['total_output_tokens'],
            total_cost=total_stats['total_cost'],
            start_time=start_time
        )

    # Final newline after progress
    print()

    # Calculate final score
    final_score = sum(scores) / len(scores) * 100 if scores else 0

    print("-" * 80)
    print("Evaluation Complete")
    print(f"Score: {final_score:.2f}%")
    print(f"Total Cost: ${total_stats['total_cost']:.4f}")
    print(f"Total Tokens: {total_stats['total_input_tokens'] + total_stats['total_output_tokens']} (input: {total_stats['total_input_tokens']}, output: {total_stats['total_output_tokens']})")
    if all_latencies:
        latency_stats = format_latency_stats(all_latencies)
        print(f"Latency: {latency_stats}")
    print(f"LM Calls: {latency_tracker.get_lm_call_count()}")
    print(f"Results saved to {results_file}")
    print("-" * 80)

    if langfuse_client:
        print("Flushing traces...")
        if hasattr(langfuse_client, 'flush'):
            try:
                langfuse_client.flush()
            except Exception as e:
                print(f"Warning: Could not flush Langfuse traces: {e}")


if __name__ == "__main__":
    main()
