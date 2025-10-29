"""
Agent wrapper that proxies Hold'em decisions to an AgentBeats A2A endpoint.

This allows the Green Agent Benchmark runner to treat remote AgentBeats
participants exactly like local ``AgentProtocol`` implementations.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict
from typing import Any, Dict, Optional

from .openai_base import _fallback_action
from ..schemas import ActionRequest, ActionResponse

logger = logging.getLogger(__name__)

try:
    # AgentBeats sources are vendored in the repository under agentbeats/src.
    # When running inside the benchmark we make sure the path is available.
    import agentbeats  # type: ignore  # noqa: F401
except ImportError:  # pragma: no cover - fallback path injection
    import pathlib
    import sys

    agentbeats_src = (
        pathlib.Path(__file__).resolve().parents[2] / "agentbeats" / "src"
    )
    if agentbeats_src.exists():
        sys.path.insert(0, str(agentbeats_src))

from agentbeats.utils.agents import send_message_to_agent  # type: ignore  # noqa: E402


class AgentBeatsRemoteAgent:
    """
    Proxy that forwards ``reset``/``act`` calls to a remote AgentBeats agent.

    The remote agent is expected to speak a JSON protocol over the A2A channel:

    - Reset payload:
        {
            "type": "texas_reset",
            "seat_id": 0,
            "table": { ... table_config ... }
        }

    - Action request payload:
        {
            "type": "texas_action_request",
            "seat_id": 0,
            "request": { ... ActionRequest dataclass as JSON ... }
        }

    The remote agent should respond to action requests with JSON containing at
    least ``action`` (one of ``fold``/``check``/``call``/``raise_to``) and, when
    applicable, ``amount`` and ``wait_time_ms``.
    """

    def __init__(
        self,
        url: str,
        name: Optional[str] = None,
        timeout: float = 45.0,
        retries: int = 1,
    ) -> None:
        self.url = url.rstrip("/")
        self.name = name or "AgentBeatsRemote"
        self.timeout = timeout
        self.retries = max(retries, 0)

    # --- Agent protocol -------------------------------------------------

    def reset(self, seat_id: int, table_config: Dict[str, Any]) -> None:
        payload = {
            "type": "texas_reset",
            "seat_id": seat_id,
            "table": table_config,
        }
        self._send(payload, silent=True)

    def act(self, request: ActionRequest) -> ActionResponse:
        payload = {
            "type": "texas_action_request",
            "seat_id": request.seat_id,
            "request": asdict(request),
        }
        response_text = self._send(payload)
        if not response_text:
            logger.warning(
                "[AgentBeatsRemote:%s] Empty response, using fallback action",
                self.name,
            )
            return _fallback_action(request)

        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            logger.error(
                "[AgentBeatsRemote:%s] Invalid JSON response: %s",
                self.name,
                response_text,
            )
            return _fallback_action(request)

        action = data.get("action")
        if action not in request.legal_actions:
            logger.error(
                "[AgentBeatsRemote:%s] Illegal action '%s' received; legal=%s",
                self.name,
                action,
                request.legal_actions,
            )
            return _fallback_action(request)

        amount = data.get("amount")
        wait_time_ms = int(data.get("wait_time_ms", 0) or 0)
        metadata = data.get("metadata")
        if action != "raise_to":
            amount = None
        return ActionResponse(
            action=action,
            amount=amount,
            metadata=metadata if isinstance(metadata, dict) else None,
            wait_time_ms=wait_time_ms,
        )

    # --- Internal helpers ----------------------------------------------

    def _send(self, payload: Dict[str, Any], silent: bool = False) -> Optional[str]:
        message = json.dumps(payload, separators=(",", ":"))
        last_error: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                return asyncio.run(send_message_to_agent(self.url, message))
            except RuntimeError as runtime_error:
                # Fallback when running inside an existing event loop (should not
                # happen because the benchmark runs in worker threads, but keep a
                # defensive path).
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    response = loop.run_until_complete(
                        send_message_to_agent(self.url, message)
                    )
                    return response
                raise
            except Exception as exc:  # pragma: no cover - network error path
                last_error = exc
                if attempt < self.retries:
                    continue
                if not silent:
                    logger.error(
                        "[AgentBeatsRemote:%s] Failed to contact remote agent %s: %s",
                        self.name,
                        self.url,
                        exc,
                    )
        if last_error and not silent:
            logger.error(
                "[AgentBeatsRemote:%s] Giving up after retries: %s",
                self.name,
                last_error,
            )
        return None
