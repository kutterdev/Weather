"""Decision computation per orderbook snapshot.

For each fresh snapshot we compute:
  my_p           : ensemble probability for the market's bucket
  market_p       : best ask on YES (worst price we'd pay to take YES)
  edge           : my_p - market_p
  fillable_size  : aggregate size at or better than market_p
  would_trade    : edge >= ev_threshold  (after configurable transaction cost)
  simulated_size : quarter-Kelly cap, never larger than fillable_size

This module computes records but does not execute. Phase 1 is observe only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from ..config import settings


@dataclass
class Decision:
    market_id: str
    snapshot_id: int | None
    forecast_id: int | None
    decided_at: str
    my_p: float
    confidence: float
    market_p: float | None
    edge: float | None
    fillable_size_at_market_p: float | None
    hours_to_resolution: float | None
    would_trade: int
    simulated_size: float


def _kelly_fraction(p: float, b: float) -> float:
    """Kelly fraction for a binary bet at odds b-to-1. Never negative."""
    if b <= 0:
        return 0.0
    q = 1.0 - p
    f = (b * p - q) / b
    return max(f, 0.0)


def compute(
    *,
    market_id: str,
    snapshot_id: int | None,
    forecast_id: int | None,
    my_p: float,
    confidence: float,
    asks_json: str | None,
    hours_to_resolution: float | None,
) -> Decision:
    asks = json.loads(asks_json) if asks_json else []
    if asks:
        # CLOB asks: list of {price, size}. Best ask is the lowest price.
        asks = sorted(asks, key=lambda x: float(x["price"]))
        market_p = float(asks[0]["price"])
        # Fillable at the best ask: aggregate every level priced at or below it.
        fillable = sum(float(a["size"]) for a in asks if float(a["price"]) <= market_p)
    else:
        market_p = None
        fillable = None

    edge = (my_p - market_p) if market_p is not None else None

    would_trade = 0
    sim_size = 0.0
    if edge is not None and edge - settings.transaction_cost >= settings.ev_threshold:
        would_trade = 1
        b = (1.0 - market_p) / market_p if market_p and market_p > 0 else 0.0
        f = _kelly_fraction(my_p, b) * settings.kelly_fraction
        sim_size = min(f, fillable or 0.0)

    return Decision(
        market_id=market_id,
        snapshot_id=snapshot_id,
        forecast_id=forecast_id,
        decided_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        my_p=my_p,
        confidence=confidence,
        market_p=market_p,
        edge=edge,
        fillable_size_at_market_p=fillable,
        hours_to_resolution=hours_to_resolution,
        would_trade=would_trade,
        simulated_size=sim_size,
    )
