"""Offline tests for the Open-Meteo response parser.

These exercise the same code paths the live puller uses, but with a hand-crafted
response that mirrors the real schema (hourly.time + temperature_2m and
temperature_2m_member01..NN).
"""

from __future__ import annotations

import asyncio
from datetime import date

from weather_bot.cities import CITIES_BY_STATION
from weather_bot.data import open_meteo
from weather_bot.model.ensemble_count import (
    member_daily_highs_f,
    probability_for_bucket,
)


def _fake_ensemble_response(n_members: int = 31) -> dict:
    # 48 hours at the top of each hour, all in UTC.
    times = [f"2026-04-28T{h:02d}:00" for h in range(24)] + \
            [f"2026-04-29T{h:02d}:00" for h in range(24)]
    hourly = {"time": times, "temperature_2m": [10.0] * 48}
    # Spread members from cool to warm so we get a non-degenerate distribution.
    for i in range(1, n_members):
        # member i has a constant offset, day 2 a bit warmer than day 1.
        day1 = [8.0 + i * 0.3] * 24
        day2 = [12.0 + i * 0.4] * 24
        hourly[f"temperature_2m_member{i:02d}"] = day1 + day2
    return {
        "latitude": 40.78,
        "longitude": -73.87,
        "hourly_units": {"temperature_2m": "°C", "time": "iso8601"},
        "hourly": hourly,
    }


def test_member_keys_in_order() -> None:
    raw = _fake_ensemble_response(31)
    keys = open_meteo._hourly_member_keys(raw["hourly"], "temperature_2m")
    assert keys[0] == "temperature_2m"
    assert keys[1] == "temperature_2m_member01"
    assert keys[-1] == "temperature_2m_member30"
    assert len(keys) == 31


def test_daily_highs_for_klga_tomorrow() -> None:
    raw = _fake_ensemble_response(31)
    keys = open_meteo._hourly_member_keys(raw["hourly"], "temperature_2m")
    members = [raw["hourly"][k] for k in keys]
    times = raw["hourly"]["time"]

    target = date(2026, 4, 29)  # day 2 in the fake response
    highs_f = member_daily_highs_f(times, members, "KLGA", target)
    # 31 members all have valid data for the target day.
    assert len(highs_f) == 31
    # Ensure F conversion ran (12C => ~53.6F for control, perturbed members warmer).
    assert min(highs_f) >= 50.0
    assert max(highs_f) <= 110.0


def test_probability_for_bucket_range() -> None:
    raw = _fake_ensemble_response(31)
    keys = open_meteo._hourly_member_keys(raw["hourly"], "temperature_2m")
    members = [raw["hourly"][k] for k in keys]
    times = raw["hourly"]["time"]

    p = probability_for_bucket(
        valid_times=times,
        members=members,
        station="KLGA",
        target_date=date(2026, 4, 29),
        bucket_kind="range",
        bucket_low_f=60.0,
        bucket_high_f=70.0,
    )
    assert p.n_members == 31
    assert 0.0 <= p.p_yes <= 1.0
    assert p.confidence_std_f >= 0.0


def test_fetch_ensemble_uses_settings(monkeypatch) -> None:
    """fetch_ensemble should call our http layer with the configured URL and
    return n_members matching the keys in the response."""
    raw = _fake_ensemble_response(31)

    async def fake_get_json(url, **kwargs):
        assert "ensemble-api.open-meteo.com" in url
        assert kwargs["params"]["models"] == "gfs025"
        return raw

    monkeypatch.setattr(open_meteo.wb_http, "get_json", fake_get_json)

    city = CITIES_BY_STATION["KLGA"]
    out = asyncio.run(open_meteo.fetch_ensemble(city, "gfs025"))
    assert out.n_members == 31
    assert len(out.valid_times) == 48
    assert len(out.members) == 31
