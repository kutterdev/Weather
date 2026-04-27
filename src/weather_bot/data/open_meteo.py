"""Open-Meteo ensemble forecast puller.

API docs: https://open-meteo.com/en/docs/ensemble-api

We hit the ensemble endpoint per (city, model) pair and store every member
verbatim. The ensemble API returns hourly arrays per variable, with extra
columns suffixed `_member01`, `_member02`, ... per perturbed member. The
unsuffixed array is the control run.

Member counts (as of 2026):
  gfs025          31  (1 control + 30 perturbed)
  ecmwf_ifs025    51  (1 control + 50 perturbed)
  icon_seamless   40
  gem_global      21
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .. import http as wb_http
from ..cities import City
from ..config import settings
from ..db import connect

log = logging.getLogger("weather_bot.open_meteo")


@dataclass
class EnsembleForecast:
    station: str
    model: str
    fetched_at: str
    target_date: str
    n_members: int
    valid_times: list[str]                     # ISO UTC, length T
    members: list[list[float | None]]          # shape [n_members][T], temperature_c
    raw: dict[str, Any]


def _hourly_member_keys(hourly: dict[str, Any], variable: str) -> list[str]:
    """Return [variable, variable_member01, ...] in member index order.

    The control run is the unsuffixed key. Perturbed members are
    `<variable>_member01` ... `<variable>_memberNN`.
    """
    keys: list[str] = []
    if variable in hourly:
        keys.append(variable)
    suffixed = sorted(
        k for k in hourly.keys()
        if k.startswith(f"{variable}_member") and k != variable
    )
    keys.extend(suffixed)
    return keys


async def fetch_ensemble(
    city: City,
    model: str,
    *,
    forecast_days: int | None = None,
    variable: str = "temperature_2m",
) -> EnsembleForecast:
    """Fetch one ensemble run for a city and model. Returns parsed members.

    target_date is the next calendar day in the city's timezone, used as a
    convenience tag on the row. Storage keeps every hour; analysis layer
    picks the relevant date when computing buckets.
    """
    days = forecast_days or settings.forecast_days
    params = {
        "latitude": city.lat,
        "longitude": city.lon,
        "hourly": variable,
        "models": model,
        "forecast_days": days,
        "timezone": "UTC",
        "temperature_unit": "celsius",
        "windspeed_unit": "kmh",
    }
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    log.info("Fetching ensemble model=%s station=%s days=%d", model, city.station, days)
    raw = await wb_http.get_json(settings.open_meteo_ensemble_url, params=params)

    hourly = raw.get("hourly") or {}
    times = hourly.get("time") or []
    keys = _hourly_member_keys(hourly, variable)
    if not keys:
        raise RuntimeError(
            f"Open-Meteo response missing variable {variable} for model {model}"
        )

    members = [hourly[k] for k in keys]
    n_members = len(members)

    # Convenience target_date: tomorrow in the city's local tz, computed from
    # the forecast horizon. Stored loosely; the analysis layer recomputes.
    from zoneinfo import ZoneInfo  # stdlib, but local import keeps top clean
    local_now = datetime.now(ZoneInfo(city.tz))
    target_date = local_now.date().isoformat()  # today; tomorrow handled by analysis

    return EnsembleForecast(
        station=city.station,
        model=model,
        fetched_at=fetched_at,
        target_date=target_date,
        n_members=n_members,
        valid_times=list(times),
        members=members,
        raw=raw,
    )


def save_forecast(f: EnsembleForecast) -> int:
    """Persist a forecast and its member time series. Returns forecast row id."""
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO forecasts
                (station, model, target_date, fetched_at, n_members, raw_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                f.station,
                f.model,
                f.target_date,
                f.fetched_at,
                f.n_members,
                json.dumps(f.raw),
            ),
        )
        if cur.rowcount == 0:
            row = conn.execute(
                """
                SELECT id FROM forecasts
                 WHERE station=? AND model=? AND target_date=? AND fetched_at=?
                """,
                (f.station, f.model, f.target_date, f.fetched_at),
            ).fetchone()
            return int(row["id"])
        forecast_id = int(cur.lastrowid)

        rows = []
        for m_idx, series in enumerate(f.members):
            for t_idx, t in enumerate(f.valid_times):
                if t_idx >= len(series):
                    break
                rows.append((forecast_id, m_idx, t, series[t_idx]))
        conn.executemany(
            """
            INSERT OR IGNORE INTO ensemble_members
                (forecast_id, member_index, valid_time, temperature_c)
            VALUES (?, ?, ?, ?)
            """,
            rows,
        )
        return forecast_id
