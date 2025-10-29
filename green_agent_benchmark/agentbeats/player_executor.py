"""
AgentBeats executor that wraps a single poker baseline agent (red/blue side).
"""

from __future__ import annotations

import asyncio
import json
import logging
import pathlib
import sys
from typing import Any, Dict, List, Optional

from ..agents.openai_base import _fallback_action
from ..agents.base import AgentProtocol, load_agent as load_custom_agent
from ..baseline_registry import make_baseline
from ..schemas import ActionHistoryEntry, ActionRequest, ActionResponse

# Ensure the vendored AgentBeats SDK is importable.
AGENTBEATS_SRC = pathlib.Path(__file__).resolve().parents[2] / "agentbeats" / "src"
if AGENTBEATS_SRC.exists() and str(AGENTBEATS_SRC) not in sys.path:
    sys.path.insert(0, str(AGENTBEATS_SRC))

from agentbeats.agent_executor import AgentBeatsExecutor, BeatsAgent  # type: ignore  # noqa: E402
from agentbeats.logging import set_battle_context  # type: ignore  # noqa: E402
from a2a.server.apps import A2AStarletteApplication  # type: ignore  # noqa: E402
from a2a.server.agent_execution import RequestContext  # type: ignore  # noqa: E402
from a2a.server.events import EventQueue  # type: ignore  # noqa: E402
from a2a.server.request_handlers import DefaultRequestHandler  # type: ignore  # noqa: E402
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater  # type: ignore  # noqa: E402
from a2a.types import AgentCard, Part, TaskState, TextPart  # type: ignore  # noqa: E402
from a2a.utils import new_agent_text_message, new_task  # type: ignore  # noqa: E402

logger = logging.getLogger(__name__)


def _instantiate_agent(spec: str, **overrides: Any) -> AgentProtocol:
    """
    Load a poker agent from baseline registry or dotted path spec.
    """
    if spec.startswith("baseline:"):
        base, _, query = spec.partition("?")
        baseline_name = base.split(":", 1)[1]
        kwargs: Dict[str, Any] = {}
        if query:
            from urllib.parse import unquote_plus

            for item in query.split("&"):
                if not item:
                    continue
                key, _, value = item.partition("=")
                if key:
                    kwargs[key] = unquote_plus(value)
        kwargs.update(overrides)
        return make_baseline(baseline_name, **kwargs)

    try:
        return make_baseline(spec, **overrides)
    except ValueError:
        return load_custom_agent(spec, **overrides)


def _build_action_request(payload: Dict[str, Any]) -> ActionRequest:
    """
    Convert JSON payload into ``ActionRequest`` dataclass.
    """
    history_raw = payload.get("action_history", [])
    history = [
        ActionHistoryEntry(
            seat_id=int(entry["seat_id"]),
            action=entry["action"],
            amount=entry.get("amount"),
            street=entry["street"],
            to_call=entry["to_call"],
            min_raise_to=entry["min_raise_to"],
        )
        for entry in history_raw
    ]

    stacks_raw = payload.get("stacks", {})
    stacks = {
        int(seat): value for seat, value in stacks_raw.items()
    }

    return ActionRequest(
        seat_count=payload["seat_count"],
        table_id=payload["table_id"],
        hand_id=payload["hand_id"],
        seat_id=payload["seat_id"],
        button_seat=payload["button_seat"],
        blinds=payload["blinds"],
        stacks=stacks,
        pot=payload["pot"],
        to_call=payload["to_call"],
        min_raise_to=payload["min_raise_to"],
        hole_cards=tuple(payload.get("hole_cards", [])),
        board=tuple(payload.get("board", [])),
        action_history=tuple(history),
        legal_actions=tuple(payload.get("legal_actions", [])),
        timebank_ms=payload["timebank_ms"],
        rng_tag=payload.get("rng_tag", ""),
    )


