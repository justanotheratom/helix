"""Emit compact, machine-readable snapshots whenever GEPA finds a new best.

The worker already streams compile stdout and parses it into ``jobs.summary``.
Keeping this observer in the runtime avoids coupling Helix to GEPA's private
checkpoint format while still making prompt evolution available during a run.
"""
from __future__ import annotations

import json
from typing import Any


BEST_PROMPT_MARKER = "HELIX_BEST_PROMPT "


class BestPromptProgressCallback:
    """GEPA callback that reports the seed and each aggregate-valset winner."""

    def __init__(self) -> None:
        self._best: dict[str, Any] | None = None

    def on_valset_evaluated(self, event: dict[str, Any]) -> None:
        if not event.get("is_best_program"):
            return

        candidate = {
            str(name): str(prompt)
            for name, prompt in (event.get("candidate") or {}).items()
        }
        current = {
            "candidateIdx": int(event["candidate_idx"]),
            "iteration": int(event["iteration"]),
            "score": float(event["average_score"]),
            "prompts": candidate,
        }
        payload = {
            "previous": self._best,
            "current": current,
            "scoreDelta": (
                None
                if self._best is None
                else current["score"] - float(self._best["score"])
            ),
        }
        print(
            BEST_PROMPT_MARKER
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            flush=True,
        )
        self._best = current


def install_best_prompt_callback(gepa_kwargs: dict[str, Any]) -> None:
    """Append the Helix observer without replacing consumer callbacks."""
    configured = gepa_kwargs.get("callbacks")
    if configured is None:
        callbacks: list[Any] = []
    elif isinstance(configured, (list, tuple)):
        callbacks = list(configured)
    else:
        callbacks = [configured]
    callbacks.append(BestPromptProgressCallback())
    gepa_kwargs["callbacks"] = callbacks
