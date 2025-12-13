#!/bin/bash

# =============================================================================
# AgentBeats + Cloudflare Tunnel 启动脚本
# 
# 使用方法:
#   1. 首次使用需要先配置 Cloudflare Tunnel (见下方说明)
#   2. 设置环境变量 CLOUDFLARE_DOMAIN 为你的域名
#   3. 运行此脚本: ./start_agentbeats_cloudflare.sh
#
# Cloudflare Tunnel 配置步骤:
#   1. 登录 Cloudflare Dashboard -> Zero Trust -> Networks -> Tunnels
#   2. 创建一个 Tunnel，记下 Tunnel Token
#   3. 配置 Public Hostname 指向 localhost:8001
#   4. 将 Token 保存到环境变量或 .env 文件
# =============================================================================

set -e

cd "$(dirname "$0")"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  AgentBeats Texas Hold'em (Cloudflare)${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 加载环境变量
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo -e "${GREEN}✓ 已加载 .env 文件${NC}"
fi

# 检查必要的环境变量
if [ -z "$CLOUDFLARE_DOMAIN" ]; then
    echo -e "${RED}✗ 请设置 CLOUDFLARE_DOMAIN 环境变量${NC}"
    echo ""
    echo "例如: export CLOUDFLARE_DOMAIN=your-subdomain.your-domain.com"
    echo "或者在 .env 文件中添加: CLOUDFLARE_DOMAIN=your-subdomain.your-domain.com"
    exit 1
fi

# 检查 cloudflared
if ! command -v cloudflared &> /dev/null; then
    echo -e "${RED}✗ cloudflared 未安装${NC}"
    echo ""
    echo "请先安装 cloudflared:"
    echo "  macOS:   brew install cloudflared"
    echo "  Linux:   参考 https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
    exit 1
fi

echo -e "${GREEN}✓ cloudflared 已安装${NC}"

# 检查 Python 虚拟环境
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}! 未找到 .venv，正在创建...${NC}"
    python3 -m venv .venv
fi

source .venv/bin/activate
echo -e "${GREEN}✓ Python 虚拟环境已激活${NC}"

# 端口配置
AGENT_PORT=${AGENT_PORT:-8001}

echo ""
echo -e "${BLUE}配置信息:${NC}"
echo "  Agent Port:    $AGENT_PORT"
echo "  Domain:        https://$CLOUDFLARE_DOMAIN"
echo ""

# 更新 Agent Card 的 URL
CARD_FILE="agentbeats/cards/texas_green_agent_card.toml"
echo -e "${YELLOW}正在更新 Agent Card URL...${NC}"

python3 << EOF
import re

with open("$CARD_FILE", "r") as f:
    content = f.read()

# 替换 url 字段
new_content = re.sub(
    r'^url\s*=\s*"[^"]*"',
    f'url                 = "https://$CLOUDFLARE_DOMAIN/"',
    content,
    flags=re.MULTILINE
)

with open("$CARD_FILE", "w") as f:
    f.write(new_content)

print("Agent Card URL 已更新为: https://$CLOUDFLARE_DOMAIN/")
EOF

echo -e "${GREEN}✓ Agent Card 已更新${NC}"

# 清理旧进程
echo -e "${YELLOW}正在清理旧进程...${NC}"
pkill -f "green_agent_benchmark.agentbeats" 2>/dev/null || true
sleep 1

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}🎉 部署信息${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "  ${GREEN}公网 URL:${NC}        https://$CLOUDFLARE_DOMAIN"
echo -e "  ${GREEN}本地 Agent:${NC}      http://localhost:$AGENT_PORT"
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${YELLOW}在 AgentBeats 注册时使用:${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "  ${GREEN}Controller URL:${NC}  https://$CLOUDFLARE_DOMAIN"
echo -e "  ${GREEN}Deploy Type:${NC}     Remote"
echo -e "  ${GREEN}Is Green Agent:${NC}  ✓"
echo ""
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}⚠️  请确保 Cloudflare Tunnel 已在另一个终端运行:${NC}"
echo -e "    cloudflared tunnel run <tunnel-name>"
echo ""
echo -e "${YELLOW}按 Ctrl+C 停止 Agent 服务${NC}"
echo ""

# 设置清理函数
cleanup() {
    echo ""
    echo -e "${YELLOW}正在停止服务...${NC}"
    pkill -f "green_agent_benchmark.agentbeats" 2>/dev/null || true
    echo -e "${GREEN}✓ 服务已停止${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# 启动 Agent 服务
echo -e "${GREEN}🚀 正在启动 Agent 服务...${NC}"
echo ""

python -m green_agent_benchmark.agentbeats.agent_server \
    agentbeats/cards/texas_green_agent_card.toml \
    --agent_host 0.0.0.0 --agent_port $AGENT_PORT \
    --output_root artifacts/agentbeats_runs \
    --hands_per_seed 50 --replicas 2
