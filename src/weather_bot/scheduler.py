"""Asyncio-based scheduler for the two pullers.

Cadences live in config (forecast_pull_interval_s, polymarket_pull_interval_s,
settlement_check_interval_s). Each job is wrapped so a single failure does not
kill the loop. Errors are logged to file and to the run_log table.

We deliberately use asyncio rather than APScheduler here. The job set is
small, both jobs are I/O bound, and a plain loop keeps cancellation and
shutdown semantics obvious.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from .cities import CITIES
from .config import settings
from .data import open_meteo, polymarket
from .db import connect, init_db
from .logging_setup import configure_logging

log = logging.getLogger("weather_bot.scheduler")


def _record(component: str, level: str, message: str, extra: dict[str, Any] | None = None) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO run_log(ts, component, level, message, extra_json) VALUES (?,?,?,?,?)",
            (
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                component,
                level,
                message,
                json.dumps(extra or {}),
            ),
        )


async def _every(interval_s: int, name: str, job: Callable[[], Awaitable[None]]) -> None:
    while True:
        started = datetime.now(timezone.utc)
        try:
            await job()
            _record(name, "INFO", "cycle ok", {"started": started.isoformat()})
        except Exception as e:
            log.exception("%s cycle failed", name)
            _record(name, "ERROR", "cycle failed", {"err": str(e), "type": type(e).__name__})
        # Sleep to next slot. We do not bother aligning to wall-clock for now.
        await asyncio.sleep(interval_s)


async def pull_forecasts_once() -> None:
    for city in CITIES:
        for model in settings.ensemble_models:
            try:
                f = await open_meteo.fetch_ensemble(city, model)
                fid = open_meteo.save_forecast(f)
                log.info(
                    "Stored forecast id=%s station=%s model=%s members=%d times=%d",
                    fid, f.station, f.model, f.n_members, len(f.valid_times),
                )
            except Exception:
                log.exception("forecast fetch failed station=%s model=%s", city.station, model)


async def pull_polymarket_once() -> None:
    matches = await polymarket.list_active_markets()
    log.info("Polymarket weather_temp_matches=%d", len(matches))

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with connect() as conn:
        for m in matches:
            conn.execute(
                """
                INSERT INTO markets
                    (market_id, slug, question, station, target_date,
                     bucket_kind, bucket_low_f, bucket_high_f, end_date_iso,
                     yes_token_id, no_token_id, raw_json,
                     first_seen_at, last_seen_at, closed)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)
                ON CONFLICT(market_id) DO UPDATE SET
                    last_seen_at=excluded.last_seen_at,
                    raw_json=excluded.raw_json,
                    end_date_iso=excluded.end_date_iso
                """,
                (
                    m.market_id, m.slug, m.question, m.station, m.target_date,
                    m.bucket_kind, m.bucket_low_f, m.bucket_high_f, m.end_date_iso,
                    m.yes_token_id, m.no_token_id, json.dumps(m.raw),
                    now, now,
                ),
            )

    # Snapshot orderbooks for markets where we found token ids.
    for m in matches:
        for outcome, tid in (("YES", m.yes_token_id), ("NO", m.no_token_id)):
            if not tid:
                continue
            try:
                book = await polymarket.fetch_clob_book(tid)
                bb, ba = polymarket.best_levels(book)
                mid = (bb + ba) / 2.0 if (bb is not None and ba is not None) else None
                with connect() as conn:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO orderbook_snapshots
                            (market_id, token_id, outcome, snapshot_at,
                             best_bid, best_ask, mid, bids_json, asks_json)
                        VALUES (?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            m.market_id, tid, outcome, now,
                            bb, ba, mid,
                            json.dumps(book.get("bids") or []),
                            json.dumps(book.get("asks") or []),
                        ),
                    )
            except Exception:
                log.exception(
                    "orderbook fetch failed market=%s token=%s", m.market_id, tid
                )


async def run() -> None:
    configure_logging("weather_bot")
    init_db()
    log.info("Starting scheduler. forecasts=%ds polymarket=%ds",
             settings.forecast_pull_interval_s, settings.polymarket_pull_interval_s)

    await asyncio.gather(
        _every(settings.forecast_pull_interval_s, "forecasts", pull_forecasts_once),
        _every(settings.polymarket_pull_interval_s, "polymarket", pull_polymarket_once),
    )


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        log.info("scheduler interrupted, shutting down")


if __name__ == "__main__":
    main()
