# Texas Hold'em Poker Agent - AgentBeats 部署指南

## 📋 项目概述

这是一个基于 A2A (Agent-to-Agent) 协议的德州扑克对战系统，部署在 AgentBeats 平台上。

### 架构

```
┌─────────────────────────────────────────────────────────────┐
│                    AgentBeats Platform                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Judge (Green Agent)                        │
│                 judge.texas-agent.org:8010                   │
│         负责：发牌、游戏流程控制、结算、评分                    │
└─────────────────────────────────────────────────────────────┘
                    │                    │
                    ▼                    ▼
┌──────────────────────────┐  ┌──────────────────────────┐
│   Player 1 (Purple Agent) │  │   Player 2 (Purple Agent) │
│  player1.texas-agent.org  │  │  player2.texas-agent.org  │
│        端口: 8021         │  │        端口: 9022         │
└──────────────────────────┘  └──────────────────────────┘
```

## 🌐 固定域名

| 服务 | 域名 | 本地端口 |
|------|------|----------|
| Judge | `https://judge.texas-agent.org` | 8010 |
| Player 1 | `https://player1.texas-agent.org` | 8021 |
| Player 2 | `https://player2.texas-agent.org` | 9022 |

## 🚀 快速部署

### 前提条件

1. 安装依赖：
```bash
pip install a2a-sdk earthshaker
brew install cloudflared  # macOS
```

2. Cloudflare Tunnel 已配置（首次需要登录）：
```bash
cloudflared tunnel login
```

### 启动服务

在 **3 个独立终端** 中分别运行：

```bash
# 终端 1 - Judge (Green Agent)
cd scenarios/texas_holdem
./deploy.sh

# 终端 2 - Player 1
cd scenarios/texas_holdem/player1
./deploy.sh

# 终端 3 - Player 2
cd scenarios/texas_holdem/player2
./deploy.sh
```

### 在 AgentBeats 平台注册

