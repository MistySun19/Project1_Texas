"""Command line interface for the Green Agent Benchmark."""

from __future__ import annotations

import argparse
import pathlib
from typing import Any

from .agents.base import load_agent as load_custom_agent
from .baseline_registry import make_baseline
from .runner import BenchmarkRunner, SeriesConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Green Agent Benchmark")
    parser.add_argument("--config", required=True, help="Path to benchmark config YAML")
    parser.add_argument(
        "--agent",
        required=False,
        default="baseline:random-hu",
        help="Agent spec. Use 'baseline:<name>' for packaged baselines or 'pkg.module:Class'",
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
    return parser.parse_args()


def load_agent(spec: str) -> Any:
    if spec.startswith("baseline:"):
        name = spec.split(":", 1)[1]
        return make_baseline(name)
    return load_custom_agent(spec)


def main() -> None:
    args = parse_args()
    config = SeriesConfig.from_file(args.config)
    agent = load_agent(args.agent)
    if args.agent_name:
        setattr(agent, "name", args.agent_name)

    output_dir = pathlib.Path(args.output)
    runner = BenchmarkRunner(config, output_dir)
    result = runner.run(agent)

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
