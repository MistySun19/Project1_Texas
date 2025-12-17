from __future__ import annotations

import logging
import os
from dataclasses import asdict
from typing import Any, Dict, Optional

from ..schemas import ActionRequest, ActionResponse
from ..agents.openai_base import _fallback_action
from ..white_agent.equity import estimate_equity
from ..white_agent.features import derived_metrics
from ..white_agent.llm import llm_decide, load_llm_config
from ..white_agent.models import DecisionState, normalize_state
from ..white_agent.policy import Decision, fallback_policy, pot_odds
from ..white_agent.ranges import bucket_from_vpip_pfr

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


def _primary_opponent_bucket(state: DecisionState) -> str:
    if not state.opponents_stats:
        return "medium"
    for _k, stats in state.opponents_stats.items():
        vpip = stats.get("vpip")
        pfr = stats.get("pfr")
        bucket, _aggr = bucket_from_vpip_pfr(vpip, pfr)
        return bucket
    return "medium"


def _opponents_count(state: DecisionState) -> int:
    if state.players_remaining and state.players_remaining >= 2:
        return max(state.players_remaining - 1, 1)
    return 1


def _hero_raised_this_street(state: DecisionState) -> bool:
    if state.hero_seat_id is None:
        return False
    for entry in state.action_history:
        try:
            if int(entry.get("seat_id", -1)) != int(state.hero_seat_id):
                continue
            if str(entry.get("street", "")) != str(state.street):
                continue
            if entry.get("action") == "raise_to":
                return True
        except Exception:
            continue
    return False


def _spr(state: DecisionState) -> Optional[float]:
    if state.hero_stack is None:
        return None
    denom = max(state.pot_size, 1)
    return float(state.hero_stack) / float(denom)


def _summarize_action_history(state: DecisionState, limit: int = 10) -> list[dict[str, object]]:
    items = []
    for entry in list(state.action_history)[-limit:]:
        if not isinstance(entry, dict):
            continue
        items.append(
            {
                "seat_id": entry.get("seat_id"),
                "street": entry.get("street"),
                "action": entry.get("action"),
                "amount": entry.get("amount"),
            }
        )
    return items


def build_llm_context(
    state: DecisionState,
    *,
    equity_tight: float,
    equity_medium: float,
    equity_loose: float,
    equity_samples: int,
    equity_seed: int,
    baseline: Decision,
) -> Dict[str, Any]:
    profiles = {}
    for opp, stats in (state.opponents_stats or {}).items():
        vpip = stats.get("vpip")
        pfr = stats.get("pfr")
        bucket, aggressive = bucket_from_vpip_pfr(vpip, pfr)
        profiles[str(opp)] = {
            "vpip": vpip,
            "pfr": pfr,
            "range_bucket": bucket,
            "aggressive": aggressive,
        }

    legal = state.legal
    spr = _spr(state)
    derived = derived_metrics(state)
    po = pot_odds(state.pot_size, state.to_call)
    return {
        "hand_id": state.hand_id,
        "blinds": {"sb": state.sb, "bb": state.bb},
        "seat_count": state.seat_count,
        "button_seat": state.button_seat,
        "street": state.street,
        "position": state.position,
        "players_remaining": state.players_remaining,
        "hero_hole_cards": list(state.hero_hole_cards),
        "board_cards": list(state.board_cards),
        "pot_size": state.pot_size,
        "to_call": state.to_call,
        "hero_stack": state.hero_stack,
        "stacks": {int(k): int(v) for k, v in (state.stacks or {}).items()} if isinstance(state.stacks, dict) else {},
        "pot_odds": po,
        "required_equity_to_call": po,
        "equity_edge_medium_minus_required": (equity_medium - po),
        "spr": spr,
        "derived_metrics": derived,
        "hero_already_raised_this_street": _hero_raised_this_street(state),
        "recent_action_history": _summarize_action_history(state, limit=10),
        "equity": {
            "tight": equity_tight,
            "medium": equity_medium,
            "loose": equity_loose,
            "samples": equity_samples,
            "seed": equity_seed,
        },
        "opponent_profile": profiles or {"default": {"range_bucket": "medium"}},
        "baseline_suggestion": {
            "action_type": baseline.action,
            "amount": baseline.amount,
            "note": baseline.reason,
        },
        "legal_actions": {
            "actions": list(legal.actions),
            "call_amount": legal.call_amount,
            "raise_sizes": list(legal.raise_sizes),
            "min_raise_to": legal.min_raise_to,
            "max_raise_to": legal.max_raise_to,
        },
        "response_schema": {"action_type": "fold|check|call|raise_to|all_in", "amount": "int|null"},
    }


