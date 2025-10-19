"""
Kimi (Moonshot) agent leveraging an OpenAI-compatible interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .openai_base import OpenAICompatibleAgent


@dataclass
class GLMAgent(OpenAICompatibleAgent):
    """
    Wrapper for GLM models when exposed via an OpenAI-style API.

    Environment variables:
        - GLM_API_KEY
        - GLM_MODEL (default: GLM-4.6)
        - GLM_API_BASE
    """

    default_model: str = field(default="GLM-4.6", init=False)
    default_name: str = field(default="GLM", init=False)
    env_prefix: str = field(default="GLM", init=False)
    default_base_url: str = field(default="https://open.bigmodel.cn/api/paas/v4", init=False)
    use_responses: bool = field(default=False, init=False)
