from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from decimal import Decimal


class SequenceGap(RuntimeError):
    pass


class BookState(StrEnum):
    EMPTY = "EMPTY"
    BUFFERING = "BUFFERING"
    VALID = "VALID"
    INVALID = "INVALID"


@dataclass
class OrderBookSync:
    """Minimal Binance-style snapshot + delta integrity state machine.

    The caller is responsible for fetching a new snapshot when apply_delta raises
    SequenceGap or state becomes INVALID.
    """

    state: BookState = BookState.EMPTY
    last_update_id: int | None = None
    bids: dict[Decimal, Decimal] = field(default_factory=dict)
    asks: dict[Decimal, Decimal] = field(default_factory=dict)
    resync_count: int = 0

    def begin_buffering(self) -> None:
        self.state = BookState.BUFFERING

    def load_snapshot(self, last_update_id: int, bids: list[list[str]], asks: list[list[str]]) -> None:
        self.bids = {Decimal(p): Decimal(q) for p, q in bids if Decimal(q) != 0}
        self.asks = {Decimal(p): Decimal(q) for p, q in asks if Decimal(q) != 0}
        self.last_update_id = int(last_update_id)
        self.state = BookState.VALID

    def invalidate(self) -> None:
        self.state = BookState.INVALID
        self.resync_count += 1

    def apply_delta(self, first_id: int, final_id: int, bids: list[list[str]], asks: list[list[str]], previous_final_id: int | None = None) -> None:
        if self.state != BookState.VALID or self.last_update_id is None:
            raise SequenceGap("book not synchronized")
        if final_id <= self.last_update_id:
            return
        expected = self.last_update_id + 1
        if previous_final_id is not None and previous_final_id != self.last_update_id:
            self.invalidate()
            raise SequenceGap(f"previous_final_id={previous_final_id} expected={self.last_update_id}")
        if not (first_id <= expected <= final_id):
            self.invalidate()
            raise SequenceGap(f"range={first_id}-{final_id} expected={expected}")
        self._apply(self.bids, bids)
        self._apply(self.asks, asks)
        self.last_update_id = int(final_id)

    @staticmethod
    def _apply(side: dict[Decimal, Decimal], updates: list[list[str]]) -> None:
        for p, q in updates:
            price, qty = Decimal(p), Decimal(q)
            if qty == 0:
                side.pop(price, None)
            else:
                side[price] = qty

    def best_bid_ask(self) -> tuple[Decimal | None, Decimal | None]:
        return (max(self.bids) if self.bids else None, min(self.asks) if self.asks else None)
