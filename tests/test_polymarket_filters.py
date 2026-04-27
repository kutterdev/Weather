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


def test_parse_temperature_event_nyc() -> None:
    event = {
        "id": 999,
        "slug": "highest-temperature-in-nyc-on-april-28",
        "title": "Highest temperature in NYC on April 28?",
        "endDate": "2026-04-29T00:00:00Z",
        "markets": [
            {
                "id": 1001,
                "conditionId": "0xa1",
                "slug": "nyc-april-28-60-61",
                "groupItemTitle": "60-61°F",
                "outcomes": '["Yes","No"]',
                "clobTokenIds": '["t1y","t1n"]',
            },
            {
                "id": 1002,
                "conditionId": "0xa2",
                "slug": "nyc-april-28-92-or-higher",
                "groupItemTitle": "92°F or higher",
                "outcomes": '["Yes","No"]',
                "clobTokenIds": '["t2y","t2n"]',
            },
            {
                "id": 1003,
                "conditionId": "0xa3",
                "slug": "nyc-april-28-below-60",
                "groupItemTitle": "below 60°F",
                "outcomes": '["Yes","No"]',
                "clobTokenIds": '["t3y","t3n"]',
            },
        ],
    }
    out = polymarket.parse_temperature_event(event)
    assert len(out) == 3
    assert {m.station for m in out} == {"KLGA"}
    assert {m.target_date for m in out} == {"2026-04-29"}
    by_id = {m.market_id: m for m in out}
    assert by_id["0xa1"].bucket_kind == "range"
    assert by_id["0xa1"].bucket_low_f == 60.0
    assert by_id["0xa1"].bucket_high_f == 61.0
    assert by_id["0xa1"].yes_token_id == "t1y"
    assert by_id["0xa2"].bucket_kind == "above"
    assert by_id["0xa2"].bucket_low_f == 92.0
    assert by_id["0xa2"].bucket_high_f is None
    assert by_id["0xa3"].bucket_kind == "below"
    assert by_id["0xa3"].bucket_high_f == 60.0


def test_parse_temperature_event_skips_unparseable_bucket() -> None:
    event = {
        "title": "Highest temperature in Chicago on April 28?",
        "slug": "highest-temperature-in-chicago-on-april-28",
        "markets": [
            {"conditionId": "0xb1", "groupItemTitle": "60-61°F",
             "outcomes": '["Yes","No"]', "clobTokenIds": '["x","y"]'},
            {"conditionId": "0xb2", "groupItemTitle": "weird label",
             "outcomes": '["Yes","No"]', "clobTokenIds": '["x","y"]'},
        ],
    }
    out = polymarket.parse_temperature_event(event)
    assert len(out) == 1
    assert out[0].market_id == "0xb1"
    assert out[0].station == "KORD"


def test_parse_temperature_event_skips_international(caplog) -> None:
    # Taipei is the only city left in INTERNATIONAL_CITY_HINTS after the
    # coverage expansion. Once we add a station for it, swap this test
    # for whatever the next unmapped Polymarket city is.
    assert "Taipei" in polymarket.INTERNATIONAL_CITY_HINTS
    event = {
        "title": "Highest temperature in Taipei on April 28?",
        "slug": "highest-temperature-in-taipei-on-april-28",
        "markets": [
            {"conditionId": "0xc1", "groupItemTitle": "60-61°F",
             "outcomes": '["Yes","No"]', "clobTokenIds": '["x","y"]'},
        ],
    }
    with caplog.at_level("INFO", logger="weather_bot.polymarket"):
        out = polymarket.parse_temperature_event(event)
    assert out == []
    assert any("Taipei" in rec.getMessage() and "no station mapping yet"
               in rec.getMessage() for rec in caplog.records)


def test_parse_temperature_event_tokyo_now_parses() -> None:
    # Tokyo is now mapped (RJTT). It should produce a PolyMarket, not skip.
    # Bucket assumed °F here; if Polymarket actually publishes Celsius
    # buckets for Tokyo we need a separate fix in _parse_bucket.
    event = {
        "title": "Highest temperature in Tokyo on April 28?",
        "slug": "highest-temperature-in-tokyo-on-april-28",
        "markets": [
            {"conditionId": "0xtok", "groupItemTitle": "60-61°F",
             "outcomes": '["Yes","No"]', "clobTokenIds": '["x","y"]'},
        ],
    }
    out = polymarket.parse_temperature_event(event)
    assert len(out) == 1
    assert out[0].station == "RJTT"


def test_parse_temperature_event_unknown_city_skipped(caplog) -> None:
    event = {
        "title": "Highest temperature in Reykjavik on April 28?",
        "slug": "highest-temperature-in-reykjavik-on-april-28",
        "markets": [
            {"conditionId": "0xd1", "groupItemTitle": "60-61°F",
             "outcomes": '["Yes","No"]', "clobTokenIds": '["x","y"]'},
        ],
    }
    with caplog.at_level("INFO", logger="weather_bot.polymarket"):
        out = polymarket.parse_temperature_event(event)
    assert out == []
    assert any("no station mapping" in rec.getMessage() for rec in caplog.records)


def test_parse_temperature_event_prefers_eventDate() -> None:
    # eventDate (May 1) should win over both the title's "April 28"
    # and the endDate "May 2".
    event = {
        "title": "Highest temperature in NYC on April 28?",
        "slug": "highest-temperature-in-nyc-on-april-28",
        "eventDate": "2026-05-01",
        "endDate": "2026-05-02T00:00:00Z",
        "markets": [
            {"conditionId": "0xz1", "groupItemTitle": "60-61°F",
             "outcomes": '["Yes","No"]', "clobTokenIds": '["x","y"]'},
        ],
    }
    out = polymarket.parse_temperature_event(event)
    assert len(out) == 1
    assert out[0].target_date == "2026-05-01"


def test_parse_temperature_event_eventDate_iso_datetime() -> None:
    event = {
        "title": "Highest temperature in NYC on April 28?",
        "slug": "x",
        "eventDate": "2026-05-01T00:00:00Z",
        "markets": [
            {"conditionId": "0xz2", "groupItemTitle": "60-61°F",
             "outcomes": '["Yes","No"]', "clobTokenIds": '["x","y"]'},
        ],
    }
    out = polymarket.parse_temperature_event(event)
    assert len(out) == 1
    assert out[0].target_date == "2026-05-01"
