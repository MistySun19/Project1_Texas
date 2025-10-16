"""
Benchmark coordinator: loads configs, runs series, and persists artefacts.
"""

from __future__ import annotations

import json
import pathlib
import random
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Literal, Optional, Tuple

from .baseline_registry import make_baseline
from .config_loader import load_config
from .engine import (
    AgentInterface,
    EngineConfig,
    HoldemEngine,
    PlayerRuntimeState,
    build_deck_from_seed,
    seat_after,
)
from .logging_utils import NDJSONLogger
from .metrics import aggregate_run_metrics


PositionHU = Literal["SB", "BB"]
PositionSix = Literal["BTN", "SB", "BB", "UTG", "HJ", "CO"]


@dataclass(slots=True)
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


@dataclass(slots=True)
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
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.mode not in {"hu", "sixmax"}:
            raise ValueError("mode must be 'hu' or 'sixmax'")
        if self.mode == "hu":
            if self.hands_per_seed is None or self.replicas is None:
                raise ValueError("HU config requires hands_per_seed and replicas")
            if not self.opponent_mix:
                raise ValueError("HU config requires opponent_mix")
        if self.mode == "sixmax":
            if self.hands_per_replica is None or self.seat_replicas is None:
                raise ValueError("6-max config requires hands_per_replica and seat_replicas")
            if not self.opponent_pool:
                raise ValueError("6-max config requires opponent_pool")


@dataclass
class RunResult:
    hand_records: List[HandRecord]
    log_paths: List[pathlib.Path]
    metrics_path: pathlib.Path
    per_hand_metrics_path: pathlib.Path
    metrics: Dict[str, Any]


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

    def __init__(self, config: SeriesConfig, output_dir: str | pathlib.Path) -> None:
        self.config = config
        self.output_dir = pathlib.Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.engine_config = EngineConfig(
            seat_count=2 if config.mode == "hu" else 6,
            small_blind=config.blinds["sb"],
            big_blind=config.blinds["bb"],
            starting_stack=config.starting_stack,
            table_id=f"green-{config.mode}",
        )

    def run(self, agent) -> RunResult:
        print(f"[BenchmarkRunner] Starting run for {getattr(agent, 'name', 'agent')} in mode {self.config.mode}")
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
        return RunResult(records, log_paths, metrics_path, per_hand_path, metrics)

    def _run_hu(self, agent) -> Tuple[List[HandRecord], List[pathlib.Path]]:
        assert self.config.opponent_mix is not None
        assert self.config.replicas is not None
        assert self.config.hands_per_seed is not None

        opponent_cycle = self._assignment_cycle(self.config.opponent_mix)
        records: List[HandRecord] = []
        log_paths: List[pathlib.Path] = []

        for seed_idx, seed in enumerate(self.config.seeds):
            opponent_name = opponent_cycle[seed_idx % len(opponent_cycle)]
            print(f"[BenchmarkRunner] HU seed {seed} vs {opponent_name}")
            for replica_id in range(self.config.replicas):
                if replica_id % 2 == 0:
                    agent_seat = 0
                    opponent_seat = 1
                    button_seat = agent_seat
                else:
                    agent_seat = 1
                    opponent_seat = 0
                    button_seat = opponent_seat

                log_path = (
                    self.output_dir
                    / "logs"
                    / "hu"
                    / opponent_name
                    / f"seed{seed}_rep{replica_id}.ndjson"
                )
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_paths.append(log_path)

                with NDJSONLogger(log_path) as logger:
                    engine = HoldemEngine(self.engine_config, logger)
                    agent_iface = AgentInterface(agent, agent_seat)
                    opponent_instance = make_baseline(opponent_name)
                    opponent_iface = AgentInterface(opponent_instance, opponent_seat)
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

                        deltas = engine.play_hand(
                            seed=seed,
                            hand_index=hand_index,
                            replica_id=replica_id,
                            button_seat=button_seat,
                            players=players,
                            agents={agent_seat: agent_iface, opponent_seat: opponent_iface},
                            deck=deck,
                        )

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
        return records, log_paths

    def _run_sixmax(self, agent) -> Tuple[List[HandRecord], List[pathlib.Path]]:
        assert self.config.opponent_pool is not None
        assert self.config.hands_per_replica is not None
        assert self.config.seat_replicas is not None

        records: List[HandRecord] = []
        log_paths: List[pathlib.Path] = []

        for seed in self.config.seeds:
            print(f"[BenchmarkRunner] 6-max seed {seed}")
            lineup = self._build_lineup(seed, self.config.opponent_pool)
            base_assignment = ["agent", *lineup]
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
                    agent_seat = 0
                    for seat, label in enumerate(rotated):
                        if label == "agent":
                            iface = AgentInterface(agent, seat)
                            agent_seat = seat
                        else:
                            baseline = make_baseline(label)
                            iface = AgentInterface(baseline, seat)
                        interfaces[seat] = iface
                        players[seat] = PlayerRuntimeState(
                            seat_id=seat,
                            name=iface.name,
                            stack=self.engine_config.starting_stack,
                        )

                    for hand_index in range(self.config.hands_per_replica):
                        print(
                            f"[BenchmarkRunner] 6-max hand seed={seed} replica={replica_id} hand_index={hand_index}"
                        )
                        deck = build_deck_from_seed(seed, hand_index, 0)
                        button_seat = (seed + hand_index) % self.engine_config.seat_count
                        positions = seat_positions(self.engine_config.seat_count, button_seat)
                        prev_timeouts = {seat: players[seat].timeouts for seat in players}
                        prev_illegal = {seat: players[seat].illegal_actions for seat in players}

                        deltas = engine.play_hand(
                            seed=seed,
                            hand_index=hand_index,
                            replica_id=replica_id,
                            button_seat=button_seat,
                            players=players,
                            agents=interfaces,
                            deck=deck,
                        )

                        post_timeouts = {seat: players[seat].timeouts for seat in players}
                        post_illegal = {seat: players[seat].illegal_actions for seat in players}

                        for seat, iface in interfaces.items():
                            records.append(
                                HandRecord(
                                    player=iface.name,
                                    opponent="mix" if seat == agent_seat else interfaces[agent_seat].name,
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
                log_paths.append(log_path)
        return records, log_paths

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

    def _rotate_assignment(self, assignment: List[str], replica_id: int) -> List[str]:
        shift = -(replica_id % len(assignment))
        return assignment[shift:] + assignment[:shift]
