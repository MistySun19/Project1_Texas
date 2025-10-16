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

    default_model: str = field(default="kimi-latest", init=False)
    default_name: str = field(default="Kimi", init=False)
    env_prefix: str = field(default="KIMI", init=False)
