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


async def events_weather() -> list[dict[str, Any]]:
    try:
        batch = await wb_http.get_json(
            f"{settings.polymarket_gamma_url}/events",
            params={"tag_slug": "weather", "closed": "false", "limit": 100},
        )
        return batch if isinstance(batch, list) else []
    except Exception as e:
        print(f"events?tag_slug=weather failed: {e}")
        return []


async def main() -> None:
    markets = await list_all()
    print(f"=== /markets active=true closed=false: {len(markets)} markets ===\n")

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

    print("\n=== /events tag_slug=weather ===")
    evs = await events_weather()
    print(f"events returned: {len(evs)}")
    for e in evs[:10]:
        title = e.get("title")
        slug = e.get("slug")
        n_sub = len(e.get("markets") or [])
        print(f"  - title={title!r}  slug={slug!r}  markets={n_sub}")
    if evs:
        # Show sub-market questions for the first weather event.
        first = evs[0]
        subs = first.get("markets") or []
        print(f"\nFirst event sub-markets ({len(subs)}):")
        for sm in subs[:10]:
            print(f"   q={(sm.get('question') or '')!r}  "
                  f"groupItemTitle={(sm.get('groupItemTitle') or '')!r}")


if __name__ == "__main__":
    asyncio.run(main())
