"""Polymarket Gamma + CLOB clients (read only).

Gamma API:  https://gamma-api.polymarket.com  (market metadata)
CLOB API:   https://clob.polymarket.com       (orderbook depth)

We only read. No keys, no signing. We never POST.

Weather temperature markets phrasing on Polymarket is fairly consistent. Recent
examples include questions like:

    "Highest temperature in NYC on April 28?"
    "Will the high in Chicago be above 70F on April 28?"

The lister pulls active markets, then filters client side by question text
matching one of the tracked cities and a temperature keyword. Bucket parsing
is best effort and stored alongside the raw JSON so we can re-parse later.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from .. import http as wb_http
from ..cities import CITIES, City
from ..config import settings

log = logging.getLogger("weather_bot.polymarket")


# Phrases that map a market question to one of our tracked cities.
# Order matters slightly: longer / more specific aliases first.
CITY_ALIASES: list[tuple[str, City]] = []
for _c in CITIES:
    aliases = {_c.name, _c.station}
    if _c.name == "New York":
        aliases.update({"NYC", "New York City"})
    if _c.name == "Los Angeles":
        aliases.update({"LA"})
    for a in aliases:
        CITY_ALIASES.append((a, _c))
CITY_ALIASES.sort(key=lambda x: -len(x[0]))


_TEMP_KEYWORDS = re.compile(
    r"\b(temperature|temp\.?|high(?:est)?|low(?:est)?|degrees?|fahrenheit|°\s?f|deg\s?f)\b",
    re.IGNORECASE,
)


@dataclass
class PolyMarket:
    market_id: str
    slug: str
    question: str
    station: str | None
    target_date: str | None
    bucket_kind: str | None
    bucket_low_f: float | None
    bucket_high_f: float | None
    end_date_iso: str | None
    yes_token_id: str | None
    no_token_id: str | None
    raw: dict[str, Any] = field(default_factory=dict)


def _looks_like_weather_temp_market(question: str) -> bool:
    if not question:
        return False
    if not _TEMP_KEYWORDS.search(question):
        return False
    return any(re.search(rf"\b{re.escape(alias)}\b", question, re.IGNORECASE)
               for alias, _ in CITY_ALIASES)


def _match_city(question: str) -> City | None:
    for alias, city in CITY_ALIASES:
        if re.search(rf"\b{re.escape(alias)}\b", question, re.IGNORECASE):
            return city
    return None


_RANGE_RE = re.compile(r"(\d{2,3})\s*(?:to|-|–)\s*(\d{2,3})\s*(?:°\s?F|F\b)?", re.IGNORECASE)
_ABOVE_RE = re.compile(r"(?:above|over|more than|>=?)\s*(\d{2,3})\s*(?:°\s?F|F\b)?", re.IGNORECASE)
_BELOW_RE = re.compile(r"(?:below|under|less than|<=?)\s*(\d{2,3})\s*(?:°\s?F|F\b)?", re.IGNORECASE)
_EXACT_RE = re.compile(r"\b(?:exactly|equal to)?\s*(\d{2,3})\s*(?:°\s?F|F\b)\b", re.IGNORECASE)

# Tail-bucket phrasings where the number comes first and the qualifier
# follows. Polymarket weather markets use these for the open-ended top
# and bottom buckets, e.g. "92°F or higher", "60°F or below", "92F+".
_TAIL_HIGH_RE = re.compile(
    r"(\d{2,3})\s*(?:°\s?F|F)?\s*(?:\+|(?:or|and)\s+(?:higher|above|more|greater|over))",
    re.IGNORECASE,
)
_TAIL_LOW_RE = re.compile(
    r"(\d{2,3})\s*(?:°\s?F|F)?\s*(?:or|and)\s+(?:lower|below|less|fewer|under)",
    re.IGNORECASE,
)


def _parse_bucket(question: str) -> tuple[str | None, float | None, float | None]:
    """Best-effort bucket parser. Real markets use varied phrasing.

    Returns (bucket_kind, low_f, high_f). For 'above X' the high bound is None
    and low is X (inclusive). For 'below X' the low is None and high is X.

    Tail-bucket phrasings ("92°F or higher", "60°F or below") are tried
    before the prefix forms because they are more specific and would
    otherwise be partially matched by the bare-number _EXACT_RE.
    """
    if (m := _RANGE_RE.search(question)):
        lo, hi = float(m.group(1)), float(m.group(2))
        return ("range", min(lo, hi), max(lo, hi))
    if (m := _TAIL_HIGH_RE.search(question)):
        return ("above", float(m.group(1)), None)
    if (m := _TAIL_LOW_RE.search(question)):
        return ("below", None, float(m.group(1)))
    if (m := _ABOVE_RE.search(question)):
        return ("above", float(m.group(1)), None)
    if (m := _BELOW_RE.search(question)):
        return ("below", None, float(m.group(1)))
    if (m := _EXACT_RE.search(question)):
        return ("exact", float(m.group(1)), float(m.group(1)))
    return (None, None, None)


def _extract_token_ids(market_raw: dict[str, Any]) -> tuple[str | None, str | None]:
    """Find YES and NO CLOB token ids in a Gamma market payload.

    Gamma returns clobTokenIds as a list aligned with outcomes. Order can be
    [Yes, No] or the reverse. We map by outcome label.
    """
    outcomes = market_raw.get("outcomes")
    tokens = market_raw.get("clobTokenIds")
    # These fields are sometimes JSON-encoded strings.
    import json
    if isinstance(outcomes, str):
        try:
            outcomes = json.loads(outcomes)
        except json.JSONDecodeError:
            outcomes = None
    if isinstance(tokens, str):
        try:
            tokens = json.loads(tokens)
        except json.JSONDecodeError:
            tokens = None
    if not outcomes or not tokens or len(outcomes) != len(tokens):
        return (None, None)
    yes_id = no_id = None
    for label, tid in zip(outcomes, tokens):
        if isinstance(label, str):
            l = label.strip().lower()
            if l in ("yes", "y", "true"):
                yes_id = tid
            elif l in ("no", "n", "false"):
                no_id = tid
    return (yes_id, no_id)


async def list_active_markets(
    *,
    page_size: int = 100,
    max_pages: int = 10,
) -> list[dict[str, Any]]:
    """Page through Gamma's /markets endpoint for active, open markets."""
    url = f"{settings.polymarket_gamma_url}/markets"
    out: list[dict[str, Any]] = []
    for page in range(max_pages):
        params = {
            "active": "true",
            "closed": "false",
            "limit": page_size,
            "offset": page * page_size,
        }
        batch = await wb_http.get_json(url, params=params)
        if not isinstance(batch, list) or not batch:
            break
        out.extend(batch)
        if len(batch) < page_size:
            break
    return out


