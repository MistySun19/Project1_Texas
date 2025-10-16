"""
GPT-5 integration built on top of the generic OpenAI-compatible agent base.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .openai_base import OpenAICompatibleAgent


@dataclass
class GPT5Agent(OpenAICompatibleAgent):
    """
    Wrapper for OpenAI's GPT-5 style models.

    Environment variables honoured:
        - OPENAI_API_KEY
        - OPENAI_MODEL
        - OPENAI_API_BASE
    """

    default_model: str = field(default="gpt-5-mini", init=False)
    default_name: str = field(default="GPT-5", init=False)
    env_prefix: str = field(default="OPENAI", init=False)
