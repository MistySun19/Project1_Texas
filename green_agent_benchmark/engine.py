"""
No-Limit Texas Hold'em state machine used by the Green Agent Benchmark.
"""

from __future__ import annotations

import enum
import math
import random
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Iterator, List, Optional, Sequence, Tuple

from .cards import Card, best_hand_rank, new_deck
from .logging_utils import NDJSONLogger
from .schemas import ActionHistoryEntry, ActionRequest, ActionResponse

STREETS = ("preflop", "flop", "turn", "river")


class HandState(enum.Enum):
    INIT = enum.auto()
    POST_BLINDS = enum.auto()
    DEAL_HOLE = enum.auto()
    PRE_FLOP = enum.auto()
    DEAL_FLOP = enum.auto()
    FLOP = enum.auto()
    DEAL_TURN = enum.auto()
    TURN = enum.auto()
    DEAL_RIVER = enum.auto()
    RIVER = enum.auto()
    SHOWDOWN = enum.auto()
    AWARD_POTS = enum.auto()
    CLEANUP = enum.auto()


@dataclass(slots=True)
class EngineConfig:
    seat_count: int
    small_blind: int
    big_blind: int
    starting_stack: int
    table_id: str
    time_per_decision_ms: int = 60000
    auto_top_up: bool = True
    ante: int = 0
    straddle: bool = False
    runout_when_all_in: bool = True
    odd_chips_rule: str = "button_left"
    timeout_fallback_policy: str = "check_if_zero_else_fold"
    illegal_action_fallback_policy: str = "check_if_zero_else_fold"


@dataclass(slots=True)
class PlayerRuntimeState:
    seat_id: int
    name: str
    stack: int
    hole_cards: List[Card] = field(default_factory=list)
    bet: int = 0
    folded: bool = False
    all_in: bool = False
    illegal_actions: int = 0
    timeouts: int = 0
    sitting_out: bool = False

    def reset_for_hand(self, starting_stack: int) -> None:
        self.stack = starting_stack
        self.bet = 0
        self.folded = False
        self.all_in = False
        self.hole_cards = []
        self.sitting_out = False


@dataclass(slots=True)
class BettingRoundResult:
    last_aggressor: Optional[int]
    aggression_occurred: bool
    everyone_all_in: bool


@dataclass(slots=True)
class Pot:
    size: int
    eligible_seats: List[int]


class IllegalActionError(RuntimeError):
    pass


class AgentInterface:
    """
    Adapter around an agent implementation.

    The agent must expose `name`, `reset(seat_id, table_config)` and
    `act(ActionRequest) -> ActionResponse`.
    """

    def __init__(self, agent, seat_id: int) -> None:
        self._agent = agent
        self.seat_id = seat_id

    @property
    def name(self) -> str:
        return getattr(self._agent, "name", self._agent.__class__.__name__)

    def reset(self, table_config: Dict[str, int]) -> None:
        reset = getattr(self._agent, "reset", None)
        if callable(reset):
            reset(self.seat_id, table_config)

    def act(self, request: ActionRequest) -> ActionResponse:
        response = self._agent.act(request)
        if not isinstance(response, ActionResponse):
            raise TypeError(f"{self.name} returned invalid response {response!r}")
        return response


def seat_after(seat: int, seat_count: int) -> int:
    return (seat + 1) % seat_count


def compute_order(street: str, seat_count: int, button_seat: int) -> List[int]:
    small_blind_seat = seat_after(button_seat, seat_count)
    big_blind_seat = seat_after(small_blind_seat, seat_count)
    if street == "preflop":
        if seat_count == 2:
            first = button_seat
        else:
            first = seat_after(big_blind_seat, seat_count)
    else:
        first = seat_after(button_seat, seat_count)
    order = []
    seat = first
    for _ in range(seat_count):
        order.append(seat)
        seat = seat_after(seat, seat_count)
    return order


def generate_hand_id(seed: int, hand_index: int, replica_id: int) -> str:
    return f"{seed}-{hand_index}-{replica_id}"


