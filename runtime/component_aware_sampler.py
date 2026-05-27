"""Component-aware GEPA batch sampler.

Problem (v06 calendar-event-agent / any single-LM-call DSPy program):
- Each training row routes to ONE predictor at forward time. The trace contains
  one entry from that predictor and zero from the others.
- GEPA's default flow samples a mixed minibatch, then `make_reflective_dataset`
  filters trace entries by predictor signature. Rows that don't route to the
  iteration's target predictor are silently dropped from the reflective
  dataset.
- Net: extract-iteration reflective datasets are tiny (1-5 rows instead of 15)
  because only ~1/3 of trainset rows route to extract.

Fix (this module):
1. `_IterCtx` — shared mutable state between CapturingCandidateSelector and
   ComponentAwareBatchSampler. Carries `curr_candidate_idx` for one iteration.
2. `CapturingCandidateSelector` — wraps the underlying CandidateSelector
   (Pareto / CurrentBest); records the selected candidate index into _IterCtx
   BEFORE the batch sampler runs.
3. `ComponentAwareBatchSampler` — reads the candidate index from _IterCtx,
   reads `state.named_predictor_id_to_update_next_for_program_candidate[idx]`
   to determine which predictor will be targeted, samples only rows that
   route to that predictor.

All three components stay in sync via the per-candidate counter that the
default RoundRobinReflectionComponentSelector advances. No global state.i
arithmetic — robust to GEPA's future parallel-proposal flows.

Wiring:
    ctx = _IterCtx()
    sampler = ComponentAwareBatchSampler(route_fn=v06_route, minibatch_size=15, ctx=ctx)
    inner = ParetoCandidateSelector(rng=random.Random(42))
    selector = CapturingCandidateSelector(inner, ctx)

    optimizer = dspy.GEPA(
        metric=...,
        candidate_selection_strategy=selector,  # NB: type hint is Literal but
                                                # the runtime accepts an obj
        component_selector="round_robin",       # default, advances counter
        reflection_minibatch_size=None,         # ← required when custom sampler
        gepa_kwargs={"batch_sampler": sampler},
    )
"""
from __future__ import annotations
import random
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class _IterCtx:
    curr_candidate_idx: int = 0


class CapturingCandidateSelector:
    """Wraps a CandidateSelector and records the selected candidate index
    into a shared context the sampler reads on the same iteration."""

    def __init__(self, inner, ctx: _IterCtx):
        self.inner = inner
        self.ctx = ctx

    def select_candidate_idx(self, state) -> int:
        idx = self.inner.select_candidate_idx(state)
        self.ctx.curr_candidate_idx = idx
        return idx


class ComponentAwareBatchSampler:
    """Sample a minibatch whose rows all route to the predictor that the
    component selector will pick this iteration.

    Pools are built lazily on first call (the loader / trainset is only
    available at that point).
    """

    def __init__(self, route_fn, minibatch_size: int, ctx: _IterCtx, seed: int = 0):
        self.route_fn = route_fn
        self.minibatch_size = minibatch_size
        self.ctx = ctx
        self.rng = random.Random(seed)
        self.pools: dict[str, list] | None = None
        self.cursors: dict[str, int] | None = None
        self._all_ids: list | None = None

    def _init_pools(self, loader) -> None:
        """Build per-predictor pools from the trainset. Called once."""
        self._all_ids = list(loader.all_ids())
        examples = loader.fetch(self._all_ids)
        self.pools = defaultdict(list)
        unroutable = 0
        for i, ex in zip(self._all_ids, examples):
            try:
                name = self.route_fn(ex)
            except Exception:
                unroutable += 1
                continue
            self.pools[name].append(i)
        self.cursors = {n: 0 for n in self.pools}
        # Shuffle pools once for randomization (subsequent wraps re-shuffle)
        for n in self.pools:
            self.rng.shuffle(self.pools[n])
        # Log a summary line so the user can see the pool distribution
        import logging
        logger = logging.getLogger(__name__)
        logger.info(
            "ComponentAwareBatchSampler initialized: "
            + ", ".join(f"{n}={len(ids)}" for n, ids in self.pools.items())
            + (f"; unroutable={unroutable}" if unroutable else "")
        )

    def next_minibatch_ids(self, loader, state):
        if self.pools is None:
            self._init_pools(loader)
        cidx = self.ctx.curr_candidate_idx
        # Per-candidate next-predictor counter; this is the same counter the
        # default RoundRobinReflectionComponentSelector advances AFTER the
        # sampler reads it on the same iteration.
        try:
            pid = state.named_predictor_id_to_update_next_for_program_candidate[cidx]
            name = state.list_of_named_predictors[pid]
        except (IndexError, AttributeError):
            # Fallback: cycle through pools by an internal counter.
            names = list(self.pools.keys())
            name = names[0] if names else None

        if name is None or name not in self.pools or not self.pools[name]:
            # Empty pool for target predictor — fall back to a random
            # minibatch from all ids so the iteration doesn't crash.
            return self._all_ids[: self.minibatch_size]

        pool = self.pools[name]
        c = self.cursors[name]
        if c + self.minibatch_size > len(pool):
            self.rng.shuffle(pool)
            c = 0
        ids = pool[c : c + self.minibatch_size]
        self.cursors[name] = c + self.minibatch_size
        return ids


def v06_calendar_route_fn(example) -> str:
    """v06 calendar-event-agent routing rule:
      - row whose gold output has `next_tool_name`  → strategy.react
      - row whose gold output has `response_to_user` → strategy.extract.predict
    """
    out = getattr(example, "output", None)
    if not isinstance(out, dict):
        out = {}
    if "next_tool_name" in out:
        return "strategy.react"
    if "response_to_user" in out:
        return "strategy.extract.predict"
    raise ValueError("Unroutable example (no next_tool_name or response_to_user in output)")


# Registry of named route functions config can reference.
ROUTE_FNS = {
    "v06_calendar": v06_calendar_route_fn,
}


def build_route_aware_components(route_name: str, minibatch_size: int, seed: int = 0):
    """Returns (capturing_candidate_selector, batch_sampler) wired against
    a shared IterCtx. Caller picks the inner CandidateSelector strategy."""
    from gepa.strategies.candidate_selector import ParetoCandidateSelector

    if route_name not in ROUTE_FNS:
        raise ValueError(
            f"Unknown route_aware route '{route_name}'. "
            f"Available: {list(ROUTE_FNS)}"
        )
    route_fn = ROUTE_FNS[route_name]
    ctx = _IterCtx()
    sampler = ComponentAwareBatchSampler(route_fn, minibatch_size, ctx, seed=seed)
    inner = ParetoCandidateSelector(rng=random.Random(seed))
    selector = CapturingCandidateSelector(inner, ctx)
    return selector, sampler
