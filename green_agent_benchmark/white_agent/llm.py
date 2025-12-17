from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

try:
    from openai import OpenAI
    from openai import RateLimitError
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore
    RateLimitError = Exception  # type: ignore

from .models import DecisionState, LegalActions
from .policy import Decision, clamp_to_raise_sizes


@dataclass(frozen=True, slots=True)
class LLMConfig:
    api_key: Optional[str]
    base_url: Optional[str]
    model: str
    temperature: Optional[float]
    use_responses: bool
    dry_run: bool
    timeout_s: float
    max_retries: int


def _model_supports_temperature(model: str) -> bool:
    """
    Some models (notably GPT-5 family) reject the `temperature` parameter.
    Only send it when we believe it's supported.
    """
    token = (model or "").strip().lower()
    if token.startswith("gpt-5"):
        return False
    return True


def _infer_use_responses(model: str, base_url: Optional[str]) -> bool:
    """
    Pick the OpenAI API surface to call.

    - OpenAI GPT-5 family: prefer `/responses`.
    - DeepSeek (OpenAI-compatible): use `/chat/completions`.
    """
    token = (model or "").strip().lower()
    base = (base_url or "").strip().lower()
    if token.startswith("deepseek") or "deepseek" in base:
        return False
    if token.startswith("kimi") or "moonshot" in base or "api.moonshot.cn" in base:
        return False
    if token.startswith("gpt-5"):
        return True
    return True


def _env_nonempty(name: str) -> Optional[str]:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def load_llm_config() -> LLMConfig:
    # Default preference: DeepSeek (if configured) -> Kimi -> OpenAI.
    # If you explicitly set WHITE_LLM_API_KEY, that fully overrides provider selection.
    white_key = _env_nonempty("WHITE_LLM_API_KEY")
    deepseek_key = _env_nonempty("DEEPSEEK_API_KEY")
    kimi_key = _env_nonempty("KIMI_API_KEY")
    openai_key = _env_nonempty("OPENAI_API_KEY")

    if white_key:
        api_key = white_key
        base_url = _env_nonempty("WHITE_LLM_API_BASE") or _env_nonempty("OPENAI_API_BASE")
        model = _env_nonempty("WHITE_LLM_MODEL") or _env_nonempty("OPENAI_MODEL") or "gpt-5-mini"
    elif deepseek_key:
        api_key = deepseek_key
        base_url = _env_nonempty("DEEPSEEK_API_BASE") or "https://api.deepseek.com"
        model = _env_nonempty("DEEPSEEK_MODEL") or "deepseek-chat"
    elif kimi_key:
        api_key = kimi_key
        base_url = _env_nonempty("KIMI_API_BASE") or "https://api.moonshot.cn/v1"
        model = _env_nonempty("KIMI_MODEL") or "kimi-k2-0905-preview"
    else:
        api_key = openai_key
        base_url = _env_nonempty("OPENAI_API_BASE")
        model = _env_nonempty("OPENAI_MODEL") or "gpt-5-mini"

    temperature: Optional[float] = None
    if "WHITE_LLM_TEMPERATURE" in os.environ:
        try:
            temperature = float(os.getenv("WHITE_LLM_TEMPERATURE", "0.1"))
        except Exception:
            temperature = None
    elif _model_supports_temperature(model):
        temperature = 0.1
    use_responses = _infer_use_responses(model, base_url)
    dry_run = os.getenv("WHITE_LLM_DRY_RUN", "").strip().lower() in ("1", "true", "yes", "y")
    if not api_key:
        dry_run = True
    timeout_s = float(os.getenv("WHITE_LLM_TIMEOUT_S", "90"))
    max_retries = int(os.getenv("WHITE_LLM_MAX_RETRIES", "2"))
    return LLMConfig(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=temperature,
        use_responses=use_responses,
        dry_run=dry_run,
        timeout_s=timeout_s,
        max_retries=max_retries,
    )

def _system_prompt() -> str:
    return (
        "You are a No-Limit Texas Hold'em decision module.\n"
        "You MUST output strict JSON only.\n"
        "Schema:\n"
        '{"action_type":"fold|check|call|raise_to|all_in","amount":integer|null,"reason":"short string"}\n'
        "Rules:\n"
        "- action_type must be one of the allowed legal actions.\n"
        "- If action_type is raise_to, amount must match one of the provided raise_sizes.\n"
        "- If action_type is all_in, use amount=null (the caller will map to all-in).\n"
        "- Prefer check/call over raising in marginal spots.\n"
        "- Avoid repeated betting/raising on the same street unless you have strong value.\n"
        "- Use the provided context signals (equity, pot_odds, SPR/effective_stack, sizing ratios, board texture, and action history).\n"
        "- Do NOT rely on fixed numeric thresholds; justify with relative comparisons (e.g., equity vs pot_odds, SPR high/low, wet/dry board).\n"
        "- baseline_suggestion is a safe default; deviate only with a clear, evidence-based reason.\n"
    )


