from __future__ import annotations

import json

from helix_worker.progress_parser import parse_text


def test_parse_text_keeps_latest_best_prompt_event() -> None:
    seed = {
        "previous": None,
        "current": {"candidateIdx": 0, "iteration": 0, "score": 0.5, "prompts": {"p": "seed"}},
        "scoreDelta": None,
    }
    winner = {
        "previous": seed["current"],
        "current": {"candidateIdx": 2, "iteration": 4, "score": 0.6, "prompts": {"p": "better"}},
        "scoreDelta": 0.1,
    }
    text = "\n".join(
        [
            "Running GEPA for approx 2200 metric calls",
            "HELIX_BEST_PROMPT " + json.dumps(seed),
            "Best valset aggregate score so far: 0.5",
            "HELIX_BEST_PROMPT " + json.dumps(winner),
            "Best valset aggregate score so far: 0.6",
        ]
    )

    parsed = parse_text(text)
    assert parsed["compile"]["bestPrompt"] == winner
    assert parsed["compile"]["bestValset"] == 0.6


def test_parse_text_ignores_malformed_best_prompt_marker() -> None:
    parsed = parse_text(
        "Running GEPA for approx 10 metric calls\nHELIX_BEST_PROMPT {not-json}"
    )
    assert parsed["compile"]["bestPrompt"] is None
