"""One-shot diagnostic: figure out why the live filter matches zero of 1000.

Not committed; throwaway. Run with `uv run python scripts/diagnose_polymarket.py`.

Prints, in order:
  1. The first 50 active market questions (raw, plus a few neighbour fields).
  2. Every market across all 1000 whose question, slug, groupItemTitle,
     description, eventTitle, events[].title, or any tag name contains a
     weather/temperature keyword or one of our tracked-city aliases.
     For each, prints which field matched and which keyword.
  3. The result of GET /events?tag_slug=weather (count + first few titles)
     so we can decide whether to switch off /markets.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from collections import Counter
from typing import Any, Iterable

# Make `weather_bot` importable when run from repo root.
sys.path.insert(0, "src")

from weather_bot import http as wb_http
from weather_bot.config import settings
from weather_bot.data.polymarket import CITY_ALIASES

CITY_PATTERNS = [(alias, re.compile(rf"\b{re.escape(alias)}\b", re.IGNORECASE))
                 for alias, _ in CITY_ALIASES]
KEYWORDS = [
    "temperature", "temp", "high in", "highest", "lowest", "fahrenheit",
    "degrees", "°f", "degf",
]
KEYWORD_PATTERNS = [(k, re.compile(re.escape(k), re.IGNORECASE)) for k in KEYWORDS]
ALL_PATTERNS = KEYWORD_PATTERNS + CITY_PATTERNS

# Fields we'll scan in addition to `question`.
TEXT_FIELDS = (
    "question", "slug", "title", "groupItemTitle", "description",
    "eventTitle", "groupSlug",
)


def _gather_text(m: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k in TEXT_FIELDS:
        v = m.get(k)
        if isinstance(v, str) and v:
            out[k] = v
    # Parent event titles (sometimes a list under "events").
    events = m.get("events") or []
    if isinstance(events, list):
        titles = [e.get("title") for e in events
                  if isinstance(e, dict) and isinstance(e.get("title"), str)]
        if titles:
            out["events[].title"] = " | ".join(titles)
        slugs = [e.get("slug") for e in events
                 if isinstance(e, dict) and isinstance(e.get("slug"), str)]
        if slugs:
            out["events[].slug"] = " | ".join(slugs)
    # Tags (sometimes objects with name).
    tags = m.get("tags") or []
    if isinstance(tags, list):
        names = [t.get("label") or t.get("name") for t in tags
                 if isinstance(t, dict)]
        names = [n for n in names if isinstance(n, str)]
        if names:
            out["tags"] = " | ".join(names)
    return out


def _scan(text_by_field: dict[str, str]) -> list[tuple[str, str, str]]:
    """Return list of (field, kind, term) hits."""
    hits: list[tuple[str, str, str]] = []
    for field, txt in text_by_field.items():
        for term, pat in KEYWORD_PATTERNS:
            if pat.search(txt):
                hits.append((field, "keyword", term))
        for alias, pat in CITY_PATTERNS:
            if pat.search(txt):
                hits.append((field, "city", alias))
    return hits


async def list_all() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for page in range(10):
        batch = await wb_http.get_json(
            f"{settings.polymarket_gamma_url}/markets",
            params={"active": "true", "closed": "false",
                    "limit": 100, "offset": page * 100},
        )
        if not isinstance(batch, list) or not batch:
            break
        out.extend(batch)
        if len(batch) < 100:
            break
    return out


async def fetch_event_by_slug(slug: str) -> list[dict[str, Any]]:
    """Look up a single event by slug. Gamma returns either a list or
    a single object depending on the endpoint variant; tolerate both.
    """
    try:
        result = await wb_http.get_json(
            f"{settings.polymarket_gamma_url}/events",
            params={"slug": slug},
        )
    except Exception as e:
        print(f"  events?slug={slug!r} ERROR {e}")
        return []
    if isinstance(result, dict):
        return [result]
    if isinstance(result, list):
        return result
    return []


async def probe_tag_slug(tag: str) -> int:
    try:
        result = await wb_http.get_json(
            f"{settings.polymarket_gamma_url}/events",
            params={"tag_slug": tag, "closed": "false", "limit": 100},
        )
    except Exception as e:
        print(f"  tag_slug={tag!r}: ERROR {e}")
        return -1
    n = len(result) if isinstance(result, list) else 0
    print(f"  tag_slug={tag!r}: {n} events")
    return n


async def search_query(q: str, limit: int = 50) -> list[dict[str, Any]]:
    try:
        result = await wb_http.get_json(
            f"{settings.polymarket_gamma_url}/events",
            params={"q": q, "closed": "false", "limit": limit},
        )
    except Exception as e:
        print(f"  q={q!r} ERROR {e}")
        return []
    return result if isinstance(result, list) else []


async def discover_tag() -> list[str]:
    """Pull a known weather event by slug, dump its shape, and return
    the tag slugs found on it (so the caller can probe each)."""
    print("=== tag discovery: known event by slug ===")
    candidate_slugs = [
        "highest-temperature-in-dallas-on-april-28-2026",
        "highest-temperature-in-dallas-on-april-28",
    ]
    found: list[dict[str, Any]] = []
    for cs in candidate_slugs:
        print(f"\n  trying slug={cs!r}")
        evs = await fetch_event_by_slug(cs)
        print(f"    -> {len(evs)} event(s)")
        if evs:
            found = evs
            break

    discovered_tag_slugs: list[str] = []
    if not found:
        print("\n  No event found by either Dallas slug. The market may have")
        print("  a different slug shape; pass one in via env or hard-code below.")
        return discovered_tag_slugs

    ev = found[0]
    print("\n  --- event keys ---")
    print(f"  {sorted(ev.keys())}")

    print("\n  --- event.tags ---")
    tags = ev.get("tags") or []
    if isinstance(tags, list):
        for t in tags:
            if not isinstance(t, dict):
                continue
            tid = t.get("id")
            label = t.get("label") or t.get("name")
            slug = t.get("slug")
            print(f"    id={tid!r}  label={label!r}  slug={slug!r}")
            if isinstance(slug, str):
                discovered_tag_slugs.append(slug)
    else:
        print(f"  (tags is not a list: {type(tags).__name__})")

    print("\n  --- event.markets[0] ---")
    subs = ev.get("markets") or []
    if subs and isinstance(subs[0], dict):
        sm0 = subs[0]
        print(f"  keys: {sorted(sm0.keys())}")
        print(f"  groupItemTitle={sm0.get('groupItemTitle')!r}")
        print(f"  question={sm0.get('question')!r}")
        print(f"  clobTokenIds={sm0.get('clobTokenIds')!r}")
        print(f"  outcomes={sm0.get('outcomes')!r}")
        print(f"  conditionId={sm0.get('conditionId')!r}")
    else:
        print(f"  (no sub-markets: markets={subs!r})")

    print(f"\n  total sub-markets on this event: {len(subs)}")
    return discovered_tag_slugs


async def events_temperature() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for page in range(5):
        try:
            batch = await wb_http.get_json(
                f"{settings.polymarket_gamma_url}/events",
                params={"tag_slug": "temperature", "closed": "false",
                        "limit": 100, "offset": page * 100},
            )
        except Exception as e:
            print(f"events?tag_slug=temperature page={page} failed: {e}")
            break
        if not isinstance(batch, list) or not batch:
            break
        out.extend(batch)
        if len(batch) < 100:
            break
    return out


async def main() -> None:
    # 0. Tag discovery first; this is what we actually need today.
    discovered = await discover_tag()

    print("\n=== tag probe ===")
    seen: set[str] = set()
    candidates = list(discovered) + [
        "temperature", "daily-temperature", "temperature-daily",
        "weather-temperature", "highest-temperature", "weather",
    ]
    for tag in candidates:
        if tag in seen:
            continue
        seen.add(tag)
        await probe_tag_slug(tag)

    print("\n=== free-text search: q=highest+temperature ===")
    res = await search_query("highest temperature", limit=50)
    print(f"events returned: {len(res)}")
    for e in res[:25]:
        title = e.get("title")
        slug = e.get("slug")
        n_sub = len(e.get("markets") or [])
        print(f"  - title={title!r}  slug={slug!r}  markets={n_sub}")

    # 1. Original /markets cross-field scan, kept as a backstop.
    markets = await list_all()
    print(f"\n=== /markets active=true closed=false: {len(markets)} markets ===\n")

    print("--- First 50 questions (with neighbour fields) ---")
    for i, m in enumerate(markets[:50]):
        q = (m.get("question") or "").strip()
        gi = (m.get("groupItemTitle") or "").strip()
        slug = (m.get("slug") or "").strip()
        ev = ""
        if isinstance(m.get("events"), list) and m["events"]:
            t = m["events"][0].get("title") if isinstance(m["events"][0], dict) else None
            ev = (t or "").strip()
        print(f"{i:3d}. q={q!r}")
        if gi or ev or slug:
            print(f"     groupItemTitle={gi!r}  events[0].title={ev!r}  slug={slug!r}")

    print("\n--- Cross-field keyword/city scan over all markets ---")
    field_counter: Counter[str] = Counter()
    term_counter: Counter[str] = Counter()
    candidates: list[dict[str, Any]] = []
    for m in markets:
        text = _gather_text(m)
        hits = _scan(text)
        if not hits:
            continue
        candidates.append({"market": m, "text": text, "hits": hits})
        for f, _kind, term in hits:
            field_counter[f] += 1
            term_counter[term] += 1

    print(f"Markets with at least one hit on any field: {len(candidates)}")
    print(f"Hits by field:  {dict(field_counter.most_common())}")
    print(f"Hits by term:   {dict(term_counter.most_common(20))}")

    print("\n--- First 30 candidate matches ---")
    for c in candidates[:30]:
        m = c["market"]
        print(f"id={m.get('id')} cond={str(m.get('conditionId'))[:20]} "
              f"q={(m.get('question') or '')!r}")
        for f, kind, term in c["hits"][:6]:
            txt = c["text"].get(f, "")
            print(f"   {kind:7s} {term!r:>14} in {f}: {txt[:120]!r}")

    print("\n=== /events tag_slug=temperature ===")
    evs = await events_temperature()
    print(f"events returned: {len(evs)}")
    for e in evs[:25]:
        title = e.get("title")
        slug = e.get("slug")
        n_sub = len(e.get("markets") or [])
        print(f"  - title={title!r}  slug={slug!r}  markets={n_sub}")
    if evs:
        # Show sub-market labels for the first temperature event.
        first = evs[0]
        subs = first.get("markets") or []
        print(f"\nFirst event sub-markets ({len(subs)}):")
        for sm in subs[:15]:
            print(f"   q={(sm.get('question') or '')!r}  "
                  f"groupItemTitle={(sm.get('groupItemTitle') or '')!r}")

    # Run our parser end-to-end and show what we'd actually ingest.
    from weather_bot.data import polymarket as wb_poly
    parsed: list = []
    for ev in evs:
        parsed.extend(wb_poly.parse_temperature_event(ev))
    print(f"\nparse_temperature_event total sub-markets parsed: {len(parsed)}")
    by_station: Counter[str] = Counter()
    for p in parsed:
        by_station[p.station or "?"] += 1
    print(f"by station: {dict(by_station.most_common())}")
    if parsed:
        print("\nFirst 15 parsed PolyMarkets:")
        for p in parsed[:15]:
            print(f"  station={p.station} target={p.target_date} "
                  f"bucket={p.bucket_kind}({p.bucket_low_f}, {p.bucket_high_f}) "
                  f"yes={str(p.yes_token_id)[:18]} q={p.question[:50]!r}")


if __name__ == "__main__":
    asyncio.run(main())
