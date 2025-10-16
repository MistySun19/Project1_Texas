"""
Green Agent Benchmark package.

Provides the reference implementation of the Green Agent Benchmark described in
the project documentation. Key modules:

- cards: Playing card representations and utilities.
- engine: No-Limit Texas Hold'em state machine.
- agents: Baseline agent implementations and agent interface.
- runner: Series coordinator implementing HU and 6-max replication schemes.
- metrics: Aggregation utilities for bb/100 and diagnostics.
- cli: Command line entry points for running benchmark suites.
"""

from . import agents
from .runner import BenchmarkRunner, SeriesConfig
from .metrics import aggregate_run_metrics

__all__ = [
    "agents",
    "BenchmarkRunner",
    "SeriesConfig",
    "aggregate_run_metrics",
]
