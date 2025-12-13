#!/bin/bash

# =============================================================================
# AgentBeats + ngrok 一键启动脚本
# 
# 此脚本会：
# 1. 启动 ngrok 进行内网穿透
# 2. 自动获取 ngrok 生成的公网 URL
# 3. 更新 Agent Card 的 URL
# 4. 启动 Agent 服务
# =============================================================================

set -e

cd "$(dirname "$0")"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  AgentBeats Texas Hold'em 部署工具${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 加载环境变量
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo -e "${GREEN}✓ 已加载 .env 文件${NC}"
fi

# 检查 ngrok 是否安装
if ! command -v ngrok &> /dev/null; then
    echo -e "${RED}✗ ngrok 未安装${NC}"
    echo ""
    echo "请先安装 ngrok:"
    echo "  macOS:   brew install ngrok"
    echo "  Linux:   参考 https://ngrok.com/download"
    echo ""
    echo "安装后运行: ngrok config add-authtoken <your-token>"
    exit 1
fi

echo -e "${GREEN}✓ ngrok 已安装${NC}"

# 检查 Python 虚拟环境
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}! 未找到 .venv，正在创建...${NC}"
    python -m venv .venv
fi

source .venv/bin/activate
echo -e "${GREEN}✓ Python 虚拟环境已激活${NC}"

# 端口配置
AGENT_PORT=${AGENT_PORT:-8001}
LAUNCHER_PORT=${LAUNCHER_PORT:-8000}

echo ""
echo -e "${BLUE}端口配置:${NC}"
echo "  Agent:    $AGENT_PORT"
echo "  Launcher: $LAUNCHER_PORT"
echo ""

# 杀死可能存在的旧进程
echo -e "${YELLOW}正在清理旧进程...${NC}"
pkill -f "ngrok http $AGENT_PORT" 2>/dev/null || true
pkill -f "green_agent_benchmark.agentbeats" 2>/dev/null || true
sleep 1

# 启动 ngrok (后台运行，添加 response header 来跳过浏览器警告)
echo -e "${YELLOW}正在启动 ngrok...${NC}"
ngrok http $AGENT_PORT --response-header-add "ngrok-skip-browser-warning: true" > /dev/null 2>&1 &
NGROK_PID=$!
echo -e "${GREEN}✓ ngrok 已启动 (PID: $NGROK_PID)${NC}"

# 等待 ngrok 初始化
echo -e "${YELLOW}等待 ngrok 初始化...${NC}"
sleep 3

# 获取 ngrok 公网 URL
NGROK_URL=""
for i in {1..10}; do
    NGROK_URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | python -c "
import sys, json
try:
    data = json.load(sys.stdin)
    tunnels = data.get('tunnels', [])
    for t in tunnels:
        if t.get('proto') == 'https':
            print(t.get('public_url', ''))
            break
except:
    pass
" 2>/dev/null)
    
    if [ -n "$NGROK_URL" ]; then
        break
    fi
    echo "  重试获取 ngrok URL... ($i/10)"
    sleep 1
done

if [ -z "$NGROK_URL" ]; then
    echo -e "${RED}✗ 无法获取 ngrok URL${NC}"
    echo "请检查 ngrok 是否正确配置 authtoken"
    kill $NGROK_PID 2>/dev/null || true
    exit 1
fi

echo -e "${GREEN}✓ ngrok URL: ${NGROK_URL}${NC}"

# 更新 Agent Card 的 URL
CARD_FILE="agentbeats/cards/texas_green_agent_card.toml"
echo -e "${YELLOW}正在更新 Agent Card URL...${NC}"

# 使用 Python 更新 TOML 文件中的 URL
python << EOF
import re

with open("$CARD_FILE", "r") as f:
    content = f.read()

# 替换 url 字段
new_content = re.sub(
    r'^url\s*=\s*"[^"]*"',
    f'url                 = "${NGROK_URL}/"',
    content,
    flags=re.MULTILINE
)

with open("$CARD_FILE", "w") as f:
    f.write(new_content)

print("Agent Card URL 已更新")
EOF

echo -e "${GREEN}✓ Agent Card 已更新${NC}"

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}🎉 部署信息${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "  ${GREEN}ngrok URL:${NC}       $NGROK_URL"
echo -e "  ${GREEN}本地 Agent:${NC}      http://localhost:$AGENT_PORT"
echo -e "  ${GREEN}本地 Launcher:${NC}   http://localhost:$LAUNCHER_PORT"
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${YELLOW}在 AgentBeats 注册时使用:${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "  ${GREEN}Controller URL:${NC}  $NGROK_URL"
echo -e "  ${GREEN}Deploy Type:${NC}     Remote"
echo -e "  ${GREEN}Is Green Agent:${NC}  ✓ (如果是裁判 Agent)"
echo ""
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}按 Ctrl+C 停止所有服务${NC}"
echo ""

# 设置清理函数
cleanup() {
    echo ""
    echo -e "${YELLOW}正在停止服务...${NC}"
    kill $NGROK_PID 2>/dev/null || true
    pkill -f "green_agent_benchmark.agentbeats" 2>/dev/null || true
    echo -e "${GREEN}✓ 服务已停止${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# 启动 Agent 服务
echo -e "${GREEN}🚀 正在启动 Agent 服务...${NC}"
echo ""

python -m green_agent_benchmark.agentbeats.launcher \
    agentbeats/cards/texas_green_agent_card.toml \
    --launcher_host 0.0.0.0 --launcher_port $LAUNCHER_PORT \
    --agent_host 0.0.0.0 --agent_port $AGENT_PORT \
    --output_root artifacts/agentbeats_runs \
    --hands_per_seed 50 --replicas 2


