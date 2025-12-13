#!/bin/bash
# Texas Hold'em Judge 部署脚本 (Named Tunnel)

set -e

cd "$(dirname "$0")"

echo "🧹 清理旧进程..."
pkill -9 -f "agentbeats" 2>/dev/null || true
pkill -9 -f "cloudflared.*texas-judge" 2>/dev/null || true
sleep 2

echo "🌐 启动 Cloudflare Named Tunnel (judge.texas-agent.org)..."
cloudflared tunnel --config ~/.cloudflared/config-judge.yml run texas-judge &
TUNNEL_PID=$!

sleep 5

PUBLIC_URL="https://judge.texas-agent.org"
HOST_WITHOUT_SCHEME="judge.texas-agent.org"

echo ""
echo "✅ Judge URL: $PUBLIC_URL"
echo ""
echo "🚀 启动 AgentBeats Controller..."
echo ""

CLOUDRUN_HOST=$HOST_WITHOUT_SCHEME agentbeats run_ctrl
