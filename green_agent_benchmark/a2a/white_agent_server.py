# -*- coding: utf-8 -*-
"""
White agent A2A server: numeric poker module + LLM decision + safe fallback.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

import uvicorn
from dotenv import load_dotenv

load_dotenv()

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentSkill, Part, TaskState, TextPart
from a2a.utils import new_agent_text_message, new_task
from a2a.utils.errors import ServerError

from ..agents.white_agent import WhiteAgent

logger = logging.getLogger("white_agent")


def create_agent_card(name: str, url: str) -> AgentCard:
    skill = AgentSkill(
        id="texas_holdem_white_agent",
        name="Texas Hold'em White Agent",
        description="Poker participant agent: equity + pot odds + opponent buckets + LLM decision + fallback.",
        tags=["poker", "texas-holdem", "participant", "white-agent"],
        examples=[],
    )
    return AgentCard(
        name=name,
        description="White agent participant for Texas Hold'em evaluations.",
        url=url,
        version="1.0.0",
        protocol_version="0.3.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[skill],
    )


def _parse_request_text(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"type": "text", "text": text}


def _response_json(action: str, amount: Optional[int] = None, *, reason: str = "") -> str:
    payload: Dict[str, Any] = {"action": action}
    if amount is not None:
        payload["amount"] = int(amount)
    if reason:
        payload["metadata"] = {"reason": reason}
    return json.dumps(payload, separators=(",", ":"))


class WhiteAgentExecutor(AgentExecutor):
    def __init__(self, agent: WhiteAgent) -> None:
        self._agent = agent
        self._seat_id: Optional[int] = None

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        raw = context.get_user_input()
        payload = _parse_request_text(raw)

        msg = context.message
        if msg:
            task = new_task(msg)
            await event_queue.enqueue_event(task)
        else:
            raise ServerError(error={"message": "Missing message."})

        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.update_status(TaskState.working, new_agent_text_message("Working...", context_id=task.context_id))

        reply = ""
        try:
            message_type = payload.get("type")
            if message_type == "texas_reset":
                self._seat_id = int(payload.get("seat_id", 0))
                table = payload.get("table") or {}
                self._agent.reset(self._seat_id, table)
                reply = json.dumps({"status": "ready", "seat_id": self._seat_id})
            elif message_type == "texas_action_request":
                request = payload.get("request") or {}
                if not isinstance(request, dict):
                    reply = _response_json("fold", reason="invalid_request")
                else:
                    request.setdefault("seat_id", payload.get("seat_id"))
                    reply = self._decide_from_raw_request(request)
            else:
                reply = json.dumps({"status": "ok"})
        except Exception as exc:
            logger.exception("White agent server error: %s", exc)
            reply = _response_json("fold", reason="server_error")

        await updater.add_artifact([Part(root=TextPart(text=reply))], name="response")
        await updater.complete()

    def _decide_from_raw_request(self, request: Dict[str, Any]) -> str:
        force_legal = request.get("legal_actions", request.get("valid_actions", [])) or []
        if isinstance(force_legal, str):
            force_legal = [force_legal]
        if not isinstance(force_legal, list):
            force_legal = []

        response = self._agent.act_from_payload(request, force_legal_actions=force_legal)
        reason = ""
        if isinstance(getattr(response, "metadata", None), dict):
            reason = str(response.metadata.get("reason", "") or "")
        return _response_json(response.action, response.amount, reason=reason)

    async def cancel(self, request: RequestContext, event_queue: EventQueue) -> Any:
        return None


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the White Agent A2A server")
    parser.add_argument("--host", default=None, help="Bind host (defaults to $HOST or 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="Bind port (defaults to $AGENT_PORT or 9019)")
    parser.add_argument("--card-url", default=None, help="External URL to advertise in the agent card")
    parser.add_argument("--name", default="TexasWhiteAgent", help="Agent name")
    return parser.parse_args(argv)


async def main(argv: Optional[List[str]] = None) -> None:
    logging.basicConfig(level=logging.INFO)
    args = parse_args(argv)
    host = args.host or os.environ.get("HOST", "127.0.0.1")
    port = int(args.port or os.environ.get("AGENT_PORT", "9019"))
    agent_url = args.card_url or os.environ.get("AGENT_URL") or f"http://{host}:{port}/"
    if agent_url.startswith("http://https://"):
        agent_url = agent_url.replace("http://https://", "https://")
    elif agent_url.startswith("http://http://"):
        agent_url = agent_url.replace("http://http://", "http://")

    agent = WhiteAgent()
    executor = WhiteAgentExecutor(agent)
    card = create_agent_card(args.name, agent_url)

    handler = DefaultRequestHandler(agent_executor=executor, task_store=InMemoryTaskStore())
    app = A2AStarletteApplication(agent_card=card, http_handler=handler).build()

    print(f"[WhiteAgent] Starting at {agent_url}")
    print(f"[WhiteAgent] Agent card: {agent_url}.well-known/agent.json")
    config = uvicorn.Config(app, host=host, port=port, timeout_keep_alive=300)
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
