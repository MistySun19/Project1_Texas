"""
Metrics aggregation utilities for the Green Agent Benchmark.
"""

from __future__ import annotations

import json
import math
import pathlib
import statistics
from collections import defaultdict
from typing import Any, Dict, Iterable, Mapping, Sequence, List


def aggregate_run_metrics(
    hand_records: Sequence[Mapping[str, Any]],
    log_paths: Sequence[pathlib.Path],
    big_blind: int,
) -> Dict[str, Any]:
    grouped: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for record in hand_records:
        grouped[record["player"]].append(record)

    behavior_map = _parse_behavior_from_logs(log_paths)

    results: Dict[str, Any] = {}
    for player, records in grouped.items():
        results[player] = _aggregate_player_metrics(records, big_blind, behavior_map.get(player, {}))
    return results


def _aggregate_player_metrics(
    records: Sequence[Mapping[str, Any]],
    big_blind: int,
    behavior: Mapping[str, Any],
) -> Dict[str, Any]:
    total_hands = len(records)
    total_delta = sum(int(record["delta"]) for record in records)
    total_bb = total_delta / big_blind if big_blind else 0.0
    bb_per_100 = (total_bb / total_hands) * 100 if total_hands else 0.0

    timeouts = sum(int(record.get("timeouts", 0)) for record in records)
    illegal = sum(int(record.get("illegal_actions", 0)) for record in records)

    per_seed = defaultdict(lambda: {"delta": 0, "hands": 0})
    for record in records:
        seed = record["seed"]
        per_seed[seed]["delta"] += int(record["delta"])
        per_seed[seed]["hands"] += 1

    per_seed_rates = []
    for data in per_seed.values():
        if data["hands"]:
            seed_bb = data["delta"] / big_blind if big_blind else 0.0
            per_seed_rates.append((seed_bb / data["hands"]) * 100)

    if len(per_seed_rates) > 1:
        stdev = statistics.stdev(per_seed_rates)
        se = stdev / math.sqrt(len(per_seed_rates))
        ci_low = bb_per_100 - 1.96 * se
        ci_high = bb_per_100 + 1.96 * se
    else:
        ci_low = ci_high = bb_per_100

    match_points = 0
    if ci_low > 0:
        match_points = 1
    elif ci_high < 0:
        match_points = -1

    behavior_stats = _behaviour_to_summary(behavior, total_hands)

    return {
        "hands": total_hands,
        "total_delta_chips": total_delta,
        "bb_per_100": bb_per_100,
        "bb_per_100_ci": [ci_low, ci_high],
        "match_points": match_points,
        "timeouts": {
            "count": timeouts,
            "per_hand": timeouts / total_hands if total_hands else 0.0,
        },
        "illegal_actions": {
            "count": illegal,
            "per_hand": illegal / total_hands if total_hands else 0.0,
        },
        "behavior": behavior_stats,
    }


