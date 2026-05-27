"""Build Langfuse trace deep-link URLs.

v1 fallback: Langfuse runs on its own loopback port (127.0.0.1:3010).
The auto-SSO trampoline (POST credentials → Set-Cookie 302) does not
work cross-origin — a cookie minted at :7000 cannot be applied to
:3010. So `traces_deep_link` returns the absolute Langfuse URL and
the user logs in once (browser remembers the 30-day NextAuth session).

The seed credentials are printed by `helix bootstrap` and live only in
the compose .env; they're never sent to the browser.

If a future Langfuse build supports runtime basePath, restore the
same-origin subpath design and reinstate `mint_session_cookie`.
"""
from __future__ import annotations

import urllib.parse


def traces_deep_link(run_label: str, project_id: str | None = None) -> str:
    from .settings import settings, langfuse_project_id

    origin = settings.langfuse_public_origin   # env/config-driven, not hardcoded
    pid = project_id or langfuse_project_id()
    return (
        f"{origin}/project/{urllib.parse.quote(pid)}"
        f"/traces?environment={urllib.parse.quote(run_label)}"
    )


async def mint_session_cookie() -> str:
    """Placeholder — cross-origin cookie mint is not supported in v1 fallback.

    Kept so future single-port designs can fill this in without touching
    callers.
    """
    raise NotImplementedError(
        "Langfuse runs on a separate origin (127.0.0.1:3010) in v1; users log in "
        "once with the LANGFUSE_INIT_USER_* credentials from helix/deploy/.env."
    )
