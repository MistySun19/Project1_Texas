# -*- coding: utf-8 -*-
"""
Entry point for running the Texas Hold'em Green Agent as an A2A server.

Usage:
    python -m green_agent_benchmark.a2a.server --host 0.0.0.0 --port 8001
    
Or with Docker:
    docker run -p 8001:8001 ghcr.io/your-repo/texas-evaluator:latest --port 8001
"""

import argparse
import asyncio
import uvicorn
from dotenv import load_dotenv

load_dotenv()

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore

from .green_executor import GreenExecutor
from .texas_evaluator import TexasHoldemEvaluator, texas_evaluator_agent_card


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run the Texas Hold'em Green Agent A2A server"
    )
    parser.add_argument(
        "--host", 
        type=str, 
        default="127.0.0.1",
        help="Host to bind the server"
    )
    parser.add_argument(
        "--port", 
        type=int, 
        default=8001,
        help="Port to bind the server"
    )
    parser.add_argument(
        "--card-url",
        type=str,
        help="External URL to advertise in the agent card (defaults to http://host:port/)"
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    
    # Determine agent URL
    agent_url = args.card_url or f"http://{args.host}:{args.port}/"
    
    # Create the evaluator and executor
    evaluator = TexasHoldemEvaluator()
    executor = GreenExecutor(evaluator)
    agent_card = texas_evaluator_agent_card("TexasHoldemEvaluator", agent_url)

    # Create request handler
    request_handler = DefaultRequestHandler(
        agent_executor=executor,
        task_store=InMemoryTaskStore(),
    )

    # Create A2A server
    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    # Run with uvicorn
    print(f"Starting Texas Hold'em Green Agent at {agent_url}")
    print(f"Agent card available at {agent_url}.well-known/agent.json")
    
    uvicorn_config = uvicorn.Config(
        server.build(), 
        host=args.host, 
        port=args.port,
        timeout_keep_alive=300,
    )
    uvicorn_server = uvicorn.Server(uvicorn_config)
    await uvicorn_server.serve()


if __name__ == "__main__":
    asyncio.run(main())