class WhiteAgent:
    name = "white-agent"

    def __init__(
        self,
        *,
        equity_samples: Optional[int] = None,
        margin: Optional[float] = None,
        log_decisions: bool = True,
    ) -> None:
        self.equity_samples = equity_samples if equity_samples is not None else _env_int("WHITE_EQUITY_SAMPLES", 600)
        self.margin = margin if margin is not None else _env_float("WHITE_MARGIN", 0.05)
        self.log_decisions = log_decisions
        self._llm_config = load_llm_config()

    def reset(self, seat_id: int, table_config: dict) -> None:
        del seat_id, table_config

    def act(self, request: ActionRequest) -> ActionResponse:
        payload = asdict(request)
        response = self.act_from_payload(payload, force_legal_actions=list(request.legal_actions))
        if response.action not in request.legal_actions:
            return _fallback_action(request)
        return response

    def act_from_payload(
        self,
        payload: Dict[str, Any],
        *,
        force_legal_actions: Optional[List[str]] = None,
    ) -> ActionResponse:
        """
        Entry point for non-engine callers (e.g. A2A servers) that receive raw JSON.

        `force_legal_actions` (when provided) is used as the authoritative action space
        to guarantee legality even if the incoming state is missing fields.
        """
        if force_legal_actions is not None:
            payload = dict(payload)
            payload["legal_actions"] = list(force_legal_actions)

        state, warnings = normalize_state(payload)
        if warnings:
            logger.warning("[WhiteAgent] normalize warnings=%s", warnings)

        try:
            opponents = _opponents_count(state)
            eq_tight = estimate_equity(
                state.hero_hole_cards,
                state.board_cards,
                "tight",
                self.equity_samples,
                seed_material=state.rng_tag + ":tight",
                opponents=opponents,
            )
            eq_medium = estimate_equity(
                state.hero_hole_cards,
                state.board_cards,
                "medium",
                self.equity_samples,
                seed_material=state.rng_tag + ":medium",
                opponents=opponents,
            )
            eq_loose = estimate_equity(
                state.hero_hole_cards,
                state.board_cards,
                "loose",
                self.equity_samples,
                seed_material=state.rng_tag + ":loose",
                opponents=opponents,
            )
        except Exception as exc:
            logger.exception("[WhiteAgent] equity estimation failed: %s", exc)
            return _fallback_action(request)

        baseline = fallback_policy(state, equity_medium=eq_medium.equity, margin=self.margin)
        context = build_llm_context(
            state,
            equity_tight=eq_tight.equity,
            equity_medium=eq_medium.equity,
            equity_loose=eq_loose.equity,
            equity_samples=eq_medium.samples,
            equity_seed=eq_medium.seed,
            baseline=baseline,
        )

        opponent_bucket = _primary_opponent_bucket(state)
        context["assumed_primary_opponent_bucket"] = opponent_bucket

        try:
            decision = llm_decide(state, context, baseline, self._llm_config)
        except Exception as exc:
            logger.exception("[WhiteAgent] LLM decision failed: %s", exc)
            decision = Decision(
                action=baseline.action,
                amount=baseline.amount,
                reason=f"llm_error -> baseline ({baseline.reason})",
                debug={"error": str(exc)},
            )

        # Final refinement step to reduce over-aggression and variance.
        decision = self._refine_decision(
            state=state,
            proposed=decision,
            baseline=baseline,
            equity_medium=eq_medium.equity,
            equity_tight=eq_tight.equity,
        )

        if self.log_decisions:
            spr_now = _spr(state)
            logger.info(
                "[WhiteAgent] hand=%s street=%s pot=%s to_call=%s spr=%s legal=%s eq(m)=%.3f po=%.3f -> %s %s | %s",
                state.rng_tag,
                state.street,
                state.pot_size,
                state.to_call,
                (f"{spr_now:.2f}" if spr_now is not None else "n/a"),
                list(state.legal.actions),
                eq_medium.equity,
                pot_odds(state.pot_size, state.to_call),
                decision.action,
                decision.amount if decision.amount is not None else "",
                decision.reason,
            )

        legal_set = set(state.legal.actions)
        if force_legal_actions is not None:
            legal_set = {a if a != "raise" else "raise_to" for a in force_legal_actions}

        if decision.action not in legal_set:
            return self._fallback_from_state(state, legal_set)
        if decision.action == "raise_to":
            if decision.amount is None:
                return self._fallback_from_state(state, legal_set)
            return ActionResponse(action="raise_to", amount=int(decision.amount), metadata={"reason": decision.reason})
        return ActionResponse(action=decision.action, metadata={"reason": decision.reason})

    def _fallback_from_state(self, state: DecisionState, legal_set: set[str]) -> ActionResponse:
        if "check" in legal_set and state.to_call <= 0:
            return ActionResponse(action="check", metadata={"reason": "fallback_check"})
        if "call" in legal_set and state.to_call > 0:
            return ActionResponse(action="call", metadata={"reason": "fallback_call"})
        if "call" in legal_set and state.to_call <= 0:
            return ActionResponse(action="call", metadata={"reason": "fallback_call_free"})
        return ActionResponse(action="fold", metadata={"reason": "fallback_fold"})

    def _refine_decision(
        self,
        *,
        state: DecisionState,
        proposed: Decision,
        baseline: Decision,
        equity_medium: float,
        equity_tight: float,
    ) -> Decision:
        """
        Conservative verifier/refiner that reduces high-variance aggression.

        Rationale: In practice we observed very high postflop AF (many raises, few calls).
        This step applies simple gates using equity/pot-odds/hand history to keep the
        policy closer to stable poker heuristics while preserving legality.
        """
        legal = state.legal
        po = pot_odds(state.pot_size, state.to_call)
        already_raised = _hero_raised_this_street(state)

        # If raising is not legal, force baseline.
        if proposed.action == "raise_to" and "raise_to" not in legal.actions:
            return Decision(
                action=baseline.action,
                amount=baseline.amount,
                reason=f"{baseline.reason} | refined:no_raise_available",
                debug=proposed.debug,
            )

        # Avoid “auto-betting” when checked to unless we are clearly strong.
        if proposed.action == "raise_to" and state.to_call <= 0:
            bet_gate = 0.70
            if already_raised and equity_medium < 0.85:
                return Decision(action="check", amount=None, reason="refined:avoid_multi_bet_same_street", debug=proposed.debug)
            if equity_medium < bet_gate and equity_tight < 0.65:
                return Decision(action="check", amount=None, reason="refined:check_marginal_when_free", debug=proposed.debug)

        # Facing a bet: only raise when comfortably above pot odds (or baseline already wants to raise).
        if proposed.action == "raise_to" and state.to_call > 0:
            raise_gate = max(po + self.margin + 0.10, 0.60)
            if equity_medium < raise_gate and baseline.action != "raise_to":
                # Prefer call over raise when marginal.
                if "call" in legal.actions:
                    return Decision(action="call", amount=None, reason="refined:call_instead_of_marginal_raise", debug=proposed.debug)
                return baseline

        # Cap raise size when not extremely strong to reduce variance.
        if proposed.action == "raise_to" and proposed.amount is not None and legal.raise_sizes:
            if equity_medium < 0.80:
                # Prefer the ~0.5 pot size if available, else min raise.
                target = legal.raise_sizes[1] if len(legal.raise_sizes) >= 2 else legal.raise_sizes[0]
                if proposed.amount != target:
                    return Decision(
                        action="raise_to",
                        amount=target,
                        reason=f"{proposed.reason} | refined:cap_raise_size",
                        debug=proposed.debug,
                    )

        return proposed
