"""Submission identity helpers."""
from __future__ import annotations


def submission_user_id(*candidates: str | None) -> str:
    """Pick the first non-empty user identifier for queue serialization.

    Callers pass candidates in trust order, most authoritative first. The
    Cloudflare-Access-injected `Cf-Access-Authenticated-User-Email` header is
    the strongest signal (set at the edge on every authenticated request; the
    API is not publicly reachable, so it cannot be spoofed by the client), so
    it should lead — ahead of the client-supplied `meta.user_id` and the
    per-credential service-token `CF-Access-Client-Id`.
    """
    for value in candidates:
        if value is None:
            continue
        normalized = value.strip()
        if normalized:
            return normalized[:256]
    return "anonymous"
