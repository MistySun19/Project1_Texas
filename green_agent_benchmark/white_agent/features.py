from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from ..cards import RANK_TO_INT, best_hand_rank, card_from_str, describe_rank
from .models import DecisionState


def _safe_float(numer: float, denom: float) -> Optional[float]:
    if denom == 0:
        return None
    return float(numer) / float(denom)


def _ranks_suits(cards: Sequence[str]) -> Tuple[list[int], list[str]]:
    ranks: list[int] = []
    suits: list[str] = []
    for token in cards:
        try:
            c = card_from_str(str(token))
        except Exception:
            continue
        ranks.append(RANK_TO_INT[c.rank])
        suits.append(c.suit)
    return ranks, suits


def hole_card_features(hole_cards: Tuple[str, str]) -> Dict[str, Any]:
    r, s = _ranks_suits(list(hole_cards))
    if len(r) != 2 or len(s) != 2:
        return {"raw": list(hole_cards)}
    r1, r2 = r[0], r[1]
    gap = abs(r1 - r2)
    high = max(r1, r2)
    low = min(r1, r2)
    suited = s[0] == s[1]
    pair = r1 == r2
    connected = gap <= 3 and not pair
    broadway = sum(1 for x in (r1, r2) if x >= 10)
    return {
        "pair": pair,
        "suited": suited,
        "gap": gap,
        "connected": connected,
        "high_rank": high,
        "low_rank": low,
        "broadway_count": broadway,
    }


def board_texture(board_cards: Sequence[str]) -> Dict[str, Any]:
    ranks, suits = _ranks_suits(list(board_cards))
    if not ranks:
        return {"cards": list(board_cards)}

    rank_counts: Dict[int, int] = {}
    for r in ranks:
        rank_counts[r] = rank_counts.get(r, 0) + 1
    suit_counts: Dict[str, int] = {}
    for s in suits:
        suit_counts[s] = suit_counts.get(s, 0) + 1

    unique_ranks = sorted(set(ranks))
    unique_suits = set(suits)
    max_suit = max(suit_counts.values()) if suit_counts else 0

    # Connectivity / straightiness: compute max consecutive run on unique ranks.
    max_run = 1
    run = 1
    for i in range(1, len(unique_ranks)):
        if unique_ranks[i] == unique_ranks[i - 1] + 1:
            run += 1
        else:
            max_run = max(max_run, run)
            run = 1
    max_run = max(max_run, run)

    return {
        "paired": any(v >= 2 for v in rank_counts.values()),
        "trips_or_better_on_board": any(v >= 3 for v in rank_counts.values()),
        "suit_count": len(unique_suits),
        "monotone": len(unique_suits) == 1 and len(board_cards) >= 3,
        "two_tone": len(unique_suits) == 2 and len(board_cards) >= 3,
        "max_suit_count": max_suit,
        "max_consecutive_run": max_run,
        "high_rank": max(ranks),
        "low_rank": min(ranks),
    }


def draw_features(hole_cards: Tuple[str, str], board_cards: Sequence[str]) -> Dict[str, Any]:
    cards = list(hole_cards) + list(board_cards)
    ranks, suits = _ranks_suits(cards)
    if len(ranks) < 4:
        return {}

    suit_counts: Dict[str, int] = {}
    for s in suits:
        suit_counts[s] = suit_counts.get(s, 0) + 1
    flush_draw = max(suit_counts.values()) >= 4

    # Straight draw heuristic: any 5-rank window missing exactly 1 rank.
    unique = sorted(set(ranks))
    # Wheel support: treat A as low as well.
    if 14 in unique:
        unique.append(1)
        unique = sorted(set(unique))

    straight_draw = False
    open_ended = False
    gutshot = False
    for start in range(1, 15):
        window = {start + i for i in range(5)}
        present = window.intersection(unique)
        if len(present) == 4:
            straight_draw = True
            missing = sorted(window - present)
            if missing:
                miss = missing[0]
                if miss == start or miss == start + 4:
                    open_ended = True
                else:
                    gutshot = True

    return {
        "flush_draw": flush_draw,
        "straight_draw": straight_draw,
        "open_ended_straight_draw": open_ended,
        "gutshot_straight_draw": gutshot,
    }


