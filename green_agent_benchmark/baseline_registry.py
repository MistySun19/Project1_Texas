"""
Factory helpers for baseline agents shipped with the benchmark.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Tuple

from .agents.random_agent import RandomAgent
from .agents.tag_agent import TagAgent
from .agents.cfr_lite_agent import CFRLiteAgent
from .agents.gpt5_agent import GPT5Agent
from .agents.gemini_agent import GeminiAgent
from .agents.deepseek_agent import DeepSeekAgent
from .agents.kimi_agent import KimiAgent
from .agents.qwen_agent import QwenAgent
from .agents.cohere_agent import CohereAgent
from .agents.doubao_agent import DoubaoAgent
from .agents.glm_agent import GLMAgent
from .agents.agentbeats_remote import AgentBeatsRemoteAgent

BASELINE_FACTORIES: Dict[str, Callable[..., Any]] = {
    "random-hu": RandomAgent,
    "random-6": RandomAgent,
    "tag-hu": TagAgent,
    "tag-6": TagAgent,
    "cfrlite-hu": CFRLiteAgent,
    "cfrlite-6": CFRLiteAgent,
    "gpt5-hu": GPT5Agent,
    "gpt5-6": GPT5Agent,
    "gemini-hu": GeminiAgent,
    "gemini-6": GeminiAgent,
    "deepseek-hu": DeepSeekAgent,
    "deepseek-6": DeepSeekAgent,
    "kimi-hu": KimiAgent,
    "kimi-6": KimiAgent,
    "qwen-hu": QwenAgent,
    "qwen-6": QwenAgent,
    "cohere-hu": CohereAgent,
    "cohere-6": CohereAgent,
    "doubao-hu": DoubaoAgent,
    "doubao-6": DoubaoAgent,
    "glm-hu": GLMAgent,
    "glm-6": GLMAgent,
    "agentbeats-remote-hu": AgentBeatsRemoteAgent,
    "agentbeats-remote-6": AgentBeatsRemoteAgent,
}


def make_baseline(name: str, **kwargs: Any):
    if name not in BASELINE_FACTORIES:
        raise ValueError(f"Unknown baseline {name}")
    factory = BASELINE_FACTORIES[name]
    try:
        return factory(**kwargs)
    except TypeError:
        if kwargs:
            raise
        return factory()


def expand_opponent_mix(mix: Dict[str, float]) -> Tuple[str, ...]:
    """
    Convert a probability map into a tuple of opponent labels ordered by weight.
    """
    items = sorted(mix.items(), key=lambda kv: kv[1], reverse=True)
    expanded = []
    for name, weight in items:
        count = max(int(weight * 10), 1)
        expanded.extend([name] * count)
    return tuple(expanded)
