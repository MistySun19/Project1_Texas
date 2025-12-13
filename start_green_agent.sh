#!/bin/bash
# 启动 Texas Hold'em Green Agent

cd "$(dirname "$0")"
source .venv/bin/activate

echo "=========================================="
echo "  Texas Hold'em Green Agent Evaluator"
echo "=========================================="

# 默认端口
PORT=${1:-8001}

echo "Starting Green Agent on port $PORT..."
echo ""
echo "Agent card will be at:"
echo "  - http://localhost:$PORT/.well-known/agent.json"
echo ""
echo "To expose via Cloudflare (run in another terminal):"
echo "  cloudflared tunnel --url http://localhost:$PORT"
echo ""

python -m green_agent_benchmark.a2a.server --host 0.0.0.0 --port $PORT
