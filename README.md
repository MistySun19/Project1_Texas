# Green Agent Benchmark

Reference implementation of the **Green Agent Benchmark** for evaluating language-model and rule-based poker agents in real-time No-Limit Texas Hold'em environments. The project follows the design outlined in the prompt: variance-controlled heads-up (HU) and 6-max tracks, deterministic logs, governance hooks, and reproducible metrics.

## Features

- NLHE engine with blinds, side pots, duplicate HU replication, and 6-max seat balancing.
- Agent-to-Agent (A2A) style interface with timeout, illegal-action, and governance penalties plus NDJSON telemetry.
- Baseline agents (`Random`, `TAG`, `CFR-lite`) covering social/random, range-based, and solver-inspired behaviours.
- Metrics pipeline computing `bb/100`, confidence intervals, match points, VPIP/PFR/AF/WTSD, timeout and illegal rates, and average decision speed directly from logs.
- Config-driven runner with YAML schedules for dev/test style executions.
- Command line interface and reusable Python API for integrating custom agents.

## Repository Layout

```
green_agent_benchmark/
  engine.py            # NLHE state machine and logging hooks
  runner.py            # Series orchestration and replication logic
  metrics.py           # Log aggregation for bb/100 and behaviour stats
  agents/              # Baseline agent implementations
  cli.py               # CLI entry point
configs/               # Example HU and 6-max configuration files
scripts/run_series.py  # Convenience launcher
```

## Installation

Requires Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
python -m pip install -r requirements.txt
```

Optional dev extras (pytest) are declared in `pyproject.toml`.

Environment secrets (e.g. `OPENAI_API_KEY`) can be stored in a local `.env`
file; the CLI automatically loads it if present.

## Running the Benchmark

### 1. Use packaged baselines

```bash
python -m green_agent_benchmark.cli \
  --config configs/dev_hu.yaml \
  --agent baseline:tag-hu \
  --output artifacts/demo_hu
```

### 2. Custom agent module

Implement an agent with the interface:

```python
from green_agent_benchmark.schemas import ActionRequest, ActionResponse


class MyAgent:
    name = "my-agent"

    def reset(self, seat_id: int, table_config: dict) -> None:
        ...  # optional per-hand reset

    def act(self, request: ActionRequest) -> ActionResponse:
        return ActionResponse(action="fold")
```

Save as `mybot.py` and run:

```bash
python -m green_agent_benchmark.cli \
  --config configs/dev_6max.yaml \
  --agent mybot:MyAgent \
  --output artifacts/mybot_run
```

The CLI accepts `--agent-name` to override display names in logs and metrics.

#### Full-table lineups

To specify every seat directly (useful for six-player LLM showdowns), provide a
`lineup` array in the config. Each entry can be `baseline:<name>` or a
`pkg.module:Class` spec. Example (`configs/sixmax_llm_showdown.yaml`):

```yaml
lineup:
  - baseline:gpt5-6
  - baseline:deepseek-6
  - baseline:gemini-6
  - baseline:kimi-6
  - baseline:qwen-6
  - baseline:cohere-6
```

With a full lineup defined, `--agent` / `--agent-name` become optional.

You can also override baseline parameters directly in the lineup via query
strings, e.g.:

```yaml
lineup:
  - baseline:gpt5-6?model=gpt-5&name=GPT5-Pro
  - baseline:gpt5-6?model=gpt-5-mini&name=GPT5-Mini
  - baseline:gemini-6
  - baseline:deepseek-6
  - baseline:kimi-6
  - baseline:qwen-6
```

Each `key=value` pair becomes a keyword argument when instantiating the agent,
so you can set model variants or display names without touching the CLI.

### 3. GPT-5 via OpenAI API

Install the `openai` dependency (already listed in `requirements.txt`), export your API key, and point the CLI at the GPT-5 wrapper:

```bash
export OPENAI_API_KEY=sk-...
python -m green_agent_benchmark.cli \
  --config configs/dev_hu.yaml \
  --agent green_agent_benchmark.agents.gpt5_agent:GPT5Agent \
  --agent-name GPT5 \
  --output artifacts/gpt5_demo
```

Optional flags for `GPT5Agent`:

- `model`: override the default `gpt-5.0-mini`.
- `temperature`: adjust sampling temperature (default `0.0`).
- `dry_run=True`: skip API calls and fall back to deterministic safety behaviour (useful for offline tests).
- `system_prompt="..."`: append extra guardrails to the base system prompt.
- `system_prompt_override="..."`: replace the default system prompt entirely (overrides any appended prompt).

Config files also accept a top-level `system_prompt_override` key; when present it
overrides the system message for any OpenAI-compatible agents created from the lineup.

### 4. Other LLM Providers (Gemini / DeepSeek / Kimi / Qwen / Cohere)

Agents for additional OpenAI-compatible providers are shipped under
`green_agent_benchmark.agents.{gemini_agent,deepseek_agent,kimi_agent,qwen_agent,cohere_agent}`
and are available in the baseline registry as `*-hu` / `*-6` variants. Each
agent reads its API configuration from environment variables:

- Gemini: `GEMINI_API_KEY`, optional `GEMINI_MODEL`, `GEMINI_API_BASE`
- DeepSeek: `DEEPSEEK_API_KEY`, optional `DEEPSEEK_MODEL`, `DEEPSEEK_API_BASE`
- Kimi: `KIMI_API_KEY`, optional `KIMI_MODEL`, `KIMI_API_BASE`
- Qwen: `QWEN_API_KEY`, optional `QWEN_MODEL`, `QWEN_API_BASE`
- Cohere: `COHERE_API_KEY`, optional `COHERE_MODEL`, `COHERE_API_BASE`

Example HU showdown using Gemini vs GPT-5:

```bash
export GEMINI_API_KEY=... \
       GEMINI_API_BASE=https://your-proxy/v1