def _parse_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                obj = json.loads(text[start : end + 1])
                return obj if isinstance(obj, dict) else None
            except json.JSONDecodeError:
                return None
    return None


def _validate_llm_choice(
    *,
    legal: LegalActions,
    action_type: str,
    amount: Any,
) -> Tuple[Optional[str], Optional[int]]:
    if action_type == "all_in":
        if "raise_to" not in legal.actions:
            return None, None
        return "raise_to", (legal.raise_sizes[-1] if legal.raise_sizes else legal.max_raise_to)

    if action_type not in legal.actions:
        return None, None

    if action_type != "raise_to":
        return action_type, None

    if not legal.raise_sizes:
        return None, None

    if isinstance(amount, (int, float)):
        chosen = clamp_to_raise_sizes(int(amount), legal)
        return "raise_to", chosen

    return None, None


def llm_decide(
    state: DecisionState,
    context: Dict[str, Any],
    baseline: Decision,
    config: LLMConfig,
) -> Decision:
    if config.dry_run or OpenAI is None:
        return Decision(
            action=baseline.action,
            amount=baseline.amount,
            reason=f"llm_dry_run -> baseline ({baseline.reason})",
            debug={"llm": {"dry_run": True}},
        )

    client_kwargs: Dict[str, Any] = {
        "api_key": config.api_key,
        "timeout": config.timeout_s,
        "max_retries": 0,
    }
    if config.base_url:
        client_kwargs["base_url"] = config.base_url
    client = OpenAI(**client_kwargs)

    prompt = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    last_error: Optional[str] = None
    for attempt in range(max(config.max_retries, 0) + 1):
        try:
            if config.use_responses:
                payload = {
                    "model": config.model,
                    "input": [
                        {"role": "system", "content": _system_prompt()},
                        {"role": "user", "content": prompt},
                    ],
                }
                if config.temperature is not None and _model_supports_temperature(config.model):
                    payload["temperature"] = config.temperature
                resp = client.responses.create(**payload)
                text = getattr(resp, "output_text", "") or ""
            else:
                messages = [
                    {"role": "system", "content": _system_prompt()},
                    {"role": "user", "content": prompt},
                ]
                payload = {"model": config.model, "messages": messages}
                if config.temperature is not None and _model_supports_temperature(config.model):
                    payload["temperature"] = config.temperature
                resp = client.chat.completions.create(**payload)
                text = ""
                try:
                    text = resp.choices[0].message.content or ""
                except Exception:
                    text = ""
            break
        except RateLimitError as exc:
            last_error = f"rate_limit: {exc}"
            if attempt >= config.max_retries:
                return Decision(
                    action=baseline.action,
                    amount=baseline.amount,
                    reason=f"llm_error -> baseline ({baseline.reason})",
                    debug={"llm": {"error": last_error}},
                )
            continue
        except Exception as exc:
            last_error = f"{exc.__class__.__name__}: {exc}"
            if attempt >= config.max_retries:
                return Decision(
                    action=baseline.action,
                    amount=baseline.amount,
                    reason=f"llm_error -> baseline ({baseline.reason})",
                    debug={"llm": {"error": last_error}},
                )
            continue
    obj = _parse_json_object(text)
    if not obj:
        return Decision(
            action=baseline.action,
            amount=baseline.amount,
            reason=f"llm_parse_failed -> baseline ({baseline.reason})",
            debug={"llm": {"raw": text}},
        )

    action_type = str(obj.get("action_type", "") or obj.get("action", "") or "").strip()
    amount = obj.get("amount")
    reason = str(obj.get("reason", "") or "").strip() or "llm"

    validated_action, validated_amount = _validate_llm_choice(
        legal=state.legal, action_type=action_type, amount=amount
    )
    if not validated_action:
        return Decision(
            action=baseline.action,
            amount=baseline.amount,
            reason=f"llm_illegal -> baseline ({baseline.reason})",
            debug={"llm": {"raw": obj}},
        )

    return Decision(
        action=validated_action,
        amount=validated_amount,
        reason=reason,
        debug={"llm": {"raw": obj}},
    )
