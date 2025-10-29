"""
Minimal launcher that mirrors AgentBeats' launcher behaviour for the Texas agent.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from typing import List, Optional

# Ensure agentbeats package is available before importing.
AGENTBEATS_SRC = pathlib.Path(__file__).resolve().parents[2] / "agentbeats" / "src"
if AGENTBEATS_SRC.exists() and str(AGENTBEATS_SRC) not in sys.path:
    sys.path.insert(0, str(AGENTBEATS_SRC))

from agentbeats.agent_launcher import BeatsAgentLauncher  # type: ignore  # noqa: E402


class TexasLauncher(BeatsAgentLauncher):
    def __init__(
        self,
        *,
        series_config: Optional[str],
        output_root: str,
        extra_overrides: List[str],
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.series_config = series_config
        self.output_root = output_root
        self.extra_overrides = extra_overrides

    def _agent_cmd(self) -> List[str]:
        cmd = [
            sys.executable,
            "-m",
            "green_agent_benchmark.agentbeats.agent_server",
            str(self.agent_card),
            "--agent_host",
            self.agent_host,
            "--agent_port",
            str(self.agent_port),
            "--model_type",
            self.model_type,
            "--model_name",
            self.model_name,
            "--output_root",
            self.output_root,
        ]
        if self.series_config:
            cmd.extend(["--series_config", self.series_config])
        cmd.extend(self.extra_overrides)
        return cmd


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launcher for the Texas Hold'em AgentBeats green agent")
    parser.add_argument("card", help="Path to agent card TOML")
    parser.add_argument("--launcher_host", default="0.0.0.0", help="Launcher host")
    parser.add_argument("--launcher_port", type=int, default=8000, help="Launcher port")
    parser.add_argument("--agent_host", default="0.0.0.0", help="Agent host")
    parser.add_argument("--agent_port", type=int, default=8001, help="Agent port")
    parser.add_argument("--model_type", default="local", help="Model type label (unused)")
    parser.add_argument("--model_name", default="texas-green-agent", help="Model name label (unused)")
    parser.add_argument("--series_config", help="Optional path to benchmark YAML config")
    parser.add_argument("--output_root", default="artifacts/agentbeats", help="Directory to store battle artifacts")
    parser.add_argument("--hands_per_seed", type=int, help="Override hands per seed")
    parser.add_argument("--replicas", type=int, help="Override replicas per seed")
    parser.add_argument("--stacks_bb", type=int, help="Override stacks in big blinds")
    parser.add_argument("--sb", type=int, help="Override small blind")
    parser.add_argument("--bb", type=int, help="Override big blind")
    parser.add_argument("--seeds", help="Comma separated seeds, e.g. 401,501,601")
    return parser


def build_override_args(args: argparse.Namespace) -> List[str]:
    override_args: List[str] = []
    if args.hands_per_seed is not None:
        override_args += ["--hands_per_seed", str(args.hands_per_seed)]
    if args.replicas is not None:
        override_args += ["--replicas", str(args.replicas)]
    if args.stacks_bb is not None:
        override_args += ["--stacks_bb", str(args.stacks_bb)]
    if args.sb is not None:
        override_args += ["--sb", str(args.sb)]
    if args.bb is not None:
        override_args += ["--bb", str(args.bb)]
    if args.seeds:
        override_args += ["--seeds", args.seeds]
    return override_args


def main(argv: Optional[List[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    output_root = pathlib.Path(args.output_root).expanduser()
    output_root.mkdir(parents=True, exist_ok=True)

    launcher = TexasLauncher(
        agent_card=args.card,
        launcher_host=args.launcher_host,
        launcher_port=args.launcher_port,
        agent_host=args.agent_host,
        agent_port=args.agent_port,
        model_type=args.model_type,
        model_name=args.model_name,
        mcp_list=[],
        tool_list=[],
        series_config=args.series_config,
        output_root=str(output_root),
        extra_overrides=build_override_args(args),
    )
    launcher.run()


if __name__ == "__main__":
    main()

