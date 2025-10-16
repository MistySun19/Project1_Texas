"""
Kimi (Moonshot) agent leveraging an OpenAI-compatible interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .openai_base import OpenAICompatibleAgent


@dataclass
class KimiAgent(OpenAICompatibleAgent):
    """
    Wrapper for Kimi (Moonshot) models when exposed via an OpenAI-style API.

    Environment variables:
        - KIMI_API_KEY
        - KIMI_MODEL (default: kimi-latest)
        - KIMI_API_BASE
    """

    default_model: str = field(default="kimi-k2-0905-preview", init=False)
    default_name: str = field(default="Kimi", init=False)
    env_prefix: str = field(default="KIMI", init=False)
    default_base_url: str = field(default="https://api.moonshot.cn/v1", init=False)
    use_responses: bool = field(default=False, init=False)
