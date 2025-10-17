"""
Structured dataclasses mirroring the Agent-to-Agent (A2A) protocol.

The actual benchmark uses JSON payloads; in this reference implementation we
work with Python dataclasses for clarity and determinism.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Sequence

ActionLiteral = Literal["fold", "check", "call", "raise_to"]


@dataclass(slots=True)
class ActionHistoryEntry:
    seat_id: int
    action: ActionLiteral
    amount: Optional[int]
    street: str
    to_call: int
    min_raise_to: int


@dataclass(slots=True)
class ActionRequest:
    seat_count: int
    table_id: str
    hand_id: str
    seat_id: int
    button_seat: int
    blinds: Dict[str, int]
    stacks: Dict[int, int]
    pot: int
    to_call: int
    min_raise_to: int
    hole_cards: Sequence[str]
    board: Sequence[str]
    action_history: Sequence[ActionHistoryEntry]
    legal_actions: Sequence[ActionLiteral]
    timebank_ms: int
    rng_tag: str


@dataclass(slots=True)
class ActionResponse:
    action: ActionLiteral
    amount: Optional[int] = None
    metadata: Optional[Dict[str, str]] = None
    wait_time_ms: int = 0


@dataclass(slots=True)
class TableEvent:
    type: str
    payload: Dict[str, object] = field(default_factory=dict)
