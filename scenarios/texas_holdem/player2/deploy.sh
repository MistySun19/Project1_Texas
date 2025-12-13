#!/bin/bash
# Player 2 部署脚本 (Named Tunnel)

set -e

cd "$(dirname "$0")"

echo "🧹 清理旧进程 (Player 2)..."
pkill -9 -f "agentbeats.*9022" 2>/dev/null || true
pkill -9 -f "cloudflared.*texas-player2" 2>/dev/null || true
sleep 2

echo "🌐 启动 Cloudflare Named Tunnel (player2.texas-agent.org)..."
cloudflared tunnel --config ~/.cloudflared/config-player2.yml run texas-player2 &
TUNNEL_PID=$!

sleep 5

PUBLIC_URL="https://player2.texas-agent.org"
HOST_WITHOUT_SCHEME="player2.texas-agent.org"

echo ""
echo "✅ Player 2 URL: $PUBLIC_URL"
echo ""
echo "🚀 启动 Player 2 Controller..."
echo ""

PORT=9022 CLOUDRUN_HOST=$HOST_WITHOUT_SCHEME agentbeats run_ctrl
