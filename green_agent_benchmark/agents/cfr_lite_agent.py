"""
Light-weight CFR-inspired baseline that uses simple showdown equity proxies.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import List

from ..cards import RANK_TO_INT, Card, best_hand_rank, card_from_str, new_deck
from ..schemas import ActionRequest, ActionResponse


@dataclass
class CFRLiteAgent:
    name: str = "CFR-lite"
    samples: int = 100

    def reset(self, seat_id: int, table_config: dict) -> None:
        del seat_id, table_config

    def act(self, request: ActionRequest) -> ActionResponse:
        if len(request.board) < 3:
            return self._preflop_policy(request)
        return self._postflop_policy(request)

    def _preflop_policy(self, request: ActionRequest) -> ActionResponse:
        hole = [card_from_str(c) for c in request.hole_cards]
        ranks = sorted((RANK_TO_INT[c.rank] for c in hole), reverse=True)
        suited = hole[0].suit == hole[1].suit
        pocket = ranks[0] == ranks[1]
        premium = pocket and ranks[0] >= 10
        strong = pocket and ranks[0] >= 7
        high_broadway = ranks[0] >= 13 and ranks[1] >= 12

        if request.to_call == 0:
            if premium:
                return self._raise(request, factor=3.5)
            if high_broadway or strong:
                return self._raise(request, factor=3.0)
            if suited and ranks[0] >= 11 and ranks[1] >= 9:
                return ActionResponse(action="check")
            return ActionResponse(action="check")

        if premium:
            return self._raise(request, factor=3.0)
        if strong or high_broadway:
            if request.to_call <= 3 * request.blinds["bb"]:
                return ActionResponse(action="call")
            return self._raise(request, factor=2.5)
        if request.to_call <= request.blinds["bb"]:
            return ActionResponse(action="call")
        return ActionResponse(action="fold")

    def _postflop_policy(self, request: ActionRequest) -> ActionResponse:
        strength = self._hand_strength(request)
        if request.to_call == 0:
            if strength >= 0.75:
                return self._raise(request, factor=2.5)
            if strength >= 0.5:
                return ActionResponse(action="check")
            return ActionResponse(action="check")

        if strength >= 0.75:
            return self._raise(request, factor=2.2)
        if strength >= 0.45:
            return ActionResponse(action="call")
        if request.to_call <= request.blinds["bb"]:
            return ActionResponse(action="call")
        return ActionResponse(action="fold")

    def _raise(self, request: ActionRequest, factor: float) -> ActionResponse:
        target = int(request.pot * factor)
        min_raise = max(request.min_raise_to, request.to_call + request.blinds["bb"])
        amount = max(min_raise, target)
        max_allowed = request.stacks[request.seat_id] + request.to_call + request.blinds["bb"]
        amount = min(amount, max_allowed)
        return ActionResponse(action="raise_to", amount=amount)

    def _hand_strength(self, request: ActionRequest) -> float:
        hole = [card_from_str(c) for c in request.hole_cards]
        board = [card_from_str(c) for c in request.board]
        deck = [c for c in new_deck() if str(c) not in set(request.board) | set(request.hole_cards)]
        my_rank = best_hand_rank(hole + board)

        needed = 5 - len(board)
        if needed <= 0:
            return 1.0
        samples = 0
        wins = 0
        for opp_cards in combinations(deck, 2):
            future_board = board

            opp_rank = best_hand_rank(list(opp_cards) + future_board)
            samples += 1
            if my_rank >= opp_rank:
                wins += 1
            if samples >= self.samples:
                break
        return wins / max(samples, 1)
