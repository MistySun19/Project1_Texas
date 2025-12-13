# -*- coding: utf-8 -*-
"""
Pydantic models for A2A Green Agent evaluation.
"""

from typing import Any, Dict
from pydantic import BaseModel, HttpUrl


class EvalRequest(BaseModel):
    """Assessment request received by the green agent."""
    participants: Dict[str, HttpUrl]  # role -> endpoint URL mapping
    config: Dict[str, Any]  # assessment-specific configuration


class EvalResult(BaseModel):
    """Assessment result produced by the green agent."""
    winner: str  # role of winner, or "draw"
    detail: Dict[str, Any]  # detailed metrics and scores
