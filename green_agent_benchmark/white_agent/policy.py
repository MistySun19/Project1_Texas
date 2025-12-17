from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .models import DecisionState, LegalActions


@dataclass(frozen=True, slots=True)
class Decision:
    action: str  # fold|check|call|raise_to
    amount: Optional[int]
    reason: str
    debug: Dict[str, Any]


def pot_odds(pot_size: int, to_call: int) -> float:
    if to_call <= 0:
        return 0.0
    denom = max(pot_size + to_call, 1)
    return float(to_call) / float(denom)


def clamp_to_raise_sizes(amount: int, legal: LegalActions) -> int:
    if not legal.raise_sizes:
        return legal.min_raise_to
    best = legal.raise_sizes[0]
    best_dist = abs(best - amount)
    for candidate in legal.raise_sizes[1:]:
        dist = abs(candidate - amount)
        if dist < best_dist or (dist == best_dist and candidate < best):
            best = candidate
            best_dist = dist
    return best


def fallback_policy(
    state: DecisionState,
    *,
    equity_medium: float,
    margin: float = 0.05,
) -> Decision:
    legal = state.legal
    po = pot_odds(state.pot_size, state.to_call)

    debug = {
        "equity_medium": equity_medium,
        "pot_odds": po,
        "margin": margin,
        "raise_sizes": list(legal.raise_sizes),
    }

    if state.to_call <= 0:
        # Betting when checked to is often high-variance; keep it conservative by default.
        if legal.allows("raise_to") and equity_medium >= 0.68 and legal.raise_sizes:
            # Prefer a small continuation/value bet size (closest to ~0.5 pot) when available.
            target = legal.raise_sizes[1] if len(legal.raise_sizes) >= 2 else legal.raise_sizes[0]
            return Decision(action="raise_to", amount=target, reason="small value/protection bet", debug=debug)
        if legal.allows("check"):
            return Decision(action="check", amount=None, reason="free check", debug=debug)
        if legal.allows("call"):
            return Decision(action="call", amount=None, reason="free call", debug=debug)
        return Decision(action="fold", amount=None, reason="no safe non-fold action", debug=debug)

    if equity_medium < po - margin:
        if legal.allows("fold"):
            return Decision(action="fold", amount=None, reason="negative EV call (equity < pot odds)", debug=debug)
        if legal.allows("check"):
            return Decision(action="check", amount=None, reason="cannot fold, check", debug=debug)
        return Decision(action="call", amount=None, reason="cannot fold, forced call", debug=debug)

    # Only raise when clearly above pot odds to avoid over-aggression.
    raise_gate = max(po + margin + 0.08, 0.55)
    if equity_medium >= raise_gate and legal.allows("raise_to") and legal.raise_sizes:
        # Prefer smaller sizes unless extremely strong.
        if equity_medium >= 0.80 and len(legal.raise_sizes) >= 3:
            target = legal.raise_sizes[2]
        elif len(legal.raise_sizes) >= 2:
            target = legal.raise_sizes[1]
        else:
            target = legal.raise_sizes[0]
        return Decision(action="raise_to", amount=target, reason="value raise (equity comfortably above pot odds)", debug=debug)

    if legal.allows("call"):
        return Decision(action="call", amount=None, reason="close spot, take the price", debug=debug)
    if legal.allows("check"):
        return Decision(action="check", amount=None, reason="close spot, check", debug=debug)
    return Decision(action="fold", amount=None, reason="no safe action", debug=debug)
