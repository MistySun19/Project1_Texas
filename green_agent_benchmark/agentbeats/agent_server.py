"""
Entry-point script to run the Texas Hold'em green agent as an AgentBeats service.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Dict, List, Optional

from .executor import TexasBeatsAgent


def _parse_overrides(args: argparse.Namespace) -> Dict[str, object]:
    overrides: Dict[str, object] = {}
    if args.hands_per_seed is not None:
        overrides["hands_per_seed"] = int(args.hands_per_seed)
    if args.replicas is not None:
        overrides["replicas"] = int(args.replicas)
    if args.stacks_bb is not None:
        overrides["stacks_bb"] = int(args.stacks_bb)
    if args.sb is not None or args.bb is not None:
        sb = args.sb if args.sb is not None else 50
        bb = args.bb if args.bb is not None else 100
        overrides["blinds"] = {"sb": int(sb), "bb": int(bb)}
    if args.seeds:
        overrides["seeds"] = [int(seed) for seed in args.seeds.split(",") if seed.strip()]
    return overrides


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Texas Hold'em agent as an AgentBeats green agent")
    parser.add_argument("card", help="Path to agent card TOML")
    parser.add_argument("--agent_host", default="0.0.0.0", help="Agent HTTP host")
    parser.add_argument("--agent_port", type=int, default=8001, help="Agent HTTP port")
    parser.add_argument("--model_type", default="local", help="Model type label (unused, for compatibility)")
    parser.add_argument("--model_name", default="texas-green-agent", help="Model name label (unused, for compatibility)")
    parser.add_argument("--series_config", help="Optional path to benchmark YAML config")
    parser.add_argument("--output_root", default="artifacts/agentbeats", help="Directory to store battle artifacts")
    parser.add_argument("--hands_per_seed", type=int, help="Override hands_per_seed for HU config")
    parser.add_argument("--replicas", type=int, help="Override replicas per seed")
    parser.add_argument("--stacks_bb", type=int, help="Override stacks_bb")
    parser.add_argument("--sb", type=int, help="Override small blind size")
    parser.add_argument("--bb", type=int, help="Override big blind size")
    parser.add_argument("--seeds", help="Comma separated seed list, e.g. 401,501,601")
    return parser


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    output_root = pathlib.Path(args.output_root).expanduser()
    output_root.mkdir(parents=True, exist_ok=True)

    overrides = _parse_overrides(args)

    agent = TexasBeatsAgent(
        name="texas-green-agent",
        agent_host=args.agent_host,
        agent_port=args.agent_port,
        model_type=args.model_type,
        model_name=args.model_name,
        series_config_path=args.series_config,
        config_overrides=overrides,
        output_root=output_root,
    )

    agent.load_agent_card(args.card)
    agent.run()


if __name__ == "__main__":
    main()