def hero_hand_summary(hole_cards: Tuple[str, str], board_cards: Sequence[str]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {"hole": hole_card_features(hole_cards)}
    if len(board_cards) + 2 >= 5:
        try:
            cards = [card_from_str(c) for c in list(hole_cards) + list(board_cards)]
            rank = best_hand_rank(cards)
            summary["best_hand"] = {"category": rank[0], "description": describe_rank(rank)}
        except Exception:
            pass
    summary["draws"] = draw_features(hole_cards, board_cards)
    return summary


def action_history_summary(state: DecisionState) -> Dict[str, Any]:
    hero = state.hero_seat_id
    last = state.action_history[-1] if state.action_history else None
    last_raise = None
    preflop_raiser = None
    raises_this_street = 0
    hero_raises_this_street = 0

    for entry in state.action_history:
        if not isinstance(entry, Mapping):
            continue
        action = entry.get("action")
        street = entry.get("street")
        seat_id = entry.get("seat_id")
        if action == "raise_to":
            last_raise = {
                "seat_id": seat_id,
                "street": street,
                "amount": entry.get("amount"),
            }
            if street == "preflop":
                preflop_raiser = seat_id
            if street == state.street:
                raises_this_street += 1
                if hero is not None and seat_id == hero:
                    hero_raises_this_street += 1

    return {
        "last_action": dict(last) if isinstance(last, Mapping) else None,
        "last_raise": last_raise,
        "preflop_last_raiser_seat": preflop_raiser,
        "raises_this_street": raises_this_street,
        "hero_raises_this_street": hero_raises_this_street,
    }


def derived_metrics(state: DecisionState) -> Dict[str, Any]:
    pot = float(max(state.pot_size, 0))
    to_call = float(max(state.to_call, 0))

    hero_stack = float(state.hero_stack) if state.hero_stack is not None else None
    hero_stack_after_call = (hero_stack - to_call) if (hero_stack is not None) else None
    pot_after_call = pot + to_call

    spr = _safe_float(hero_stack, max(pot, 1.0)) if hero_stack is not None else None
    spr_after_call = _safe_float(hero_stack_after_call, max(pot_after_call, 1.0)) if hero_stack_after_call is not None else None

    stacks = dict(state.stacks) if isinstance(state.stacks, Mapping) else {}
    opp_stacks = [v for k, v in stacks.items() if state.hero_seat_id is None or int(k) != int(state.hero_seat_id)]
    eff_stack = None
    if hero_stack is not None and opp_stacks:
        try:
            eff_stack = float(min(hero_stack, float(min(opp_stacks))))
        except Exception:
            eff_stack = hero_stack

    return {
        "bb": state.bb,
        "sb": state.sb,
        "seat_count": state.seat_count,
        "button_seat": state.button_seat,
        "effective_stack": eff_stack,
        "spr": spr,
        "spr_after_call": spr_after_call,
        "to_call_ratio_pot": _safe_float(to_call, max(pot, 1.0)),
        "to_call_ratio_stack": _safe_float(to_call, hero_stack) if hero_stack is not None else None,
        "pot_after_call": pot_after_call,
        "hero_stack_after_call": hero_stack_after_call,
        "board_texture": board_texture(state.board_cards),
        "hero_hand": hero_hand_summary(state.hero_hole_cards, state.board_cards),
        "action_history_summary": action_history_summary(state),
        "legal_sizing": {
            "raise_sizes_to_pot": [
                _safe_float(float(x), max(pot, 1.0)) for x in list(state.legal.raise_sizes)
            ],
            "call_amount_to_pot": _safe_float(float(state.legal.call_amount), max(pot, 1.0)),
        },
    }
