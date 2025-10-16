"""
Card primitives and hand evaluation utilities for Texas Hold'em.

The evaluator follows the common "rank tuple" approach that is easy to reason
about and good enough for benchmarking throughput.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Iterable, List, Sequence, Tuple

SUITS: Tuple[str, ...] = ("s", "h", "d", "c")
RANKS: Tuple[str, ...] = ("2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A")
RANK_TO_INT = {rank: idx for idx, rank in enumerate(RANKS, start=2)}
INT_TO_RANK = {idx: rank for rank, idx in RANK_TO_INT.items()}


@dataclass(frozen=True)
class Card:
    rank: str
    suit: str

    def __post_init__(self) -> None:
        if self.rank not in RANK_TO_INT:
            raise ValueError(f"invalid rank {self.rank}")
        if self.suit not in SUITS:
            raise ValueError(f"invalid suit {self.suit}")

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"

    def __repr__(self) -> str:
        return f"Card(rank={self.rank!r}, suit={self.suit!r})"


def card_from_str(token: str) -> Card:
    token = token.strip()
    if len(token) != 2:
        raise ValueError(f"invalid card token: {token!r}")
    return Card(rank=token[0], suit=token[1])


def new_deck() -> List[Card]:
    return [Card(rank, suit) for rank in RANKS for suit in SUITS]


def card_int(card: Card) -> int:
    """Compact integer representation (2..14 for rank, suit encoded as bitmask)."""
    return (RANK_TO_INT[card.rank] << 2) | SUITS.index(card.suit)


def evaluate_five(cards: Sequence[Card]) -> Tuple[int, Tuple[int, ...]]:
    """
    Evaluate a five-card hand and return a tuple (category, kickers).

    Categories follow standard poker ranking (9=straight flush ... 1=high card).
    """
    ranks = sorted((RANK_TO_INT[c.rank] for c in cards), reverse=True)
    suits = [c.suit for c in cards]
    unique_ranks = sorted(set(ranks), reverse=True)
    is_flush = len(set(suits)) == 1

    # Straight detection with wheel handling.
    rank_set = set(ranks)
    is_straight = False
    straight_high = None
    for start in range(14, 3, -1):
        window = {start - i for i in range(5)}
        if window == rank_set and len(rank_set) == 5:
            is_straight = True
            straight_high = start
            break
    if not is_straight and rank_set == {14, 5, 4, 3, 2}:
        is_straight = True
        straight_high = 5

    counts = {r: ranks.count(r) for r in unique_ranks}
    count_values = sorted(counts.values(), reverse=True)

    if is_flush and is_straight:
        return 9, (straight_high,)
    if count_values == [4, 1]:
        four_rank = max(counts, key=lambda r: (counts[r], r))
        kicker = max(r for r in unique_ranks if r != four_rank)
        return 8, (four_rank, kicker)
    if count_values == [3, 2]:
        trips_rank = max(r for r, c in counts.items() if c == 3)
        pair_rank = max(r for r, c in counts.items() if c == 2)
        return 7, (trips_rank, pair_rank)
    if is_flush:
        return 6, tuple(ranks)
    if is_straight:
        return 5, (straight_high,)
    if count_values == [3, 1, 1]:
        trips_rank = max(r for r, c in counts.items() if c == 3)
        kickers = tuple(sorted((r for r in unique_ranks if r != trips_rank), reverse=True))
        return 4, (trips_rank, *kickers)
    if count_values == [2, 2, 1]:
        pair_ranks = sorted((r for r, c in counts.items() if c == 2), reverse=True)
        kicker = max(r for r, c in counts.items() if c == 1)
        return 3, (*pair_ranks, kicker)
    if count_values == [2, 1, 1, 1]:
        pair_rank = max(r for r, c in counts.items() if c == 2)
        kicker = tuple(sorted((r for r in unique_ranks if r != pair_rank), reverse=True))
        return 2, (pair_rank, *kicker)
    return 1, tuple(ranks)


def best_hand_rank(cards: Sequence[Card]) -> Tuple[int, Tuple[int, ...]]:
    """
    Compute the best 5-card hand rank for a 7-card combination (Texas Hold'em).

    Returns a tuple comparable with standard tuple comparison rules.
    """
    if len(cards) < 5:
        raise ValueError("at least five cards required")
    best = (0, ())
    for combo in combinations(cards, 5):
        value = evaluate_five(combo)
        if value > best:
            best = value
    return best


def describe_rank(rank_tuple: Tuple[int, Tuple[int, ...]]) -> str:
    category, kickers = rank_tuple
    category_names = {
        9: "Straight Flush",
        8: "Four of a Kind",
        7: "Full House",
        6: "Flush",
        5: "Straight",
        4: "Three of a Kind",
        3: "Two Pair",
        2: "One Pair",
        1: "High Card",
    }
    kickers_text = "-".join(INT_TO_RANK.get(v, str(v)) for v in kickers)
    return f"{category_names[category]} ({kickers_text})"


def cards_from_iterable(tokens: Iterable[str]) -> List[Card]:
    return [card_from_str(token) for token in tokens]