export OPENAI_API_KEY=...

python -m green_agent_benchmark.cli \
  --config configs/demo_hu_10hands.yaml \
  --agent green_agent_benchmark.agents.gpt5_agent:GPT5Agent \
  --agent-name GPT5 \
  --output artifacts/gpt5_vs_gemini
```

In the YAML config swap `opponent_mix` to `gemini-hu: 1.0` (or any mixture of
`gpt5-hu`, `deepseek-hu`, `kimi-hu`) to stage LLM-vs-LLM matches. For Six-Max
you can also specify a complete `lineup` of six agent specs (baseline or custom
module paths); when provided, the CLI automatically instantiates every seat so
`--agent` / `--agent-name` are optional.

### 5. Quick Demos

- **10-hand smoke test (Random baseline):**

  ```bash
  python -m green_agent_benchmark.cli \
    --config configs/demo_hu_10hands.yaml \
    --agent baseline:random-hu \
    --output artifacts/random_demo
  ```

- **GPT-5 (OpenAI) vs DeepSeek (both require API keys):**

  ```bash
  export OPENAI_API_KEY=...
  export DEEPSEEK_API_KEY=...
  python -m green_agent_benchmark.cli \
    --config configs/demo_hu_deepseek_vs_gpt5.yaml \
    --agent green_agent_benchmark.agents.gpt5_agent:GPT5Agent \
    --agent-name GPT5 \
    --output artifacts/gpt5_vs_deepseek
  ```

  CLI output now prints a summary block per player and `metrics/metrics.json`
  contains separate entries (e.g. `"GPT5"`, `"DeepSeek"`) so you can compare both
  sides directly.

- **6-max LLM showdown (GPT-5 + DeepSeek + Gemini + Kimi + Qwen + Cohere):**

  ```bash
  python -m green_agent_benchmark.cli \
    --config configs/sixmax_llm_showdown.yaml \
    --output artifacts/sixmax_llm
  ```

  Ensure `.env` contains all six providers' API keys/bases. Because the config
  declares a full six-player `lineup`, the CLI instantiates every seat
  automatically and the output metrics list one block per model so you can
  analyse the entire table in a single run.

## Outputs

Each run populates the chosen `--output` directory with:

- `logs/<mode>/.../*.ndjson`: deterministic event traces (hand start, actions, penalties, showdowns).
- `metrics/per_hand_metrics.ndjson`: per-hand summary records for the evaluated agent.
- `metrics/metrics.json`: aggregated statistics keyed by player name (both the evaluated agent and every baseline/LLM opponent), including bb/100 with CI, behaviour frequencies, timeout/illegal rates, and decision-time summaries.

Example fragment from `metrics.json`:

```json
{
  "GPT5": {
    "bb_per_100": -35.0,
    "bb_per_100_ci": [-40.0, -30.0],
    "behavior": {
      "vpip": {"count": 7, "rate": 0.70},
      "pfr": {"count": 4, "rate": 0.40},
      "af": 1.75,
      "wt_sd": {"count": 3, "rate": 0.60},
      "decision_time_ms": {"mean": 850.4, "samples": 22}
    }
  },
  "DeepSeek": {
    "bb_per_100": 35.0,
    "bb_per_100_ci": [30.0, 40.0],
    "behavior": {
      "vpip": {"count": 8, "rate": 0.80},
      "pfr": {"count": 5, "rate": 0.50},
      "af": 2.10,
      "wt_sd": {"count": 4, "rate": 0.67},
      "decision_time_ms": {"mean": 430.2, "samples": 21}
    }
  }
}
```

## Extending the Benchmark

- **Opponents:** customise `opponent_mix` (HU) or `opponent_pool` (6-max) in configs; add new baseline classes under `green_agent_benchmark/agents/` and register them in `baseline_registry.py`.
- **Schedules:** increase `seeds`, `hands_per_seed`, or `hands_per_replica` for larger evaluation suites. The engine is deterministic with respect to `seed`, hand index, and replica index.
- **Metrics:** enhance `metrics.py` to compute additional diagnostics such as VRR or exploitability deltas; the NDJSON schema is intentionally transparent for easy post-processing.

## Python API

```python
from green_agent_benchmark.runner import BenchmarkRunner, SeriesConfig
from mybot import MyAgent

config = SeriesConfig.from_file("configs/dev_hu.yaml")
runner = BenchmarkRunner(config, "artifacts/api_run")
result = runner.run(MyAgent())
print(result.metrics)
```

## Governance Hooks

- **Timeouts:** each decision is capped (`time_per_decision_ms` default 60s). Exceeding the cap triggers auto-check/fold and logs a penalty.
- **Illegal actions:** invalid responses are replaced with safe fallbacks and recorded as penalties.
- **Logging:** every event contains an ISO timestamp and reproducible RNG tag. Deck order is derived from `(seed, hand_index)` and reused for HU duplicates and 6-max seat replicas.

## Next Steps

- Increase seeds/hands and plug into bootstrap tooling for tighter confidence intervals.
- Integrate the `metrics.json` outputs with dashboards or leaderboards.
- Extend `HoldemEngine` with antes, MTT scheduling, or additional governance checks as described in the design brief.

Enjoy benchmarking!
