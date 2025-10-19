"""
Kimi (Moonshot) agent leveraging an OpenAI-compatible interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .openai_base import OpenAICompatibleAgent


@dataclass
class DoubaoAgent(OpenAICompatibleAgent):
    """
    Wrapper for Doubao models when exposed via an OpenAI-style API.

    Environment variables:
        - DOUBAO_API_KEY
        - DOUBAO_MODEL (default: doubao-latest)
        - DOUBAO_API_BASE
    """

    default_model: str = field(default="doubao-1-5-thinking-pro-250415", init=False)
    default_name: str = field(default="Doubao", init=False)
    env_prefix: str = field(default="DOUBAO", init=False)
    default_base_url: str = field(default="https://ark.cn-beijing.volces.com/api/v3", init=False)
    use_responses: bool = field(default=False, init=False)
