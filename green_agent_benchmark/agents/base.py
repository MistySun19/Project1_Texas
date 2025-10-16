"""
Agent base interfaces.
"""

from __future__ import annotations

import importlib
from typing import Any, Protocol

from ..schemas import ActionRequest, ActionResponse


class AgentProtocol(Protocol):
    name: str

    def reset(self, seat_id: int, table_config: dict) -> None:
        ...

    def act(self, request: ActionRequest) -> ActionResponse:
        ...


def load_agent(dotted_path: str, **kwargs: Any) -> AgentProtocol:
    """
    Dynamically import an agent class from a dotted path "module:Class".
    """
    if ":" not in dotted_path:
        raise ValueError("Agent dotted path must look like 'package.module:ClassName'")
    module_name, class_name = dotted_path.split(":", 1)
    module = importlib.import_module(module_name)
    agent_cls = getattr(module, class_name)
    return agent_cls(**kwargs)
