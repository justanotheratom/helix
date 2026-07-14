from __future__ import annotations

import json

from best_prompt_progress import (
    BEST_PROMPT_MARKER,
    BestPromptProgressCallback,
    install_best_prompt_callback,
)


def _event(*, idx: int, score: float, prompt: str, best: bool = True):
    return {
        "is_best_program": best,
        "candidate_idx": idx,
        "iteration": idx,
        "average_score": score,
        "candidate": {"strategy.react": prompt},
    }


def test_callback_emits_seed_and_previous_best_diff_input(capsys) -> None:
    callback = BestPromptProgressCallback()
    callback.on_valset_evaluated(_event(idx=0, score=0.5, prompt="seed"))
    callback.on_valset_evaluated(_event(idx=1, score=0.4, prompt="loser", best=False))
    callback.on_valset_evaluated(_event(idx=2, score=0.6, prompt="winner"))

    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    seed = json.loads(lines[0].removeprefix(BEST_PROMPT_MARKER))
    winner = json.loads(lines[1].removeprefix(BEST_PROMPT_MARKER))
    assert seed["previous"] is None
    assert winner["previous"]["prompts"]["strategy.react"] == "seed"
    assert winner["current"]["prompts"]["strategy.react"] == "winner"
    assert abs(winner["scoreDelta"] - 0.1) < 1e-12


def test_install_preserves_consumer_callbacks() -> None:
    existing = object()
    kwargs = {"callbacks": [existing]}
    install_best_prompt_callback(kwargs)
    assert kwargs["callbacks"][0] is existing
    assert isinstance(kwargs["callbacks"][1], BestPromptProgressCallback)
