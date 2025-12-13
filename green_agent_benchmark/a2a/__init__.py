# -*- coding: utf-8 -*-
"""
A2A protocol support for the Texas Hold'em Green Agent Benchmark.

This module implements the new AgentBeats A2A protocol for agent evaluation.
"""

from .green_executor import GreenAgent, GreenExecutor
from .models import EvalRequest, EvalResult
from .client import send_message
from .tool_provider import ToolProvider

__all__ = [
    "GreenAgent",
    "GreenExecutor", 
    "EvalRequest",
    "EvalResult",
    "send_message",
    "ToolProvider",
]