class HoldemEngine:
    """
    Deterministic heads-up / 6-max engine that follows the v1.0 NLHE spec.
    """

    def __init__(self, config: EngineConfig, logger: NDJSONLogger) -> None:
        self.config = config
        self.logger = logger

    def play_hand(
        self,
        seed: int,
        hand_index: int,
        replica_id: int,
        button_seat: int,
        players: Dict[int, PlayerRuntimeState],
        agents: Dict[int, AgentInterface],
        deck: Sequence[Card],
    ) -> Dict[int, int]:
        if self.config.straddle:
            raise NotImplementedError("Straddle support is not implemented in the reference engine.")

        rng_tag = f"{seed}:{hand_index}:{replica_id}"
        hand_id = generate_hand_id(seed, hand_index, replica_id)

        for player in players.values():
            starting_stack = self.config.starting_stack if self.config.auto_top_up else player.stack
            player.reset_for_hand(starting_stack)

        for agent in agents.values():
            agent.reset(
                {
                    "seat_count": self.config.seat_count,
                    "small_blind": self.config.small_blind,
                    "big_blind": self.config.big_blind,
                    "starting_stack": self.config.starting_stack,
                    "seat_id": agent.seat_id,
                    "seat_names": {
                        seat: players[seat].name for seat in players
                    },
                }
            )

        self.logger.log(
            "hand_start",
            {
                "table_id": self.config.table_id,
                "hand_id": hand_id,
                "seed": seed,
                "hand_index": hand_index,
                "replica_id": replica_id,
                "button_seat": button_seat,
                "blinds": {
                    "sb": self.config.small_blind,
                    "bb": self.config.big_blind,
                },
                "seats": {
                    seat_id: {
                        "name": players[seat_id].name,
                        "stack": players[seat_id].stack,
                    }
                    for seat_id in range(self.config.seat_count)
                    if seat_id in players
                },
                "rng_tag": rng_tag,
            },
        )

        contributions: Dict[int, int] = {seat: 0 for seat in players}
        pot = 0
        board_cards: List[Card] = []
        action_history: List[ActionHistoryEntry] = []

        deck_iter = iter(deck)
        self._deal_hole_cards(hand_id, button_seat, players, deck_iter)

        if self.config.ante > 0:
            for offset in range(self.config.seat_count):
                seat = (button_seat + offset) % self.config.seat_count
                player = players.get(seat)
                if not player or player.sitting_out:
                    continue
                pot += self._post_ante(player, self.config.ante, contributions)

        sb_seat, bb_seat = self._blind_seats(button_seat)
        if sb_seat in players and not players[sb_seat].sitting_out:
            pot += self._post_blind(players[sb_seat], self.config.small_blind, contributions, "small")
        if bb_seat in players and not players[bb_seat].sitting_out:
            pot += self._post_blind(players[bb_seat], self.config.big_blind, contributions, "big")

        current_bet = max((p.bet for p in players.values()), default=0)
        last_full_raise = self.config.big_blind

        round_result, current_bet, last_full_raise, pot = self._betting_round(
            street="preflop",
            hand_id=hand_id,
            button_seat=button_seat,
            players=players,
            agents=agents,
            contributions=contributions,
            action_history=action_history,
            board_cards=board_cards,
            rng_tag=rng_tag,
            current_bet=current_bet,
            last_full_raise=last_full_raise,
            pot=pot,
        )
        showdown_last_aggressor: Optional[int] = (
            round_result.last_aggressor if round_result.aggression_occurred else None
        )

        if self._players_remaining(players) == 1:
            winner = self._remaining_seat(players)
            payouts = {winner: sum(contributions.values())}
            self._announce_showdown(hand_id, board_cards, payouts, contributions, players)
            return self._apply_payouts(players, contributions, payouts)

        auto_runout = round_result.everyone_all_in and self.config.runout_when_all_in

        for street in ("flop", "turn", "river"):
            if auto_runout:
                break
            self._deal_board(street, hand_id, board_cards, deck_iter)
            self._reset_bets(players)
            current_bet = 0
            last_full_raise = 0
            round_result, current_bet, last_full_raise, pot = self._betting_round(
                street=street,
                hand_id=hand_id,
                button_seat=button_seat,
                players=players,
                agents=agents,
                contributions=contributions,
                action_history=action_history,
                board_cards=board_cards,
                rng_tag=rng_tag,
                current_bet=current_bet,
                last_full_raise=last_full_raise,
                pot=pot,
            )
            showdown_last_aggressor = round_result.last_aggressor if round_result.aggression_occurred else None

            if self._players_remaining(players) == 1:
                winner = self._remaining_seat(players)
                payouts = {winner: sum(contributions.values())}
                self._announce_showdown(hand_id, board_cards, payouts, contributions, players)
                return self._apply_payouts(players, contributions, payouts)

            if round_result.everyone_all_in and self.config.runout_when_all_in:
                auto_runout = True
                break

        if auto_runout:
            self._run_out_board(hand_id, board_cards, deck_iter)

        survivors = self._players_remaining(players)
        if len(survivors) == 1:
            winner = survivors[0]
            payouts = {winner: sum(contributions.values())}
            self._announce_showdown(hand_id, board_cards, payouts, contributions, players)
            return self._apply_payouts(players, contributions, payouts)

        payouts = self._resolve_showdown(players, board_cards, contributions, button_seat)
        self._announce_showdown(hand_id, board_cards, payouts, contributions, players, showdown_last_aggressor)
        return self._apply_payouts(players, contributions, payouts)

    def _deal_hole_cards(
        self,
        hand_id: str,
        button_seat: int,
        players: Dict[int, PlayerRuntimeState],
        deck_iter: Iterator[Card],
    ) -> None:
        for _ in range(2):
            for offset in range(self.config.seat_count):
                seat = (button_seat + 1 + offset) % self.config.seat_count
                player = players.get(seat)
                if player is None or player.sitting_out:
                    continue
                player.hole_cards.append(next(deck_iter))

        for seat, player in players.items():
            if player.sitting_out:
                continue
            self.logger.log(
                "deal_hole",
                {
                    "hand_id": hand_id,
                    "seat": seat,
                    "cards": [str(card) for card in player.hole_cards],
                },
            )

    def _blind_seats(self, button_seat: int) -> Tuple[int, int]:
        if self.config.seat_count == 2:
            small_blind = button_seat
            big_blind = seat_after(small_blind, self.config.seat_count)
            return small_blind, big_blind
        small_blind = seat_after(button_seat, self.config.seat_count)
        big_blind = seat_after(small_blind, self.config.seat_count)
        return small_blind, big_blind

    def _post_blind(
        self,
        player: PlayerRuntimeState,
        amount: int,
        contributions: Dict[int, int],
        blind_type: str,
    ) -> int:
        posted = min(amount, player.stack)
        if posted == 0:
            player.all_in = True
            return 0
        player.stack -= posted
        player.bet += posted
        contributions[player.seat_id] += posted
        if player.stack == 0:
            player.all_in = True
        self.logger.log(
            "blind",
            {
                "seat": player.seat_id,
                "amount": posted,
                "type": blind_type,
            },
        )
        return posted

    def _post_ante(
        self,
        player: PlayerRuntimeState,
        amount: int,
        contributions: Dict[int, int],
    ) -> int:
        posted = min(amount, player.stack)
        if posted == 0:
            player.all_in = True
            return 0
        player.stack -= posted
        contributions[player.seat_id] += posted
        if player.stack == 0:
            player.all_in = True
        self.logger.log(
            "ante",
            {
                "seat": player.seat_id,
                "amount": posted,
            },
        )
        return posted

    def _deal_board(
        self,
        street: str,
        hand_id: str,
        board_cards: List[Card],
        deck_iter: Iterator[Card],
    ) -> None:
        next(deck_iter)  # burn card
        if street == "flop":
            cards = [next(deck_iter) for _ in range(3)]
        else:
            cards = [next(deck_iter)]
        board_cards.extend(cards)
        self.logger.log(
            "street_transition",
            {
                "hand_id": hand_id,
                "street": street,
                "board": [str(card) for card in board_cards],
            },
        )

    def _run_out_board(self, hand_id: str, board_cards: List[Card], deck_iter: Iterator[Card]) -> None:
        while len(board_cards) < 5:
            if len(board_cards) == 0:
                self._deal_board("flop", hand_id, board_cards, deck_iter)
            elif len(board_cards) == 3:
                self._deal_board("turn", hand_id, board_cards, deck_iter)
            elif len(board_cards) == 4:
                self._deal_board("river", hand_id, board_cards, deck_iter)

    def _betting_round(
        self,
        *,
        street: str,
        hand_id: str,
        button_seat: int,
        players: Dict[int, PlayerRuntimeState],
        agents: Dict[int, AgentInterface],
        contributions: Dict[int, int],
        action_history: List[ActionHistoryEntry],
        board_cards: Sequence[Card],
        rng_tag: str,
        current_bet: int,
        last_full_raise: int,
        pot: int,
    ) -> Tuple[BettingRoundResult, int, int, int]:
        if self._all_non_folded_all_in(players):
            return BettingRoundResult(None, False, True), current_bet, last_full_raise, pot

        order = compute_order(street, self.config.seat_count, button_seat)
        active_order = self._active_order(order, players)
        if not active_order:
            everyone_all_in = self._all_non_folded_all_in(players)
            return BettingRoundResult(None, False, everyone_all_in), current_bet, last_full_raise, pot

        acted: Dict[int, bool] = {seat: False for seat in active_order}
        queue: Deque[int] = deque(active_order)
        last_aggressor: Optional[int] = None
        aggression_occurred = False

        while queue:
            seat = queue.popleft()
            player = players[seat]

            if player.folded or player.all_in:
                active_order = self._active_order(order, players)
                acted = {s: acted.get(s, False) for s in active_order}
                continue

            to_call = current_bet - player.bet
            need_action = to_call > 0 or not acted.get(seat, False)
            if not need_action:
                if not queue:
                    active_order = self._active_order(order, players)
                    remaining = [
                        s for s in active_order if (current_bet - players[s].bet) > 0 or not acted.get(s, False)
                    ]
                    if remaining:
                        queue = deque(remaining)
                    else:
                        if self._betting_round_complete(current_bet, players):
                            break
                        queue = deque(active_order)
                continue

            min_raise_to = self._min_raise_target(current_bet, last_full_raise)
            allow_raise = not acted.get(seat, False)
            legal_actions = self._legal_actions(player, to_call, min_raise_to, allow_raise)

            request = ActionRequest(
                seat_count=self.config.seat_count,
                table_id=self.config.table_id,
                hand_id=hand_id,
                seat_id=seat,
                button_seat=button_seat,
                blinds={"sb": self.config.small_blind, "bb": self.config.big_blind},
                stacks={s: players[s].stack for s in players},
                pot=pot,
                to_call=to_call,
                min_raise_to=min_raise_to,
                hole_cards=[str(c) for c in player.hole_cards],
                board=[str(c) for c in board_cards],
                action_history=list(action_history),
                legal_actions=list(legal_actions),
                timebank_ms=self.config.time_per_decision_ms,
                rng_tag=rng_tag,
            )

            response, elapsed_ms = self._invoke_agent(agents[seat], request)

            if elapsed_ms > self.config.time_per_decision_ms:
                player.timeouts += 1
                fallback = self._timeout_fallback(to_call, legal_actions)
                self.logger.log(
                    "penalty",
                    {
                        "hand_id": hand_id,
                        "seat": seat,
                        "kind": "timeout",
                        "elapsed_ms": math.ceil(elapsed_ms),
                        "fallback": fallback.action,
                    },
                )
                response = fallback
                elapsed_ms = self.config.time_per_decision_ms

            response, penalty_payload = self._normalize_action(
                hand_id=hand_id,
                seat=seat,
                player=player,
                response=response,
                legal_actions=legal_actions,
                to_call=to_call,
                min_raise_to=min_raise_to,
                current_bet=current_bet,
                last_full_raise=last_full_raise,
            )
            if penalty_payload is not None:
                player.illegal_actions += 1
                self.logger.log("penalty", penalty_payload)

            elapsed_ms_int = math.ceil(max(elapsed_ms, 0.0))

            if response.action == "fold":
                self._apply_fold(player)
                active_order = self._active_order(order, players)
                acted = {s: acted.get(s, False) for s in active_order}
                queue = deque(active_order)
                pot_delta = 0
            elif response.action == "check":
                self._apply_check(player, to_call)
                acted[seat] = True
                pot_delta = 0
            elif response.action == "call":
                added = self._apply_call(player, to_call, contributions)
                pot += added
                pot_delta = added
                acted[seat] = True
            elif response.action == "raise_to":
                added, current_bet, last_full_raise, is_full_raise = self._apply_raise_to(
                    player=player,
                    desired=response.amount,
                    to_call=to_call,
                    min_raise_to=min_raise_to,
                    current_bet=current_bet,
                    last_full_raise=last_full_raise,
                    contributions=contributions,
                )
                pot += added
                pot_delta = added
                acted[seat] = True
                aggression_occurred = True
                last_aggressor = seat

                active_order = self._active_order(order, players)
                if is_full_raise and not player.all_in:
                    acted = {s: (s == seat) for s in active_order}
                else:
                    acted = {s: (s == seat) or acted.get(s, False) for s in active_order}
                queue = deque(self._rotation_after(active_order, seat))
            else:
                raise IllegalActionError(f"Unsupported action {response.action!r}")

            action_history.append(
                ActionHistoryEntry(
                    seat_id=seat,
                    action=response.action,
                    amount=response.amount,
                    street=street,
                    to_call=to_call,
                    min_raise_to=min_raise_to,
                )
            )
            self.logger.log(
                "action",
                {
                    "hand_id": hand_id,
                    "seat": seat,
                    "action": response.action,
                    "amount": response.amount,
                    "to_call": to_call,
                    "min_raise_to": min_raise_to,
                    "elapsed_ms": elapsed_ms_int,
                    "stack_after": player.stack,
                    "bet": player.bet,
                    "street": street,
                    "pot_delta": pot_delta,
                    "pot": pot,
                },
            )

            if self._all_non_folded_all_in(players):
                return BettingRoundResult(last_aggressor, aggression_occurred, True), current_bet, last_full_raise, pot

            if self._betting_round_complete(current_bet, players) and not queue:
                break

            if not queue:
                active_order = self._active_order(order, players)
                remaining = [
                    s for s in active_order if (current_bet - players[s].bet) > 0 or not acted.get(s, False)
                ]
                if remaining:
                    queue = deque(remaining)
                else:
                    if self._betting_round_complete(current_bet, players):
                        break
                    queue = deque(active_order)

        everyone_all_in = self._all_non_folded_all_in(players)
        return BettingRoundResult(last_aggressor, aggression_occurred, everyone_all_in), current_bet, last_full_raise, pot

    def _invoke_agent(self, agent: AgentInterface, request: ActionRequest) -> Tuple[ActionResponse, float]:
        start = time.perf_counter()
        response = agent.act(request)
        wait_time_ms = getattr(response, "wait_time_ms", 0)
        if wait_time_ms > 0:
            print(f"[Engine] Agent {agent.name} wait_time_ms={wait_time_ms}")
        elapsed_ms = (time.perf_counter() - start) * 1000 - wait_time_ms
        return response, elapsed_ms

    def _normalize_action(
        self,
        *,
        hand_id: str,
        seat: int,
        player: PlayerRuntimeState,
        response: ActionResponse,
        legal_actions: Sequence[str],
        to_call: int,
        min_raise_to: int,
        current_bet: int,
        last_full_raise: int,
    ) -> Tuple[ActionResponse, Optional[Dict[str, object]]]:
        if response.action not in legal_actions:
            fallback = self._illegal_fallback(to_call, legal_actions)
            payload = {
                "hand_id": hand_id,
                "seat": seat,
                "kind": "illegal_action",
                "attempted": {"action": response.action, "amount": response.amount},
                "fallback": fallback.action,
            }
            return fallback, payload

        if response.action != "raise_to":
            return response, None

        desired = response.amount
        if desired is None or not isinstance(desired, int):
            fallback = self._illegal_fallback(to_call, legal_actions)
            payload = {
                "hand_id": hand_id,
                "seat": seat,
                "kind": "illegal_action",
                "attempted": {"action": response.action, "amount": response.amount},
                "fallback": fallback.action,
            }
            return fallback, payload

        call_total = player.bet + to_call
        max_total = player.bet + player.stack

        if max_total <= call_total or desired <= call_total:
            fallback = self._illegal_fallback(to_call, legal_actions)
            payload = {
                "hand_id": hand_id,
                "seat": seat,
                "kind": "illegal_action",
                "attempted": {"action": response.action, "amount": response.amount},
                "fallback": fallback.action,
            }
            return fallback, payload

        min_raise_target = self._min_raise_target(current_bet, last_full_raise)
        if max_total >= min_raise_target and desired < min_raise_target:
            fallback = self._illegal_fallback(to_call, legal_actions)
            payload = {
                "hand_id": hand_id,
                "seat": seat,
                "kind": "illegal_action",
                "attempted": {"action": response.action, "amount": response.amount},
                "fallback": fallback.action,
            }
            return fallback, payload

        if max_total < min_raise_target and desired != max_total:
            fallback = self._illegal_fallback(to_call, legal_actions)
            payload = {
                "hand_id": hand_id,
                "seat": seat,
                "kind": "illegal_action",
                "attempted": {"action": response.action, "amount": response.amount},
                "fallback": fallback.action,
            }
            return fallback, payload

        desired = min(desired, max_total)
        return ActionResponse(action="raise_to", amount=desired), None

    def _apply_fold(self, player: PlayerRuntimeState) -> None:
        player.folded = True

    def _apply_check(self, player: PlayerRuntimeState, to_call: int) -> None:
        if to_call != 0:
            raise IllegalActionError("cannot check facing a bet")

    def _apply_call(self, player: PlayerRuntimeState, to_call: int, contributions: Dict[int, int]) -> int:
        amount = min(to_call, player.stack)
        player.stack -= amount
        player.bet += amount
        contributions[player.seat_id] += amount
        if player.stack == 0:
            player.all_in = True
        return amount

    def _apply_raise_to(
        self,
        *,
        player: PlayerRuntimeState,
        desired: Optional[int],
        to_call: int,
        min_raise_to: int,
        current_bet: int,
        last_full_raise: int,
        contributions: Dict[int, int],
    ) -> Tuple[int, int, int, bool]:
        if desired is None:
            raise IllegalActionError("raise_to requires an amount")

        call_total = player.bet + to_call
        max_total = player.bet + player.stack
        if desired > max_total:
            desired = max_total

        added = desired - player.bet
        player.stack -= added
        player.bet = desired
        contributions[player.seat_id] += added
        if player.stack == 0:
            player.all_in = True

        is_full_raise = False
        new_last_full_raise = last_full_raise

        if current_bet == 0:
            if desired >= self.config.big_blind:
                is_full_raise = True
                new_last_full_raise = desired
            current_bet = desired
        else:
            if desired > current_bet and desired >= current_bet + last_full_raise:
                is_full_raise = True
                new_last_full_raise = desired - current_bet
            current_bet = max(current_bet, desired)

        return added, current_bet, new_last_full_raise, is_full_raise

    def _min_raise_target(self, current_bet: int, last_full_raise: int) -> int:
        if current_bet == 0:
            return max(self.config.big_blind, 1)
        raise_increment = max(last_full_raise, self.config.big_blind)
        return current_bet + raise_increment

    def _legal_actions(
        self,
        player: PlayerRuntimeState,
        to_call: int,
        min_raise_to: int,
        may_raise: bool,
    ) -> List[str]:
        legal: List[str] = ["fold"]
        if to_call == 0:
            legal.append("check")
        else:
            if player.stack > 0:
                legal.append("call")
        max_total = player.bet + player.stack
        if may_raise and player.stack > 0 and max_total > player.bet + to_call:
            legal.append("raise_to")
        return legal

    def _timeout_fallback(self, to_call: int, legal_actions: Sequence[str]) -> ActionResponse:
        policy = self.config.timeout_fallback_policy
        if policy == "fold":
            if "fold" in legal_actions:
                return ActionResponse(action="fold")
        if to_call == 0 and "check" in legal_actions:
            return ActionResponse(action="check")
        if "fold" in legal_actions:
            return ActionResponse(action="fold")
        if "call" in legal_actions:
            return ActionResponse(action="call")
        return ActionResponse(action=legal_actions[0])

    def _illegal_fallback(self, to_call: int, legal_actions: Sequence[str]) -> ActionResponse:
        policy = self.config.illegal_action_fallback_policy
        if policy == "fold":
            if "fold" in legal_actions:
                return ActionResponse(action="fold")
        if to_call == 0 and "check" in legal_actions:
            return ActionResponse(action="check")
        if "fold" in legal_actions:
            return ActionResponse(action="fold")
        if "call" in legal_actions:
            return ActionResponse(action="call")
        return ActionResponse(action=legal_actions[0])

    def _reset_bets(self, players: Dict[int, PlayerRuntimeState]) -> None:
        for player in players.values():
            player.bet = 0

    def _players_remaining(self, players: Dict[int, PlayerRuntimeState]) -> List[int]:
        return [seat for seat, player in players.items() if not player.folded]

    def _remaining_seat(self, players: Dict[int, PlayerRuntimeState]) -> int:
        for seat, player in players.items():
            if not player.folded:
                return seat
        raise RuntimeError("no remaining players")

    def _all_non_folded_all_in(self, players: Dict[int, PlayerRuntimeState]) -> bool:
        active = [p for p in players.values() if not p.folded]
        return bool(active) and all(p.all_in for p in active)

    def _active_order(self, order: Sequence[int], players: Dict[int, PlayerRuntimeState]) -> List[int]:
        return [
            seat
            for seat in order
            if seat in players and not players[seat].folded and not players[seat].all_in and not players[seat].sitting_out
        ]

    def _rotation_after(self, order: Sequence[int], seat: int) -> List[int]:
        if seat not in order:
            return list(order)
        idx = order.index(seat)
        return list(order[idx + 1 :]) + list(order[:idx])

    def _betting_round_complete(self, current_bet: int, players: Dict[int, PlayerRuntimeState]) -> bool:
        contenders = [p for p in players.values() if not p.folded and not p.all_in]
        if len(contenders) <= 1:
            return True
        return all(p.bet == current_bet for p in contenders)

    def _build_side_pots(
        self,
        players: Dict[int, PlayerRuntimeState],
        contributions: Dict[int, int],
    ) -> List[Pot]:
        levels = sorted({amount for amount in contributions.values() if amount > 0})
        pots: List[Pot] = []
        previous = 0
        for amount in levels:
            contributors = [seat for seat, total in contributions.items() if total >= amount]
            size = (amount - previous) * len(contributors)
            eligible = [seat for seat in contributors if not players[seat].folded]
            pots.append(Pot(size=size, eligible_seats=eligible))
            previous = amount
        return pots

    def _resolve_showdown(
        self,
        players: Dict[int, PlayerRuntimeState],
        board_cards: Sequence[Card],
        contributions: Dict[int, int],
        button_seat: int,
    ) -> Dict[int, int]:
        pots = self._build_side_pots(players, contributions)
        payouts: Dict[int, int] = {seat: 0 for seat in players}
        active_seats = [seat for seat, player in players.items() if not player.folded]
        hand_ranks = {
            seat: best_hand_rank(players[seat].hole_cards + list(board_cards))
            for seat in active_seats
        }

        odd_chip_order = self._odd_chip_distribution_order(button_seat)

        for pot in pots:
            if not pot.eligible_seats:
                continue
            best_rank = max(hand_ranks[seat] for seat in pot.eligible_seats)
            winners = [seat for seat in pot.eligible_seats if hand_ranks[seat] == best_rank]
            share, remainder = divmod(pot.size, len(winners))
            for seat in winners:
                payouts[seat] += share
            if remainder:
                for seat in odd_chip_order:
                    if seat in winners:
                        payouts[seat] += 1
                        remainder -= 1
                        if remainder == 0:
                            break
        return payouts

    def _odd_chip_distribution_order(self, button_seat: int) -> List[int]:
        if self.config.odd_chips_rule == "button_left":
            order = []
            seat = seat_after(button_seat, self.config.seat_count)
            for _ in range(self.config.seat_count):
                order.append(seat)
                seat = seat_after(seat, self.config.seat_count)
            return order
        raise NotImplementedError(f"Odd chip rule {self.config.odd_chips_rule!r} is not implemented.")

    def _apply_payouts(
        self,
        players: Dict[int, PlayerRuntimeState],
        contributions: Dict[int, int],
        payouts: Dict[int, int],
    ) -> Dict[int, int]:
        deltas: Dict[int, int] = {}
        for seat, player in players.items():
            winnings = payouts.get(seat, 0)
            spent = contributions.get(seat, 0)
            player.stack += winnings
            deltas[seat] = winnings - spent
        self.logger.log(
            "hand_end",
            {"payouts": payouts, "contributions": contributions},
        )
        return deltas

    def _announce_showdown(
        self,
        hand_id: str,
        board_cards: Sequence[Card],
        payouts: Dict[int, int],
        contributions: Dict[int, int],
        players: Dict[int, PlayerRuntimeState],
        last_aggressor: Optional[int] = None,
    ) -> None:
        standings = {
            seat: {
                "cards": [str(card) for card in players[seat].hole_cards],
                "stack": players[seat].stack,
            }
            for seat in players
        }
        payload = {
            "hand_id": hand_id,
            "board": [str(card) for card in board_cards],
            "payouts": payouts,
            "contributions": contributions,
            "standings": standings,
        }
        if last_aggressor is not None:
            payload["last_aggressor"] = last_aggressor
        self.logger.log("showdown", payload)


def build_deck_from_seed(seed: int, hand_index: int, replica_id: int) -> List[Card]:
    deck = new_deck()
    rng = random.Random()
    composite_seed = f"{seed}:{hand_index}:{replica_id}"
    rng.seed(composite_seed)
    rng.shuffle(deck)
    return deck
