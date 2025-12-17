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

# Avoid importing the full benchmark stack at package import time. Some optional
# integrations (e.g. AgentBeats SDK wiring) are environment-dependent and can
# raise during import in minimal deployments (such as participant-only servers).
try:  # pragma: no cover
    from .runner import BenchmarkRunner, SeriesConfig
    from .metrics import aggregate_run_metrics
except Exception:  # pragma: no cover
    BenchmarkRunner = None  # type: ignore
    SeriesConfig = None  # type: ignore
    aggregate_run_metrics = None  # type: ignore

__all__ = [
    "agents",
    "BenchmarkRunner",
    "SeriesConfig",
    "aggregate_run_metrics",
]
