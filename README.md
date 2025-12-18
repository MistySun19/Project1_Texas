# Green Agent Benchmark

A reference implementation for evaluating LLM and rule-based poker agents in real-time No-Limit Texas Hold'em environments. Features variance-controlled evaluation, deterministic logging, governance hooks, and reproducible metrics.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

---

## 📋 Table of Contents

1. [Features](#features)
2. [Quick Start](#quick-start)
3. [Installation](#installation)
4. [Environment Setup](#environment-setup)
5. [Running Experiments](#running-experiments)
6. [Configuration Files](#configuration-files)
7. [Agent Development](#agent-development)
8. [Leaderboard System](#leaderboard-system)
9. [Output and Metrics](#output-and-metrics)
10. [Documentation](#documentation)
11. [Troubleshooting](#troubleshooting)

---

## ✨ Features

- **Complete NLHE Engine**: Blinds, side pots, all-in handling, duplicate HU replication, 6-max seat balancing
- **Agent-to-Agent (A2A) Interface**: Timeout/illegal-action governance with NDJSON telemetry
- **Baseline Agents**: Random, TAG (Tight-Aggressive), CFR-lite strategies
- **LLM Agent Support**: GPT-5, DeepSeek, Gemini, Kimi, Qwen, Cohere, Doubao, GLM
- **Comprehensive Metrics**: bb/100, confidence intervals, match points, VPIP/PFR/AF/WTSD
- **Dual Evaluation Modes**: Heads-up (HU) and 6-max with variance control
- **Config-Driven**: YAML-based experiment configuration
- **Web Leaderboard**: Real-time interactive ranking system
- **Full Reproducibility**: Deterministic RNG with seed-based logging

---

## 🚀 Quick Start

### 5-Minute Demo

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set API key (for LLM agents)
export OPENROUTER_API_KEY=your_key_here

# 3. Run quick test (10 hands, heads-up)
python -m green_agent_benchmark.cli \
    --config configs/demo_hu_10hands.yaml \
    --agent baseline:random-hu \
    --output artifacts/quick_test

# 4. View results
cat artifacts/quick_test/metrics.json
```

### Expected Output

```json
{
  "run_id": "20250117_103045",
  "total_hands": 10,
  "agents": {
    "random-hu": {
      "bb100": 5.2,
      "bb100_ci": [-12.3, 22.7],
      "match_points": 0,
      "behavior": {
        "vpip": 52.3,
        "pfr": 28.1
      }
    }
  }
}
```

---

## 📦 Installation

### Requirements

- Python 3.10 or higher
- pip or Poetry
- (Optional) Docker for containerized deployment

### Standard Installation

```bash
# Clone repository
git clone https://github.com/your-org/green-agent-benchmark.git
cd green-agent-benchmark

# Install dependencies
pip install -r requirements.txt

# Verify installation
python -m green_agent_benchmark.cli --help
```

### Development Installation

```bash
# Install with Poetry (recommended for development)
poetry install

# Or install in editable mode with pip
pip install -e .
```

### Docker Installation

```bash
# Build image
docker build -t green-agent-benchmark .

# Run container
docker run -v $(pwd)/artifacts:/app/artifacts \
    -e OPENROUTER_API_KEY=your_key \
    green-agent-benchmark \
    --config configs/demo_hu_10hands.yaml \
    --agent baseline:gpt5-hu
```

---

## 🔧 Environment Setup

### API Keys for LLM Agents

Configure API keys as environment variables:

```bash
# OpenRouter (supports multiple models)
export OPENROUTER_API_KEY=your_key

# Provider-specific keys
export DEEPSEEK_API_KEY=your_key
export GEMINI_API_KEY=your_key
export KIMI_API_KEY=your_key
export QWEN_API_KEY=your_key
export COHERE_API_KEY=your_key
export DOUBAO_API_KEY=your_key
export GLM_API_KEY=your_key
```

### Persistent Configuration

Add to `~/.bashrc` or `~/.zshrc`:

```bash
# Green Agent Benchmark Configuration
export OPENROUTER_API_KEY=sk-or-v1-xxxxx
export DEEPSEEK_API_KEY=sk-xxxxx
export GEMINI_API_KEY=AIzaxxxxx

# Optional: Experiment defaults
export TEXAS_AGENT_SEEDS=401,501,601,701
export TEXAS_HANDS_PER_SEED=50
export TEXAS_REPLICAS=2
```

### Verifying Setup

```bash
# Test environment variables
python -c "import os; print('OpenRouter:', os.getenv('OPENROUTER_API_KEY')[:10])"

# Test LLM agent connectivity
python -m green_agent_benchmark.cli \
    --config configs/ultra_fast_test.yaml \
    --agent baseline:gpt5-hu \
    --output artifacts/connectivity_test
```

---

## 🎮 Running Experiments

### Basic Usage

```bash
python -m green_agent_benchmark.cli \
    --config configs/dev_hu.yaml \
    --agent baseline:deepseek-hu \
    --output artifacts/my_experiment
```

### Command-Line Options

| Option | Description | Example |
|--------|-------------|---------|
| `--config PATH` | Experiment configuration file | `configs/dev_hu.yaml` |
| `--agent SPEC` | Agent to evaluate | `baseline:gpt5-hu` |
| `--output DIR` | Output directory | `artifacts/results` |
| `--log-level LEVEL` | Logging verbosity | `DEBUG`, `INFO`, `WARNING` |

### Agent Specification Formats

```bash
# Baseline agents (from registry)
--agent baseline:random-hu
--agent baseline:tag-hu
--agent baseline:deepseek-hu

# Custom agent (module path)
--agent my_agents.poker:MyAgent

# Multiple opponents (HU mode)
--config configs/dev_hu.yaml  # Define opponent_mix in YAML
```

### Experiment Modes

#### Heads-Up (HU) Mode

```bash
# HU with duplicate matching (variance reduction)
python -m green_agent_benchmark.cli \
    --config configs/dev_hu.yaml \
    --agent baseline:gpt5-hu \
    --output artifacts/hu_gpt5
```

**Config example** (`configs/dev_hu.yaml`):
```yaml
mode: hu
blinds: {sb: 50, bb: 100}
stacks_bb: 200
hands_per_seed: 100
replicas: 2  # Duplicate matching
seeds: [101, 102, 103, 104, 105]
opponent_mix:
  baseline:random-hu: 0.5
  baseline:tag-hu: 0.5
```

#### 6-Max Mode

```bash
# 6-max with seat rotation
python -m green_agent_benchmark.cli \
    --config configs/dev_6max.yaml \
    --agent baseline:deepseek-hu \
    --output artifacts/sixmax_deepseek
```

**Config example** (`configs/dev_6max.yaml`):
```yaml
mode: sixmax
blinds: {sb: 50, bb: 100}
stacks_bb: 200
hands_per_replica: 50
seat_replicas: 6  # Each agent plays from all positions
seeds: [201, 202, 203]
lineup:
  - baseline:random-hu
  - baseline:tag-hu
  - baseline:gpt5-hu
  - baseline:gemini-hu
  - baseline:deepseek-hu
  - baseline:kimi-hu
```

### Advanced Examples

#### LLM Showdown (Multiple Models)

```bash
bash scripts/run_series.py \
    --config configs/sixmax_llm_showdown.yaml \
    --output artifacts/llm_showdown
```

#### Custom Agent Evaluation

```python
# custom_agent.py
from green_agent_benchmark.agents.base import AgentProtocol
from green_agent_benchmark.schemas import ActionRequest, ActionResponse

class MyAgent(AgentProtocol):
    name = "my-custom-agent"
    
    def act(self, request: ActionRequest) -> ActionResponse:
        # Your strategy here
        return ActionResponse(action="fold")
```

```bash
python -m green_agent_benchmark.cli \
    --config configs/dev_hu.yaml \
    --agent custom_agent:MyAgent \
    --output artifacts/custom_test
```

---

## ⚙️ Configuration Files

### YAML Configuration Structure

```yaml
# configs/my_experiment.yaml

# Game mode: "hu" or "sixmax"
mode: hu

# Blind structure
blinds:
  sb: 50
  bb: 100

# Starting stacks (in big blinds)
stacks_bb: 200

# RNG seeds for variance control
seeds: [101, 102, 103, 104, 105]

# Decision timeout (seconds)
timeout_seconds: 60

# === Heads-Up Specific ===
hands_per_seed: 100       # Hands per seed
replicas: 2               # Duplicate matching (2 = each hand played twice)

opponent_mix:
  baseline:random-hu: 0.3
  baseline:tag-hu: 0.7

# === 6-Max Specific ===
# hands_per_replica: 50   # Hands per seat replica
# seat_replicas: 6        # Seat rotation count

# lineup:
#   - baseline:agent1
#   - baseline:agent2
#   - baseline:agent3
#   - baseline:agent4
#   - baseline:agent5
#   - baseline:agent6
```

### Pre-configured Templates

Located in `configs/`:

| Config File | Mode | Hands | Purpose |
|-------------|------|-------|---------|
| `ultra_fast_test.yaml` | HU | 10 | Connectivity test |
| `demo_hu_10hands.yaml` | HU | 20 | Quick demo |
| `dev_hu.yaml` | HU | 500 | Development testing |
| `dev_6max.yaml` | 6-max | 300 | 6-max development |
| `sixmax_llm_showdown.yaml` | 6-max | 1000 | LLM comparison |

### Environment Variable Overrides

Override config values without editing YAML:

```bash
export TEXAS_AGENT_SEEDS=401,501,601,701
export TEXAS_HANDS_PER_SEED=100
export TEXAS_REPLICAS=2
export TEXAS_SB=50
export TEXAS_BB=100
export TEXAS_STACKS_BB=200

# Config will use these values instead
python -m green_agent_benchmark.cli \
    --config configs/dev_hu.yaml \
    --agent baseline:gpt5-hu
```

---

## 🤖 Agent Development

### Implementing Custom Agents

#### Minimal Agent

```python
from green_agent_benchmark.agents.base import AgentProtocol
from green_agent_benchmark.schemas import ActionRequest, ActionResponse

class SimpleAgent(AgentProtocol):
    name = "simple-agent"
    
    def reset(self, seat_id: int, table_config: dict) -> None:
        """Called at start of each seed."""
        self.seat_id = seat_id
        self.hands_played = 0
    
    def act(self, request: ActionRequest) -> ActionResponse:
        """Make poker decision."""
        self.hands_played += 1
        
        # Simple strategy: call if pot odds > 30%, else fold
        pot_odds = request.to_call / (request.pot + request.to_call)
        
        if pot_odds < 0.3:
            return ActionResponse(action="call")
        else:
            return ActionResponse(action="fold")
```

#### Advanced Agent with Hand Strength

```python
from green_agent_benchmark.cards import evaluate_hand

class SmartAgent(AgentProtocol):
    name = "smart-agent"
    
    def act(self, request: ActionRequest) -> ActionResponse:
        # Calculate hand strength
        hand_strength = self._evaluate_strength(
            request.hole_cards,
            request.board
        )
        
        # Aggressive play with strong hands
        if hand_strength > 0.7:
            raise_amount = int(request.pot * 1.5)
            return ActionResponse(
                action="raise_to",
                amount=min(raise_amount, request.stacks[self.seat_id])
            )
        
        # Call with medium hands
        elif hand_strength > 0.4:
            return ActionResponse(action="call")
        
        # Fold weak hands
        else:
            return ActionResponse(action="fold")
    
    def _evaluate_strength(self, hole_cards, board):
        # Implement hand evaluation logic
        # Return value between 0.0 (weak) and 1.0 (strong)
        pass
```

### Using Custom Agents

```bash
# Via module path
python -m green_agent_benchmark.cli \
    --config configs/dev_hu.yaml \
    --agent my_agents:SimpleAgent \
    --output artifacts/simple_agent_test
```

### Baseline Agent Registry

Available baseline agents:

| Agent Name | Type | Description |
|------------|------|-------------|
| `random-hu` | Rule-based | Random legal actions |
| `tag-hu` | Rule-based | Tight-Aggressive strategy |
| `cfr-lite-hu` | Solver | CFR-inspired with equity estimation |
| `gpt5-hu` | LLM | OpenAI GPT-5 |
| `deepseek-hu` | LLM | DeepSeek Chat |
| `gemini-hu` | LLM | Google Gemini |
| `kimi-hu` | LLM | Moonshot Kimi |
| `qwen-hu` | LLM | Alibaba Qwen |
| `cohere-hu` | LLM | Cohere Command |
| `doubao-hu` | LLM | ByteDance Doubao |
| `glm-hu` | LLM | Zhipu GLM |

---

## 📊 Leaderboard System

### Starting the Leaderboard

```bash
# Method 1: Direct script
bash start_leaderboard.sh

# Method 2: Python launcher
python -m leaderboard.launcher

# Method 3: Manual start
cd leaderboard && python server.py
```

Access at: **http://localhost:8080**

### Leaderboard Features

- **Real-time Updates**: Auto-refresh every 30 seconds
- **Multi-metric Ranking**: bb/100, win rate, match points
- **Behavioral Stats**: VPIP, PFR, Aggression Factor, WTSD
- **Filtering**: By agent type (LLM, rule-based, custom)
- **Sorting**: By any metric column
- **Export**: Download data as JSON/CSV

### Adding Experiments to Leaderboard

```bash
# 1. Run experiment with standardized output
python -m green_agent_benchmark.cli \
    --config configs/dev_hu.yaml \
    --agent baseline:new-agent \
    --output artifacts/new_agent_results

# 2. Leaderboard auto-detects new results in artifacts/
# 3. Refresh browser to see updated rankings
```

### Manual Leaderboard Update

```python
# leaderboard/manual_update.py
from leaderboard.leaderboard_generator import generate_leaderboard

generate_leaderboard(
    artifacts_dir="artifacts/",
    output_file="leaderboard/data/leaderboard.json"
)
```

---

## 📈 Output and Metrics

### Output Directory Structure

```
artifacts/my_experiment/
├── logs/
│   ├── gpt5-hu_vs_random-hu_seed101.ndjson
│   ├── gpt5-hu_vs_random-hu_seed102.ndjson
│   └── gpt5-hu_vs_tag-hu_seed101.ndjson
├── metrics/
│   ├── gpt5-hu_vs_random-hu.json
│   └── gpt5-hu_vs_tag-hu.json
└── metrics.json  # Aggregated results
```

### Metrics JSON Format

```json
{
  "run_id": "20250117_103045",
  "mode": "hu",
  "total_hands": 1000,
  "seeds": [101, 102, 103, 104, 105],
  "agents": {
    "gpt5-hu": {
      "total_hands": 1000,
      "total_delta": 15000,
      "bb100": 15.0,
      "bb100_ci": [8.2, 21.8],
      "match_points": 1,
      "winrate_pct": 55.2,
      "timeout_count": 0,
      "illegal_action_count": 0,
      "behavior": {
        "vpip": 28.5,
        "pfr": 22.3,
        "aggression_factor": 2.1,
        "wtsd": 35.2
      }
    }
  }
}
```

### Metric Definitions

| Metric | Description | Formula |
|--------|-------------|---------|
| **bb/100** | Big blinds won per 100 hands | `(total_delta / bb / hands) × 100` |
| **bb/100 CI** | 95% confidence interval | Bootstrap across seeds |
| **Match Points** | Match outcome | `+1` if CI > 0, `-1` if CI < 0, `0` otherwise |
| **Win Rate %** | Percentage of hands won | `(hands_won / total_hands) × 100` |
| **VPIP** | Voluntarily Put $ In Pot % | Preflop participation rate |
| **PFR** | Preflop Raise % | Preflop aggression rate |
| **Aggression Factor** | Post-flop aggression | `(raises + bets) / calls` |
| **WTSD** | Went To Showdown % | Showdown frequency |

### NDJSON Log Format

Each line is a JSON event:

```json
{"timestamp": "2025-01-17T10:30:45.123Z", "type": "hand_start", "hand_id": "101-0-0", "payload": {...}}
{"timestamp": "2025-01-17T10:30:46.234Z", "type": "action", "hand_id": "101-0-0", "payload": {"seat": 0, "action": "raise_to", "amount": 300}}
{"timestamp": "2025-01-17T10:30:48.567Z", "type": "showdown", "hand_id": "101-0-0", "payload": {"winner": 0, "pot": 600}}
{"timestamp": "2025-01-17T10:30:49.012Z", "type": "hand_end", "hand_id": "101-0-0", "payload": {"delta": {0: 300, 1: -300}}}
```

---

## 🔍 Troubleshooting

### Common Issues

#### Issue: API Key Not Found

**Symptoms**: `Error: OPENROUTER_API_KEY environment variable not set`

**Solution**:
```bash
# Check if key is set
echo $OPENROUTER_API_KEY

# Set key for current session
export OPENROUTER_API_KEY=your_key

# Set permanently (add to ~/.bashrc or ~/.zshrc)
echo 'export OPENROUTER_API_KEY=your_key' >> ~/.bashrc
source ~/.bashrc
```

#### Issue: LLM Agent Timeout

**Symptoms**: High `timeout_count` in metrics, "Agent timed out" in logs

**Solutions**:
1. Increase timeout in config:
   ```yaml
   timeout_seconds: 120  # Default is 60
   ```

2. Check API latency:
   ```bash
   curl -X POST https://openrouter.ai/api/v1/chat/completions \
       -H "Authorization: Bearer $OPENROUTER_API_KEY" \
       -d '{"model": "openai/gpt-4o", "messages": [{"role": "user", "content": "test"}]}'
   ```

3. Use faster model or reduce prompt complexity

#### Issue: Illegal Actions

**Symptoms**: High `illegal_action_count`, agent folding unexpectedly

**Solution**: Check agent's action validation:
```python
def act(self, request: ActionRequest) -> ActionResponse:
    # Ensure action is in legal_actions
    if "raise_to" in request.legal_actions and self.wants_to_raise():
        return ActionResponse(action="raise_to", amount=valid_amount)
    elif "call" in request.legal_actions:
        return ActionResponse(action="call")
    else:
        return ActionResponse(action="fold")
```

#### Issue: Leaderboard Not Updating

**Symptoms**: New results not appearing on leaderboard

**Solutions**:
1. Check output directory:
   ```bash
   ls -lh artifacts/my_experiment/metrics.json
   ```

2. Verify metrics.json format:
   ```bash
   cat artifacts/my_experiment/metrics.json | python -m json.tool
   ```

3. Manual regeneration:
   ```bash
   cd leaderboard
   python leaderboard_generator.py
   ```

4. Clear browser cache and refresh

#### Issue: Import Errors

**Symptoms**: `ModuleNotFoundError: No module named 'green_agent_benchmark'`

**Solution**:
```bash
# Ensure package is installed
pip install -e .

# Or add to PYTHONPATH
export PYTHONPATH=$PWD:$PYTHONPATH
```

### Debug Mode

Enable verbose logging:

```bash
python -m green_agent_benchmark.cli \
    --config configs/dev_hu.yaml \
    --agent baseline:gpt5-hu \
    --output artifacts/debug_run \
    --log-level DEBUG
```

### Getting Help

1. **Check Documentation**:
   - [API Reference](API_REFERENCE.md)
   - [Architecture Guide](docs/ARCHITECTURE.md)
   - [Development Guide](docs/DEVELOPMENT.md)

2. **Review Logs**:
   ```bash
   # Check NDJSON logs for errors
   tail -n 100 artifacts/my_experiment/logs/*.ndjson
   ```

3. **Run Minimal Test**:
   ```bash
   # Ultra-fast connectivity test
   python -m green_agent_benchmark.cli \
       --config configs/ultra_fast_test.yaml \
       --agent baseline:random-hu \
       --output artifacts/minimal_test
   ```

---

## 📚 Documentation

### Complete Documentation Index

| Document | Description | Audience |
|----------|-------------|----------|
| **README.md** (this file) | Complete usage guide and quick start | All users |
| [API_REFERENCE.md](API_REFERENCE.md) | Complete API documentation | Developers |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture and design | Contributors |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Development guide and best practices | Contributors |
| [docs/AGENTBEATS.md](docs/AGENTBEATS.md) | AgentBeats platform integration | Platform users |
| [QUICK_START.md](QUICK_START.md) | 5-minute quick start guide | New users |
| [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) | Project overview and goals | All users |

### Quick Reference

#### Running Experiments
```bash
# HU quick test
python -m green_agent_benchmark.cli --config configs/demo_hu_10hands.yaml --agent baseline:gpt5-hu

# 6-max evaluation
python -m green_agent_benchmark.cli --config configs/dev_6max.yaml --agent baseline:deepseek-hu

# Custom agent
python -m green_agent_benchmark.cli --config configs/dev_hu.yaml --agent my_agents:MyAgent
```

#### Starting Services
```bash
# Leaderboard
bash start_leaderboard.sh

# AgentBeats integration
bash start_agentbeats.sh
```

#### Analyzing Results
```bash
# View metrics
cat artifacts/my_experiment/metrics.json | jq .

# Count hands
wc -l artifacts/my_experiment/logs/*.ndjson

# Extract specific metric
jq '.agents["gpt5-hu"].bb100' artifacts/my_experiment/metrics.json
```
