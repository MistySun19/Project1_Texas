"""
TAG (tight-aggressive) reference agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from ..cards import RANK_TO_INT, best_hand_rank, card_from_str
from ..schemas import ActionRequest, ActionResponse


@dataclass
class TagAgent:
    """
    A simple strategy that plays premium hands aggressively and keeps weak
    holdings passive. It is not meant to be optimal but to provide a stable,
    interpretable baseline.
    """

    name: str = "TAG"

    def reset(self, seat_id: int, table_config: dict) -> None:
        del seat_id, table_config

    def act(self, request: ActionRequest) -> ActionResponse:
        if request.seat_count == 2:
            return self._heads_up_policy(request)
        return self._ring_policy(request)

    def _heads_up_policy(self, request: ActionRequest) -> ActionResponse:
        hole = [card_from_str(c) for c in request.hole_cards]
        ranks = sorted((RANK_TO_INT[c.rank] for c in hole), reverse=True)
        suited = hole[0].suit == hole[1].suit
        pocket = ranks[0] == ranks[1]

        aggressive = False
        if pocket and ranks[0] >= 10:
            aggressive = True
        elif ranks[0] >= 13 and ranks[1] >= 10 and suited:
            aggressive = True
        elif ranks[0] >= 14 and ranks[1] >= 11:
            aggressive = True

        if request.to_call == 0:
            if aggressive:
                return self._raise_request(request, pot_growth=2.5)
            return ActionResponse(action="check")

        if aggressive:
            return self._raise_request(request, pot_growth=2.0)

        if request.to_call <= request.blinds["bb"]:
            return ActionResponse(action="call")
        return ActionResponse(action="fold")

    def _ring_policy(self, request: ActionRequest) -> ActionResponse:
        hole = [card_from_str(c) for c in request.hole_cards]
        ranks = sorted((RANK_TO_INT[c.rank] for c in hole), reverse=True)
        suited = hole[0].suit == hole[1].suit
        pocket = ranks[0] == ranks[1]
        premium = pocket and ranks[0] >= 10
        strong = (pocket and ranks[0] >= 7) or (ranks[0] >= 13 and ranks[1] >= 12)
        playable = suited and ranks[0] >= 11 and ranks[1] >= 9

        if request.to_call == 0:
            if premium:
                return self._raise_request(request, pot_growth=3.5)
            if strong:
                return self._raise_request(request, pot_growth=3.0)
            if playable:
                return ActionResponse(action="check")
            return ActionResponse(action="check")

        if premium:
            return self._raise_request(request, pot_growth=3.0)
        if strong or (playable and request.to_call <= 2 * request.blinds["bb"]):
            return ActionResponse(action="call")
        if request.to_call <= request.blinds["bb"]:
            return ActionResponse(action="call")
        return ActionResponse(action="fold")

    def _raise_request(self, request: ActionRequest, pot_growth: float) -> ActionResponse:
        target = int(request.pot * pot_growth)
        min_raise = max(request.min_raise_to, request.to_call + request.blinds["bb"])
        amount = max(min_raise, target)
        max_allowed = request.stacks[request.seat_id] + request.to_call + request.blinds["bb"]
        amount = min(amount, max_allowed)
        return ActionResponse(action="raise_to", amount=amount)
