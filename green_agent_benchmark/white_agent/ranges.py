from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

from ..cards import Card, RANK_TO_INT


def bucket_from_vpip_pfr(vpip: float | None, pfr: float | None) -> Tuple[str, bool]:
    bucket = "medium"
    aggressive = False
    if isinstance(vpip, (int, float)):
        if vpip < 0.15:
            bucket = "tight"
        elif vpip > 0.30:
            bucket = "loose"
    if isinstance(pfr, (int, float)) and pfr > 0.10:
        aggressive = True
    return bucket, aggressive


def _rank_value(rank: str) -> int:
    return RANK_TO_INT.get(rank, 0)


def _starting_hand_strength(card1: Card, card2: Card) -> float:
    r1 = _rank_value(card1.rank)
    r2 = _rank_value(card2.rank)
    high = max(r1, r2) / 14.0
    low = min(r1, r2) / 14.0
    suited = 1.0 if card1.suit == card2.suit else 0.0
    gap = abs(r1 - r2)
    connected = 1.0 if gap <= 2 else 0.0
    pair = 1.0 if r1 == r2 else 0.0
    return min(1.0, 0.55 * high + 0.15 * low + 0.18 * suited + 0.12 * connected + 0.45 * pair)


@dataclass(frozen=True, slots=True)
class RangeSpec:
    bucket: str  # tight|medium|loose

    def accepts(self, strength: float) -> bool:
        if self.bucket == "tight":
            return strength >= 0.78
        if self.bucket == "loose":
            return strength >= 0.45
        return strength >= 0.60


def sample_opponent_hole_cards(
    rng: random.Random,
    deck: Sequence[Card],
    dead_cards: Iterable[Card],
    range_bucket: str,
    *,
    max_attempts: int = 2000,
) -> Tuple[Card, Card]:
    dead = {str(c) for c in dead_cards}
    range_spec = RangeSpec(bucket=range_bucket)

    available: List[Card] = [c for c in deck if str(c) not in dead]
    if len(available) < 2:
        raise ValueError("Not enough cards to sample opponent hole cards.")

    for _ in range(max_attempts):
        c1, c2 = rng.sample(available, 2)
        strength = _starting_hand_strength(c1, c2)
        if range_spec.accepts(strength):
            return c1, c2

    return tuple(rng.sample(available, 2))  # type: ignore[return-value]

