-- Phase 1 schema. Append-only fact tables. No mutation of historical rows.
-- All timestamps are ISO 8601 UTC strings unless noted.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;

-- One row per (station, model, target_date, fetched_at). Holds the metadata
-- and a JSON copy of the raw response for debugging.
CREATE TABLE IF NOT EXISTS forecasts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    station      TEXT    NOT NULL,
    model        TEXT    NOT NULL,
    target_date  TEXT    NOT NULL,           -- YYYY-MM-DD in the city's local tz
    fetched_at   TEXT    NOT NULL,
    n_members    INTEGER NOT NULL,
    raw_json     TEXT    NOT NULL,
    UNIQUE(station, model, target_date, fetched_at)
);
CREATE INDEX IF NOT EXISTS idx_forecasts_station_target ON forecasts(station, target_date);
CREATE INDEX IF NOT EXISTS idx_forecasts_fetched ON forecasts(fetched_at);

-- One row per (forecast_id, member_index, valid_time). We store hourly values
-- so we can later compute daily highs in the city's local tz.
CREATE TABLE IF NOT EXISTS ensemble_members (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    forecast_id     INTEGER NOT NULL REFERENCES forecasts(id) ON DELETE CASCADE,
    member_index    INTEGER NOT NULL,        -- 0 = control, 1..N perturbed
    valid_time      TEXT    NOT NULL,        -- ISO UTC
    temperature_c   REAL,
    UNIQUE(forecast_id, member_index, valid_time)
);
CREATE INDEX IF NOT EXISTS idx_members_forecast ON ensemble_members(forecast_id);
CREATE INDEX IF NOT EXISTS idx_members_valid ON ensemble_members(valid_time);

-- Polymarket weather temperature markets we have decided to track.
CREATE TABLE IF NOT EXISTS markets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id       TEXT    NOT NULL UNIQUE, -- polymarket condition_id or slug
    slug            TEXT,
    question        TEXT,
    station         TEXT,                    -- mapped airport, may be NULL if parser fails
    target_date     TEXT,                    -- YYYY-MM-DD
    bucket_kind     TEXT,                    -- 'range' | 'above' | 'below' | 'exact'
    bucket_low_f    REAL,
    bucket_high_f   REAL,
    end_date_iso    TEXT,
    yes_token_id    TEXT,
    no_token_id     TEXT,
    raw_json        TEXT,
    first_seen_at   TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL,
    closed          INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_markets_station_date ON markets(station, target_date);
CREATE INDEX IF NOT EXISTS idx_markets_closed ON markets(closed);

-- Full orderbook depth per snapshot. bids_json and asks_json are JSON arrays
-- of {price, size} sorted best-first.
CREATE TABLE IF NOT EXISTS orderbook_snapshots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id    TEXT NOT NULL,
    token_id     TEXT NOT NULL,
    outcome      TEXT,                       -- 'YES' or 'NO'
    snapshot_at  TEXT NOT NULL,
    best_bid     REAL,
    best_ask     REAL,
    mid          REAL,
    bids_json    TEXT,
    asks_json    TEXT,
    UNIQUE(market_id, token_id, snapshot_at)
);
CREATE INDEX IF NOT EXISTS idx_book_market_time ON orderbook_snapshots(market_id, snapshot_at);
CREATE INDEX IF NOT EXISTS idx_book_time ON orderbook_snapshots(snapshot_at);

-- One row per (snapshot, model output). would_trade is the strategy's binary
-- decision under the current EV threshold and Kelly fraction.
CREATE TABLE IF NOT EXISTS decisions (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id                   TEXT NOT NULL,
    snapshot_id                 INTEGER REFERENCES orderbook_snapshots(id) ON DELETE SET NULL,
    forecast_id                 INTEGER REFERENCES forecasts(id) ON DELETE SET NULL,
    decided_at                  TEXT NOT NULL,
    my_p                        REAL,
    confidence                  REAL,
    market_p                    REAL,
    edge                        REAL,
    fillable_size_at_market_p   REAL,
    hours_to_resolution         REAL,
    would_trade                 INTEGER,     -- 0 or 1
    simulated_size              REAL
);
CREATE INDEX IF NOT EXISTS idx_decisions_market ON decisions(market_id);
CREATE INDEX IF NOT EXISTS idx_decisions_time ON decisions(decided_at);

-- Settlements pulled from IEM/ASOS once a market resolves.
CREATE TABLE IF NOT EXISTS settlements (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id        TEXT NOT NULL UNIQUE,
    station          TEXT,
    target_date      TEXT,
    observed_high_f  REAL,
    observed_low_f   REAL,
    observed_at      TEXT,
    bucket_hit       INTEGER,                -- 1 if bucket contained observed value
    raw_json         TEXT
);
CREATE INDEX IF NOT EXISTS idx_settlements_station_date ON settlements(station, target_date);

-- Structured events for dashboards and incident review. The rotating file
-- handler captures free-form diagnostics; this captures things we will query.
CREATE TABLE IF NOT EXISTS run_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    component   TEXT,
    level       TEXT,
    message     TEXT,
    extra_json  TEXT
);
CREATE INDEX IF NOT EXISTS idx_runlog_ts ON run_log(ts);
