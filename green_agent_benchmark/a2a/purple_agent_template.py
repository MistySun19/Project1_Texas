# -*- coding: utf-8 -*-
"""
Texas Hold'em Purple Agent - Participant agent for poker evaluation.

This is a template for creating a purple agent that can participate
in Texas Hold'em evaluations on the AgentBeats platform.

Purple agents receive action requests and return poker decisions.
"""

import argparse
import asyncio
import json
import logging
import uvicorn
from typing import Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from a2a.utils import new_agent_text_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("texas_agent")


class TexasPokerAgentExecutor(AgentExecutor):
    """
    Purple agent executor for Texas Hold'em.
    
    This is a template - implement your own logic in `decide_action`.
    """

    def __init__(self):
        self.conversation_history: Dict[str, List[Dict]] = {}

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Handle incoming messages from the green agent."""
        user_input = context.get_user_input()
        logger.info(f"Received: {user_input[:200]}...")

        try:
            # Parse the incoming message
            data = json.loads(user_input)
            msg_type = data.get("type")

            if msg_type == "texas_reset":
                # New hand starting
                seat_id = data.get("seat_id")
                table_info = data.get("table", {})
                response = self.handle_reset(seat_id, table_info)
                
            elif msg_type == "texas_action_request":
                # Need to make a decision
                seat_id = data.get("seat_id")
                request = data.get("request", {})
                response = await self.handle_action_request(seat_id, request)
                
            else:
                # Generic message - respond with acknowledgment
                response = {"status": "ok", "message": "Message received"}

        except json.JSONDecodeError:
            # Plain text message
            response = await self.handle_text_message(user_input)
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            response = {"action": "fold", "error": str(e)}

        # Send response
        response_text = json.dumps(response)
        await event_queue.enqueue_event(
            new_agent_text_message(response_text, context_id=context.context_id)
        )

    def handle_reset(self, seat_id: int, table_info: Dict[str, Any]) -> Dict[str, Any]:
        """Handle hand reset - called at the start of each hand."""
        logger.info(f"Hand reset: seat={seat_id}, table={table_info}")
        return {"status": "ready", "seat_id": seat_id}

    async def handle_action_request(
        self, 
        seat_id: int, 
        request: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle action request - decide what poker action to take.
        
        Request contains:
        - hand_id: str - Unique hand identifier
        - seat_id: int - Your seat number
        - hole_cards: List[str] - Your cards, e.g. ["Ah", "Kd"]
        - community_cards: List[str] - Board cards
        - pot: int - Current pot size
        - to_call: int - Amount needed to call
        - min_raise: int - Minimum raise amount
        - max_raise: int - Maximum raise amount (your stack)
        - valid_actions: List[str] - Available actions
        - history: List - Action history for this hand
        
        Returns:
        - action: str - "fold", "check", "call", or "raise_to"
        - amount: int (optional) - Required for "raise_to"
        """
        logger.info(f"Action request: {request}")
        
        # Extract info from request
        hole_cards = request.get("hole_cards", [])
        community_cards = request.get("community_cards", [])
        pot = request.get("pot", 0)
        to_call = request.get("to_call", 0)
        min_raise = request.get("min_raise", 0)
        max_raise = request.get("max_raise", 0)
        valid_actions = request.get("valid_actions", ["fold"])
        
        # YOUR DECISION LOGIC HERE
        # This is a simple example - replace with your strategy
        action, amount = await self.decide_action(
            hole_cards=hole_cards,
            community_cards=community_cards,
            pot=pot,
            to_call=to_call,
            min_raise=min_raise,
            max_raise=max_raise,
            valid_actions=valid_actions,
        )
        
        response = {"action": action}
        if amount is not None:
            response["amount"] = amount
            
        logger.info(f"Decision: {response}")
        return response

    async def decide_action(
        self,
        hole_cards: List[str],
        community_cards: List[str],
        pot: int,
        to_call: int,
        min_raise: int,
        max_raise: int,
        valid_actions: List[str],
    ) -> tuple[str, int | None]:
        """
        YOUR STRATEGY IMPLEMENTATION HERE.
        
        This template uses a simple strategy:
        - Check if free
        - Call small bets
        - Fold to large bets unless we have strong cards
        
        Replace this with your own logic, LLM calls, or trained model.
        """
        
        # Simple hand strength evaluation
        def is_strong_hand(cards: List[str]) -> bool:
            """Check if hole cards are strong (pairs, high cards)."""
            if len(cards) < 2:
                return False
            ranks = [c[:-1] for c in cards]  # Extract ranks
            # Pairs
            if ranks[0] == ranks[1]:
                return True
            # High cards (A, K, Q, J, T)
            high_ranks = {'A', 'K', 'Q', 'J', 'T'}
            if ranks[0] in high_ranks and ranks[1] in high_ranks:
                return True
            return False
        
        strong = is_strong_hand(hole_cards)
        
        # Decision logic
        if to_call == 0 and "check" in valid_actions:
            return "check", None
            
        if to_call == 0 and "call" in valid_actions:
            return "call", None
        
        # Call small bets or with strong hands
        if "call" in valid_actions:
            if to_call <= pot * 0.5 or strong:
                return "call", None
        
        # Raise with strong hands
        if strong and "raise_to" in valid_actions and min_raise > 0:
            raise_amount = min(min_raise * 2, max_raise)
            return "raise_to", raise_amount
        
        # Fold otherwise
        return "fold", None

    async def handle_text_message(self, text: str) -> Dict[str, Any]:
        """Handle plain text messages."""
        return {"status": "ok", "message": f"Received: {text[:100]}"}

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancel is not implemented."""
        raise NotImplementedError


def create_agent_card(name: str, url: str, role: str = "player") -> AgentCard:
    """Create the agent card for this purple agent."""
    skill = AgentSkill(
        id="texas_holdem_player",
        name="Texas Hold'em Player",
        description=f"Plays No-Limit Texas Hold'em as {role}",
        tags=["poker", "texas-holdem", role],
        examples=[],
    )
    return AgentCard(
        name=name,
        description=f"Texas Hold'em {role} agent - participates in poker evaluations",
        url=url,
        version="1.0.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(),
        skills=[skill],
    )


def main():
    parser = argparse.ArgumentParser(description="Run Texas Hold'em purple agent")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind")
    parser.add_argument("--port", type=int, default=9019, help="Port to bind")
    parser.add_argument("--card-url", type=str, help="External URL for agent card")
    parser.add_argument("--name", type=str, default="TexasAgent", help="Agent name")
    parser.add_argument("--role", type=str, default="player", help="Agent role (blue/red/player)")
    args = parser.parse_args()

    agent_url = args.card_url or f"http://{args.host}:{args.port}/"
    
    logger.info(f"Starting {args.name} ({args.role}) at {agent_url}")

    card = create_agent_card(args.name, agent_url, args.role)

    request_handler = DefaultRequestHandler(
        agent_executor=TexasPokerAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    app = A2AStarletteApplication(
        agent_card=card,
        http_handler=request_handler,
    )

    uvicorn.run(
        app.build(),
        host=args.host,
        port=args.port,
        timeout_keep_alive=300,
    )


if __name__ == "__main__":
    main()