1. 访问 [AgentBeats](https://agentbeats.ai)
2. 注册 Green Agent：`https://judge.texas-agent.org`
3. 注册 Purple Agent 1：`https://player1.texas-agent.org`
4. 注册 Purple Agent 2：`https://player2.texas-agent.org`
5. 运行评估

## 📁 文件结构

```
scenarios/texas_holdem/
├── README.md              # 本文档
├── deploy.sh              # Judge 部署脚本
├── texas_judge.py         # Judge (Green Agent) 实现
├── poker_player.py        # Player (Purple Agent) 实现
├── scenario.toml          # Agent 配置文件
├── player1/
│   └── deploy.sh          # Player 1 部署脚本
└── player2/
    └── deploy.sh          # Player 2 部署脚本
```

## 🎮 游戏规则

- **游戏类型**: Heads-Up No-Limit Texas Hold'em (1v1 无限注德州扑克)
- **初始筹码**: 每人 1000 chips
- **盲注**: 小盲 5 / 大盲 10
- **手数**: 默认 10 手
- **评分**: 基于最终筹码变化

---

# 🔧 开发者指南：如何编写自定义 Player

## 方法一：修改现有 `poker_player.py`

最简单的方式是修改 `poker_player.py` 中的 `decide_action` 方法：

```python
# 在 poker_player.py 中找到 PokerPlayerAgent 类

class PokerPlayerAgent:
    async def decide_action(self, game_state: dict) -> str:
        """
        根据游戏状态决定行动
        
        参数:
            game_state: 包含以下字段的字典
                - hole_cards: 你的手牌，如 ["Ah", "Kd"]
                - community_cards: 公共牌，如 ["Qs", "Jc", "Td"]
                - pot: 当前底池
                - current_bet: 当前需要跟注的金额
                - my_stack: 你的筹码
                - opponent_stack: 对手筹码
                - position: "SB" 或 "BB"
                - betting_round: "preflop", "flop", "turn", "river"
                - valid_actions: 可用行动列表
                - action_history: 本轮行动历史
        
        返回:
            行动字符串: "fold", "check", "call", "raise X" (X为加注金额)
        """
        # 在这里实现你的策略
        hole_cards = game_state.get("hole_cards", [])
        community_cards = game_state.get("community_cards", [])
        valid_actions = game_state.get("valid_actions", [])
        
        # 示例：简单策略
        if "check" in valid_actions:
            return "check"
        elif "call" in valid_actions:
            return "call"
        else:
            return "fold"
```

## 方法二：创建新的 Player 文件

如果你想要完全自定义的 Player，可以创建新文件：

### 步骤 1: 复制模板

```bash
cp poker_player.py my_smart_player.py
```

### 步骤 2: 修改 Agent 信息

```python
# my_smart_player.py

AGENT_CARD = AgentCard(
    name="My Smart Poker Player",  # 修改名称
    description="An AI poker player using advanced strategy",
    url=agent_url,
    version="1.0.0",
    default_input_modes=["text"],
    default_output_modes=["text"],
    capabilities=AgentCapabilities(streaming=False, pushNotifications=False),
    skills=[
        AgentSkill(
            id="play_poker",
            name="Play Texas Hold'em",
            description="Plays poker with advanced strategy",
            tags=["poker", "game", "strategy"],
            examples=["Make a poker decision based on game state"]
        )
    ]
)
```

### 步骤 3: 实现策略

```python
class SmartPokerPlayer:
    def __init__(self):
        self.hand_history = []
        
    async def decide_action(self, game_state: dict) -> str:
        """实现你的策略"""
        hole_cards = game_state["hole_cards"]
        community_cards = game_state.get("community_cards", [])
        pot = game_state["pot"]
        current_bet = game_state["current_bet"]
        my_stack = game_state["my_stack"]
        
        # 计算手牌强度
        hand_strength = self.evaluate_hand(hole_cards, community_cards)
        
        # 计算底池赔率
        pot_odds = current_bet / (pot + current_bet) if current_bet > 0 else 0
        
        # 决策逻辑
        if hand_strength > 0.8:
            # 强牌：加注
            raise_amount = min(pot, my_stack)
            return f"raise {raise_amount}"
        elif hand_strength > pot_odds:
            # 有利可图：跟注
            return "call" if current_bet > 0 else "check"
        else:
            # 弃牌
            return "check" if "check" in game_state["valid_actions"] else "fold"
    
    def evaluate_hand(self, hole_cards, community_cards):
        """评估手牌强度 (0-1)"""
        # 实现手牌评估逻辑
        # 可以使用现有的 green_agent_benchmark/cards.py
        pass
```

### 步骤 4: 创建部署脚本

```bash
# 创建新的 player 目录
mkdir -p scenarios/texas_holdem/my_player

# 创建部署脚本
cat > scenarios/texas_holdem/my_player/deploy.sh << 'EOF'
#!/bin/bash
set -e
cd "$(dirname "$0")"

# 使用不同的端口
PORT=8030
TUNNEL_NAME="texas-myplayer"
DOMAIN="myplayer.texas-agent.org"

echo "🚀 启动 My Smart Player..."
PORT=$PORT CLOUDRUN_HOST=$DOMAIN agentbeats run_ctrl
EOF

chmod +x scenarios/texas_holdem/my_player/deploy.sh
```

### 步骤 5: 添加 Cloudflare Tunnel（可选，用于固定域名）

```bash
# 创建新的 tunnel
cloudflared tunnel create texas-myplayer

# 添加 DNS 路由
cloudflared tunnel route dns texas-myplayer myplayer.texas-agent.org

# 创建配置文件
cat > ~/.cloudflared/config-myplayer.yml << EOF
tunnel: <TUNNEL_ID>
credentials-file: /Users/misty/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: myplayer.texas-agent.org
    service: http://localhost:8030
  - service: http_status:404
EOF
```

## 方法三：集成 LLM (如 GPT-4, Claude)

参考项目中已有的 LLM Agent 实现：

```
green_agent_benchmark/agents/
├── openai_base.py      # OpenAI API 基类
├── gpt5_agent.py       # GPT-5 实现
├── deepseek_agent.py   # DeepSeek 实现
├── gemini_agent.py     # Gemini 实现
├── cohere_agent.py     # Cohere 实现
└── qwen_agent.py       # 通义千问实现
```

### 示例：GPT-4 Poker Player

```python
import openai

class GPT4PokerPlayer:
    def __init__(self):
        self.client = openai.OpenAI(api_key="your-api-key")
        
    async def decide_action(self, game_state: dict) -> str:
        prompt = f"""You are an expert poker player. Given the current game state, decide your action.

Game State:
- Your hole cards: {game_state['hole_cards']}
- Community cards: {game_state.get('community_cards', [])}
- Pot: {game_state['pot']}
- Current bet to call: {game_state['current_bet']}
- Your stack: {game_state['my_stack']}
- Valid actions: {game_state['valid_actions']}

Respond with ONLY your action: fold, check, call, or raise X (where X is the amount).
"""
        response = self.client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=50
        )
        
        return response.choices[0].message.content.strip().lower()
```

## 📊 游戏状态详解

Judge 发送给 Player 的游戏状态包含：

```json
{
  "type": "action_request",
  "hand_id": 1,
  "betting_round": "flop",
  "hole_cards": ["Ah", "Kd"],
  "community_cards": ["Qs", "Jc", "Td"],
  "pot": 100,
  "current_bet": 20,
  "my_stack": 980,
  "opponent_stack": 920,
  "my_position": "BTN",
  "valid_actions": ["fold", "call", "raise"],
  "min_raise": 40,
  "max_raise": 980,
  "action_history": [
    {"player": "opponent", "action": "bet", "amount": 20}
  ]
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | string | 消息类型，`action_request` 表示需要行动 |
| `hand_id` | int | 当前手牌编号 |
| `betting_round` | string | 当前轮次：`preflop`, `flop`, `turn`, `river` |
| `hole_cards` | array | 你的两张底牌 |
| `community_cards` | array | 公共牌（0-5张） |
| `pot` | int | 当前底池大小 |
| `current_bet` | int | 需要跟注的金额 |
| `my_stack` | int | 你的剩余筹码 |
| `opponent_stack` | int | 对手剩余筹码 |
| `my_position` | string | 你的位置：`BTN`(按钮位) 或 `BB`(大盲) |
| `valid_actions` | array | 可用行动列表 |
| `min_raise` | int | 最小加注额 |
| `max_raise` | int | 最大加注额（全押） |
| `action_history` | array | 本轮行动历史 |

### 牌面格式

牌面使用两个字符表示：`{Rank}{Suit}`

- **Rank**: `2-9`, `T`(10), `J`, `Q`, `K`, `A`
- **Suit**: `s`(♠), `h`(♥), `d`(♦), `c`(♣)

示例：`Ah` = A♥, `Td` = 10♦, `2c` = 2♣

## 🔍 调试技巧

### 本地测试

无需部署到平台，可以本地测试：

```bash
cd scenarios/texas_holdem

# 启动 Judge（不通过 Tunnel）
python texas_judge.py &

# 启动 Player 1
PORT=8021 python poker_player.py &

# 启动 Player 2
PORT=9022 python poker_player.py &

# 手动触发游戏
curl -X POST http://localhost:8010/run \
  -H "Content-Type: application/json" \
  -d '{"player_0_url": "http://localhost:8021", "player_1_url": "http://localhost:9022"}'
```

### 查看日志

```bash
# 查看 Tunnel 状态
cloudflared tunnel list

# 查看实时日志
tail -f ~/.cloudflared/cloudflared.log
```

### 常见问题

1. **端口被占用**
   ```bash
   lsof -i :8010  # 查看占用端口的进程
   kill -9 <PID>  # 终止进程
   ```

2. **Tunnel 无法连接**
   ```bash
   # 检查 DNS
   dig judge.texas-agent.org
   
   # 重启 Tunnel
   cloudflared tunnel cleanup texas-judge
   cloudflared tunnel run texas-judge
   ```

3. **Agent Card 格式错误**
   - 确保 `default_input_modes` 和 `default_output_modes` 使用 `["text"]` 而不是 `["text/plain"]`

## 📚 相关资源

- [A2A SDK 文档](https://github.com/google/a2a-sdk)
- [AgentBeats 平台](https://agentbeats.ai)
- [Cloudflare Tunnel 文档](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
- [Texas Hold'em 规则](https://en.wikipedia.org/wiki/Texas_hold_%27em)

## 📝 许可证

MIT License
