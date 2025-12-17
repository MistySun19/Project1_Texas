"""Command line interface for the Green Agent Benchmark."""

from __future__ import annotations

import argparse
import json
import logging
import pathlib
import sys
from typing import Any

from .agents.base import load_agent as load_custom_agent
from .baseline_registry import make_baseline
from .env_loader import load_env
from .runner import BenchmarkRunner, SeriesConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Green Agent Benchmark")
    parser.add_argument("--config", required=True, help="Path to benchmark config YAML")
    parser.add_argument(
        "--agent",
        required=False,
        default=None,
        help="Agent spec (baseline:<name> or pkg.module:Class). Optional when config defines a full lineup.",
    )
    parser.add_argument(
        "--output",
        required=False,
        default="artifacts/latest_run",
        help="Directory to store logs and metrics",
    )
    parser.add_argument(
        "--agent-name",
        required=False,
        help="Override agent display name",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        help="Python logging level (e.g. INFO, WARNING). Use INFO to see per-decision traces.",
    )
    return parser.parse_args()


def load_agent(spec: str) -> Any:
    if spec.startswith("baseline:"):
        name = spec.split(":", 1)[1]
        return make_baseline(name)
    return load_custom_agent(spec)


def main() -> None:
    load_env()
    args = parse_args()
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.WARNING))
    # The `openai` Python SDK is used as an HTTP client for multiple providers
    # (OpenAI/DeepSeek/Kimi/etc.). Its INFO logs can be noisy for beginners, so
    # keep them at WARNING.
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("openai._base_client").setLevel(logging.WARNING)
    config = SeriesConfig.from_file(args.config)

    if config.lineup:
        if args.agent:
            print("[CLI] Config defines full lineup; ignoring --agent", file=sys.stderr)
        if args.agent_name:
            print("[CLI] Config defines full lineup; ignoring --agent-name", file=sys.stderr)
        agent = None
    else:
        spec = args.agent or "baseline:random-hu"
        agent = load_agent(spec)
        if args.agent_name and agent is not None:
            setattr(agent, "name", args.agent_name)

    output_dir = pathlib.Path(args.output)
    runner = BenchmarkRunner(config, output_dir)
    result = runner.run(agent)

    if result.stop_info:
        print("=== Run Stopped Early ===")
        print(json.dumps(result.stop_info, indent=2, sort_keys=True))

    metrics = result.metrics
    print("=== Green Agent Benchmark Summary ===")
    for player in sorted(metrics):
        stats = metrics[player]
        print(f"-- {player} --")
        print(f"Hands played: {stats['hands']}")
        print(
            f"bb/100: {stats['bb_per_100']:.2f} (CI {stats['bb_per_100_ci'][0]:.2f}, {stats['bb_per_100_ci'][1]:.2f})"
        )
        print(f"Match points: {stats['match_points']}")
        timeouts = stats["timeouts"]
        print(f"Timeouts: {timeouts['count']} (per hand {timeouts['per_hand']:.3f})")
        illegal = stats["illegal_actions"]
        print(f"Illegal actions: {illegal['count']} (per hand {illegal['per_hand']:.3f})")
        behavior = stats["behavior"]
        print(
            f"VPIP {behavior['vpip']['rate']:.3f}, PFR {behavior['pfr']['rate']:.3f}, AF {behavior['af']:.2f}, WTSD {behavior['wt_sd']['rate']:.3f}"
        )
        print(
            f"Decision time mean: {behavior['decision_time_ms']['mean']:.2f} ms over {behavior['decision_time_ms']['samples']} actions"
        )
        print()
    print(f"Artifacts written to: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
