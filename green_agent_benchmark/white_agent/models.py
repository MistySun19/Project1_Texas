from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


Street = str


@dataclass(frozen=True, slots=True)
class OpponentProfile:
    vpip: Optional[float] = None
    pfr: Optional[float] = None
    range_bucket: str = "medium"  # tight|medium|loose
    aggressive: bool = False


@dataclass(frozen=True, slots=True)
class LegalActions:
    actions: Tuple[str, ...]  # fold|check|call|raise_to
    call_amount: int
    min_raise_to: int
    max_raise_to: int
    raise_sizes: Tuple[int, ...]  # raise_to targets, incl all-in if legal

    def allows(self, action: str) -> bool:
        return action in self.actions


@dataclass(frozen=True, slots=True)
class DecisionState:
    hand_id: str
    bb: int
    sb: int
    seat_count: Optional[int]
    button_seat: Optional[int]
    street: Street
    hero_seat_id: Optional[int]
    hero_hole_cards: Tuple[str, str]
    board_cards: Tuple[str, ...]
    pot_size: int
    to_call: int
    hero_stack: Optional[int]
    stacks: Mapping[int, int]
    position: Optional[str]
    players_remaining: Optional[int]
    action_history: Tuple[Mapping[str, Any], ...]
    opponents_stats: Mapping[str, Mapping[str, Any]]
    rng_tag: str
    legal: LegalActions


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _derive_street(board: Sequence[str]) -> Street:
    n = len(board)
    if n == 0:
        return "preflop"
    if n == 3:
        return "flop"
    if n == 4:
        return "turn"
    if n == 5:
        return "river"
    return "unknown"


