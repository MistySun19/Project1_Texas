"""
AgentBeats executor for orchestrating Texas Hold'em battles.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import pathlib
import sys
import time
from dataclasses import replace
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from ..runner import BenchmarkRunner, SeriesConfig

logger = logging.getLogger(__name__)

# Ensure the vendored AgentBeats sources are importable.
AGENTBEATS_SRC = pathlib.Path(__file__).resolve().parents[2] / "agentbeats" / "src"
if AGENTBEATS_SRC.exists() and str(AGENTBEATS_SRC) not in sys.path:
    sys.path.insert(0, str(AGENTBEATS_SRC))

from agentbeats.agent_executor import AgentBeatsExecutor, BeatsAgent  # type: ignore  # noqa: E402
from agentbeats.logging import get_battle_context, get_battle_id, update_battle_process  # type: ignore  # noqa: E402
from agentbeats.logging.context import set_battle_context  # type: ignore  # noqa: E402
from agentbeats.logging.logging import log_error  # type: ignore  # noqa: E402
from a2a.server.apps import A2AStarletteApplication  # type: ignore  # noqa: E402
from a2a.server.tasks import TaskUpdater, InMemoryTaskStore  # type: ignore  # noqa: E402
from a2a.server.events import EventQueue  # type: ignore  # noqa: E402
from a2a.server.agent_execution import RequestContext  # type: ignore  # noqa: E402
from a2a.server.request_handlers import DefaultRequestHandler  # type: ignore  # noqa: E402
from a2a.types import AgentCard, Part, TextPart, TaskState  # type: ignore  # noqa: E402
from a2a.utils import new_agent_text_message, new_task  # type: ignore  # noqa: E402


def _default_seeds() -> List[int]:
    return [401, 501, 601, 701]


def _parse_seed_list(value: Optional[str]) -> Optional[List[int]]:
    if not value:
        return None
    result: List[int] = []
    for chunk in value.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            result.append(int(chunk))
        except ValueError:
            logger.warning("Ignoring invalid seed '%s' in TEXAS_AGENT_SEEDS", chunk)
    return result or None


class TexasAgentBeatsExecutor(AgentBeatsExecutor):
    """
    Agent executor that runs the Green Agent Benchmark when a battle starts.
    """

    def __init__(
        self,
        agent_card_json: Dict[str, Any],
        model_type: str,
        model_name: str,
        *,
        series_config_path: Optional[str] = None,
        config_overrides: Optional[Dict[str, Any]] = None,
        output_root: Optional[pathlib.Path] = None,
        mcp_url_list: Optional[List[str]] = None,
        tool_list: Optional[List[Any]] = None,
    ) -> None:
        super().__init__(
            agent_card_json=agent_card_json,
            model_type=model_type,
            model_name=model_name,
            mcp_url_list=mcp_url_list,
            tool_list=tool_list,
        )
        self.series_config_path = series_config_path
        self.config_overrides = config_overrides or {}
        self.output_root = (output_root or pathlib.Path("artifacts/agentbeats")).expanduser()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self._battle_tasks: Dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

        # Defaults can be overridden by environment variables.
        env_seeds = _parse_seed_list(os.getenv("TEXAS_AGENT_SEEDS"))
        if env_seeds:
            self.config_overrides.setdefault("seeds", env_seeds)
        env_hands = os.getenv("TEXAS_HANDS_PER_SEED")
        if env_hands and env_hands.isdigit():
            self.config_overrides.setdefault("hands_per_seed", int(env_hands))
        env_replicas = os.getenv("TEXAS_REPLICAS")
        if env_replicas and env_replicas.isdigit():
            self.config_overrides.setdefault("replicas", int(env_replicas))

    # ------------------------------------------------------------------
    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """
        Handle incoming A2A requests from AgentBeats.
        """
        task = context.current_task
        if task is None:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)

        await updater.update_status(
            TaskState.working,
            new_agent_text_message("", task.context_id, task.id),
        )

        raw_input = context.get_user_input()
        reply_text = None

        try:
            payload = json.loads(raw_input)
        except json.JSONDecodeError:
            # Fallback to generic agent handling (LLM prompt) if message is not JSON.
            reply_text = await self.invoke_agent(context)
        else:
            message_type = payload.get("type")
            if message_type == "battle_info":
                set_battle_context(
                    {
                        "frontend_agent_name": payload.get("agent_name"),
                        "agent_id": payload.get("agent_id"),
                        "battle_id": payload.get("battle_id"),
                        "backend_url": payload.get("backend_url"),
                    }
                )
                reply_text = "Texas green agent synced battle metadata."
            elif message_type == "battle_start":
                await self._handle_battle_start(payload)
                reply_text = "Texas Hold'em benchmark started; results will be reported via battle logs."
            else:
                reply_text = await self.invoke_agent(context)

        await updater.add_artifact(
            [Part(root=TextPart(text=reply_text or "Texas agent idle."))],
            name="response",
        )
        await updater.complete()

    # ------------------------------------------------------------------
    async def _handle_battle_start(self, payload: Dict[str, Any]) -> None:
        battle_id = payload.get("battle_id") or get_battle_id()
        if not battle_id:
            logger.error("Received battle_start without battle_id: %s", payload)
            return

        async with self._lock:
            existing = self._battle_tasks.get(battle_id)
            if existing and not existing.done():
                logger.warning(
                    "Battle %s already running; ignoring duplicate start signal",
                    battle_id,
                )
                return
            task = asyncio.create_task(self._run_battle(battle_id, payload))
            self._battle_tasks[battle_id] = task

    async def _run_battle(self, battle_id: str, payload: Dict[str, Any]) -> None:
        context = get_battle_context()
        backend_url = (context or {}).get("backend_url") or payload.get("backend_url")
        opponent_infos = payload.get("opponent_infos") or []
        task_config = payload.get("task_config") or payload.get("green_battle_context", {}).get("task_config")

        if not backend_url:
            logger.error("No backend URL available for battle %s", battle_id)
            return

        start_detail = {
            "battle_id": battle_id,
            "opponents": opponent_infos,
            "task_config": task_config,
        }
        await asyncio.to_thread(
            update_battle_process,
            battle_id,
            backend_url,
            "Starting Texas Hold'em evaluation.",
            detail=start_detail,
            reported_by="green_agent",
        )

        try:
            series_config = self._build_series_config(opponent_infos, task_config)
        except Exception as exc:
            logger.exception("Failed to build series config: %s", exc)
            await self._record_failure(
                battle_id,
                backend_url,
                f"Configuration error: {exc}",
            )
            return

        output_dir = self.output_root / battle_id

        def _progress_callback(event: Dict[str, Any]) -> None:
            event_type = event.get("type", "update")
            try:
                if event_type == "seed_start":
                    message = f"Seed {event.get('seed')} ({event.get('mode')}) starting."
                elif event_type == "replica_start":
                    message = (
                        f"Replica {event.get('replica')} for seed {event.get('seed')} "
                        f"({event.get('mode')}) starting."
                    )
                elif event_type == "hand_result":
                    players = event.get("players", [])
                    summary = ", ".join(
                        f"{p.get('name')} Δ {int(p.get('delta', 0)):+d}"
                        for p in players
                    )
                    message = (
                        f"Hand {event.get('hand_index')} result "
                        f"(seed {event.get('seed')}, replica {event.get('replica')}): {summary}"
                    )
                else:
                    message = f"Battle progress update ({event_type})."

                detail = json.loads(json.dumps(event, default=str))
                update_battle_process(
                    battle_id,
                    backend_url,
                    message,
                    detail=detail,
                    reported_by="green_agent",
                )
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error("Failed to post progress update: %s", exc)

        def run_series() -> Dict[str, Any]:
            runner = BenchmarkRunner(series_config, output_dir, progress_callback=_progress_callback)
            result = runner.run(agent=None)
            return {
                "metrics": result.metrics,
                "metrics_path": str(result.metrics_path),
                "per_hand_path": str(result.per_hand_metrics_path),
            }

        try:
            series_result = await asyncio.to_thread(run_series)
        except Exception as exc:  # pragma: no cover - runtime execution failure
            logger.exception("Texas benchmark failed: %s", exc)
            await self._record_failure(
                battle_id,
                backend_url,
                f"Benchmark execution failed: {exc}",
            )
            return
        finally:
            # Remove the task entry regardless of success/failure.
            async with self._lock:
                self._battle_tasks.pop(battle_id, None)

        metrics: Dict[str, Any] = series_result["metrics"]
        winner, summary = self._determine_winner(metrics)
        detail = {
            "metrics": summary,
            "artifacts": {
                "aggregate": series_result["metrics_path"],
                "per_hand": series_result["per_hand_path"],
                "output_dir": str(output_dir),
            },
        }

        await asyncio.to_thread(
            update_battle_process,
            battle_id,
            backend_url,
            "Texas Hold'em evaluation completed.",
            detail=detail,
            reported_by="green_agent",
        )

        await self._submit_result(
            battle_id=battle_id,
            backend_url=backend_url,
            winner=winner,
            detail=detail,
        )

    # ------------------------------------------------------------------
    async def _record_failure(self, battle_id: str, backend_url: str, message: str) -> None:
        await asyncio.to_thread(
            update_battle_process,
            battle_id,
            backend_url,
            "Texas Hold'em evaluation failed.",
            detail={"error": message},
            reported_by="green_agent",
        )
        context = get_battle_context()
        if context:
            await asyncio.to_thread(log_error, context, message)
        await self._submit_result(
            battle_id=battle_id,
            backend_url=backend_url,
            winner="draw",
            detail={"error": message},
            message="Battle ended with error.",
        )

    def _build_series_config(
        self,
        opponent_infos: List[Dict[str, Any]],
        task_config: Optional[str],
    ) -> SeriesConfig:
        if len(opponent_infos) != 2:
            raise ValueError(
                f"Texas Hold'em battles require exactly 2 opponents, got {len(opponent_infos)}"
            )

        if self.series_config_path:
            base_config = SeriesConfig.from_file(self.series_config_path)
        else:
            base_config = SeriesConfig(
                mode="hu",
                blinds={"sb": 50, "bb": 100},
                stacks_bb=100,
                seeds=_default_seeds(),
                hands_per_seed=50,
                replicas=2,
            )

        overrides = dict(self.config_overrides)
        overrides.update(self._parse_task_config(task_config))

        if "seeds" in overrides:
            seeds_value = overrides["seeds"]
            if isinstance(seeds_value, str):
                parsed = _parse_seed_list(seeds_value)
                if parsed:
                    overrides["seeds"] = parsed
            elif isinstance(seeds_value, list):
                overrides["seeds"] = [int(s) for s in seeds_value]

        # Apply overrides to the base config.
        base_config = replace(
            base_config,
            blinds=overrides.get("blinds", base_config.blinds),
            stacks_bb=int(overrides.get("stacks_bb", base_config.stacks_bb)),
            seeds=list(overrides.get("seeds", base_config.seeds)),
            hands_per_seed=int(
                overrides.get("hands_per_seed", base_config.hands_per_seed or 0)
            )
            or base_config.hands_per_seed,
            replicas=int(overrides.get("replicas", base_config.replicas or 0))
            or base_config.replicas,
        )

        lineup: List[str] = []
        for info in opponent_infos:
            url = info.get("agent_url")
            if not url:
                raise ValueError("Opponent info missing agent_url")
            display_name = info.get("name") or info.get("agent_name") or "remote_agent"
            lineup.append(
                f"baseline:agentbeats-remote-hu?url={quote_plus(url)}&name={quote_plus(display_name)}"
            )

        base_config.lineup = lineup
        base_config.validate()
        return base_config

    # ------------------------------------------------------------------
    def _determine_winner(self, metrics: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        summary: Dict[str, Any] = {}
        best_name = "draw"
        best_value = float("-inf")

        for name, stats in metrics.items():
            bb_per_100 = float(stats.get("bb_per_100", 0.0))
            summary[name] = {
                "bb_per_100": bb_per_100,
                "bb_per_100_ci": stats.get("bb_per_100_ci"),
                "hands": stats.get("hands"),
                "match_points": stats.get("match_points"),
                "timeouts": stats.get("timeouts"),
                "illegal_actions": stats.get("illegal_actions"),
            }

            if bb_per_100 > best_value + 1e-9:
                best_value = bb_per_100
                best_name = name
            elif abs(bb_per_100 - best_value) <= 1e-9:
                best_name = "draw"

        if best_name == "draw":
            return "draw", summary
        return best_name, summary

    async def _submit_result(
        self,
        battle_id: str,
        backend_url: str,
        winner: str,
        detail: Optional[Dict[str, Any]] = None,
        message: str = "Texas Hold'em evaluation complete.",
    ) -> None:
        payload = {
            "is_result": True,
            "winner": winner,
            "reported_by": "green_agent",
            "detail": detail or {},
            "message": message,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        await asyncio.to_thread(
            self._post_event,
            backend_url,
            battle_id,
            payload,
        )

    @staticmethod
    def _post_event(backend_url: str, battle_id: str, payload: Dict[str, Any]) -> None:
        import requests

        url = f"{backend_url.rstrip('/')}/battles/{battle_id}"
        try:
            requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
        except Exception as exc:  # pragma: no cover - network failure path
            logger.error("Failed to POST battle event to %s: %s", url, exc)

    @staticmethod
    def _parse_task_config(task_config: Optional[str]) -> Dict[str, Any]:
        if not task_config:
            return {}
        try:
            return json.loads(task_config) if isinstance(task_config, str) else {}
        except json.JSONDecodeError:
            logger.warning("task_config is not valid JSON: %s", task_config)
            return {}


class TexasBeatsAgent(BeatsAgent):
    """
    ``BeatsAgent`` subclass that wires in :class:`TexasAgentBeatsExecutor`.
    """

    def __init__(
        self,
        name: str,
        agent_host: str,
        agent_port: int,
        model_type: str,
        model_name: str,
        *,
        series_config_path: Optional[str] = None,
        config_overrides: Optional[Dict[str, Any]] = None,
        output_root: Optional[pathlib.Path] = None,
    ) -> None:
        super().__init__(name, agent_host, agent_port, model_type, model_name)
        self._series_config_path = series_config_path
        self._config_overrides = config_overrides or {}
        self._output_root = output_root

    def _make_app(self) -> None:
        executor = TexasAgentBeatsExecutor(
            agent_card_json=self.agent_card_json,
            model_type=self.model_type,
            model_name=self.model_name,
            series_config_path=self._series_config_path,
            config_overrides=self._config_overrides,
            output_root=self._output_root,
            mcp_url_list=self.mcp_url_list,
            tool_list=self.tool_list,
        )
        self.app = A2AStarletteApplication(
            agent_card=AgentCard(**self.agent_card_json),
            http_handler=DefaultRequestHandler(
                agent_executor=executor,
                task_store=InMemoryTaskStore(),
            ),
        ).build()
