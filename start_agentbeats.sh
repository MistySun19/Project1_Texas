#!/bin/bash

# AgentBeats Agent 启动脚本
# 用法: ./start_agentbeats.sh [green|red|blue]

set -e

cd "$(dirname "$0")"

# 加载环境变量
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

MODE=${1:-green}

case $MODE in
    green)
        echo "🟢 启动 Green Agent (裁判/评估器)..."
        echo "端口: launcher=8000, agent=8001"
        echo ""
        echo "⚠️  请在另一个终端运行以下命令进行内网穿透:"
        echo "   ngrok http 8001"
        echo "   ngrok http 8000"
        echo ""
        python -m green_agent_benchmark.agentbeats.launcher \
            agentbeats/cards/texas_green_agent_card.toml \
            --launcher_host 0.0.0.0 --launcher_port 8000 \
            --agent_host 0.0.0.0 --agent_port 8001 \
            --output_root artifacts/agentbeats_runs \
            --hands_per_seed 50 --replicas 2
        ;;
    red)
        echo "🔴 启动 Red Agent (进攻方)..."
        echo "端口: 9011"
        echo ""
        echo "⚠️  请在另一个终端运行: ngrok http 9011"
        echo ""
        AGENT_SPEC=${AGENT_SPEC:-baseline:deepseek-hu}
        python -m green_agent_benchmark.agentbeats.player_server \
            agentbeats/cards/texas_red_agent_card.toml \
            --agent_spec "$AGENT_SPEC" \
            --agent_host 0.0.0.0 --agent_port 9011 \
            --name texas-red
        ;;
    blue)
        echo "🔵 启动 Blue Agent (防守方)..."
        echo "端口: 9021"
        echo ""
        echo "⚠️  请在另一个终端运行: ngrok http 9021"
        echo ""
        AGENT_SPEC=${AGENT_SPEC:-baseline:gemini-hu}
        python -m green_agent_benchmark.agentbeats.player_server \
            agentbeats/cards/texas_blue_agent_card.toml \
            --agent_spec "$AGENT_SPEC" \
            --agent_host 0.0.0.0 --agent_port 9021 \
            --name texas-blue
        ;;
    *)
        echo "用法: $0 [green|red|blue]"
        echo ""
        echo "  green - 启动 Green Agent (评估器/裁判)"
        echo "  red   - 启动 Red Agent (进攻方参赛者)"
        echo "  blue  - 启动 Blue Agent (防守方参赛者)"
        echo ""
        echo "环境变量:"
        echo "  AGENT_SPEC - 指定使用的 agent，如 'baseline:deepseek-hu'"
        exit 1
        ;;
esac


