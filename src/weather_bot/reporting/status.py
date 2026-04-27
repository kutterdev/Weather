"""Learning-state readout, served from SQLite.

The CLI calls this. The output is the database's view of itself: how many
markets we've seen, how many have settled, how calibrated my_p has been per
decile, mean edge on would_trade decisions, and short-window drift.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from ..db import connect


@dataclass
class CalibrationBucket:
    decile: int                 # 0..9, decile of my_p
    n: int
    mean_my_p: float
    hit_rate: float | None      # None if no settled rows in this decile


@dataclass
class StatusReport:
    generated_at: str
    n_markets_tracked: int
    n_open_markets: int
    n_settled_markets: int
    n_decisions: int
    n_would_trade: int
    mean_edge_would_trade: float | None
    calibration: list[CalibrationBucket] = field(default_factory=list)
    drift_7d: float | None = None
    last_forecast_at: str | None = None
    last_snapshot_at: str | None = None
    last_settlement_at: str | None = None


def _decile(p: float) -> int:
    if p < 0:
        return 0
    if p >= 1:
        return 9
    return min(int(p * 10), 9)


def build_status() -> StatusReport:
    with connect() as conn:
        n_markets = conn.execute("SELECT COUNT(*) c FROM markets").fetchone()["c"]
        n_open = conn.execute("SELECT COUNT(*) c FROM markets WHERE closed=0").fetchone()["c"]
        n_settled = conn.execute("SELECT COUNT(*) c FROM settlements").fetchone()["c"]
        n_decisions = conn.execute("SELECT COUNT(*) c FROM decisions").fetchone()["c"]

        wt = conn.execute(
            """
            SELECT COUNT(*) AS c, AVG(edge) AS mean_edge
              FROM decisions
             WHERE would_trade=1
            """
        ).fetchone()

        last_fc = conn.execute("SELECT MAX(fetched_at) v FROM forecasts").fetchone()["v"]
        last_snap = conn.execute("SELECT MAX(snapshot_at) v FROM orderbook_snapshots").fetchone()["v"]
        last_sett = conn.execute("SELECT MAX(observed_at) v FROM settlements").fetchone()["v"]

        # Calibration: join decisions to settlements via market_id, bucket by decile.
        rows = conn.execute(
            """
            SELECT d.my_p AS my_p, s.bucket_hit AS hit
              FROM decisions d
              JOIN settlements s ON s.market_id = d.market_id
             WHERE d.my_p IS NOT NULL
            """
        ).fetchall()

        buckets: dict[int, list[tuple[float, int]]] = {}
        for r in rows:
            buckets.setdefault(_decile(r["my_p"]), []).append((r["my_p"], int(r["hit"])))
        calibration = []
        for d in range(10):
            entries = buckets.get(d, [])
            if not entries:
                calibration.append(CalibrationBucket(d, 0, (d + 0.5) / 10.0, None))
                continue
            mp = sum(e[0] for e in entries) / len(entries)
            hr = sum(e[1] for e in entries) / len(entries)
            calibration.append(CalibrationBucket(d, len(entries), mp, hr))

        drift = _drift_last_7d(conn)

    return StatusReport(
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        n_markets_tracked=int(n_markets),
        n_open_markets=int(n_open),
        n_settled_markets=int(n_settled),
        n_decisions=int(n_decisions),
        n_would_trade=int(wt["c"] or 0),
        mean_edge_would_trade=(float(wt["mean_edge"]) if wt["mean_edge"] is not None else None),
        calibration=calibration,
        drift_7d=drift,
        last_forecast_at=last_fc,
        last_snapshot_at=last_snap,
        last_settlement_at=last_sett,
    )


def _drift_last_7d(conn) -> float | None:
    """Mean (my_p - bucket_hit) on settlements observed in the last 7 days.

    Positive drift means we are systematically too high; negative means too low.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="seconds")
    row = conn.execute(
        """
        SELECT AVG(d.my_p - s.bucket_hit) AS drift
          FROM decisions d
          JOIN settlements s ON s.market_id = d.market_id
         WHERE s.observed_at >= ?
        """,
        (cutoff,),
    ).fetchone()
    return float(row["drift"]) if row and row["drift"] is not None else None
