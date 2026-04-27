"""Probability model v1: ensemble member counting.

Given a city, target date, temperature bucket, and a recent ensemble forecast,
estimate p_yes as the fraction of ensemble members whose simulated daily high
falls inside the bucket. Confidence is reported as the ensemble standard
deviation of the daily high (in Fahrenheit).

Caveats we acknowledge here so the analysis layer is honest:
  - Member counting is a raw frequentist estimate. With 31 GFS members,
    point estimates have meaningful sampling noise (a 0.0 or 1.0 bucket
    can simply mean no member happened to land there).
  - We do not (yet) calibrate against historical residuals. That is v2.
  - The 'daily high' here is the max of hourly temperatures in the city's
    local-day window. Polymarket resolves on the official ASOS daily max,
    which can differ slightly from hourly METAR maxima.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import mean, pstdev
from zoneinfo import ZoneInfo

from ..cities import get_city


def c_to_f(c: float) -> float:
    return c * 9.0 / 5.0 + 32.0


@dataclass
class EnsembleProbability:
    p_yes: float
    n_members: int
    n_in_bucket: int
    member_highs_f: list[float]
    confidence_std_f: float        # ensemble std of the daily high
    target_date: str
    station: str


def _local_day_window_utc(station: str, target_date: date) -> tuple[datetime, datetime]:
    city = get_city(station)
    tz = ZoneInfo(city.tz)
    start_local = datetime.combine(target_date, datetime.min.time(), tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(ZoneInfo("UTC")), end_local.astimezone(ZoneInfo("UTC"))


def _parse_iso(s: str) -> datetime:
    # Open-Meteo returns naive ISO strings ("2026-04-28T15:00") in the tz we
    # asked for. We requested timezone=UTC so we tag UTC explicitly.
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt


def member_daily_highs_f(
    valid_times: list[str],
    members: list[list[float | None]],
    station: str,
    target_date: date,
) -> list[float]:
    """Compute each member's daily high (F) for the city-local target_date."""
    start_utc, end_utc = _local_day_window_utc(station, target_date)
    parsed = [_parse_iso(t) for t in valid_times]
    in_window = [start_utc <= t < end_utc for t in parsed]

    highs: list[float] = []
    for series in members:
        vals = [
            c_to_f(v)
            for v, keep in zip(series, in_window)
            if keep and v is not None
        ]
        if vals:
            highs.append(max(vals))
    return highs


def probability_for_bucket(
    *,
    valid_times: list[str],
    members: list[list[float | None]],
    station: str,
    target_date: date,
    bucket_kind: str,
    bucket_low_f: float | None,
    bucket_high_f: float | None,
) -> EnsembleProbability:
    """Return p_yes and a confidence metric for a bucket.

    bucket_kind in {'range', 'above', 'below', 'exact'}:
      range  : low_f <= high <= high_f
      above  : high >= low_f
      below  : high <= high_f
      exact  : floor(high) == floor(low_f)  (treats market as 1F-wide)
    """
    highs = member_daily_highs_f(valid_times, members, station, target_date)
    n = len(highs)
    if n == 0:
        return EnsembleProbability(
            p_yes=float("nan"),
            n_members=0,
            n_in_bucket=0,
            member_highs_f=[],
            confidence_std_f=float("nan"),
            target_date=target_date.isoformat(),
            station=station,
        )

    def in_bucket(h: float) -> bool:
        if bucket_kind == "range":
            return (bucket_low_f is not None and bucket_high_f is not None
                    and bucket_low_f <= h <= bucket_high_f)
        if bucket_kind == "above":
            return bucket_low_f is not None and h >= bucket_low_f
        if bucket_kind == "below":
            return bucket_high_f is not None and h <= bucket_high_f
        if bucket_kind == "exact":
            if bucket_low_f is None:
                return False
            return int(h) == int(bucket_low_f)
        return False

    hits = sum(1 for h in highs if in_bucket(h))
    std = pstdev(highs) if n >= 2 else 0.0
    return EnsembleProbability(
        p_yes=hits / n,
        n_members=n,
        n_in_bucket=hits,
        member_highs_f=highs,
        confidence_std_f=std,
        target_date=target_date.isoformat(),
        station=station,
    )


def ensemble_summary(highs: list[float]) -> dict[str, float]:
    if not highs:
        return {"n": 0}
    return {
        "n": len(highs),
        "mean_f": mean(highs),
        "min_f": min(highs),
        "max_f": max(highs),
        "std_f": pstdev(highs) if len(highs) >= 2 else 0.0,
    }
