"""Top-level CLI.

Subcommands:
  init                 create the SQLite schema
  fetch-forecast       run the ensemble puller once and print a sample
  list-markets         list active Polymarket weather temperature markets
  fetch-book           fetch CLOB depth for one token id and print
  observe              start the long-running scheduler
  status               print learning state from the database
  backfill             backfill ASOS observations for past target dates
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from . import scheduler as sched
from .cities import CITIES, CITIES_BY_STATION
from .config import settings
from .data import iem, open_meteo, polymarket
from .db import init_db
from .logging_setup import configure_logging
from .model.ensemble_count import (
    ensemble_summary,
    member_daily_highs_f,
)
from .reporting.status import build_status

app = typer.Typer(add_completion=False, help="Polymarket weather bot, observe-only Phase 1.")
console = Console()


@app.command("init")
def cmd_init() -> None:
    """Create or migrate the SQLite schema."""
    path = init_db()
    rprint(f"[green]Initialized database[/green] at {path}")


@app.command("fetch-forecast")
def cmd_fetch_forecast(
    station: str = typer.Option("KLGA", "--station", "-s"),
    model: str = typer.Option("gfs025", "--model", "-m"),
    days_ahead: int = typer.Option(1, "--days-ahead", help="0=today, 1=tomorrow."),
    save: bool = typer.Option(False, "--save", help="Persist into SQLite."),
) -> None:
    """Pull one ensemble forecast and print member summary for the chosen day."""
    configure_logging("cli")
    if station not in CITIES_BY_STATION:
        raise typer.BadParameter(f"Unknown station {station}")
    city = CITIES_BY_STATION[station]
    f = asyncio.run(open_meteo.fetch_ensemble(city, model))

    target = (datetime.now().date() + timedelta(days=days_ahead))
    highs = member_daily_highs_f(f.valid_times, f.members, station, target)
    summary = ensemble_summary(highs)

    table = Table(title=f"Ensemble {model} for {station} on {target.isoformat()}")
    table.add_column("Field")
    table.add_column("Value", justify="right")
    table.add_row("members returned", str(f.n_members))
    table.add_row("members with data", str(summary.get("n", 0)))
    if summary.get("n", 0):
        table.add_row("min daily high (F)", f"{summary['min_f']:.1f}")
        table.add_row("mean daily high (F)", f"{summary['mean_f']:.1f}")
        table.add_row("max daily high (F)", f"{summary['max_f']:.1f}")
        table.add_row("std daily high (F)", f"{summary['std_f']:.2f}")
    console.print(table)

    if highs:
        rprint("[bold]Per-member daily highs (F):[/bold]")
        rprint(", ".join(f"{h:.1f}" for h in highs))

    if save:
        fid = open_meteo.save_forecast(f)
        rprint(f"[green]Saved forecast id={fid}[/green]")


@app.command("list-markets")
def cmd_list_markets(
    save: bool = typer.Option(False, "--save", help="Persist matches into SQLite."),
    limit: int = typer.Option(50, "--limit"),
) -> None:
    """List active Polymarket weather temperature markets."""
    configure_logging("cli")
    raw = asyncio.run(polymarket.list_active_markets())
    matches = polymarket.filter_weather_temp_markets(raw)
    rprint(f"[bold]Active markets total:[/bold] {len(raw)}   "
           f"[bold]weather temp matches:[/bold] {len(matches)}")
    if not matches:
        rprint("[yellow]No matching markets right now.[/yellow]")
        return
    table = Table(title="Weather temperature markets (active)")
    table.add_column("station")
    table.add_column("target")
    table.add_column("bucket")
    table.add_column("question", overflow="fold")
    table.add_column("end")
    for m in matches[:limit]:
        bucket = (
            f"{m.bucket_kind} {m.bucket_low_f}..{m.bucket_high_f}"
            if m.bucket_kind else "?"
        )
        table.add_row(
            m.station or "?",
            m.target_date or "?",
            bucket,
            m.question,
            (m.end_date_iso or "")[:19],
        )
    console.print(table)

    if save:
        asyncio.run(sched.pull_polymarket_once())
        rprint("[green]Saved markets and snapshots into SQLite.[/green]")


@app.command("fetch-book")
def cmd_fetch_book(token_id: str = typer.Argument(...)) -> None:
    """Fetch the CLOB orderbook for a given token id and pretty-print it."""
    configure_logging("cli")
    book = asyncio.run(polymarket.fetch_clob_book(token_id))
    bb, ba = polymarket.best_levels(book)
    rprint(f"[bold]best_bid[/bold]={bb}  [bold]best_ask[/bold]={ba}")
    rprint(json.dumps({k: book.get(k) for k in ("market", "asset_id", "bids", "asks")}, indent=2))


@app.command("observe")
def cmd_observe() -> None:
    """Start the long-running scheduler. Ctrl-C to stop."""
    sched.main()


@app.command("status")
def cmd_status() -> None:
    """Print learning state read from the database."""
    init_db()
    s = build_status()

    head = Table(title="Weather bot status")
    head.add_column("metric")
    head.add_column("value", justify="right")
    head.add_row("generated_at", s.generated_at)
    head.add_row("markets tracked", str(s.n_markets_tracked))
    head.add_row("markets open", str(s.n_open_markets))
    head.add_row("markets settled", str(s.n_settled_markets))
    head.add_row("decisions written", str(s.n_decisions))
    head.add_row("would_trade decisions", str(s.n_would_trade))
    head.add_row(
        "mean edge (would_trade)",
        f"{s.mean_edge_would_trade:.4f}" if s.mean_edge_would_trade is not None else "n/a",
    )
    head.add_row("drift last 7d", f"{s.drift_7d:.4f}" if s.drift_7d is not None else "n/a")
    head.add_row("last forecast at", s.last_forecast_at or "n/a")
    head.add_row("last snapshot at", s.last_snapshot_at or "n/a")
    head.add_row("last settlement at", s.last_settlement_at or "n/a")
    console.print(head)

    cal = Table(title="Calibration by my_p decile")
    cal.add_column("decile")
    cal.add_column("range")
    cal.add_column("n", justify="right")
    cal.add_column("mean my_p", justify="right")
    cal.add_column("hit rate", justify="right")
    for b in s.calibration:
        cal.add_row(
            str(b.decile),
            f"{b.decile/10:.1f}..{(b.decile+1)/10:.1f}",
            str(b.n),
            f"{b.mean_my_p:.3f}",
            f"{b.hit_rate:.3f}" if b.hit_rate is not None else "n/a",
        )
    console.print(cal)


@app.command("backfill")
def cmd_backfill(
    days: int = typer.Option(7, "--days"),
    station: Optional[str] = typer.Option(None, "--station"),
) -> None:
    """Pull ASOS observations for recent dates and store as settlements.

    For each tracked station and each calendar date in [today-days, today-1],
    fetch the day's high/low and upsert a settlement row keyed by station+date.
    Bucket-hit is computed lazily by the analysis layer when a market is mapped.
    """
    init_db()
    configure_logging("cli")
    today = datetime.now(timezone.utc).date()
    stations = [station] if station else [c.station for c in CITIES]

    async def go() -> None:
        from .db import connect
        for st in stations:
            for d in range(1, days + 1):
                target = today - timedelta(days=d)
                try:
                    obs = await iem.fetch_daily_high_low(st, target)
                except Exception as e:
                    rprint(f"[red]{st} {target}: {e}[/red]")
                    continue
                rprint(
                    f"{st} {target.isoformat()}: high={obs['high_f']} low={obs['low_f']} "
                    f"n={obs['n_obs']}"
                )
                with connect() as conn:
                    conn.execute(
                        """
                        INSERT INTO settlements
                            (market_id, station, target_date,
                             observed_high_f, observed_low_f, observed_at, bucket_hit, raw_json)
                        VALUES (?,?,?,?,?,?,?,?)
                        ON CONFLICT(market_id) DO UPDATE SET
                            observed_high_f=excluded.observed_high_f,
                            observed_low_f=excluded.observed_low_f,
                            observed_at=excluded.observed_at
                        """,
                        (
                            f"obs:{st}:{target.isoformat()}",
                            st,
                            target.isoformat(),
                            obs["high_f"],
                            obs["low_f"],
                            obs["observed_at"],
                            None,
                            json.dumps(obs),
                        ),
                    )

    asyncio.run(go())


if __name__ == "__main__":
    app()
