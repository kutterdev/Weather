"""Probability model v2 (interface stub).

The v2 method convolves the deterministic point forecast (or the ensemble
mean) with the empirical (forecast, observed) residual distribution at the
same station and lead time, drawn from historical settlements. This module
is a stub so callers can branch on a stable interface today.

Not implemented in this session. Wire it up after we have a few weeks of
residual data in the settlements and forecasts tables.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ResidualProbability:
    p_yes: float
    confidence: float


def probability_for_bucket(*args, **kwargs) -> ResidualProbability:
    raise NotImplementedError(
        "Residual-convolution model is a v2 task; see CLAUDE.md."
    )
