"""
Reusable base class for agents that call OpenAI-compatible chat APIs.

Providers such as OpenAI, DeepSeek, Moonshot (Kimi), and third-party hosts
expose an OpenAI-compatible `/responses` (or `/chat/completions`) endpoint.
This module implements the shared mechanics for converting Hold'em requests
into JSON prompts, invoking the API, and mapping responses back to
``ActionResponse`` instances.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    from openai import OpenAI
    from openai import RateLimitError
except ImportError:  # pragma: no cover - optional dependency
    OpenAI = None  # type: ignore
    RateLimitError = Exception  # type: ignore

from ..schemas import ActionRequest, ActionResponse


def _fallback_action(request: ActionRequest, wait_time_ms: int = 0) -> ActionResponse:
    """
    Deterministic safe fallback used when the model output cannot be parsed.
    """
    if "check" in request.legal_actions:
        return ActionResponse(action="check", wait_time_ms=wait_time_ms)
    if "call" in request.legal_actions:
        return ActionResponse(action="call", wait_time_ms=wait_time_ms)
    return ActionResponse(action="fold", wait_time_ms=wait_time_ms)


def _legal_raise_amount(request: ActionRequest, amount: int) -> int:
    """
    Clip the raise target into a legal amount (>= min_raise_to and <= stack cap).
    """
    min_raise = max(request.min_raise_to, request.to_call + request.blinds["bb"])
    max_raise = request.stacks[request.seat_id] + request.to_call + request.blinds["bb"]
    amount = max(amount, min_raise)
    amount = min(amount, max_raise)
    return amount


@dataclass
class OpenAICompatibleAgent:
    """
    Shared implementation for OpenAI-style poker agents.

    Parameters are intentionally generic so subclasses can adapt the defaults
    for their specific provider.
    """

    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: Optional[float] = None
    system_prompt: Optional[str] = None
    system_prompt_override: Optional[str] = None
    dry_run: bool = False
    name: Optional[str] = None
    use_responses: bool = True
    max_retries: int = 4
    retry_delay: float = 5.0

    env_prefix: str = field(default="OPENAI", init=False)
    default_model: str = field(default="gpt-5.0-mini", init=False)
    default_name: str = field(default="LLM", init=False)
    default_base_url: Optional[str] = field(default=None, init=False)
    metrics_path: Optional[str] = None
    metrics_summary: Optional[Dict[str, Any]] = field(default=None, init=False, repr=False)
    _seat_names: Dict[int, str] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        model_env = os.getenv(f"{self.env_prefix}_MODEL")
        api_key_env = os.getenv(f"{self.env_prefix}_API_KEY")
        base_env = os.getenv(f"{self.env_prefix}_API_BASE")

        self.model = self.model or model_env or self.default_model
        self.base_url = self.base_url or base_env or self.default_base_url
        self.name = self.name or self.default_name

        key = self.api_key or api_key_env
        if not self.dry_run and (OpenAI is None or key is None):
            raise RuntimeError(
                f"{self.name} agent requires the 'openai' package and a valid API key. "
                f"Set {self.env_prefix}_API_KEY or pass api_key=..."
            )

        if self.dry_run:
            self._client = None
        else:
            client_kwargs = {"api_key": key}
            if self.base_url:
                client_kwargs["base_url"] = self.base_url
            self._client = OpenAI(**client_kwargs)

        self._load_metrics()

    # --- lifecycle hooks -------------------------------------------------

    def reset(self, seat_id: int, table_config: Dict[str, Any]) -> None:
        del seat_id
        self._seat_names = {
            int(seat): str(name)
            for seat, name in (table_config.get("seat_names") or {}).items()
        }
        self._load_metrics()

    # --- internal helpers ------------------------------------------------

    def _load_metrics(self) -> None:
        metrics_path = self.metrics_path or os.getenv(f"{self.env_prefix}_METRICS_PATH")
        if not metrics_path:
            self.metrics_summary = None
            return
        try:
            with open(metrics_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            self.metrics_summary = None
            return
        except Exception as exc:
            print(f"[{self.name}Agent] Failed to load metrics from {metrics_path}: {exc}")
            self.metrics_summary = None
            return

        summary: Optional[Dict[str, Any]] = None
        if isinstance(data, dict):
            key = self.name or ""
            summary = data.get(key)
            if summary is None and key:
                lowered = key.lower()
                for candidate, stats in data.items():
                    if isinstance(candidate, str) and candidate.lower() == lowered:
                        summary = stats
                        break
        self.metrics_summary = summary if isinstance(summary, dict) else None

    # --- action selection ------------------------------------------------

    def act(self, request: ActionRequest) -> ActionResponse:
        debug_prefix = f"[{self.name}Agent]"
        street = request.action_history[-1].street if request.action_history else "preflop"
        sb = request.blinds.get("sb")
        bb = request.blinds.get("bb")
        (sb_seat, sb_name), (bb_seat, bb_name) = self._blind_info(request)
        print(
            f"{debug_prefix} act called | hand_id={request.hand_id} | street={street} | "
            f"blinds=SB {sb} / BB {bb} | SB seat {sb_seat} ({sb_name}) | "
            f"BB seat {bb_seat} ({bb_name}) | to_call={request.to_call} | legal={list(request.legal_actions)}"
        )
        if self.dry_run or self._client is None:
            print(f"{debug_prefix} dry_run or client unavailable, using fallback action")
            return _fallback_action(request)

        prompt = self._build_prompt(request)
        print(f"{debug_prefix} sending request to API | model={self.model} | base={self.base_url}")

        # Retry logic for rate limiting
        wait_time_total = 0
        for attempt in range(self.max_retries + 1):
            try:
                if self.use_responses:
                    payload = {
                        "model": self.model,
                        "input": [
                            {"role": "system", "content": self._system_message()},
                            {"role": "user", "content": prompt},
                        ],
                    }
                    if self.temperature is not None:
                        payload["temperature"] = self.temperature
                    response = self._client.responses.create(**payload)
                    content = self._extract_responses_text(response)
                else:
                    messages = [
                        {"role": "system", "content": self._system_message()},
                        {"role": "user", "content": prompt},
                    ]
                    payload = {"model": self.model, "messages": messages}
                    if self.temperature is not None:
                        payload["temperature"] = self.temperature
                    response = self._client.chat.completions.create(**payload)
                    content = self._extract_chat_text(response)
                break  # Get response successfully, exit the retry loop
            except RateLimitError as e:
                if attempt < self.max_retries:
                    wait_time = self.retry_delay * (2 ** attempt)  # Exponential backoff
                    wait_time_total += wait_time * 1000
                    print(f"{debug_prefix} Rate limit exceeded. Retrying in {wait_time} seconds... (attempt {attempt + 1}/{self.max_retries})")
                    time.sleep(wait_time)
                else:
                    print(f"{debug_prefix} Max retries exceeded. Falling back to safe action.")
                    return _fallback_action(request, wait_time_ms=wait_time_total)
            except Exception as e:
                print(f"{debug_prefix} Unexpected error: {e}. Falling back to safe action.")
                return _fallback_action(request, wait_time_ms=wait_time_total)

        action = self._parse_text(content, request)
        if action is None:
            print(f"{debug_prefix} failed to parse response, falling back")
            return _fallback_action(request, wait_time_ms=wait_time_total)
        print(
            f"{debug_prefix} parsed action: {action.action}"
            + (f" to {action.amount}" if action.amount is not None else "")
        )
        setattr(action, "wait_time_ms", wait_time_total)
        return action

    # --- prompt and parsing helpers -------------------------------------

    def _system_message(self) -> str:
        if self.system_prompt_override is not None:
            # print("Using system prompt override.")
            # print(self.system_prompt_override)
            return self.system_prompt_override
        base = (
            "You are a professional No-Limit Texas Hold'em assistant. "
            "Respond with a JSON object matching this schema:\n"
            '{"action": "fold|check|call|raise_to", "amount": optional integer}. '
            "Only use actions present in the provided legal actions list. "
            "When raising, supply a numeric target in chips."
        )
        if isinstance(self.metrics_summary, dict) and self.metrics_summary:
            base = (
                f"{base}\nPerformance context: Recent chip results drive evaluation; "
                "focus on actions that build stack growth while avoiding repeated losses from speculative calls."
            )
        if self.system_prompt:
            # print(f"Appending custom system prompt:\n{self.system_prompt}")
            return f"{base}\n{self.system_prompt}"
        return base

    def _build_prompt(self, request: ActionRequest) -> str:
        lines: List[str] = []
        lines.append("Game state:")
        lines.append(f"- Seat count: {request.seat_count}")
        lines.append(f"- Your seat: {request.seat_id}")
        lines.append(f"- Button seat: {request.button_seat}")
        lines.append(f"- Blinds: SB {request.blinds['sb']} / BB {request.blinds['bb']}")
        lines.append(f"- Pot: {request.pot}")
        lines.append(f"- To call: {request.to_call}")
        lines.append(f"- Min raise to: {request.min_raise_to}")
        lines.append(f"- Stacks: {request.stacks}")
        lines.append(f"- Hole cards: {list(request.hole_cards)}")
        lines.append(f"- Board: {list(request.board)}")
        lines.append(f"- Street action history (most recent last):")
        for entry in request.action_history:
            lines.append(
                f"    seat {entry.seat_id} -> {entry.action}"
                + (f" {entry.amount}" if entry.amount is not None else "")
                + f" on {entry.street}"
            )
        lines.append(f"- Legal actions: {list(request.legal_actions)}")
        lines.append("Respond with a JSON decision.")
        return "\n".join(lines)

    def _blind_info(self, request: ActionRequest) -> Tuple[Tuple[int, str], Tuple[int, str]]:
        seat_count = request.seat_count
        button = request.button_seat
        if seat_count == 2:
            sb_seat = button
        else:
            sb_seat = (button + 1) % seat_count
        bb_seat = (sb_seat + 1) % seat_count
        sb_name = self._seat_names.get(sb_seat, f"seat-{sb_seat}")
        bb_name = self._seat_names.get(bb_seat, f"seat-{bb_seat}")
        return (sb_seat, sb_name), (bb_seat, bb_name)

    def _extract_responses_text(self, response) -> str:
        try:
            content = response.output_text
        except AttributeError:
            chunks = getattr(response, "output", []) or []
            fragments: List[str] = []
            for chunk in chunks:
                for part in getattr(chunk, "content", []) or []:
                    text = getattr(part, "text", None)
                    if text is None:
                        continue
                    value = getattr(text, "value", None)
                    fragments.append(value if isinstance(value, str) else str(value))
            content = "\n".join(fragments).strip()
        return content

    def _extract_chat_text(self, response) -> str:
        choices = getattr(response, "choices", []) or []
        if not choices:
            return ""
        message = choices[0].message
        content = getattr(message, "content", "")
        if isinstance(content, list):
            parts = []
            for part in content:
                text = getattr(part, "text", None)
                if text is None:
                    continue
                value = getattr(text, "value", None)
                parts.append(value if isinstance(value, str) else str(value))
            content = "\n".join(parts)
        return content or ""

    def _parse_text(self, content: str, request: ActionRequest) -> Optional[ActionResponse]:
        if not content:
            return None
        payload = None
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    payload = json.loads(content[start : end + 1])
                except json.JSONDecodeError:
                    payload = None
        if not isinstance(payload, dict):
            return None

        action = payload.get("action")
        if action not in request.legal_actions:
            return None

        if action == "raise_to":
            amount = payload.get("amount")
            if not isinstance(amount, (int, float)):
                return None
            legal_amount = _legal_raise_amount(request, int(amount))
            return ActionResponse(action="raise_to", amount=legal_amount)

        return ActionResponse(action=action)
