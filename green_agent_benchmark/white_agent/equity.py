from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Sequence, Tuple

from ..cards import Card, best_hand_rank, card_from_str, new_deck
from .ranges import sample_opponent_hole_cards


@dataclass(frozen=True, slots=True)
class EquityEstimate:
    equity: float
    stderror: float
    samples: int
    seed: int


def _hash_seed(seed_material: str, fallback: int = 0) -> int:
    if not seed_material:
        return fallback
    acc = 2166136261
    for ch in seed_material.encode("utf-8", errors="ignore"):
        acc ^= ch
        acc = (acc * 16777619) & 0xFFFFFFFF
    return int(acc)


def estimate_equity(
    hero_hole: Sequence[str],
    board: Sequence[str],
    opponent_range: str,
    n_samples: int,
    *,
    seed: int | None = None,
    seed_material: str = "",
    opponents: int = 1,
) -> EquityEstimate:
    if len(hero_hole) < 2:
        raise ValueError("hero_hole must have two cards")
    n_samples = max(int(n_samples), 1)
    opponents = max(int(opponents), 1)

    seed_int = int(seed) if seed is not None else _hash_seed(seed_material, 0)
    rng = random.Random(seed_int)

    deck = new_deck()
    hero_cards = [card_from_str(c) for c in hero_hole[:2]]
    board_cards = [card_from_str(c) for c in board]

    dead: List[Card] = [*hero_cards, *board_cards]
    remaining_board = max(5 - len(board_cards), 0)

    win_share_total = 0.0
    for _ in range(n_samples):
        dead_now: List[Card] = list(dead)
        opp_hands: List[Tuple[Card, Card]] = []
        for _j in range(opponents):
            c1, c2 = sample_opponent_hole_cards(rng, deck, dead_now, opponent_range)
            opp_hands.append((c1, c2))
            dead_now.extend([c1, c2])

        dead_str = {str(x) for x in dead_now}
        available = [c for c in deck if str(c) not in dead_str]
        runout = rng.sample(available, remaining_board) if remaining_board else []
        full_board = board_cards + runout

        hero_rank = best_hand_rank(hero_cards + full_board)
        opp_ranks = [best_hand_rank([h1, h2] + full_board) for (h1, h2) in opp_hands]

        best_rank = hero_rank
        for r in opp_ranks:
            if r > best_rank:
                best_rank = r

        winners = 0
        hero_wins = hero_rank == best_rank
        if hero_wins:
            winners += 1
        winners += sum(1 for r in opp_ranks if r == best_rank)

        if hero_wins:
            win_share_total += 1.0 / max(winners, 1)

    equity = win_share_total / n_samples
    stderror = math.sqrt(max(equity * (1.0 - equity), 0.0) / n_samples)
    return EquityEstimate(equity=equity, stderror=stderror, samples=n_samples, seed=seed_int)

