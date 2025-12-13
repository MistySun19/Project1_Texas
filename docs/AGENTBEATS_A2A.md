# AgentBeats A2A Integration Guide

This document explains how to use the Texas Hold'em Green Agent with the new AgentBeats A2A protocol.

## Quick Start

### 1. Run the Green Agent Locally

```bash
# Install dependencies
pip install -e .
pip install a2a-sdk uvicorn httpx

# Start the green agent server
python -m green_agent_benchmark.a2a.server --host 0.0.0.0 --port 8001
```

The agent card will be available at: `http://localhost:8001/.well-known/agent.json`

### 2. Test with a Purple Agent

Send an assessment request to the green agent:

```bash
curl -X POST http://localhost:8001/tasks/send \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "role": "user",
      "parts": [{
        "text": "{\"participants\": {\"agent\": \"http://localhost:9019\"}, \"config\": {\"mode\": \"hu\", \"num_hands\": 10}}"
      }]
    }
  }'
```

### 3. Docker Build & Run

```bash
# Build the image
docker build --platform linux/amd64 -t texas-evaluator:latest -f Dockerfile.evaluator .

# Run locally
docker run -p 8001:8001 texas-evaluator:latest

# Or with custom URL
docker run -p 8001:8001 texas-evaluator:latest --port 8001 --card-url https://your-domain.com/
```

## Assessment Flow

### Request Format

The green agent expects an `EvalRequest` in JSON format:

```json
{
  "participants": {
    "player1": "http://agent1.example.com:8001",
    "player2": "http://agent2.example.com:8001"
  },
  "config": {
    "mode": "hu",
    "num_hands": 100,
    "seeds": [101, 102, 103],
    "blinds": {"sb": 50, "bb": 100},
    "stacks_bb": 100,
    "opponent": "random"
  }
}
```

### Config Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `mode` | string | "hu" | Game mode: "hu" (heads-up) or "sixmax" |
| `num_hands` | int | 10 | Total hands to play |
| `seeds` | list[int] | [101, 102] | Random seeds for reproducibility |
| `blinds` | object | {"sb": 50, "bb": 100} | Blind sizes |
| `stacks_bb` | int | 100 | Starting stack in big blinds |
| `opponent` | string | "random" | Baseline opponent for single-agent mode |

### Response Format

The green agent produces artifacts with evaluation results:

```json
{
  "mode": "hu",
  "num_hands": 100,
  "results": {
    "participants": {
      "player1": "http://agent1.example.com:8001",
      "player2": "http://agent2.example.com:8001"
    },
    "hands_played": 100,
    "player_deltas": {
      "player1": 1250,
      "player2": -1250
    },
    "player1_bb_100": 12.5,
    "player2_bb_100": -12.5
  },
  "winner": "player1",
  "time_used": 45.2
}
```

## Purple Agent Protocol

Purple agents (participants) must respond to Texas Hold'em action requests:

### Action Request (from Green Agent)

```json
{
  "type": "texas_action_request",
  "seat_id": 0,
  "request": {
    "hand_id": "101-0-0",
    "seat_id": 0,
    "hole_cards": ["Ah", "Kd"],
    "community_cards": ["Qh", "Jh", "Th"],
    "pot": 500,
    "to_call": 100,
    "min_raise": 200,
    "max_raise": 5000,
    "valid_actions": ["fold", "call", "raise_to"]
  }
}
```

### Action Response (from Purple Agent)

```json
{
  "action": "raise_to",
  "amount": 300
}
```

Valid actions:
- `fold` - Give up the hand
- `check` - Pass (when to_call is 0)
- `call` - Match the current bet
- `raise_to` - Raise to a specific amount (requires `amount` field)

## Registering on AgentBeats

### 1. Build and Push Docker Image

```bash
# Tag for GHCR
docker tag texas-evaluator:latest ghcr.io/YOUR_USERNAME/texas-evaluator:latest

# Push to registry
docker push ghcr.io/YOUR_USERNAME/texas-evaluator:latest
```

### 2. Create Leaderboard Repository

Fork the [leaderboard template](https://github.com/agentbeats/leaderboard-template) and configure it for your benchmark.

### 3. Register Green Agent

Go to [agentbeats.dev](https://agentbeats.dev/) and register your green agent with:
- Leaderboard repository URL
- Docker image reference: `ghcr.io/YOUR_USERNAME/texas-evaluator:latest`

## Local Development

### Using scenario.toml

Create a `scenario.toml` file:

```toml
[green_agent]
endpoint = "http://localhost:8001"
cmd = "python -m green_agent_benchmark.a2a.server --host 127.0.0.1 --port 8001"

[[participants]]
role = "player1"
endpoint = "http://localhost:9019"
agentbeats_id = ""

[config]
mode = "hu"
num_hands = 10
seeds = [101, 102]
```

### Running with Docker Compose

```yaml
version: '3.8'
services:
  evaluator:
    build:
      context: .
      dockerfile: Dockerfile.evaluator
    ports:
      - "8001:8001"
    environment:
      - PYTHONUNBUFFERED=1

  agent:
    image: your-purple-agent:latest
    ports:
      - "9019:9019"
```

```bash
docker compose up
```

## Architecture

```
green_agent_benchmark/
├── a2a/                          # New A2A protocol support
│   ├── __init__.py
│   ├── models.py                 # EvalRequest, EvalResult
│   ├── green_executor.py         # GreenAgent, GreenExecutor base classes
│   ├── client.py                 # A2A client utilities
│   ├── tool_provider.py          # Agent communication helper
│   ├── texas_evaluator.py        # Texas Hold'em green agent
│   └── server.py                 # Entry point for A2A server
├── engine.py                     # Poker game engine
├── runner.py                     # Benchmark orchestration
├── agents/                       # Agent implementations
└── ...

scenarios/
└── texas_holdem/
    └── scenario.toml             # Assessment configuration
```

## Troubleshooting

### Agent Card Not Found

Make sure the server is running and accessible:
```bash
curl http://localhost:8001/.well-known/agent.json
```

### Connection Refused

Check that the port is not blocked and the host is accessible:
```bash
# For Docker on Mac/Windows, use host.docker.internal
curl http://host.docker.internal:9019/.well-known/agent.json
```

### Timeout Errors

Increase the timeout in config or ensure agents respond within the default timeout (300s).