def normalize_state(payload: Mapping[str, Any]) -> Tuple[DecisionState, Dict[str, Any]]:
    """
    Normalize a heterogeneous request payload into the fields needed by the white agent.

    Supported payload shapes:
    - Benchmark engine ActionRequest JSON (fields like `legal_actions`, `min_raise_to`, `board`).
    - AgentBeats A2A request (fields like `valid_actions`, `min_raise`, `max_raise`, `community_cards`).
    - Custom state JSON (fields like `hero_hole_cards`, `board_cards`, `pot_size`).
    """
    warnings: Dict[str, Any] = {}

    hole = payload.get("hero_hole_cards") or payload.get("hole_cards") or payload.get("cards") or []
    if not isinstance(hole, (list, tuple)) or len(hole) < 2:
        warnings["missing_hole_cards"] = True
        hole_cards = ("As", "Ad")
    else:
        hole_cards = (str(hole[0]), str(hole[1]))

    board = payload.get("board_cards") or payload.get("community_cards") or payload.get("board") or []
    if not isinstance(board, (list, tuple)):
        board_cards: Tuple[str, ...] = ()
        warnings["invalid_board_cards"] = True
    else:
        board_cards = tuple(str(c) for c in board)

    street = payload.get("street")
    if not isinstance(street, str) or not street:
        street = _derive_street(board_cards)

    pot_size = _safe_int(payload.get("pot_size", payload.get("pot", 0)), 0)
    to_call = _safe_int(payload.get("to_call", payload.get("call_amount", 0)), 0)

    hand_id = str(payload.get("hand_id", payload.get("rng_tag", "")) or "")

    blinds = payload.get("blinds") if isinstance(payload.get("blinds"), dict) else {}
    bb = _safe_int(blinds.get("bb", 0), 0)
    sb = _safe_int(blinds.get("sb", 0), 0)

    seat_count = payload.get("seat_count")
    seat_count_int = _safe_int(seat_count, 0) if seat_count is not None else None
    if seat_count_int is not None and seat_count_int <= 0:
        seat_count_int = None

    button_seat = payload.get("button_seat")
    button_seat_int = _safe_int(button_seat, 0) if button_seat is not None else None

    stacks_payload = payload.get("stacks")
    stacks: Dict[int, int] = {}
    if isinstance(stacks_payload, dict):
        for k, v in stacks_payload.items():
            try:
                stacks[int(k)] = _safe_int(v, 0)
            except Exception:
                continue

    hero_stack = payload.get("hero_stack")
    if hero_stack is None:
        seat_id_raw = payload.get("seat_id", payload.get("hero_seat_id"))
        if seat_id_raw is not None:
            try:
                hero_stack = stacks.get(int(seat_id_raw))
            except Exception:
                hero_stack = None
    hero_stack_int = _safe_int(hero_stack, 0) if hero_stack is not None else None

    min_raise_to = payload.get("min_raise_to", payload.get("min_raise"))
    min_raise_to_int = _safe_int(min_raise_to, 0)

    max_raise_to = payload.get("max_raise_to", payload.get("max_raise"))
    max_raise_to_int = _safe_int(max_raise_to, 0)

    if max_raise_to_int <= 0 and hero_stack_int is not None:
        # Best-effort cap when the protocol doesn't provide one.
        max_raise_to_int = hero_stack_int + max(to_call, 0) + (bb or 0)

    legal_actions = payload.get("legal_actions") or payload.get("valid_actions") or payload.get("legal") or []
    if isinstance(legal_actions, str):
        legal_actions = [legal_actions]
    if not isinstance(legal_actions, (list, tuple)):
        legal_actions = []
        warnings["missing_legal_actions"] = True

    normalized_actions: List[str] = []
    for item in legal_actions:
        if not item:
            continue
        token = str(item)
        if token == "raise":
            token = "raise_to"
        if token in ("fold", "check", "call", "raise_to") and token not in normalized_actions:
            normalized_actions.append(token)

    if not normalized_actions:
        warnings["derived_legal_actions"] = True
        normalized_actions = ["fold"]
        if to_call == 0:
            normalized_actions.append("check")
        else:
            normalized_actions.append("call")
        if hero_stack_int is None or hero_stack_int > to_call:
            normalized_actions.append("raise_to")

    if "raise_to" in normalized_actions and (min_raise_to_int <= 0):
        min_raise_to_int = max(1, (bb or 1) * 2)
        warnings["derived_min_raise_to"] = True

    if "raise_to" in normalized_actions and (max_raise_to_int <= 0 or max_raise_to_int < min_raise_to_int):
        normalized_actions = [a for a in normalized_actions if a != "raise_to"]
        warnings["disabled_raise_to"] = True
        max_raise_to_int = 0

    call_amount = max(to_call, 0)

    raise_sizes: Tuple[int, ...] = ()
    if "raise_to" in normalized_actions:
        candidates = [
            min_raise_to_int,
            min_raise_to_int + int(0.5 * pot_size),
            min_raise_to_int + int(1.0 * pot_size),
            min_raise_to_int + int(2.0 * pot_size),
            max_raise_to_int,
        ]
        clamped: List[int] = []
        for amt in candidates:
            amt_int = int(amt)
            if amt_int < min_raise_to_int:
                amt_int = min_raise_to_int
            if amt_int > max_raise_to_int:
                amt_int = max_raise_to_int
            if amt_int not in clamped:
                clamped.append(amt_int)
        raise_sizes = tuple(sorted(a for a in clamped if a >= min_raise_to_int and a > 0))
        if not raise_sizes:
            normalized_actions = [a for a in normalized_actions if a != "raise_to"]
            warnings["disabled_raise_to_no_sizes"] = True

    seat_id = payload.get("seat_id", payload.get("hero_seat_id"))
    hero_seat_id = _safe_int(seat_id, 0) if seat_id is not None else None

    position = payload.get("position")
    if position is not None and not isinstance(position, str):
        position = None

    players_remaining = payload.get("players_remaining")
    players_remaining_int = _safe_int(players_remaining, 0) if players_remaining is not None else None
    if players_remaining_int is not None and players_remaining_int <= 0:
        players_remaining_int = None

    action_history = payload.get("action_history", payload.get("history", []))
    if isinstance(action_history, list):
        action_history_tuple = tuple(
            entry if isinstance(entry, dict) else {"raw": entry} for entry in action_history[-30:]
        )
    else:
        action_history_tuple = tuple()

    opponents_stats = payload.get("opponents_stats") or payload.get("opponent_stats") or {}
    if not isinstance(opponents_stats, dict):
        opponents_stats = {}

    rng_tag = str(payload.get("rng_tag", payload.get("hand_id", "")) or "")

    legal = LegalActions(
        actions=tuple(normalized_actions),
        call_amount=call_amount,
        min_raise_to=min_raise_to_int,
        max_raise_to=max_raise_to_int,
        raise_sizes=raise_sizes,
    )

    state = DecisionState(
        hand_id=hand_id,
        bb=bb,
        sb=sb,
        seat_count=seat_count_int,
        button_seat=button_seat_int,
        street=street,
        hero_seat_id=hero_seat_id,
        hero_hole_cards=hole_cards,
        board_cards=board_cards,
        pot_size=pot_size,
        to_call=to_call,
        hero_stack=hero_stack_int,
        stacks=stacks,
        position=position,
        players_remaining=players_remaining_int,
        action_history=action_history_tuple,
        opponents_stats=opponents_stats,
        rng_tag=rng_tag,
        legal=legal,
    )
    return state, warnings
