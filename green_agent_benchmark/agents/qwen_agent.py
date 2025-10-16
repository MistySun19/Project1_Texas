"""
Qwen (Alibaba) agent wrapper.

Assumes an OpenAI-compatible Responses/Chat API. Configure credentials via:
    - QWEN_API_KEY
    - QWEN_MODEL (optional, default `qwen-plus`)
    - QWEN_API_BASE (optional, e.g. https://dashscope.aliyuncs.com/compatible-mode/v1)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .openai_base import OpenAICompatibleAgent


@dataclass
class QwenAgent(OpenAICompatibleAgent):
    default_model: str = field(default="qwen-plus", init=False)
    default_name: str = field(default="Qwen", init=False)
    env_prefix: str = field(default="QWEN", init=False)
    default_base_url: str = field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1", init=False
    )
    use_responses: bool = field(default=False, init=False)
