"""Submission identity helpers."""
from __future__ import annotations


def submission_user_id(*candidates: str | None) -> str:
    """Pick the first non-empty user identifier for queue serialization."""
    for value in candidates:
        if value is None:
            continue
        normalized = value.strip()
        if normalized:
            return normalized[:256]
    return "anonymous"
