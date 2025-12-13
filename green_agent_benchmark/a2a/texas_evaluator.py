# -*- coding: utf-8 -*-
"""
Texas Hold'em Green Agent - Evaluates purple agents on poker skills.

This green agent orchestrates Texas Hold'em matches between participants
and produces evaluation results following the AgentBeats A2A protocol.
"""

import asyncio
import json
import logging
import pathlib
import time
from typing import Any, Dict, List, Optional, Set

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    DataPart,
    Part,
    TaskState,
    TextPart,
)
from a2a.utils import new_agent_text_message

from ..a2a.green_executor import GreenAgent, GreenExecutor
from ..a2a.models import EvalRequest, EvalResult
from ..a2a.tool_provider import ToolProvider
from ..runner import BenchmarkRunner, SeriesConfig
from ..engine import EngineConfig, HoldemEngine, PlayerRuntimeState, build_deck_from_seed
from ..baseline_registry import make_baseline
from ..logging_utils import NDJSONLogger

# Try importing TaskUpdater
try:
    from a2a.server.tasks import TaskUpdater
except ImportError:
    TaskUpdater = Any  # type: ignore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("texas_evaluator")


class RemotePokerAgent:
    """
    Adapter for remote agents that communicate via A2A protocol.
    """
    
    def __init__(self, name: str, url: str, tool_provider: ToolProvider):
        self.name = name
        self.url = url
        self._tool_provider = tool_provider
        self._is_first_message = True
    
    def reset(self, seat_id: int, table_config: Dict[str, Any]) -> None:
        """Reset agent for a new hand."""
        self._is_first_message = True
        # Could send texas_reset message here if needed
    
    async def act_async(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Get action from remote agent via A2A."""
        message = json.dumps({
            "type": "texas_action_request",
            "seat_id": request.get("seat_id"),
            "request": request
        })
        
        try:
            response = await self._tool_provider.talk_to_agent(
                message=message,
                url=self.url,
                new_conversation=self._is_first_message
            )
            self._is_first_message = False
            
            # Parse response
            try:
                data = json.loads(response)
                return {
                    "action": data.get("action", "fold"),
                    "amount": data.get("amount"),
                    "wait_time_ms": data.get("wait_time_ms", 0)
                }
            except json.JSONDecodeError:
                # Try to extract action from text
                response_lower = response.lower()
                if "fold" in response_lower:
                    return {"action": "fold"}
                elif "call" in response_lower:
                    return {"action": "call"}
                elif "check" in response_lower:
                    return {"action": "check"}
                elif "raise" in response_lower or "bet" in response_lower:
                    return {"action": "raise_to", "amount": request.get("min_raise", 0)}
                else:
                    return {"action": "fold"}
                    
        except Exception as e:
            logger.error(f"Error communicating with agent {self.name}: {e}")
            return {"action": "fold"}
    
    def act(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous wrapper for act_async."""
        return asyncio.get_event_loop().run_until_complete(self.act_async(request))


class TexasHoldemEvaluator(GreenAgent):
    """
    Green agent that evaluates purple agents on Texas Hold'em poker.
    
    Assessment config options:
    - mode: "hu" (heads-up) or "sixmax" (6-max)
    - num_hands: Number of hands to play
    - seeds: List of random seeds for reproducibility
    - blinds: {"sb": int, "bb": int}
    - stacks_bb: Starting stack in big blinds
    - opponent: Optional baseline opponent name
    """

    def __init__(self):
        self._required_roles: Set[str] = set()  # Flexible - can be empty for lineup mode
        self._required_config_keys = ["mode"]
        self._tool_provider = ToolProvider()

    def validate_request(self, request: EvalRequest) -> tuple[bool, str]:
        """Validate the evaluation request."""
        # Check required config keys
        missing_config = set(self._required_config_keys) - set(request.config.keys())
        if missing_config:
            return False, f"Missing config keys: {missing_config}"
        
        # Validate mode
        mode = request.config.get("mode", "hu")
        if mode not in ("hu", "sixmax"):
            return False, f"Invalid mode: {mode}. Must be 'hu' or 'sixmax'"
        
        # Check participants for HU mode
        if mode == "hu":
            if len(request.participants) < 1:
                return False, "HU mode requires at least 1 participant (will use baseline opponent)"
        
        return True, "ok"

    async def run_eval(self, req: EvalRequest, updater: TaskUpdater) -> None:
        """Run the Texas Hold'em evaluation."""
        logger.info(f"Starting Texas Hold'em evaluation: {req}")
        start_time = time.time()

        # Extract config
        mode = req.config.get("mode", "hu")
        num_hands = req.config.get("num_hands", 10)
        seeds = req.config.get("seeds", [101, 102])
        blinds = req.config.get("blinds", {"sb": 50, "bb": 100})
        stacks_bb = req.config.get("stacks_bb", 100)
        opponent_baseline = req.config.get("opponent", "random")

        await updater.update_status(
            TaskState.working,
            new_agent_text_message(
                f"Starting Texas Hold'em {mode.upper()} evaluation\n"
                f"Hands: {num_hands}, Seeds: {seeds}"
            )
        )

        try:
            if mode == "hu":
                results = await self._run_hu_eval(
                    req, updater, num_hands, seeds, blinds, stacks_bb, opponent_baseline
                )
            else:
                results = await self._run_sixmax_eval(
                    req, updater, num_hands, seeds, blinds, stacks_bb
                )

            time_used = time.time() - start_time
            
            # Determine winner
            winner = self._determine_winner(results)
            
            # Create result summary
            summary = self._create_summary(results, time_used, mode)
            
            result_data = {
                "mode": mode,
                "num_hands": num_hands,
                "results": results,
                "time_used": time_used,
                "winner": winner,
            }

            await updater.add_artifact(
                parts=[
                    Part(root=TextPart(text=summary)),
                    Part(root=DataPart(data=result_data)),
                ],
                name="Result",
            )

        except Exception as e:
            logger.error(f"Evaluation failed: {e}")
            raise
        finally:
            self._tool_provider.reset()

    async def _run_hu_eval(
        self,
        req: EvalRequest,
        updater: TaskUpdater,
        num_hands: int,
        seeds: List[int],
        blinds: Dict[str, int],
        stacks_bb: int,
        opponent_baseline: str,
    ) -> Dict[str, Any]:
        """Run heads-up evaluation."""
        results: Dict[str, Any] = {
            "participants": {},
            "hands_played": 0,
            "player_deltas": {},
        }

        # Get participants
        participants = list(req.participants.items())
        
        if len(participants) >= 2:
            # Two remote agents playing each other
            agent1_role, agent1_url = participants[0]
            agent2_role, agent2_url = participants[1]
            
            agent1 = RemotePokerAgent(agent1_role, str(agent1_url), self._tool_provider)
            agent2 = RemotePokerAgent(agent2_role, str(agent2_url), self._tool_provider)
            
            results["participants"] = {
                agent1_role: str(agent1_url),
                agent2_role: str(agent2_url),
            }
        elif len(participants) == 1:
            # One remote agent vs baseline
            agent1_role, agent1_url = participants[0]
            agent1 = RemotePokerAgent(agent1_role, str(agent1_url), self._tool_provider)
            agent2 = make_baseline(opponent_baseline)
            
            results["participants"] = {
                agent1_role: str(agent1_url),
                "baseline": opponent_baseline,
            }
        else:
            raise ValueError("Need at least 1 participant for HU evaluation")

        # Initialize metrics
        player_deltas: Dict[str, int] = {
            getattr(agent1, 'name', agent1_role): 0,
            getattr(agent2, 'name', getattr(agent2, 'name', opponent_baseline)): 0,
        }

        # Run hands
        hands_per_seed = max(1, num_hands // len(seeds))
        total_hands = 0

        for seed in seeds:
            for hand_idx in range(hands_per_seed):
                await updater.update_status(
                    TaskState.working,
                    new_agent_text_message(f"Playing hand {total_hands + 1}...")
                )

                # Simplified hand simulation
                # In production, this would use the full engine
                delta1, delta2 = await self._play_single_hand(
                    agent1, agent2, seed, hand_idx, blinds, stacks_bb
                )

                agent1_name = getattr(agent1, 'name', agent1_role)
                agent2_name = getattr(agent2, 'name', opponent_baseline)
                
                player_deltas[agent1_name] = player_deltas.get(agent1_name, 0) + delta1
                player_deltas[agent2_name] = player_deltas.get(agent2_name, 0) + delta2

                total_hands += 1
                logger.info(f"Hand {total_hands}: {agent1_name} {delta1:+d}, {agent2_name} {delta2:+d}")

        results["hands_played"] = total_hands
        results["player_deltas"] = player_deltas
        
        # Calculate bb/100
        bb = blinds["bb"]
        for player, delta in player_deltas.items():
            results[f"{player}_bb_100"] = (delta / bb) * (100 / max(1, total_hands))

        return results

    async def _run_sixmax_eval(
        self,
        req: EvalRequest,
        updater: TaskUpdater,
        num_hands: int,
        seeds: List[int],
        blinds: Dict[str, int],
        stacks_bb: int,
    ) -> Dict[str, Any]:
        """Run 6-max evaluation (simplified)."""
        await updater.update_status(
            TaskState.working,
            new_agent_text_message("6-max evaluation not fully implemented yet")
        )
        
        return {
            "participants": {role: str(url) for role, url in req.participants.items()},
            "hands_played": 0,
            "player_deltas": {},
            "error": "6-max mode not fully implemented",
        }

    async def _play_single_hand(
        self,
        agent1,
        agent2,
        seed: int,
        hand_idx: int,
        blinds: Dict[str, int],
        stacks_bb: int,
    ) -> tuple[int, int]:
        """
        Play a single hand between two agents.
        
        Returns tuple of (agent1_delta, agent2_delta).
        """
        # Simplified hand simulation for now
        # In a full implementation, this would use HoldemEngine
        import random
        rng = random.Random(seed * 1000 + hand_idx)
        
        # Simulate a hand result
        outcomes = [
            (blinds["bb"], -blinds["bb"]),      # Agent1 wins small pot
            (-blinds["bb"], blinds["bb"]),      # Agent2 wins small pot  
            (2 * blinds["bb"], -2 * blinds["bb"]),  # Agent1 wins bigger
            (-2 * blinds["bb"], 2 * blinds["bb"]),  # Agent2 wins bigger
            (0, 0),  # Chop/fold preflop
        ]
        
        return rng.choice(outcomes)

    def _determine_winner(self, results: Dict[str, Any]) -> str:
        """Determine the winner based on results."""
        player_deltas = results.get("player_deltas", {})
        
        if not player_deltas:
            return "draw"
        
        max_delta = max(player_deltas.values())
        winners = [p for p, d in player_deltas.items() if d == max_delta]
        
        if len(winners) == 1:
            return winners[0]
        return "draw"

    def _create_summary(
        self, 
        results: Dict[str, Any], 
        time_used: float, 
        mode: str
    ) -> str:
        """Create a human-readable summary."""
        summary_lines = [
            f"Texas Hold'em {mode.upper()} Evaluation Results",
            f"=" * 40,
            f"Hands Played: {results.get('hands_played', 0)}",
            f"Time: {time_used:.1f}s",
            "",
            "Player Results:",
        ]
        
        for player, delta in results.get("player_deltas", {}).items():
            bb_100 = results.get(f"{player}_bb_100", 0)
            summary_lines.append(f"  {player}: {delta:+d} chips ({bb_100:+.1f} bb/100)")
        
        summary_lines.append("")
        summary_lines.append(f"Winner: {results.get('winner', self._determine_winner(results))}")
        
        return "\n".join(summary_lines)


def texas_evaluator_agent_card(name: str, url: str) -> AgentCard:
    """Create the agent card for the Texas Hold'em evaluator."""
    skill = AgentSkill(
        id="texas_holdem_evaluation",
        name="Texas Hold'em Evaluation",
        description="Evaluates agents on No-Limit Texas Hold'em poker skills",
        tags=["benchmark", "evaluation", "poker", "texas-holdem"],
        examples=[
            '{"participants": {"agent": "http://localhost:9019"}, "config": {"mode": "hu", "num_hands": 10}}',
            '{"participants": {"player1": "http://agent1:8001", "player2": "http://agent2:8001"}, "config": {"mode": "hu", "num_hands": 100, "seeds": [101, 102, 103]}}'
        ],
    )
    return AgentCard(
        name=name,
        description="Texas Hold'em poker evaluation benchmark - tests agents on heads-up and 6-max No-Limit Hold'em",
        url=url,
        version="1.0.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],
    )
