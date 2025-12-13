# AgentBeats 部署指南

本项目已按照 [agentbeats/tutorial](https://github.com/agentbeats/tutorial) 官方教程配置。

## 快速开始

### 1. 安装依赖

```bash
# 安装 uv（如果没有）
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# 进入 tutorial 目录同步依赖
cd agentbeats-tutorial
uv sync
```

### 2. 配置环境变量

```bash
# 复制环境变量模板
cp sample.env .env

# 编辑 .env 填入 API keys（如果需要 LLM）
# GOOGLE_API_KEY=your_key
# OPENAI_API_KEY=your_key
```

### 3. 本地运行 Texas Hold'em 场景

```bash
cd agentbeats-tutorial
uv run agentbeats-run ../scenarios/texas_holdem/scenario.toml --show-logs
```

## 项目结构

```
Project1_Texas/
├── agentbeats-tutorial/           # 官方教程（提供运行框架）
│   └── src/agentbeats/            # 核心 SDK 代码
├── scenarios/
│   └── texas_holdem/
│       ├── scenario.toml          # 场景配置
│       ├── texas_judge.py         # Green Agent（评估者/裁判）
│       └── poker_player.py        # Purple Agent（玩家）
└── green_agent_benchmark/         # 原有的扑克引擎
```

## 关键概念

### Controller 是什么？

在 AgentBeats 平台上：
- **Controller** = AgentBeats 平台本身的调度服务
- **Green Agent** = 你的评估器（texas_judge.py），负责协调游戏
- **Purple Agent** = 参赛的 AI 玩家

当你在 AgentBeats 平台注册 Green Agent 时，平台的 Controller 会：
1. 获取你的 Agent Card（从 `/.well-known/agent.json`）
2. 验证连接是否可达
3. 当有评估请求时，Controller 会调用你的 Green Agent

### 本地测试 vs 云端部署

**本地测试**（不需要 Controller）：
```bash
uv run agentbeats-run scenarios/texas_holdem/scenario.toml
```

**云端部署**（需要公网可访问的 URL）：

1. 启动 Green Agent 并暴露到公网：
```bash
# 使用 Cloudflare Tunnel
python scenarios/texas_holdem/texas_judge.py \
    --host 0.0.0.0 --port 9009 \
    --cloudflare-quick-tunnel
```

2. 复制输出的公网 URL（如 `https://xxx.trycloudflare.com`）

3. 在 AgentBeats 平台注册这个 URL 作为你的 Green Agent

## 场景配置说明

`scenario.toml` 文件定义了整个评估场景：

```toml
[green_agent]
endpoint = "http://127.0.0.1:9009"    # Green Agent 地址
cmd = "python texas_judge.py ..."     # 启动命令

[[participants]]
role = "player_0"                      # 角色名
endpoint = "http://127.0.0.1:9019"    # Purple Agent 地址
cmd = "python poker_player.py ..."    # 启动命令

[config]
num_hands = 10                         # 打几手牌
starting_stack = 1000                  # 初始筹码
small_blind = 10                       # 小盲注
big_blind = 20                         # 大盲注
```

## 常见问题

### Q: "Controller Reachable: No" 错误

A: 这意味着 AgentBeats 平台无法访问你的服务。确保：
1. 使用 Cloudflare Tunnel 或 ngrok 暴露到公网
2. 防火墙没有阻止连接
3. Agent Card 端点返回正确的 JSON

### Q: 如何测试 Agent Card？

```bash
curl http://localhost:9009/.well-known/agent.json
```

### Q: 如何用真正的 LLM？

编辑 `poker_player.py`，取消注释 LiteLLM 部分，并确保 `.env` 中有正确的 API key。

---

更多信息请参考官方教程：https://github.com/agentbeats/tutorial
