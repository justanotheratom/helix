import json
import threading
import time
from pathlib import Path

import dspy
import jsonschema
import pytest
import yaml
from dspy.utils.parallelizer import ParallelExecutor

from evaluate import (
    evaluate_example,
    load_existing_results,
    resolve_num_threads,
    sort_results_file,
)


EVAL_SCHEMA = yaml.safe_load(Path(__file__).with_name("eval.schema.yaml").read_text())


class ConcurrentProgram:
    def __init__(self):
        self._lock = threading.Lock()
        self.active = 0
        self.max_active = 0

    def __call__(self, value):
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(0.05)
            return dspy.Prediction(answer=value)
        finally:
            with self._lock:
                self.active -= 1


def test_parallel_executor_runs_independent_examples_concurrently():
    program = ConcurrentProgram()
    examples = [dspy.Example(value=i) for i in range(8)]

    def run(item):
        idx, example = item
        return evaluate_example(
            idx,
            example,
            program,
            ["value"],
            lambda expected, prediction, trace: expected.value == prediction.answer,
        )

    results = ParallelExecutor(
        num_threads=4,
        disable_progress_bar=True,
        timeout=0,
    ).execute(run, list(enumerate(examples)))

    assert program.max_active == 4
    assert [result["example_idx"] for result in results] == list(range(8))
    assert all(result["score"] == 1.0 for result in results)


def test_metric_error_preserves_inference_result_and_latency():
    program = ConcurrentProgram()
    result = evaluate_example(
        7,
        dspy.Example(value="kept"),
        program,
        ["value"],
        lambda expected, prediction, trace: (_ for _ in ()).throw(
            ValueError("bad metric")
        ),
    )

    assert result["score"] == 0.0
    assert result["error"] == "Metric error: bad metric"
    assert result["latency"] > 0
    assert "kept" in result["prediction"]


def test_results_are_deduplicated_for_resume_and_sorted(tmp_path):
    results_file = tmp_path / "results.jsonl"
    entries = [
        {
            "example_idx": 2,
            "score": 0.2,
            "latency": 2,
            "cost": 2,
            "tokens": {"input": 2, "output": 2},
        },
        {
            "example_idx": 0,
            "score": 0.0,
            "latency": 0,
            "cost": 0,
            "tokens": {"input": 0, "output": 0},
        },
        {
            "example_idx": 2,
            "score": 0.9,
            "latency": 9,
            "cost": 9,
            "tokens": {"input": 9, "output": 9},
        },
        {
            "example_idx": 1,
            "score": 0.1,
            "latency": 1,
            "cost": 1,
            "tokens": {"input": 1, "output": 1},
        },
    ]
    results_file.write_text("".join(json.dumps(entry) + "\n" for entry in entries))

    loaded = load_existing_results(results_file)
    assert loaded["completed_indices"] == {0, 1, 2}
    assert loaded["scores"] == [0.0, 0.1, 0.9]
    assert loaded["total_input_tokens"] == 10
    assert loaded["total_output_tokens"] == 10
    assert loaded["total_cost"] == 10

    sort_results_file(results_file)
    normalized = [json.loads(line) for line in results_file.read_text().splitlines()]
    assert [entry["example_idx"] for entry in normalized] == [0, 1, 2]
    assert normalized[2]["score"] == 0.9


@pytest.mark.parametrize("num_threads", [1, 8, 256])
def test_eval_schema_accepts_num_threads(num_threads):
    config = {
        "num_threads": num_threads,
        "metric": {"module": "programs.example.metrics", "function": "metric"},
        "data": {
            "source": "data/001.jsonl",
            "splits": "data/splits/001_001.yaml",
            "program_inputs": ["input"],
        },
    }
    jsonschema.validate(config, EVAL_SCHEMA)
    assert resolve_num_threads(config) == num_threads


def test_num_threads_defaults_to_sequential():
    assert resolve_num_threads({}) == 1


@pytest.mark.parametrize("num_threads", [0, -1, 257, 1.5, True])
def test_eval_schema_rejects_invalid_num_threads(num_threads):
    config = {
        "num_threads": num_threads,
        "metric": {"module": "programs.example.metrics", "function": "metric"},
        "data": {
            "source": "data/001.jsonl",
            "splits": "data/splits/001_001.yaml",
            "program_inputs": ["input"],
        },
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(config, EVAL_SCHEMA)
    with pytest.raises(ValueError, match="between 1 and 256"):
        resolve_num_threads(config)