class TexasPlayerExecutor(AgentBeatsExecutor):
    """
    Lightweight executor bridging AgentBeats A2A messages to a local poker agent.
    """

    def __init__(
        self,
        agent_card_json: Dict[str, Any],
        agent_spec: str,
        agent_kwargs: Optional[Dict[str, Any]] = None,
        *,
        mcp_url_list: Optional[List[str]] = None,
        tool_list: Optional[List[Any]] = None,
    ) -> None:
        super().__init__(
            agent_card_json=agent_card_json,
            model_type="local",
            model_name="texas-player",
            mcp_url_list=mcp_url_list,
            tool_list=tool_list,
        )
        self._agent = _instantiate_agent(agent_spec, **(agent_kwargs or {}))
        self._battle_id: Optional[str] = None
        self._seat_id: Optional[int] = None

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        task = context.current_task
        if task is None:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)

        await updater.update_status(
            TaskState.working,
            new_agent_text_message("", task.context_id, task.id),
        )

        raw_input = context.get_user_input()
        reply_text = ""

        try:
            payload = json.loads(raw_input)
        except json.JSONDecodeError:
            reply_text = "Acknowledged."
        else:
            message_type = payload.get("type")
            if message_type == "battle_info":
                reply_text = self._handle_battle_info(payload)
            elif message_type == "texas_reset":
                reply_text = self._handle_reset(payload)
            elif message_type == "texas_action_request":
                reply_text = self._handle_action(payload)
            else:
                reply_text = "Unsupported message type."

        await updater.add_artifact(
            [Part(root=TextPart(text=reply_text))],
            name="response",
        )
        await updater.complete()

    async def cleanup(self) -> None:
        # No long-lived resources to tear down.
        return None

    # ------------------------------------------------------------------
    def _handle_battle_info(self, payload: Dict[str, Any]) -> str:
        battle_id = payload.get("battle_id")
        if battle_id:
            self._battle_id = battle_id
            set_battle_context(
                {
                    "battle_id": battle_id,
                    "agent_id": payload.get("agent_id"),
                    "frontend_agent_name": payload.get("agent_name"),
                    "backend_url": payload.get("backend_url"),
                }
            )
        return "Battle info received."

    def _handle_reset(self, payload: Dict[str, Any]) -> str:
        self._seat_id = int(payload.get("seat_id", 0))
        table_config = payload.get("table") or {}
        reset = getattr(self._agent, "reset", None)
        if callable(reset):
            try:
                reset(self._seat_id, table_config)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("Player agent reset failed: %s", exc)
                return f"Reset failed: {exc}"
        return "Reset acknowledged."

    def _handle_action(self, payload: Dict[str, Any]) -> str:
        data = payload.get("request")
        if not isinstance(data, dict):
            return json.dumps({"action": "fold"})

        try:
            request = _build_action_request(data)
        except Exception as exc:  # pragma: no cover - defensive path
            logger.exception("Unable to parse action request: %s", exc)
            return json.dumps({"action": "fold"})

        response = self._safe_act(request)

        result = {
            "action": response.action,
        }
        if response.amount is not None:
            result["amount"] = response.amount
        if response.metadata:
            result["metadata"] = response.metadata
        if response.wait_time_ms:
            result["wait_time_ms"] = response.wait_time_ms
        return json.dumps(result)

    def _safe_act(self, request: ActionRequest) -> ActionResponse:
        try:
            return self._agent.act(request)
        except Exception as exc:
            logger.exception("Player agent act raised error: %s", exc)
            return _fallback_action(request)


class TexasPlayerBeatsAgent(BeatsAgent):
    """
    Wrapper for exposing a single poker agent through AgentBeats.
    """

    def __init__(
        self,
        name: str,
        agent_host: str,
        agent_port: int,
        agent_spec: str,
        agent_kwargs: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            name=name,
            agent_host=agent_host,
            agent_port=agent_port,
            model_type="local",
            model_name="texas-player",
        )
        self._agent_spec = agent_spec
        self._agent_kwargs = agent_kwargs or {}

    def _make_app(self) -> None:
        executor = TexasPlayerExecutor(
            agent_card_json=self.agent_card_json,
            agent_spec=self._agent_spec,
            agent_kwargs=self._agent_kwargs,
            mcp_url_list=self.mcp_url_list,
            tool_list=self.tool_list,
        )
        self.app = A2AStarletteApplication(
            agent_card=AgentCard(**self.agent_card_json),
            http_handler=DefaultRequestHandler(
                agent_executor=executor,
                task_store=InMemoryTaskStore(),
            ),
        ).build()
