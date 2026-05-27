"""
Tracking utilities for DSPy programs.
Provides latency tracking via callbacks and usage aggregation helpers.
"""

import time
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional

import litellm
from dspy.utils.callback import BaseCallback

from llm_pricing import calculate_cost


# ---------------------------------------------------------------------------
# Drop unsupported params per provider.
# ---------------------------------------------------------------------------
#
# Different providers accept different OpenAI-compat params. Most notably,
# `seed` is silently honored by Cerebras / OpenAI / OpenRouter but raised as
# UnsupportedParamsError by Gemini. We commonly set the same lm_configs across
# student + reflection LMs (e.g. seed=42 on every entry); without this flag
# the run errors at the first Gemini call.
# `litellm.drop_params=True` makes litellm silently drop params the chosen
# provider doesn't support, which is the canonical escape hatch.
litellm.drop_params = True


# ---------------------------------------------------------------------------
# OpenRouter cost-tracking patch
# ---------------------------------------------------------------------------
#
# OpenRouter routes per-request to whichever upstream provider it picks; the
# actual price varies request-to-request. They expose the authoritative cost
# in `usage.cost` IF the request includes `extra_body={"usage": {"include": True}}`.
#
# Rather than asking every program to set this (it's a tracking concern, not
# an agent-behavior concern), we monkey-patch litellm.completion / acompletion
# at import time to inject the flag whenever the call targets OpenRouter.
# `calculate_cost_from_usage` (below) then prefers the authoritative `cost`
# field over the local pricing table.
#
# Idempotent: guarded by `_lfm_or_patched` so re-imports don't double-wrap.

def _wrap_or_inject_usage(original: Callable) -> Callable:
    def wrapper(*args, **kwargs):
        model = kwargs.get("model", "") or ""
        api_base = kwargs.get("api_base", "") or ""
        if model.startswith("openrouter/") or "openrouter.ai" in api_base:
            eb = kwargs.get("extra_body") or {}
            if not isinstance(eb, dict):
                eb = {}
            usage = eb.get("usage")
            if not isinstance(usage, dict):
                eb["usage"] = {"include": True}
            elif "include" not in usage:
                eb["usage"]["include"] = True
            kwargs["extra_body"] = eb
        return original(*args, **kwargs)
    return wrapper


if not getattr(litellm.completion, "_lfm_or_patched", False):
    litellm.completion = _wrap_or_inject_usage(litellm.completion)
    litellm.completion._lfm_or_patched = True
if not getattr(litellm.acompletion, "_lfm_or_patched", False):
    litellm.acompletion = _wrap_or_inject_usage(litellm.acompletion)
    litellm.acompletion._lfm_or_patched = True


class LatencyTracker(BaseCallback):
    """Tracks latency for LM and module calls using DSPy's callback system."""

    def __init__(self):
        self.lm_latencies: List[Dict[str, Any]] = []
        self.module_latencies: defaultdict = defaultdict(list)
        self._start_times: Dict[str, float] = {}

    def on_lm_start(self, call_id, instance, inputs):
        self._start_times[call_id] = {
            "start": time.time(),
            "model": getattr(instance, "model", "unknown")
        }

    def on_lm_end(self, call_id, outputs, exception):
        if call_id in self._start_times:
            start_info = self._start_times[call_id]
            latency = time.time() - start_info["start"]
            self.lm_latencies.append({
                "call_id": call_id,
                "latency_seconds": latency,
                "model": start_info["model"],
                "exception": exception is not None
            })
            del self._start_times[call_id]

    def on_module_start(self, call_id, instance, inputs):
        self._start_times[f"module_{call_id}"] = {
            "start": time.time(),
            "module_name": instance.__class__.__name__
        }

    def on_module_end(self, call_id, outputs, exception):
        module_key = f"module_{call_id}"
        if module_key in self._start_times:
            start_info = self._start_times[module_key]
            latency = time.time() - start_info["start"]
            self.module_latencies[start_info["module_name"]].append(latency)
            del self._start_times[module_key]

    def get_total_lm_latency(self) -> float:
        return sum(entry["latency_seconds"] for entry in self.lm_latencies)

    def get_average_lm_latency(self) -> float:
        if not self.lm_latencies:
            return 0.0
        return self.get_total_lm_latency() / len(self.lm_latencies)

    def get_lm_call_count(self) -> int:
        return len(self.lm_latencies)

    def get_module_stats(self) -> Dict[str, Dict[str, Any]]:
        stats = {}
        for module_name, latencies in self.module_latencies.items():
            if latencies:
                stats[module_name] = {
                    "count": len(latencies),
                    "total_seconds": sum(latencies),
                    "average_seconds": sum(latencies) / len(latencies),
                    "min_seconds": min(latencies),
                    "max_seconds": max(latencies)
                }
        return stats

    def reset(self):
        self.lm_latencies.clear()
        self.module_latencies.clear()
        self._start_times.clear()


def aggregate_usage(usage_data: Dict[str, Dict[str, int]]) -> Dict[str, int]:
    """
    Aggregate token usage across all models.

    Args:
        usage_data: Dict from prediction.get_lm_usage(), keyed by model name

    Returns:
        Dict with total_tokens, prompt_tokens, completion_tokens
    """
    totals = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0
    }
    for model_usage in usage_data.values():
        totals["prompt_tokens"] += model_usage.get("prompt_tokens", 0)
        totals["completion_tokens"] += model_usage.get("completion_tokens", 0)
        totals["total_tokens"] += model_usage.get("total_tokens", 0)
    return totals


def calculate_cost_from_usage(usage_data: Dict[str, Dict[str, int]]) -> float:
    """
    Calculate total cost from usage data returned by get_lm_usage().

    Provider-reported cost (when present) is authoritative — OpenRouter, for
    example, returns `usage.cost` in dollars when the request includes
    `extra_body={"usage": {"include": True}}`. That number reflects the actual
    upstream provider that served the request (OpenRouter routes per-request,
    so static pricing tables are approximate).

    Falls back to local pricing (llm_pricing.yaml) when no `cost` field is
    present in the usage block.

    Args:
        usage_data: Dict from prediction.get_lm_usage(), keyed by model name

    Returns:
        Total cost in USD
    """
    total_cost = 0.0
    for model_name, usage in usage_data.items():
        # Prefer authoritative provider-reported cost when present.
        reported = usage.get("cost")
        if isinstance(reported, (int, float)) and reported > 0:
            total_cost += float(reported)
            continue
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        cost = calculate_cost(model_name, prompt_tokens, completion_tokens)
        if cost is not None:
            total_cost += cost
    return total_cost

