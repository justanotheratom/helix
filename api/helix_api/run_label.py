"""40-char Langfuse `environment` slug derived deterministically per job."""
from __future__ import annotations

import hashlib
import re


def make_run_label(stem: str) -> str:
    s = re.sub(r"[^a-z0-9_-]+", "-", stem.lower()).strip("-_")
    digest = hashlib.sha1(stem.encode()).hexdigest()[:6]
    keep = max(0, 40 - 1 - len(digest))
    return f"{s[:keep]}_{digest}" if keep else digest
