"""Offline tests for the per-snapshot decision computation."""

from __future__ import annotations

import json

from weather_bot.analysis import decisions
from weather_bot.config import settings


def test_no_book_yields_no_trade() -> None:
    d = decisions.compute(
        market_id="m1", snapshot_id=None, forecast_id=None,
        my_p=0.7, confidence=2.0,
        asks_json=None, hours_to_resolution=10.0,
    )
    assert d.market_p is None
    assert d.would_trade == 0
    assert d.simulated_size == 0.0


def test_positive_edge_marks_would_trade() -> None:
    asks = json.dumps([{"price": 0.40, "size": 100.0}, {"price": 0.42, "size": 50.0}])
    d = decisions.compute(
        market_id="m1", snapshot_id=1, forecast_id=2,
        my_p=0.70, confidence=1.5,
        asks_json=asks, hours_to_resolution=12.0,
    )
    assert d.market_p == 0.40
    assert abs(d.edge - 0.30) < 1e-9
    # default ev_threshold 0.03, transaction_cost 0.03; 0.30 - 0.03 >= 0.03
    assert d.would_trade == 1
    assert d.simulated_size > 0


def test_thin_edge_below_threshold_does_not_trade(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ev_threshold", 0.05)
    monkeypatch.setattr(settings, "transaction_cost", 0.03)
    asks = json.dumps([{"price": 0.50, "size": 100.0}])
    d = decisions.compute(
        market_id="m1", snapshot_id=None, forecast_id=None,
        my_p=0.55, confidence=1.0,
        asks_json=asks, hours_to_resolution=8.0,
    )
    # edge=0.05, after tx cost 0.02, below threshold 0.05 -> no trade
    assert d.would_trade == 0
