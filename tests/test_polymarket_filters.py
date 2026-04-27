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


def test_parse_live_groupitem_titles() -> None:
    # Strings observed on the live Polymarket weather market UI.
    cases = [
        ("76-77°F",         "range", 76.0, 77.0),
        ("78-79°F",         "range", 78.0, 79.0),
        ("92°F or higher",  "above", 92.0, None),
    ]
    for label, kind, lo, hi in cases:
        got_kind, got_lo, got_hi = polymarket._parse_bucket(label)
        assert got_kind == kind, f"{label!r}: kind {got_kind!r}"
        assert got_lo == lo, f"{label!r}: low {got_lo!r}"
        assert got_hi == hi, f"{label!r}: high {got_hi!r}"


def test_parse_tail_bucket_phrasings() -> None:
    # Variants we want to accept for the open-ended top/bottom buckets.
    above_cases = ["92°F or higher", "92F or above", "92 or higher",
                   "92°F and above", "92F+"]
    for q in above_cases:
        kind, lo, hi = polymarket._parse_bucket(q)
        assert kind == "above", f"{q!r}: kind {kind!r}"
        assert lo == 92.0
        assert hi is None

    below_cases = ["60°F or lower", "60F or below", "60 or lower",
                   "60°F and below"]
    for q in below_cases:
        kind, lo, hi = polymarket._parse_bucket(q)
        assert kind == "below", f"{q!r}: kind {kind!r}"
        assert lo is None
        assert hi == 60.0

    # Existing prefix forms still work.
    kind, lo, hi = polymarket._parse_bucket("below 60F")
    assert kind == "below"
    assert hi == 60.0


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
