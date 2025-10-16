"""
Cohere agent wrapper using the OpenAI-compatible interface.

Environment variables:
    - COHERE_API_KEY
    - COHERE_MODEL (default `command-r`)
    - COHERE_API_BASE (e.g. https://api.cohere.ai/v1 if proxying)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .openai_base import OpenAICompatibleAgent


@dataclass
class CohereAgent(OpenAICompatibleAgent):
    default_model: str = field(default="command-r", init=False)
    default_name: str = field(default="Cohere", init=False)
    env_prefix: str = field(default="COHERE", init=False)
