# -*- coding: utf-8 -*-
"""
A2A protocol support for the Texas Hold'em Green Agent Benchmark.

This module implements the new AgentBeats A2A protocol for agent evaluation.
"""

try:  # pragma: no cover
    from .green_executor import GreenAgent, GreenExecutor
    from .models import EvalRequest, EvalResult
    from .client import send_message
    from .tool_provider import ToolProvider
except Exception:  # pragma: no cover
    GreenAgent = None  # type: ignore
    GreenExecutor = None  # type: ignore
    EvalRequest = None  # type: ignore
    EvalResult = None  # type: ignore
    send_message = None  # type: ignore
    ToolProvider = None  # type: ignore

__all__ = [
    "GreenAgent",
    "GreenExecutor", 
    "EvalRequest",
    "EvalResult",
    "send_message",
    "ToolProvider",
]
