"""
DeepSeek agent (OpenAI-compatible API).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .openai_base import OpenAICompatibleAgent


@dataclass
class DeepSeekAgent(OpenAICompatibleAgent):
    """
    Wrapper for DeepSeek models deployed via an OpenAI-compatible endpoint.

    Supported environment variables:
        - DEEPSEEK_API_KEY
        - DEEPSEEK_MODEL (default: deepseek-chat)
        - DEEPSEEK_API_BASE (if using a custom endpoint)
    """

    default_model: str = field(default="deepseek-chat", init=False)
    default_name: str = field(default="DeepSeek", init=False)
    env_prefix: str = field(default="DEEPSEEK", init=False)
    default_base_url: str = field(default="https://api.deepseek.com", init=False)
    use_responses: bool = field(default=False, init=False)
