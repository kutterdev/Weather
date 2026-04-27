# weather-bot

Polymarket weather temperature trading bot, Phase 1: data layer plus
probability model only. No trading code, no wallet, no signing, no
execution. We collect data and write decision records, then watch
calibration for at least two weeks before discussing execution.

## What it does today

1. Pulls full ensemble forecasts (GFS 31-member, ECMWF 51-member) from
   the Open-Meteo public API every hour for eight tracked cities.
2. Pulls active Polymarket weather temperature markets from the Gamma
   API every 15 minutes and stores the full CLOB orderbook depth (not
   just mid) for the YES and NO outcome tokens.
3. After a market resolves, pulls the official observed temperature
   from Iowa Environmental Mesonet (NOAA ASOS) and records the outcome.
4. Computes my_p (ensemble member counting) for each fresh snapshot,
   compares to market_p, and writes a decision row including a
   would_trade flag and a quarter-Kelly simulated_size. No real orders.

## Cities and resolving stations

The contracts resolve on the airport ASOS station, not the city center.

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

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run weather-bot init           # creates data/weather_bot.db
```

## Run

```bash
# One-shot smoke tests
uv run weather-bot fetch-forecast --station KLGA --model gfs025 --days-ahead 1
uv run weather-bot list-markets

# Long running scheduler (Ctrl-C to stop)
uv run weather-bot observe

# Read learning state from the database
uv run weather-bot status

# Backfill ASOS observations for the past N days
uv run weather-bot backfill --days 7
```

## Task scripts

Convenience wrappers in `scripts/`:

- `scripts/setup.sh`                 install deps and init the database
- `scripts/run_observe.sh`           start the long-running scheduler
- `scripts/status.sh`                print learning state
- `scripts/backfill_observations.sh` backfill ASOS observations

## Architecture (five layers)

1. Data layer: forecast puller, Polymarket snapshotter, settlement recorder.
2. Probability model (importable): v1 ensemble counting, v2 residual stub.
3. Analysis layer: writes decision rows from snapshots and forecasts.
4. Calibration and reporting: `status` CLI reads from the database.
5. Execution layer: STUB ONLY in Phase 1. No keys, no signing, no orders.

## Conventions

- Python 3.11+, uv for deps, SQLite for storage.
- Free APIs only, all read-only, no auth required.
- Every external HTTP call has an explicit timeout and exponential
  backoff retry policy. This will run 24/7.
- Diagnostics go to a rotating file in `logs/`. Structured events go
  to the `run_log` table in SQLite.
- No em dash characters anywhere in code, comments, logs, or docs.
- No wallet, key handling, signing, or trade execution code in Phase 1.

## Layout

```
src/weather_bot/
  cities.py            tracked cities and station mapping
  config.py            env-driven settings
  http.py              shared async HTTP client with retry+backoff
  logging_setup.py     rotating-file logger setup
  db/                  schema.sql and sqlite connection helper
  data/
    open_meteo.py      ensemble forecast puller
    polymarket.py      Gamma lister + CLOB orderbook fetcher
    iem.py             ASOS settlement puller
  model/
    ensemble_count.py  v1 probability model
    residual.py        v2 residual-convolution stub
  analysis/
    decisions.py       per-snapshot decision computation
  reporting/
    status.py          status report builder
  execution/
    stub.py            interface only, raises ExecutionDisabled
  scheduler.py         async scheduler for the two pullers
  cli.py               typer CLI

journal/               human-written decision notes (not auto-generated)
scripts/               bash task runners
data/                  SQLite database (gitignored)
logs/                  rotating log files (gitignored)
```

See `CLAUDE.md` for the agent-facing project orientation.
