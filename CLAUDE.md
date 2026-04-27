# CLAUDE.md

Agent-facing project orientation. Read this first.

## Project goal

Polymarket weather temperature trading bot. Long term: take edge on
city daily-high temperature contracts using ensemble forecast skill.
Short term: Phase 1, observe only.

## Current phase

Phase 1: data layer plus probability model only.
- No trading code, no wallet integration, no private keys, no execution.
- Pure observe mode for at least 2 weeks before any execution work.
- Calibration must look real before we discuss execution.

## Architecture (five layers)

1. Data layer
   - Forecast puller (hourly): Open-Meteo ensemble API, every member kept.
   - Polymarket snapshotter (every 15 min): Gamma + CLOB, full depth.
   - Settlement recorder: IEM/NOAA ASOS daily high after a market resolves.
2. Probability model (importable)
   - v1: ensemble member counting. p = members in bucket / total members.
   - v2: convolve point forecast with empirical residual distribution
     (stub today, implement after we have weeks of residual data).
3. Analysis layer
   - Per snapshot: compute my_p, market_p, edge, fillable size, would_trade,
     simulated_size. Write a decisions row. No real orders.
4. Calibration and reporting
   - `weather-bot status` reads from SQLite. Reliability per decile,
     mean edge on would_trade, drift in last 7 days.
5. Execution layer
   - STUB ONLY in Phase 1. Module exists with raising methods. No keys.

## Key conventions

- Python 3.11+, uv for deps, SQLite for storage.
- Free APIs only, no auth. Open-Meteo, IEM/ASOS, Polymarket Gamma + CLOB.
- Every external HTTP call must use `weather_bot.http` so it gets the
  shared timeout and retry/backoff. This will run 24/7.
- No em dash characters anywhere (code, comments, README, log strings,
  CLI output). Use commas, parentheses, or periods.
- No wallet, key handling, signing, or trade execution code in Phase 1.
- No pulling or forking from third-party Polymarket trading bot repos.
- Diagnostics go to a rotating file in `logs/`. Structured events go
  to the `run_log` table in SQLite.

## City to station mapping

The contract resolves on the airport ASOS station, not city center.

| city         | station |
|--------------|---------|
| New York     | KLGA    |
| Chicago      | KORD    |
| Miami        | KMIA    |
| Dallas       | KDAL    |
| Seattle      | KSEA    |
| Atlanta      | KATL    |
| Los Angeles  | KLAX    |
| Phoenix      | KPHX    |

## Commands

```bash
uv sync
uv run weather-bot init
uv run weather-bot fetch-forecast --station KLGA --model gfs025 --days-ahead 1
uv run weather-bot list-markets
uv run weather-bot observe          # the long-running scheduler
uv run weather-bot status
uv run weather-bot backfill --days 7
uv run pytest -q
```

## Where things live

```
src/weather_bot/
  cities.py              tracked cities and station mapping
  config.py              env-driven settings (WEATHER_BOT_* env vars)
  http.py                shared async HTTP client (timeout + backoff)
  logging_setup.py       rotating-file logger
  db/schema.sql          authoritative schema, idempotent
  db/connection.py       sqlite3 helpers
  data/open_meteo.py     ensemble forecast puller
  data/polymarket.py     Gamma lister + CLOB book fetch
  data/iem.py            ASOS settlement puller
  model/ensemble_count.py  v1 probability model
  model/residual.py      v2 stub
  analysis/decisions.py  per-snapshot decision record builder
  reporting/status.py    learning-state readout
  execution/stub.py      INTENTIONALLY raises ExecutionDisabled
  scheduler.py           asyncio loop driving the two pullers
  cli.py                 typer CLI entrypoint

tests/                   offline parser/model tests (no network)
journal/                 human-written decision notes (do not auto-generate)
data/                    SQLite DB (gitignored)
logs/                    rotating log files (gitignored)
scripts/                 bash task runners
```

## SQLite tables (high level)

- forecasts: one row per (station, model, target_date, fetched_at).
- ensemble_members: hourly per-member values for each forecast.
- markets: tracked Polymarket weather temperature markets.
- orderbook_snapshots: full bid/ask depth per token per snapshot.
- decisions: my_p vs market_p per snapshot, plus would_trade flag.
- settlements: actual observed daily high/low from ASOS, plus bucket_hit.
- run_log: structured events from the scheduler.

Indices exist on (market_id, snapshot_at), (station, target_date),
fetched_at, and a few others. See `db/schema.sql`.

## Probability model contract (v1)

```python
from datetime import date
from weather_bot.model import probability_for_bucket

p = probability_for_bucket(
    valid_times=...,        # ISO UTC strings, length T
    members=...,            # list of length M, each list of length T (Celsius)
    station="KLGA",
    target_date=date(2026, 4, 28),
    bucket_kind="range",    # 'range' | 'above' | 'below' | 'exact'
    bucket_low_f=60.0,
    bucket_high_f=65.0,
)
# p.p_yes, p.confidence_std_f, p.member_highs_f, p.n_members
```

## Decision policy

Default thresholds in `config.Settings`:
- ev_threshold = 0.03
- kelly_fraction = 0.25
- transaction_cost = 0.03  (3 cents per round trip)

`would_trade=1` iff `(my_p - market_p) - transaction_cost >= ev_threshold`.
`simulated_size = min(quarter_kelly, fillable_size_at_market_p)`.

## What NOT to do

- Do not call any Polymarket POST endpoints.
- Do not import from `py-clob-client` or any signing library.
- Do not hold any private key, mnemonic, or API secret in repo or env.
- Do not write em dashes anywhere.
- Do not auto-generate journal entries (humans write those).

## Gotchas

- 2026-04-27: Polymarket lister returns 1000 active markets but the
  weather temperature filter matches zero. Diagnosis: weather markets
  on Gamma are now multi-outcome events with sub-markets, where the
  per-market `question` field is the bucket label (e.g. "60-65°F" or
  just "Yes") and the city, date, and "highest temperature" context
  live on the parent event. Our filter requires both a temp keyword
  and a city alias inside the per-market `question`, so every
  sub-market falls out. To fix: also scan `groupItemTitle`,
  `events[].title`, `slug`, `description`, and `tags` per market, or
  switch to `GET /events?tag_slug=weather` and walk the sub-markets
  from there. See `scripts/diagnose_polymarket.py` for the probe.
  The temp-keyword regex also doesn't match a bare "60-64F" (needs
  °, "high", "deg", or similar), so even bucket-only questions fail
  on text alone.
- Primary source for daily temp markets is `/events?tag_slug=daily-temperature`,
  not `/markets`. Sub-market bucket lives in `groupItemTitle`, not
  `question`. City + date live on the parent event title/slug. The
  /markets-based path is kept as `list_active_markets_legacy` plus
  `filter_weather_temp_markets` in case the events endpoint changes
  shape, but it is best-effort against today's market layout.
- Polymarket Gamma /events tag for daily city temperature markets
  is `daily-temperature`, NOT `temperature` (which returns 0).
  Discovered 2026-04-27 via tag-discovery probe on the Dallas event
  payload. The Weather tag (slug=`weather`) is broader and includes
  hurricanes, earthquakes, hottest-year markets, etc. The
  `highest-temperature` slug is an alias/superset that also returns
  the daily city markets but may include other phrasings later.
  Prefer `event.eventDate` for the target date when present; fall
  back to parsing the title/slug for "Month DD" only if absent.
