"""
No-Limit Texas Hold'em state machine used by the Green Agent Benchmark.
"""

from __future__ import annotations

import math
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .cards import Card, best_hand_rank, new_deck
from .logging_utils import NDJSONLogger
from .schemas import ActionHistoryEntry, ActionRequest, ActionResponse

STREETS = ("preflop", "flop", "turn", "river")


@dataclass(slots=True)
class EngineConfig:
    seat_count: int
    small_blind: int
    big_blind: int
    starting_stack: int
    table_id: str
    time_per_decision_ms: int = 60000
    auto_top_up: bool = True


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

    def reset_for_hand(self, starting_stack: int) -> None:
        self.stack = starting_stack
        self.bet = 0
        self.folded = False
        self.all_in = False
        self.hole_cards = []


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
    Deterministic heads-up / 6-max engine.
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
        """
        Runs one hand and returns per-seat chip deltas relative to the starting stack.
        """
        rng_tag = f"{seed}:{hand_index}:{replica_id}"
        hand_id = generate_hand_id(seed, hand_index, replica_id)
        for player in players.values():
            player.reset_for_hand(self.config.starting_stack if self.config.auto_top_up else player.stack)

        for agent in agents.values():
            agent.reset(
                {
                    "seat_count": self.config.seat_count,
                    "small_blind": self.config.small_blind,
                    "big_blind": self.config.big_blind,
                    "starting_stack": self.config.starting_stack,
                    "seat_id": agent.seat_id,
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
                "seats": {
                    seat_id: {
                        "name": players[seat_id].name,
                        "stack": players[seat_id].stack,
                    }
                    for seat_id in range(self.config.seat_count)
                },
                "rng_tag": rng_tag,
            },
        )

        deck_iter = iter(deck)
        # Deal hole cards (two per player, button first)
        for _ in range(2):
            for offset in range(self.config.seat_count):
                seat = (button_seat + 1 + offset) % self.config.seat_count
                players[seat].hole_cards.append(next(deck_iter))

        for seat, player in players.items():
            self.logger.log(
                "deal_hole",
                {
                    "hand_id": hand_id,
                    "seat": seat,
                    "cards": [str(card) for card in player.hole_cards],
                },
            )

        pot = 0
        action_history: List[ActionHistoryEntry] = []
        contributions = {seat: 0 for seat in players}
        active_seats = [seat for seat in players]
        board_cards: List[Card] = []
        # Blinds
        small_blind_seat = seat_after(button_seat, self.config.seat_count)
        big_blind_seat = seat_after(small_blind_seat, self.config.seat_count)

        self._post_blind(players[small_blind_seat], self.config.small_blind, contributions)
        self._post_blind(players[big_blind_seat], self.config.big_blind, contributions)
        pot = contributions[small_blind_seat] + contributions[big_blind_seat]
        street = "preflop"
        highest_bet = max(p.bet for p in players.values())
        last_raise = self.config.big_blind
        order = compute_order(street, self.config.seat_count, button_seat)

        def betting_round(order: List[int], street_name: str, highest: int, last_raise_size: int) -> Tuple[int, int]:
            nonlocal pot
            acted_since_raise: Dict[int, bool] = {seat: False for seat in players}
            to_act_cycle = [seat for seat in order if not players[seat].folded and not players[seat].all_in]
            if not to_act_cycle:
                return highest, last_raise_size
            idx = 0
            while True:
                seat = to_act_cycle[idx % len(to_act_cycle)]
                player = players[seat]
                idx += 1
                if player.folded or player.all_in:
                    acted_since_raise[seat] = True
                    if all(acted_since_raise.values()) and self._betting_round_complete(highest, players):
                        break
                    continue

                to_call = highest - player.bet
                min_raise_to = max(highest + last_raise_size, highest + self.config.big_blind)
                legal = self._legal_actions(player, to_call, min_raise_to)

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
                    legal_actions=legal,
                    timebank_ms=self.config.time_per_decision_ms,
                    rng_tag=rng_tag,
                )

                start = time.perf_counter()
                response = agents[seat].act(request)
                wait_time_ms = getattr(response, "wait_time_ms", 0)
                if wait_time_ms > 0:
                    print(f"[Engine] Agent {agents[seat].name} wait_time_ms={wait_time_ms}")
                elapsed_ms = (time.perf_counter() - start) * 1000 - wait_time_ms

                if elapsed_ms > self.config.time_per_decision_ms:
                    player.timeouts += 1
                    response = self._timeout_fallback(to_call)
                    self.logger.log(
                        "penalty",
                        {
                            "hand_id": hand_id,
                            "seat": seat,
                            "kind": "timeout",
                            "elapsed_ms": math.ceil(elapsed_ms),
                            "fallback": response.action,
                        },
                    )

                if response.action not in legal:
                    player.illegal_actions += 1
                    response = self._illegal_fallback(to_call)
                    self.logger.log(
                        "penalty",
                        {
                            "hand_id": hand_id,
                            "seat": seat,
                            "kind": "illegal_action",
                            "attempted": getattr(response.metadata or {}, "attempted", None),
                            "fallback": response.action,
                        },
                    )

                if response.action == "fold":
                    self._apply_fold(player)
                elif response.action == "check":
                    self._apply_check(player, to_call)
                elif response.action == "call":
                    added = self._apply_call(player, to_call, contributions)
                    pot += added
                elif response.action == "raise_to":
                    desired = response.amount
                    if desired is None:
                        raise IllegalActionError("raise_to requires amount")
                    added, highest, last_raise_size = self._apply_raise_to(
                        player, desired, to_call, min_raise_to, highest, contributions
                    )
                    pot += added

                action_history.append(
                    ActionHistoryEntry(
                        seat_id=seat,
                        action=response.action,
                        amount=response.amount,
                        street=street_name,
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
                        "elapsed_ms": math.ceil(elapsed_ms),
                        "stack_after": player.stack,
                        "bet": player.bet,
                        "street": street_name,
                    },
                )
                acted_since_raise[seat] = True

                if response.action == "raise_to":
                    for other_seat in acted_since_raise:
                        acted_since_raise[other_seat] = (
                            players[other_seat].folded or players[other_seat].all_in
                        )
                    acted_since_raise[seat] = True

                if self._betting_round_complete(highest, players) and all(acted_since_raise.values()):
                    break

            return highest, last_raise_size

        highest_bet, last_raise = betting_round(order, street, highest_bet, last_raise)

        # Early win by folding
        if self._active_players(players) == 1:
            winner_seat = self._remaining_seat(players)
            winners = {winner_seat: pot}
            self._announce_showdown(hand_id, board_cards, winners, contributions, players)
            return self._apply_payouts(players, contributions, winners)

        # Community cards
        board_cards.extend([next(deck_iter) for _ in range(3)])  # flop
        self.logger.log(
            "street_transition",
            {
                "hand_id": hand_id,
                "street": "flop",
                "board": [str(c) for c in board_cards],
            },
        )
        street = "flop"
        self._reset_bets(players)
        order = compute_order(street, self.config.seat_count, button_seat)
        highest_bet, last_raise = betting_round(order, street, 0, self.config.big_blind)

        if self._active_players(players) == 1:
            winner_seat = self._remaining_seat(players)
            winners = {winner_seat: pot}
            self._announce_showdown(hand_id, board_cards, winners, contributions, players)
            return self._apply_payouts(players, contributions, winners)

        board_cards.append(next(deck_iter))  # turn
        self.logger.log(
            "street_transition",
            {
                "hand_id": hand_id,
                "street": "turn",
                "board": [str(c) for c in board_cards],
            },
        )
        street = "turn"
        self._reset_bets(players)
        order = compute_order(street, self.config.seat_count, button_seat)
        highest_bet, last_raise = betting_round(order, street, 0, self.config.big_blind)

        if self._active_players(players) == 1:
            winner_seat = self._remaining_seat(players)
            winners = {winner_seat: pot}
            self._announce_showdown(hand_id, board_cards, winners, contributions, players)
            return self._apply_payouts(players, contributions, winners)

        board_cards.append(next(deck_iter))  # river
        self.logger.log(
            "street_transition",
            {
                "hand_id": hand_id,
                "street": "river",
                "board": [str(c) for c in board_cards],
            },
        )
        street = "river"
        self._reset_bets(players)
        order = compute_order(street, self.config.seat_count, button_seat)
        betting_round(order, street, 0, self.config.big_blind)

        winners = self._resolve_showdown(players, board_cards, contributions)
        self._announce_showdown(hand_id, board_cards, winners, contributions, players)
        return self._apply_payouts(players, contributions, winners)

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
        player: PlayerRuntimeState,
        desired: int,
        to_call: int,
        min_raise_to: int,
        highest_bet: int,
        contributions: Dict[int, int],
    ) -> Tuple[int, int, int]:
        if desired < min_raise_to:
            desired = min_raise_to
        desired = min(desired, player.bet + player.stack)
        raise_amount = desired - player.bet
        if raise_amount <= to_call:
            raise_amount = to_call + self.config.big_blind
            desired = player.bet + raise_amount
        added = desired - player.bet
        player.stack -= added
        player.bet = desired
        contributions[player.seat_id] += added
        if player.stack == 0:
            player.all_in = True
        new_highest = max(highest_bet, desired)
        new_last_raise = desired - highest_bet
        return added, new_highest, new_last_raise

    def _post_blind(self, player: PlayerRuntimeState, amount: int, contributions: Dict[int, int]) -> None:
        posted = min(amount, player.stack)
        player.stack -= posted
        player.bet += posted
        contributions[player.seat_id] = posted
        if player.stack == 0:
            player.all_in = True
        self.logger.log(
            "blind",
            {
                "seat": player.seat_id,
                "amount": posted,
                "type": "small" if amount == self.config.small_blind else "big",
            },
        )

    def _betting_round_complete(
        self, highest_bet: int, players: Dict[int, PlayerRuntimeState]
    ) -> bool:
        """
        A betting round is complete when every non-folded/non-all-in player has
        matched the current highest bet.
        """
        active_players = [p for p in players.values() if not p.folded and not p.all_in]
        if len(active_players) <= 1:
            return True
        return all(p.bet == highest_bet for p in active_players)

    def _legal_actions(self, player: PlayerRuntimeState, to_call: int, min_raise_to: int) -> List[str]:
        legal: List[str] = []
        if to_call > 0:
            legal.append("fold")
            legal.append("call")
        else:
            legal.append("check")
        max_raise = player.bet + player.stack
        if player.stack > 0 and max_raise >= min_raise_to:
            legal.append("raise_to")
        elif to_call > 0 and player.stack > to_call:
            legal.append("raise_to")
        return legal

    def _timeout_fallback(self, to_call: int) -> ActionResponse:
        if to_call > 0:
            return ActionResponse(action="fold")
        return ActionResponse(action="check")

    def _illegal_fallback(self, to_call: int) -> ActionResponse:
        return self._timeout_fallback(to_call)

    def _reset_bets(self, players: Dict[int, PlayerRuntimeState]) -> None:
        for player in players.values():
            player.bet = 0

    def _active_players(self, players: Dict[int, PlayerRuntimeState]) -> int:
        return sum(not p.folded and not p.all_in for p in players.values())

    def _remaining_seat(self, players: Dict[int, PlayerRuntimeState]) -> int:
        for seat, player in players.items():
            if not player.folded:
                return seat
        raise RuntimeError("no remaining players")

    def _resolve_showdown(
        self,
        players: Dict[int, PlayerRuntimeState],
        board_cards: Sequence[Card],
        contributions: Dict[int, int],
    ) -> Dict[int, int]:
        active = [p for p in players.values() if not p.folded]
        showdowns = {p.seat_id: best_hand_rank(p.hole_cards + list(board_cards)) for p in active}
        pots = self._build_side_pots(players, contributions)
        results: Dict[int, int] = {seat: 0 for seat in players}
        for pot_amount, eligible in pots:
            contenders = [seat for seat in eligible if not players[seat].folded]
            if not contenders:
                continue
            best_value = max(showdowns[seat] for seat in contenders)
            winners = [seat for seat in contenders if showdowns[seat] == best_value]
            share = pot_amount // len(winners)
            remainder = pot_amount % len(winners)
            for seat in winners:
                results[seat] += share
            if remainder:
                winners_sorted = sorted(winners)
                for i in range(remainder):
                    results[winners_sorted[i]] += 1
        return results

    def _build_side_pots(
        self,
        players: Dict[int, PlayerRuntimeState],
        contributions: Dict[int, int],
    ) -> List[Tuple[int, List[int]]]:
        entries = [(seat, contributions[seat]) for seat in players if contributions[seat] > 0]
        if not entries:
            return []
        unique = sorted({amount for _, amount in entries})
        pots: List[Tuple[int, List[int]]] = []
        prev = 0
        for amount in unique:
            eligible = [seat for seat, contrib in entries if contrib >= amount]
            pot_amount = (amount - prev) * len(eligible)
            pots.append((pot_amount, eligible))
            prev = amount
        return pots

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
            delta = winnings - spent
            deltas[seat] = delta
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
    ) -> None:
        standings = {
            seat: {
                "cards": [str(c) for c in players[seat].hole_cards],
                "stack": players[seat].stack,
            }
            for seat in players
        }
        self.logger.log(
            "showdown",
            {
                "hand_id": hand_id,
                "board": [str(c) for c in board_cards],
                "payouts": payouts,
                "contributions": contributions,
                "standings": standings,
            },
        )


def build_deck_from_seed(seed: int, hand_index: int, replica_id: int) -> List[Card]:
    deck = new_deck()
    rng = random.Random()
    composite_seed = f"{seed}:{hand_index}:{replica_id}"
    rng.seed(composite_seed)
    rng.shuffle(deck)
    return deck
