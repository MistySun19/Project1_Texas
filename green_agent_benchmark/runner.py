"""
Benchmark coordinator: loads configs, runs series, and persists artefacts.
"""

from __future__ import annotations

import json
import pathlib
import random
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Literal, Optional, Tuple

from .baseline_registry import make_baseline
from .agents.base import load_agent as load_custom_agent
from .config_loader import load_config
from .engine import (
    AgentInterface,
    BenchmarkStop,
    EngineConfig,
    HoldemEngine,
    PlayerRuntimeState,
    build_deck_from_seed,
    generate_hand_id,
    seat_after,
)
from .logging_utils import NDJSONLogger
from .metrics import aggregate_run_metrics


PositionHU = Literal["SB", "BB"]
PositionSix = Literal["BTN", "SB", "BB", "UTG", "HJ", "CO"]


@dataclass
class HandRecord:
    player: str
    opponent: str
    mode: str
    seed: int
    hand_index: int
    replica_id: int
    seat: int
    position: str
    delta: int
    timeouts: int
    illegal_actions: int
    log_path: str


@dataclass
class SeriesConfig:
    mode: Literal["hu", "sixmax"]
    blinds: Dict[str, int]
    stacks_bb: int
    seeds: List[int]
    hands_per_seed: Optional[int] = None
    replicas: Optional[int] = None
    opponent_mix: Optional[Dict[str, float]] = None
    hands_per_replica: Optional[int] = None
    seat_replicas: Optional[int] = None
    opponent_pool: Optional[Dict[str, float]] = None
    population_mirroring: bool = False
    opponent_lineup: Optional[List[str]] = None
    lineup: Optional[List[str]] = None
    system_prompt_override: Optional[str] = None

    @property
    def starting_stack(self) -> int:
        return self.stacks_bb * self.blinds["bb"]

    @classmethod
    def from_file(cls, path: str | pathlib.Path) -> "SeriesConfig":
        data = load_config(path)
        mode = data["mode"]
        config = cls(
            mode=mode,
            blinds=data["blinds"],
            stacks_bb=data.get("stacks_bb", 100),
            seeds=list(data["seeds"]),
            hands_per_seed=data.get("hands_per_seed"),
            replicas=data.get("replicas"),
            opponent_mix=data.get("opponent_mix"),
            hands_per_replica=data.get("hands_per_replica"),
            seat_replicas=data.get("seat_replicas"),
            opponent_pool=data.get("opponent_pool"),
            population_mirroring=data.get("population_mirroring", False),
            opponent_lineup=data.get("opponent_lineup"),
            lineup=data.get("lineup"),
            system_prompt_override=data.get("system_prompt_override"),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.mode not in {"hu", "sixmax"}:
            raise ValueError("mode must be 'hu' or 'sixmax'")
        if self.mode == "hu":
            if self.hands_per_seed is None or self.replicas is None:
                raise ValueError("HU config requires hands_per_seed and replicas")
            if self.lineup:
                if len(self.lineup) != 2:
                    raise ValueError("HU lineup must contain exactly 2 entries")
            elif not self.opponent_mix:
                raise ValueError("HU config requires opponent_mix or lineup")
        if self.lineup and self.mode != "sixmax":
            if len(self.lineup) != 2:
                raise ValueError("HU lineup must contain exactly 2 entries")
        if self.mode == "sixmax":
            if self.hands_per_replica is None or self.seat_replicas is None:
                raise ValueError("6-max config requires hands_per_replica and seat_replicas")
            if self.lineup:
                if len(self.lineup) != 6:
                    raise ValueError("6-max lineup must contain exactly 6 entries")
                return
            if self.opponent_lineup:
                if len(self.opponent_lineup) != 5:
                    raise ValueError("6-max opponent_lineup must contain 5 entries")
            elif not self.opponent_pool:
                raise ValueError("6-max config requires opponent_pool or opponent_lineup")


@dataclass
class RunResult:
    hand_records: List[HandRecord]
    log_paths: List[pathlib.Path]
    metrics_path: pathlib.Path
    per_hand_metrics_path: pathlib.Path
    metrics: Dict[str, Any]
    stop_path: Optional[pathlib.Path] = None
    stop_info: Optional[Dict[str, Any]] = None

# Sentinel label used to mark the CLI-provided agent when constructing 6-max lineups
CLI_AGENT_SENTINEL = "__CLI_AGENT__"


def seat_positions(seat_count: int, button_seat: int) -> Dict[int, str]:
    if seat_count == 2:
        mapping = {
            button_seat: "SB",
            seat_after(button_seat, seat_count): "BB",
        }
        return mapping
    labels = ["BTN", "SB", "BB", "UTG", "HJ", "CO"]
    mapping: Dict[int, str] = {}
    seat = button_seat
    for label in labels[:seat_count]:
        mapping[seat] = label
        seat = seat_after(seat, seat_count)
    return mapping


class BenchmarkRunner:
    """
    High-level orchestrator for the Green Agent Benchmark.
    """

    def __init__(
        self,
        config: SeriesConfig,
        output_dir: str | pathlib.Path,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.config = config
        self.output_dir = pathlib.Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.progress_callback = progress_callback
        self._stop_info: Optional[Dict[str, Any]] = None
        self.engine_config = EngineConfig(
            seat_count=2 if config.mode == "hu" else 6,
            small_blind=config.blinds["sb"],
            big_blind=config.blinds["bb"],
            starting_stack=config.starting_stack,
            table_id=f"green-{config.mode}",
        )

    def run(self, agent=None) -> RunResult:
        self._stop_info = None
        agent = self._apply_global_overrides(agent) if agent is not None else None
        runner_name = getattr(agent, "name", "lineup") if agent is not None else "lineup"
        print(f"[BenchmarkRunner] Starting run for {runner_name} in mode {self.config.mode}")
        if self.config.mode == "hu":
            records, log_paths = self._run_hu(agent)
        else:
            records, log_paths = self._run_sixmax(agent)
        per_hand_path = self.output_dir / "metrics" / "per_hand_metrics.ndjson"
        per_hand_path.parent.mkdir(parents=True, exist_ok=True)
        with per_hand_path.open("w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(asdict(rec), sort_keys=True) + "\n")
        metrics_path = self.output_dir / "metrics" / "metrics.json"
        metrics = aggregate_run_metrics(
            [asdict(rec) for rec in records],
            log_paths,
            self.config.blinds["bb"],
        )
        metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
        stop_path: Optional[pathlib.Path] = None
        if self._stop_info is not None:
            stop_path = self.output_dir / "metrics" / "stop.json"
            stop_path.write_text(
                json.dumps(self._stop_info, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        return RunResult(records, log_paths, metrics_path, per_hand_path, metrics, stop_path, self._stop_info)

    def _run_hu(self, agent) -> Tuple[List[HandRecord], List[pathlib.Path]]:

        use_full_lineup = bool(self.config.lineup)
        if use_full_lineup:
            lineup_agents = [
                self._create_agent_from_spec(spec) for spec in self.config.lineup or []
            ]
            replicas = self.config.replicas or 2
        else:
            assert agent is not None
            assert self.config.opponent_mix is not None
            assert self.config.replicas is not None
            opponent_cycle = self._assignment_cycle(self.config.opponent_mix)
            replicas = self.config.replicas

        assert self.config.hands_per_seed is not None

        records: List[HandRecord] = []
        log_paths: List[pathlib.Path] = []

        for seed_idx, seed in enumerate(self.config.seeds):
            if use_full_lineup:
                print(f"[BenchmarkRunner] HU seed {seed} (lineup mode)")
                rotated_agents = self._rotate_assignment(lineup_agents, seed_idx)
            else:
                opponent_name = opponent_cycle[seed_idx % len(opponent_cycle)]
                print(f"[BenchmarkRunner] HU seed {seed} vs {opponent_name}")
            self._emit_progress(
                {
                    "type": "seed_start",
                    "mode": "hu",
                    "seed": seed,
                    "seed_index": seed_idx,
                    "use_full_lineup": use_full_lineup,
                }
            )

            for replica_id in range(replicas):
                if use_full_lineup:
                    # Replica controls button order only; seats are fixed by rotated_agents
                    agent_iface = AgentInterface(rotated_agents[0], 0)
                    opponent_iface = AgentInterface(rotated_agents[1], 1)
                    agent_seat, opponent_seat = 0, 1
                    button_seat = 0 if replica_id % 2 == 0 else 1
                    log_dir = self.output_dir / "logs" / "hu" / opponent_iface.name
                else:
                    if replica_id % 2 == 0:
                        agent_seat = 0
                        opponent_seat = 1
                        button_seat = agent_seat
                    else:
                        agent_seat = 1
                        opponent_seat = 0
                        button_seat = opponent_seat
                    agent_iface = AgentInterface(agent, agent_seat)
                    opponent_name = opponent_cycle[seed_idx % len(opponent_cycle)]
                    opponent_agent = self._apply_global_overrides(
                        make_baseline(opponent_name)
                    )
                    opponent_iface = AgentInterface(opponent_agent, opponent_seat)
                    log_dir = self.output_dir / "logs" / "hu" / opponent_name

                log_path = log_dir / f"seed{seed}_rep{replica_id}.ndjson"
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_paths.append(log_path)

                self._emit_progress(
                    {
                        "type": "replica_start",
                        "mode": "hu",
                        "seed": seed,
                        "replica": replica_id,
                        "button_seat": button_seat,
                        "agent": {
                            "name": agent_iface.name,
                            "seat": agent_seat,
                        },
                        "opponent": {
                            "name": opponent_iface.name,
                            "seat": opponent_seat,
                        },
                    }
                )

                with NDJSONLogger(log_path) as logger:
                    engine = HoldemEngine(self.engine_config, logger)
                    players = {
                        agent_seat: PlayerRuntimeState(
                            seat_id=agent_seat,
                            name=agent_iface.name,
                            stack=self.engine_config.starting_stack,
                        ),
                        opponent_seat: PlayerRuntimeState(
                            seat_id=opponent_seat,
                            name=opponent_iface.name,
                            stack=self.engine_config.starting_stack,
                        ),
                    }

                    for hand_index in range(self.config.hands_per_seed):
                        print(
                            f"[BenchmarkRunner] HU hand seed={seed} replica={replica_id} hand_index={hand_index} button={button_seat}"
                        )
                        deck = build_deck_from_seed(seed, hand_index, 0)
                        positions = seat_positions(self.engine_config.seat_count, button_seat)
                        prev_timeouts = {seat_id: players[seat_id].timeouts for seat_id in players}
                        prev_illegal = {seat_id: players[seat_id].illegal_actions for seat_id in players}

                        try:
                            deltas = engine.play_hand(
                                seed=seed,
                                hand_index=hand_index,
                                replica_id=replica_id,
                                button_seat=button_seat,
                                players=players,
                                agents={agent_seat: agent_iface, opponent_seat: opponent_iface},
                                deck=deck,
                            )
                        except BenchmarkStop as exc:
                            self._stop_info = {
                                "type": "benchmark_stop",
                                "mode": "hu",
                                "seed": seed,
                                "replica": replica_id,
                                "hand_index": hand_index,
                                "hand_id": exc.hand_id,
                                "seat": exc.seat,
                                "agent": exc.agent_name,
                                "agent_reason": exc.agent_reason,
                            }
                            print(f"[BenchmarkRunner] STOP: {exc}")
                            self._emit_progress(dict(self._stop_info))
                            return records, log_paths

                        post_timeouts = {seat_id: players[seat_id].timeouts for seat_id in players}
                        post_illegal = {seat_id: players[seat_id].illegal_actions for seat_id in players}

                        records.append(
                            HandRecord(
                                player=agent_iface.name,
                                opponent=opponent_iface.name,
                                mode="hu",
                                seed=seed,
                                hand_index=hand_index,
                                replica_id=replica_id,
                                seat=agent_seat,
                                position=positions[agent_seat],
                                delta=deltas.get(agent_seat, 0),
                                timeouts=post_timeouts[agent_seat] - prev_timeouts[agent_seat],
                                illegal_actions=post_illegal[agent_seat] - prev_illegal[agent_seat],
                                log_path=str(log_path),
                            )
                        )

                        records.append(
                            HandRecord(
                                player=opponent_iface.name,
                                opponent=agent_iface.name,
                                mode="hu",
                                seed=seed,
                                hand_index=hand_index,
                                replica_id=replica_id,
                                seat=opponent_seat,
                                position=positions[opponent_seat],
                                delta=deltas.get(opponent_seat, 0),
                                timeouts=post_timeouts[opponent_seat] - prev_timeouts[opponent_seat],
                                illegal_actions=post_illegal[opponent_seat] - prev_illegal[opponent_seat],
                                log_path=str(log_path),
                            )
                        )

                        hand_event = {
                            "type": "hand_result",
                            "hand_id": generate_hand_id(seed, hand_index, replica_id),
                            "mode": "hu",
                            "seed": seed,
                            "replica": replica_id,
                            "hand_index": hand_index,
                            "button_seat": button_seat,
                            "players": [
                                {
                                    "name": agent_iface.name,
                                    "seat": agent_seat,
                                    "position": positions[agent_seat],
                                    "delta": deltas.get(agent_seat, 0),
                                    "timeouts": post_timeouts[agent_seat] - prev_timeouts[agent_seat],
                                    "illegal_actions": post_illegal[agent_seat] - prev_illegal[agent_seat],
                                },
                                {
                                    "name": opponent_iface.name,
                                    "seat": opponent_seat,
                                    "position": positions[opponent_seat],
                                    "delta": deltas.get(opponent_seat, 0),
                                    "timeouts": post_timeouts[opponent_seat] - prev_timeouts[opponent_seat],
                                    "illegal_actions": post_illegal[opponent_seat] - prev_illegal[opponent_seat],
                                },
                            ],
                        }
                        self._emit_progress(hand_event)
        return records, log_paths

    def _run_sixmax(self, agent) -> Tuple[List[HandRecord], List[pathlib.Path]]:
        assert self.config.hands_per_replica is not None
        assert self.config.seat_replicas is not None

        records: List[HandRecord] = []
        log_paths: List[pathlib.Path] = []

        use_full_lineup = bool(self.config.lineup)

        for seed in self.config.seeds:
            print(f"[BenchmarkRunner] 6-max seed {seed}")
            self._emit_progress(
                {
                    "type": "seed_start",
                    "mode": "sixmax",
                    "seed": seed,
                    "use_full_lineup": use_full_lineup,
                }
            )
            if use_full_lineup:
                base_assignment = list(self.config.lineup or [])
            else:
                if self.config.opponent_lineup:
                    opponents = list(self.config.opponent_lineup)
                else:
                    assert self.config.opponent_pool is not None
                    opponents = self._build_lineup(seed, self.config.opponent_pool)
                if agent is None:
                    raise ValueError("6-max requires --agent when lineup is not provided in config")
                base_assignment = [CLI_AGENT_SENTINEL, *opponents]
            for replica_id in range(self.config.seat_replicas):
                print(f"[BenchmarkRunner] 6-max seat replica {replica_id}")
                rotated = self._rotate_assignment(base_assignment, replica_id)
                log_path = (
                    self.output_dir
                    / "logs"
                    / "sixmax"
                    / f"seed{seed}_rep{replica_id}.ndjson"
                )
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with NDJSONLogger(log_path) as logger:
                    engine = HoldemEngine(self.engine_config, logger)
                    players: Dict[int, PlayerRuntimeState] = {}
                    interfaces: Dict[int, AgentInterface] = {}
                    primary_seat: Optional[int] = None
                    primary_name: Optional[str] = None
                    for seat, label in enumerate(rotated):
                        if use_full_lineup:
                            agent_obj = self._create_agent_from_spec(label)
                            iface = AgentInterface(agent_obj, seat)
                        else:
                            if label == CLI_AGENT_SENTINEL:
                                iface = AgentInterface(agent, seat)
                                primary_seat = seat
                                primary_name = iface.name
                            else:
                                agent_obj = self._create_agent_from_spec(label)
                                iface = AgentInterface(agent_obj, seat)
                        interfaces[seat] = iface
                        players[seat] = PlayerRuntimeState(
                            seat_id=seat,
                            name=iface.name,
                            stack=self.engine_config.starting_stack,
                        )

                    assignment_event = {
                        "type": "replica_start",
                        "mode": "sixmax",
                        "seed": seed,
                        "replica": replica_id,
                        "assignment": [
                            {
                                "seat": seat,
                                "name": interfaces[seat].name,
                                "label": rotated[seat],
                            }
                            for seat in sorted(interfaces)
                        ],
                    }
                    self._emit_progress(assignment_event)

                    for hand_index in range(self.config.hands_per_replica):
                        print(
                            f"[BenchmarkRunner] 6-max hand seed={seed} replica={replica_id} hand_index={hand_index}"
                        )
                        deck = build_deck_from_seed(seed, hand_index, 0)
                        button_seat = (seed + hand_index) % self.engine_config.seat_count
                        positions = seat_positions(self.engine_config.seat_count, button_seat)
                        prev_timeouts = {seat: players[seat].timeouts for seat in players}
                        prev_illegal = {seat: players[seat].illegal_actions for seat in players}

                        try:
                            deltas = engine.play_hand(
                                seed=seed,
                                hand_index=hand_index,
                                replica_id=replica_id,
                                button_seat=button_seat,
                                players=players,
                                agents=interfaces,
                                deck=deck,
                            )
                        except BenchmarkStop as exc:
                            self._stop_info = {
                                "type": "benchmark_stop",
                                "mode": "sixmax",
                                "seed": seed,
                                "replica": replica_id,
                                "hand_index": hand_index,
                                "hand_id": exc.hand_id,
                                "seat": exc.seat,
                                "agent": exc.agent_name,
                                "agent_reason": exc.agent_reason,
                            }
                            print(f"[BenchmarkRunner] STOP: {exc}")
                            self._emit_progress(dict(self._stop_info))
                            return records, log_paths

                        post_timeouts = {seat: players[seat].timeouts for seat in players}
                        post_illegal = {seat: players[seat].illegal_actions for seat in players}

                        for seat, iface in interfaces.items():
                            if use_full_lineup or primary_seat is None:
                                opponent_label = "table"
                            else:
                                opponent_label = "mix" if seat == primary_seat else (primary_name or "agent")
                            records.append(
                                HandRecord(
                                    player=iface.name,
                                    opponent=opponent_label,
                                    mode="sixmax",
                                    seed=seed,
                                    hand_index=hand_index,
                                    replica_id=replica_id,
                                    seat=seat,
                                    position=positions[seat],
                                    delta=deltas.get(seat, 0),
                                    timeouts=post_timeouts[seat] - prev_timeouts[seat],
                                    illegal_actions=post_illegal[seat] - prev_illegal[seat],
                                    log_path=str(log_path),
                                )
                            )
                        hand_event = {
                            "type": "hand_result",
                            "hand_id": generate_hand_id(seed, hand_index, replica_id),
                            "mode": "sixmax",
                            "seed": seed,
                            "replica": replica_id,
                            "hand_index": hand_index,
                            "button_seat": button_seat,
                            "players": [
                                {
                                    "name": interfaces[seat].name,
                                    "seat": seat,
                                    "position": positions[seat],
                                    "delta": deltas.get(seat, 0),
                                    "timeouts": post_timeouts[seat] - prev_timeouts[seat],
                                    "illegal_actions": post_illegal[seat] - prev_illegal[seat],
                                }
                                for seat in sorted(interfaces)
                            ],
                        }
                        self._emit_progress(hand_event)
                log_paths.append(log_path)
        return records, log_paths

    def _apply_global_overrides(self, agent_obj):
        if agent_obj is None:
            return None
        override = self.config.system_prompt_override
        if override is not None and hasattr(agent_obj, "system_prompt_override"):
            setattr(agent_obj, "system_prompt_override", override)
        return agent_obj

    def _assignment_cycle(self, mix: Dict[str, float]) -> Tuple[str, ...]:
        expanded: List[str] = []
        for name, weight in sorted(mix.items(), key=lambda x: x[0]):
            if weight <= 0:
                continue
            count = max(int(weight * 10), 1)
            expanded.extend([name] * count)
        return tuple(expanded) if expanded else tuple(mix.keys())

    def _build_lineup(self, seed: int, pool: Dict[str, float]) -> List[str]:
        rng = random.Random(seed)
        names = list(pool.keys())
        weights = [pool[n] for n in names]
        lineup: List[str] = []
        for _ in range(self.engine_config.seat_count - 1):
            lineup.append(rng.choices(names, weights=weights, k=1)[0])
        return lineup

    def _rotate_assignment(self, assignment: List[Any], replica_id: int) -> List[Any]:
        shift = -(replica_id % len(assignment))
        return assignment[shift:] + assignment[:shift]

    def _create_agent_from_spec(self, spec: str):
        base, sep, params = spec.partition("?")
        kwargs: Dict[str, Any] = {}
        if sep:
            from urllib.parse import unquote_plus

            for item in params.split("&"):
                if not item:
                    continue
                key, _, value = item.partition("=")
                if key:
                    kwargs[key] = unquote_plus(value)

        display_name = kwargs.pop("name", None)
        if base.startswith("baseline:"):
            baseline_name = base.split(":", 1)[1]
            agent_obj = make_baseline(baseline_name, **kwargs)
        else:
            try:
                agent_obj = make_baseline(base)
            except ValueError:
                agent_obj = load_custom_agent(base)
        if display_name:
            setattr(agent_obj, "name", display_name)
        return self._apply_global_overrides(agent_obj)

    def _emit_progress(self, event: Dict[str, Any]) -> None:
        if not self.progress_callback:
            return
        try:
            self.progress_callback(event)
        except Exception as exc:
            print(f"[BenchmarkRunner] progress callback failed: {exc}")
