"""
Random baseline agent.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

from ..schemas import ActionRequest, ActionResponse


@dataclass
class RandomAgent:
    name: str = "Random"
    seed: Optional[int] = None

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def reset(self, seat_id: int, table_config: dict) -> None:
        del seat_id, table_config

    def act(self, request: ActionRequest) -> ActionResponse:
        action = self._rng.choice(list(request.legal_actions))
        if action == "raise_to":
            span = max(request.min_raise_to, request.to_call + request.blinds["bb"])
            max_raise = request.stacks[request.seat_id] + span
            amount = min(max_raise, span)
            return ActionResponse(action="raise_to", amount=amount)
        return ActionResponse(action=action)
