"""Offline tests for the Polymarket question/bucket filters."""

from __future__ import annotations

from weather_bot.data import polymarket


def test_match_nyc_temperature_market() -> None:
    q = "Highest temperature in NYC on April 28?"
    assert polymarket._looks_like_weather_temp_market(q)
    assert polymarket._match_city(q).station == "KLGA"


def test_match_chicago_above_bucket() -> None:
    q = "Will the high in Chicago be above 70F on April 28?"
    assert polymarket._looks_like_weather_temp_market(q)
    kind, lo, hi = polymarket._parse_bucket(q)
    assert kind == "above"
    assert lo == 70.0
    assert hi is None
    assert polymarket._match_city(q).station == "KORD"


def test_match_dallas_range_bucket() -> None:
    q = "Highest temperature in Dallas: 80 to 84F on April 28?"
    kind, lo, hi = polymarket._parse_bucket(q)
    assert kind == "range"
    assert lo == 80.0
    assert hi == 84.0


def test_no_match_unrelated_market() -> None:
    q = "Will Bitcoin close above 100k on April 28?"
    assert not polymarket._looks_like_weather_temp_market(q)


def test_filter_extracts_market_id_and_tokens() -> None:
    raw = [
        {
            "id": 12345,
            "conditionId": "0xabc",
            "slug": "highest-temperature-in-nyc-april-28",
            "question": "Highest temperature in NYC on April 28: 60-65F?",
            "endDate": "2026-04-29T00:00:00Z",
            "outcomes": '["Yes","No"]',
            "clobTokenIds": '["tok-yes","tok-no"]',
        },
        {
            "id": 67890,
            "question": "Will it rain in Seattle?",
            "endDate": "2026-04-29T00:00:00Z",
        },
    ]
    out = polymarket.filter_weather_temp_markets(raw)
    assert len(out) == 1
    m = out[0]
    assert m.market_id == "0xabc"
    assert m.station == "KLGA"
    assert m.bucket_kind == "range"
    assert m.bucket_low_f == 60.0
    assert m.bucket_high_f == 65.0
    assert m.yes_token_id == "tok-yes"
    assert m.no_token_id == "tok-no"
    assert m.target_date == "2026-04-29"
