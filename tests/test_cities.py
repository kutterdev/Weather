"""Sanity checks on the tracked-city table.

These catch typos at import time rather than 24 hours into observe mode.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

from weather_bot.cities import CITIES, CITIES_BY_STATION
from weather_bot.data import polymarket


def test_all_cities_have_valid_iana_tz() -> None:
    for c in CITIES:
        # ZoneInfo raises on unknown tz strings; this is the cheapest typo guard.
        ZoneInfo(c.tz)


def test_all_cities_have_country_code() -> None:
    for c in CITIES:
        assert isinstance(c.country, str) and len(c.country) == 2, (
            f"{c.name} has bad country={c.country!r}"
        )


def test_station_codes_unique() -> None:
    stations = [c.station for c in CITIES]
    assert len(stations) == len(set(stations)), (
        f"duplicate station code: {sorted(stations)}"
    )
    # And the by-station index covers every city.
    assert len(CITIES_BY_STATION) == len(CITIES)


def test_us_filter_via_country() -> None:
    us = [c for c in CITIES if c.country == "US"]
    assert {c.station for c in us} >= {
        "KLGA", "KORD", "KMIA", "KDAL", "KSEA", "KATL", "KLAX", "KPHX",
        "KAUS", "KDEN", "KIAH", "KSFO",
    }


def test_alias_matches_polymarket_slug_forms() -> None:
    # Slug-style hyphenated lowercase, the form Polymarket uses on /events.
    cases = {
        "highest-temperature-in-san-francisco-on-may-1": "KSFO",
        "highest-temperature-in-new-york-on-may-1":      "KLGA",
        "highest-temperature-in-hong-kong-on-may-1":     "VHHH",
        "highest-temperature-in-buenos-aires-on-may-1":  "SAEZ",
        "highest-temperature-in-mexico-city-on-may-1":   "MMMX",
        "highest-temperature-in-sao-paulo-on-may-1":     "SBGR",
        "highest-temperature-in-los-angeles-on-may-1":   "KLAX",
    }
    for slug, expected_station in cases.items():
        city = polymarket._match_city(slug)
        assert city is not None, f"no match for {slug!r}"
        assert city.station == expected_station, (
            f"{slug!r} matched {city.station} (wanted {expected_station})"
        )


def test_alias_short_forms() -> None:
    for short, expected in [
        ("NYC", "KLGA"),
        ("LA",  "KLAX"),
        ("SF",  "KSFO"),
        ("HK",  "VHHH"),
    ]:
        m = polymarket._match_city(f"high in {short} on April 28")
        assert m is not None and m.station == expected, (
            f"{short!r} -> {m and m.station}, wanted {expected}"
        )
