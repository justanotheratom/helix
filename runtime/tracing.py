"""Shared tracing utilities for DSPy programs."""
from __future__ import annotations

import asyncio
import os

_langfuse_client = None
_flush_task: asyncio.Task | None = None
FLUSH_INTERVAL = 60.0


def setup_langfuse_tracing():
    """Setup Langfuse tracing using OpenInference and Langfuse client.

    Requires the following environment variables:
    - LANGFUSE_PUBLIC_KEY: Langfuse public key
    - LANGFUSE_SECRET_KEY: Langfuse secret key
    - LANGFUSE_BASE_URL: Langfuse instance URL
    - LANGFUSE_SAMPLE_RATE: Sampling rate (0.0-1.0)

    Note: DSPy instrumentation is global to the Python process. Call this once at startup
    (before any DSPy programs are instantiated) to trace all subsequent DSPy execution.

    Raises:
        RuntimeError: If any required environment variable is missing or invalid.
    """
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    base_url = os.getenv("LANGFUSE_BASE_URL")
    env_sample_rate = os.getenv("LANGFUSE_SAMPLE_RATE")

    if not public_key:
        raise RuntimeError("LANGFUSE_PUBLIC_KEY environment variable is required but not set")
    if not secret_key:
        raise RuntimeError("LANGFUSE_SECRET_KEY environment variable is required but not set")
    if not base_url:
        raise RuntimeError("LANGFUSE_BASE_URL environment variable is required but not set")
    if env_sample_rate is None:
        raise RuntimeError("LANGFUSE_SAMPLE_RATE environment variable is required but not set")

    try:
        sample_rate = float(env_sample_rate)
    except ValueError:
        raise RuntimeError(
            f"LANGFUSE_SAMPLE_RATE must be a float between 0.0 and 1.0 (got {env_sample_rate!r})"
        )

    if not 0.0 <= sample_rate <= 1.0:
        raise RuntimeError(
            f"LANGFUSE_SAMPLE_RATE must be between 0.0 and 1.0 (got {sample_rate})"
        )

    try:
        from langfuse import Langfuse
        from openinference.instrumentation.dspy import DSPyInstrumentor
    except ImportError as e:
        raise RuntimeError(f"Failed to import tracing dependencies: {e}") from e

    # Per-run correlation tag. The launcher sets KIN_AI_RUN_LABEL to the
    # log basename (e.g. "compile_0028_20260525T120000Z") so every trace
    # from this process is filterable by environment in the Langfuse UI,
    # which lets you jump from /tmp/<label>.log straight to the traces.
    run_label = os.getenv("KIN_AI_RUN_LABEL") or os.getenv("LANGFUSE_TRACING_ENVIRONMENT")

    if sample_rate == 0.0:
        print(f"Langfuse tracing configured but disabled (LANGFUSE_SAMPLE_RATE=0.0).")
    else:
        suffix = f" environment={run_label}" if run_label else ""
        print(f"Setting up Langfuse tracing to {base_url} (sample_rate={sample_rate}){suffix}...")

    global _langfuse_client
    langfuse_kwargs = dict(
        public_key=public_key,
        secret_key=secret_key,
        base_url=base_url,
        sample_rate=sample_rate,
    )
    if run_label:
        langfuse_kwargs["environment"] = run_label
    langfuse = Langfuse(**langfuse_kwargs)
    _langfuse_client = langfuse

    if sample_rate > 0.0:
        if hasattr(langfuse, 'auth_check'):
            try:
                if langfuse.auth_check():
                    print("Langfuse client authenticated and ready!")
                else:
                    raise RuntimeError("Langfuse authentication failed")
            except Exception as e:
                raise RuntimeError(f"Could not verify Langfuse connection: {e}") from e

        DSPyInstrumentor().instrument()
        print("Langfuse tracing enabled.")

    return langfuse


async def start_periodic_flush():
    """Start background task for periodic Langfuse flush. Call from lifespan."""
    global _flush_task

    async def _periodic_flush():
        while True:
            await asyncio.sleep(FLUSH_INTERVAL)
            if _langfuse_client and hasattr(_langfuse_client, 'flush'):
                try:
                    await asyncio.to_thread(_langfuse_client.flush)
                except Exception:
                    pass

    if _flush_task is None:
        _flush_task = asyncio.create_task(_periodic_flush())


def shutdown_langfuse():
    """Shutdown Langfuse - cancel flush task and final flush."""
    global _langfuse_client, _flush_task
    if _flush_task:
        _flush_task.cancel()
        _flush_task = None
    if _langfuse_client:
        try:
            _langfuse_client.flush()
        except Exception:
            pass
        _langfuse_client = None
