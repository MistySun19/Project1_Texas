# -*- coding: utf-8 -*-
"""
LLM-powered Texas Hold'em Agent.

This purple agent uses an LLM (GPT-4, Claude, etc.) to make poker decisions.
You can use this as a reference for creating your own intelligent agent.
"""

import argparse
import asyncio
import json
import logging
import os
import uvicorn
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

load_dotenv()

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from a2a.utils import new_agent_text_message

# Import your preferred LLM library
try:
    from openai import AsyncOpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    from litellm import acompletion
    HAS_LITELLM = True
except ImportError:
    HAS_LITELLM = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("llm_agent")


POKER_SYSTEM_PROMPT = """You are an expert Texas Hold'em poker player.

You will receive game state information and must decide on an action.
Analyze the hand strength, position, pot odds, and opponent tendencies.

You MUST respond with a JSON object in this exact format:
{
    "reasoning": "Brief explanation of your decision",
    "action": "fold" | "check" | "call" | "raise_to",
    "amount": <number or null>
}

Rules:
- "check" is only valid when to_call is 0
- "call" matches the current bet
- "raise_to" requires an "amount" between min_raise and max_raise
- "fold" gives up the hand

Consider:
- Hand strength (pairs, high cards, draws)
- Position (acting first vs last)
- Pot odds (to_call vs pot size)
- Stack sizes (max_raise = your remaining stack)
"""


class LLMPokerAgentExecutor(AgentExecutor):
    """
    LLM-powered poker agent.
    
    Uses GPT-4 or other LLMs via OpenAI API or LiteLLM.
    """

    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        self.conversation_history: Dict[str, List[Dict]] = {}
        
        if HAS_OPENAI:
            self.client = AsyncOpenAI()
        elif HAS_LITELLM:
            self.client = None  # Use litellm.acompletion directly
        else:
            raise ImportError("Please install openai or litellm: pip install openai litellm")

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Handle incoming messages."""
        user_input = context.get_user_input()
        logger.info(f"Received: {user_input[:200]}...")

        try:
            data = json.loads(user_input)
            msg_type = data.get("type")

            if msg_type == "texas_action_request":
                request = data.get("request", {})
                response = await self.handle_action_with_llm(request)
            else:
                response = {"status": "ok"}

        except json.JSONDecodeError:
            response = {"status": "ok", "message": "Received text message"}
        except Exception as e:
            logger.error(f"Error: {e}")
            response = {"action": "fold", "error": str(e)}

        response_text = json.dumps(response)
        await event_queue.enqueue_event(
            new_agent_text_message(response_text, context_id=context.context_id)
        )

    async def handle_action_with_llm(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Use LLM to decide poker action."""
        
        # Format game state for LLM
        game_state = self._format_game_state(request)
        
        try:
            # Call LLM
            llm_response = await self._call_llm(game_state)
            
            # Parse response
            action_data = json.loads(llm_response)
            
            action = action_data.get("action", "fold")
            amount = action_data.get("amount")
            
            # Validate action
            valid_actions = request.get("valid_actions", ["fold"])
            if action not in valid_actions:
                logger.warning(f"LLM chose invalid action {action}, falling back to fold")
                action = "fold"
                amount = None
            
            # Validate raise amount
            if action == "raise_to" and amount:
                min_raise = request.get("min_raise", 0)
                max_raise = request.get("max_raise", 0)
                amount = max(min_raise, min(amount, max_raise))
            
            response = {"action": action}
            if amount is not None:
                response["amount"] = amount
            
            logger.info(f"LLM decision: {response} (reasoning: {action_data.get('reasoning', 'N/A')})")
            return response
            
        except Exception as e:
            logger.error(f"LLM error: {e}")
            # Fallback to simple strategy
            return self._fallback_action(request)

    def _format_game_state(self, request: Dict[str, Any]) -> str:
        """Format game state for LLM prompt."""
        return f"""
Current Game State:
- Your hole cards: {request.get('hole_cards', [])}
- Community cards: {request.get('community_cards', [])}
- Pot size: {request.get('pot', 0)}
- Amount to call: {request.get('to_call', 0)}
- Minimum raise: {request.get('min_raise', 0)}
- Maximum raise (your stack): {request.get('max_raise', 0)}
- Valid actions: {request.get('valid_actions', [])}

What action do you take?
"""

    async def _call_llm(self, game_state: str) -> str:
        """Call the LLM API."""
        messages = [
            {"role": "system", "content": POKER_SYSTEM_PROMPT},
            {"role": "user", "content": game_state}
        ]
        
        if HAS_OPENAI and self.client:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            return response.choices[0].message.content
        elif HAS_LITELLM:
            response = await acompletion(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            return response.choices[0].message.content
        else:
            raise RuntimeError("No LLM client available")

    def _fallback_action(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Simple fallback when LLM fails."""
        to_call = request.get("to_call", 0)
        valid_actions = request.get("valid_actions", ["fold"])
        
        if to_call == 0 and "check" in valid_actions:
            return {"action": "check"}
        if "call" in valid_actions and to_call <= request.get("pot", 0) * 0.3:
            return {"action": "call"}
        return {"action": "fold"}

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError


def create_agent_card(name: str, url: str) -> AgentCard:
    skill = AgentSkill(
        id="llm_poker_player",
        name="LLM Poker Player",
        description="AI-powered Texas Hold'em player using language models",
        tags=["poker", "texas-holdem", "llm", "ai"],
        examples=[],
    )
    return AgentCard(
        name=name,
        description="LLM-powered Texas Hold'em agent",
        url=url,
        version="1.0.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(),
        skills=[skill],
    )


def main():
    parser = argparse.ArgumentParser(description="Run LLM-powered poker agent")
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9019)
    parser.add_argument("--card-url", type=str)
    parser.add_argument("--name", type=str, default="LLMPokerAgent")
    parser.add_argument("--model", type=str, default="gpt-4o-mini", 
                        help="LLM model (gpt-4o-mini, gpt-4o, claude-3-sonnet, etc.)")
    args = parser.parse_args()

    agent_url = args.card_url or f"http://{args.host}:{args.port}/"
    
    logger.info(f"Starting {args.name} with model {args.model} at {agent_url}")

    card = create_agent_card(args.name, agent_url)

    request_handler = DefaultRequestHandler(
        agent_executor=LLMPokerAgentExecutor(model=args.model),
        task_store=InMemoryTaskStore(),
    )

    app = A2AStarletteApplication(
        agent_card=card,
        http_handler=request_handler,
    )

    uvicorn.run(app.build(), host=args.host, port=args.port, timeout_keep_alive=300)


if __name__ == "__main__":
    main()
