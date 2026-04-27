"""Iowa Environmental Mesonet ASOS observation puller.

Settlement source. We hit the public ASOS download endpoint and ask for the
daily max temperature in Fahrenheit at the resolving airport.

Endpoint: https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py

The endpoint returns CSV. We do not need the full hourly record for the
settlement; the daily summary fields are enough. For Phase 1 we fetch the
hourly window and compute max/min ourselves so we control the timezone
boundaries (Polymarket markets resolve on the calendar day in the city's
local time, not UTC).
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime, timedelta
from typing import Iterable

from .. import http as wb_http
from ..cities import get_city
from ..config import settings

log = logging.getLogger("weather_bot.iem")


def _f_to_f(v: str) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


async def fetch_daily_high_low(station: str, target_date: date) -> dict[str, float | str | None]:
    """Return {high_f, low_f, n_obs, observed_at} for a station on a date.

    We pull the hourly METAR temperatures for the target_date in the city's
    local timezone, plus a one-hour buffer on each side. The 'tmpf' column is
    air temperature in Fahrenheit.
    """
    city = get_city(station)
    # ASOS endpoint expects bare 3-letter or 4-letter station codes.
    # KLGA works directly. Strip leading K only if needed.
    asos_station = station

    # Target window in the city's local tz, then converted to UTC for the API.
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(city.tz)
    start_local = datetime.combine(target_date, datetime.min.time(), tzinfo=tz)
    end_local = start_local + timedelta(days=1)

    params = {
        "station": asos_station,
        "data": "tmpf",
        "year1": start_local.year,
        "month1": start_local.month,
        "day1": start_local.day,
        "year2": end_local.year,
        "month2": end_local.month,
        "day2": end_local.day,
        "tz": city.tz,
        "format": "onlycomma",
        "missing": "M",
        "trace": "T",
        "latlon": "no",
        "elev": "no",
        "report_type": 3,    # 3 = MADIS HFMETAR
    }
    text = await wb_http.get_text(settings.iem_asos_url, params=params)

    high: float | None = None
    low: float | None = None
    n = 0
    last_ts: str | None = None
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        v = _f_to_f(row.get("tmpf", ""))
        if v is None:
            continue
        n += 1
        last_ts = row.get("valid")
        high = v if high is None else max(high, v)
        low = v if low is None else min(low, v)

    return {
        "high_f": high,
        "low_f": low,
        "n_obs": n,
        "observed_at": last_ts,
    }


def stations() -> Iterable[str]:
    from ..cities import CITIES
    return [c.station for c in CITIES]
