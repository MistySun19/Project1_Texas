"""
Gemini (Google) agent using an OpenAI-compatible endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .openai_base import OpenAICompatibleAgent


@dataclass
class GeminiAgent(OpenAICompatibleAgent):
    """
    Wrapper for Google Gemini models exposed via an OpenAI-compatible gateway.

    Set the following environment variables (or pass the parameters directly):
        - GEMINI_API_KEY
        - GEMINI_MODEL (default: gemini-1.5-pro)
        - GEMINI_API_BASE (if using a self-hosted proxy)
    """

    default_model: str = field(default="gemini-2.5-flash", init=False)
    default_name: str = field(default="Gemini", init=False)
    env_prefix: str = field(default="GEMINI", init=False)
    default_base_url: str = field(
        default="https://generativelanguage.googleapis.com/v1beta/openai", init=False
    )
    use_responses: bool = field(default=False, init=False)
