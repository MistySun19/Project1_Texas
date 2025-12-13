#!/bin/bash
# Player 1 部署脚本 (Named Tunnel)

set -e

cd "$(dirname "$0")"

echo "🧹 清理旧进程 (Player 1)..."
pkill -9 -f "agentbeats.*8021" 2>/dev/null || true
pkill -9 -f "cloudflared.*texas-player1" 2>/dev/null || true
sleep 2

echo "🌐 启动 Cloudflare Named Tunnel (player1.texas-agent.org)..."
cloudflared tunnel --config ~/.cloudflared/config-player1.yml run texas-player1 &
TUNNEL_PID=$!

sleep 5

PUBLIC_URL="https://player1.texas-agent.org"
HOST_WITHOUT_SCHEME="player1.texas-agent.org"

echo ""
echo "✅ Player 1 URL: $PUBLIC_URL"
echo ""
echo "🚀 启动 Player 1 Controller..."
echo ""

PORT=8021 CLOUDRUN_HOST=$HOST_WITHOUT_SCHEME agentbeats run_ctrl