def filter_weather_temp_markets(raw_markets: Iterable[dict[str, Any]]) -> list[PolyMarket]:
    results: list[PolyMarket] = []
    for m in raw_markets:
        question = m.get("question") or m.get("title") or ""
        if not _looks_like_weather_temp_market(question):
            continue
        city = _match_city(question)
        kind, lo, hi = _parse_bucket(question)
        yes_id, no_id = _extract_token_ids(m)

        # Try a few common id fields. Gamma uses 'id' (numeric) plus 'conditionId'.
        market_id = (
            m.get("conditionId")
            or m.get("condition_id")
            or m.get("id")
            or m.get("slug")
        )
        if market_id is None:
            continue

        results.append(
            PolyMarket(
                market_id=str(market_id),
                slug=m.get("slug") or "",
                question=question,
                station=city.station if city else None,
                target_date=_extract_target_date(m, question),
                bucket_kind=kind,
                bucket_low_f=lo,
                bucket_high_f=hi,
                end_date_iso=m.get("endDate") or m.get("end_date_iso"),
                yes_token_id=yes_id,
                no_token_id=no_id,
                raw=m,
            )
        )
    return results


_DATE_IN_QUESTION = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})\b",
    re.IGNORECASE,
)


def _extract_target_date(m: dict[str, Any], question: str) -> str | None:
    end = m.get("endDate") or m.get("end_date_iso")
    if isinstance(end, str):
        try:
            return datetime.fromisoformat(end.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            pass
    if (mt := _DATE_IN_QUESTION.search(question)):
        month_name, day = mt.group(1), int(mt.group(2))
        try:
            month = datetime.strptime(month_name, "%B").month
            today = datetime.now(timezone.utc).date()
            year = today.year
            candidate = datetime(year, month, day).date()
            if candidate < today:
                candidate = datetime(year + 1, month, day).date()
            return candidate.isoformat()
        except ValueError:
            return None
    return None


async def fetch_clob_book(token_id: str) -> dict[str, Any]:
    """Fetch full orderbook depth for a CLOB token id."""
    url = f"{settings.polymarket_clob_url}/book"
    return await wb_http.get_json(url, params={"token_id": token_id})


def best_levels(book: dict[str, Any]) -> tuple[float | None, float | None]:
    """Return (best_bid, best_ask) from a CLOB book payload.

    CLOB returns bids sorted ascending and asks sorted ascending. Best bid is
    the highest price on bids, best ask is the lowest on asks. We tolerate
    either ordering by taking max/min explicitly.
    """
    bids = book.get("bids") or []
    asks = book.get("asks") or []
    best_bid = max((float(b["price"]) for b in bids), default=None)
    best_ask = min((float(a["price"]) for a in asks), default=None)
    return best_bid, best_ask
