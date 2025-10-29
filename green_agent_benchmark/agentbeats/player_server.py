"""
CLI entrypoint for running a single poker agent (red/blue) via AgentBeats.
"""

from __future__ import annotations

import argparse
import pathlib
from typing import Dict, List, Optional

from .player_executor import TexasPlayerBeatsAgent


def _parse_kv_pairs(pairs: Optional[List[str]]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    if not pairs:
        return result
    for item in pairs:
        if "=" not in item:
            raise ValueError(f"Invalid parameter '{item}', expected key=value")
        key, value = item.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Expose a single Texas Hold'em poker agent through AgentBeats."
    )
    parser.add_argument("card", help="Path to agent card TOML")
    parser.add_argument("--agent_spec", default="baseline:deepseek-hu", help="Agent spec (baseline:*, pkg.module:Class)")
    parser.add_argument("--param", action="append", help="Additional key=value parameters to pass when instantiating the agent")
    parser.add_argument("--agent_host", default="0.0.0.0", help="Agent HTTP host")
    parser.add_argument("--agent_port", type=int, default=9011, help="Agent HTTP port")
    parser.add_argument("--name", default="texas-player", help="Display name for the Beats agent")
    parser.add_argument("--mcp", action="append", default=[], help="Optional MCP SSE server URLs")
    parser.add_argument("--tool", action="append", default=[], help="Optional tool definition modules")
    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    params = _parse_kv_pairs(args.param)
    card_path = pathlib.Path(args.card).expanduser()
    if not card_path.exists():
        raise FileNotFoundError(f"Agent card not found: {card_path}")

    agent = TexasPlayerBeatsAgent(
        name=args.name,
        agent_host=args.agent_host,
        agent_port=args.agent_port,
        agent_spec=args.agent_spec,
        agent_kwargs=params,
    )

    for tool in args.tool:
        from importlib import import_module

        import_module(tool)

    agent.load_agent_card(str(card_path))
    for url in args.mcp:
        if url:
            agent.add_mcp_server(url)

    agent.run()


if __name__ == "__main__":
    main()

