"""Build the URL that the `traces_url` field on a Job/JobSubmissionResult
points at.

Langfuse is now internal-only (no host port). Trace browsing lives inside the
Helix UI at `/jobs/{job_id}/traces`, which calls the Helix-API trace proxy
endpoints (helix-api → langfuse-web on the docker network).
"""
from __future__ import annotations

import uuid


def traces_url(job_id: uuid.UUID | str) -> str:
    """Absolute URL into the Helix UI's trace view for this job."""
    from .settings import settings

    return f"{settings.public_base_url.rstrip('/')}/jobs/{job_id}/traces"