def _parse_behavior_from_logs(log_paths: Sequence[pathlib.Path]) -> Dict[str, Dict[str, Any]]:
    per_player: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "hands": 0,
            "vpip": 0,
            "pfr": 0,
            "saw_flop": 0,
            "went_sd": 0,
            "postflop_raises": 0,
            "postflop_calls": 0,
            "decision_times": [],
        }
    )

    for path in log_paths:
        if not path.exists():
            continue
        hand_states: Dict[str, Dict[int, Dict[str, Any]]] = {}
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                event = json.loads(line)
                payload = event.get("payload", {})
                hand_id = payload.get("hand_id")

                if event["type"] == "hand_start":
                    seats = {int(seat): info for seat, info in payload.get("seats", {}).items()}
                    hand_states[hand_id] = {}
                    for seat, info in seats.items():
                        name = info.get("name", f"seat-{seat}")
                        hand_states[hand_id][seat] = {
                            "player": name,
                            "vpip": False,
                            "pfr": False,
                            "postflop_calls": 0,
                            "postflop_raises": 0,
                            "saw_flop": False,
                            "went_sd": False,
                            "folded": False,
                            "decision_times": [],
                        }
                        per_player[name]["hands"] += 1

                elif hand_id and hand_id in hand_states:
                    states = hand_states[hand_id]
                    if event["type"] == "street_transition":
                        if payload.get("street") == "flop":
                            for state in states.values():
                                if not state["folded"]:
                                    state["saw_flop"] = True
                    elif event["type"] == "action":
                        seat = payload.get("seat")
                        if seat not in states:
                            continue
                        state = states[seat]
                        action = payload.get("action")
                        street = payload.get("street")
                        to_call = payload.get("to_call", 0)
                        elapsed = payload.get("elapsed_ms")
                        if isinstance(elapsed, (int, float)):
                            state["decision_times"].append(elapsed)
                        if street == "preflop":
                            if action in {"call", "raise_to"} and (to_call > 0 or action == "raise_to"):
                                state["vpip"] = True
                            if action == "raise_to":
                                state["pfr"] = True
                        else:
                            if action == "raise_to":
                                state["postflop_raises"] += 1
                            elif action == "call":
                                state["postflop_calls"] += 1
                        if action == "fold":
                            state["folded"] = True
                    elif event["type"] == "showdown":
                        for seat, state in states.items():
                            if not state["folded"]:
                                state["went_sd"] = True
                    elif event["type"] == "hand_end":
                        states = hand_states.pop(hand_id, {})
                        for state in states.values():
                            name = state["player"]
                            agg = per_player[name]
                            if state["vpip"]:
                                agg["vpip"] += 1
                            if state["pfr"]:
                                agg["pfr"] += 1
                            if state["saw_flop"]:
                                agg["saw_flop"] += 1
                            if state["went_sd"]:
                                agg["went_sd"] += 1
                            agg["postflop_raises"] += state["postflop_raises"]
                            agg["postflop_calls"] += state["postflop_calls"]
                            agg["decision_times"].extend(state["decision_times"])
        for states in hand_states.values():
            for state in states.values():
                name = state["player"]
                agg = per_player[name]
                if state["vpip"]:
                    agg["vpip"] += 1
                if state["pfr"]:
                    agg["pfr"] += 1
                if state["saw_flop"]:
                    agg["saw_flop"] += 1
                if state["went_sd"]:
                    agg["went_sd"] += 1
                agg["postflop_raises"] += state["postflop_raises"]
                agg["postflop_calls"] += state["postflop_calls"]
                agg["decision_times"].extend(state["decision_times"])

    return per_player


def _behaviour_to_summary(behavior: Mapping[str, Any], total_hands: int) -> Dict[str, Any]:
    hands = behavior.get("hands", total_hands)
    vpip_count = behavior.get("vpip", 0)
    pfr_count = behavior.get("pfr", 0)
    saw_flop_count = behavior.get("saw_flop", 0)
    went_sd_count = behavior.get("went_sd", 0)
    postflop_raises = behavior.get("postflop_raises", 0)
    postflop_calls = behavior.get("postflop_calls", 0)
    decision_times = behavior.get("decision_times", [])

    af = postflop_raises / postflop_calls if postflop_calls else float(postflop_raises)
    mean_decision = (
        sum(decision_times) / len(decision_times) if decision_times else 0.0
    )

    return {
        "vpip": {
            "count": vpip_count,
            "rate": vpip_count / hands if hands else 0.0,
        },
        "pfr": {
            "count": pfr_count,
            "rate": pfr_count / hands if hands else 0.0,
        },
        "af": af,
        "wt_sd": {
            "count": went_sd_count,
            "rate": (went_sd_count / saw_flop_count) if saw_flop_count else 0.0,
        },
        "postflop": {
            "raises": postflop_raises,
            "calls": postflop_calls,
        },
        "decision_time_ms": {
            "mean": mean_decision,
            "samples": len(decision_times),
        },
    }
