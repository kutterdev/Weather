"""Execution layer stub. INTENTIONALLY non functional in Phase 1.

We define the interface here so the analysis layer compiles against a stable
shape, but every method raises. There is no wallet, no key handling, no
signing, and no trade-related code in this session by design (see CLAUDE.md).

When we eventually wire this up:
  - Use the official py-clob-client SDK from Polymarket.
  - Hold the proxy wallet key in an OS keychain or a hardware wallet, not env.
  - Gate trade calls on a manual config flag default false, plus a per-day
    notional cap, plus a per-market cap.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OrderIntent:
    market_id: str
    token_id: str
    side: str               # 'BUY' or 'SELL' (we will only BUY in v1)
    price: float
    size: float


class ExecutionDisabled(RuntimeError):
    pass


def submit(_: OrderIntent) -> None:
    raise ExecutionDisabled(
        "Execution is disabled in Phase 1. See CLAUDE.md."
    )


def cancel(_: str) -> None:
    raise ExecutionDisabled(
        "Execution is disabled in Phase 1. See CLAUDE.md."
    )


def open_orders() -> list[OrderIntent]:
    raise ExecutionDisabled(
        "Execution is disabled in Phase 1. See CLAUDE.md."
    )
