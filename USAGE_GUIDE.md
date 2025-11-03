# Green Agent Benchmark - 完整使用指南

这是Green Agent Benchmark项目的完整使用说明文档，涵盖安装、配置、运行实验和查看结果的全流程。

## 📋 目录

1. [项目概述](#项目概述)
2. [快速开始](#快速开始)
3. [环境配置](#环境配置)
4. [运行实验](#运行实验)
5. [配置文件详解](#配置文件详解)
6. [代理开发](#代理开发)
7. [排行榜系统](#排行榜系统)
8. [数据分析](#数据分析)
9. [高级用法](#高级用法)
10. [故障排除](#故障排除)

---

## 📖 项目概述

Green Agent Benchmark是一个用于评估大语言模型（LLM）和基于规则的扑克代理的实时No-Limit Texas Hold'em评估框架。该项目提供：

### 🎯 核心功能
- **NLHE游戏引擎**: 完整的德州扑克状态机，支持盲注、边池、全押锁定
- **双模式评估**: Heads-Up (HU)和6-Max两种游戏模式
- **方差控制**: Duplicate-HU匹配和位置平衡副本技术
- **多代理支持**: 支持LLM、规则型、强化学习等多种类型代理
- **统计指标**: bb/100、置信区间、行为统计（VPIP/PFR/AF等）
- **Web排行榜**: 实时更新的交互式排行榜系统
- **完全可复现**: 基于种子的确定性日志记录

### 🏗️ 项目结构
```
Project1_Texas/
├── green_agent_benchmark/    # 核心评估框架
│   ├── engine.py            # 德州扑克游戏引擎
│   ├── runner.py            # 实验协调器
│   ├── agents/              # 各种代理实现
│   ├── metrics.py           # 指标计算
│   └── cli.py               # 命令行接口
├── leaderboard/             # Web排行榜系统
├── configs/                 # 实验配置文件
├── artifacts/               # 实验结果存储
├── scripts/                 # 辅助脚本
└── docs/                    # 文档
```

---

## 🚀 快速开始

### 1. 环境要求
- **Python 3.10+**
- **操作系统**: macOS/Linux/Windows
- **内存**: 建议8GB+
- **存储**: 至少5GB可用空间

### 2. 安装步骤

```bash
# 1. 克隆项目
git clone https://github.com/lusunjia/Project1_Texas.git
cd Project1_Texas

# 2. 创建虚拟环境
python -m venv .venv

# 3. 激活虚拟环境
# macOS/Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# 4. 安装依赖
pip install -r requirements.txt

# 5. 验证安装
python -m green_agent_benchmark.cli --help
```

### 3. 运行第一个实验

```bash
# 运行10手快速测试
python -m green_agent_benchmark.cli \
  --config configs/demo_hu_10hands.yaml \
  --agent baseline:random-hu \
  --output artifacts/first_test
```

### 4. 启动排行榜

```bash
# 生成排行榜数据
python leaderboard/leaderboard_generator.py

# 启动Web服务器
python leaderboard/server.py
# 浏览器访问: http://localhost:8000
```

---

## ⚙️ 环境配置

### API密钥配置

创建 `.env` 文件来存储API密钥：

```bash
# .env 文件内容
# OpenAI (GPT-5)
OPENAI_API_KEY=sk-your-openai-key

# DeepSeek
DEEPSEEK_API_KEY=your-deepseek-key
DEEPSEEK_API_BASE=https://api.deepseek.com/v1

# Gemini
GEMINI_API_KEY=your-gemini-key
GEMINI_API_BASE=https://generativelanguage.googleapis.com/v1beta

# Moonshot Kimi
KIMI_API_KEY=your-kimi-key
KIMI_API_BASE=https://api.moonshot.cn/v1

# Alibaba Qwen
QWEN_API_KEY=your-qwen-key
QWEN_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1

# ByteDance Doubao
DOUBAO_API_KEY=your-doubao-key
DOUBAO_API_BASE=https://ark.cn-beijing.volces.com/api/v3
```

### 环境变量说明
- `*_API_KEY`: 各平台的API密钥
- `*_API_BASE`: API基础URL（可选，有默认值）
- `*_MODEL`: 模型名称（可选，有默认值）

---

## 🎮 运行实验

### HU (Heads-Up) 模式

#### 1. 基础HU实验
```bash
# Random代理 vs TAG代理
python -m green_agent_benchmark.cli \
  --config configs/dev_hu.yaml \
  --agent baseline:random-hu \
  --output artifacts/random_vs_tag
```

#### 2. LLM vs LLM对战
```bash
# GPT-5 vs DeepSeek
export OPENAI_API_KEY=your-key
export DEEPSEEK_API_KEY=your-key

python -m green_agent_benchmark.cli \
  --config configs/demo_hu_deepseek_vs_gpt5.yaml \
  --agent green_agent_benchmark.agents.gpt5_agent:GPT5Agent \
  --agent-name GPT5 \
  --output artifacts/gpt5_vs_deepseek
```

#### 3. 自定义代理测试
```bash
# 使用自己开发的代理
python -m green_agent_benchmark.cli \
  --config configs/dev_hu.yaml \
  --agent mybot:MyAgent \
  --agent-name "My Custom Agent" \
  --output artifacts/my_agent_test
```

### 6-Max 模式

#### 1. 6-Max基础测试
```bash
python -m green_agent_benchmark.cli \
  --config configs/dev_6max.yaml \
  --agent baseline:tag-6 \
  --output artifacts/tag_6max
```

#### 2. LLM Showdown (6个LLM同台竞技)
```bash
# 确保所有API密钥都已配置
python -m green_agent_benchmark.cli \
  --config configs/sixmax_llm_showdown.yaml \
  --output artifacts/sixmax_showdown
```

### 实验输出

每个实验会在指定的 `--output` 目录生成：

```
artifacts/experiment_name/
├── logs/                    # 详细游戏日志
│   ├── hu/                  # HU模式日志
│   └── sixmax/              # 6-Max模式日志
└── metrics/                 # 统计指标
    ├── metrics.json         # 聚合统计数据
    └── per_hand_metrics.ndjson  # 逐手详细数据
```

---

## 📝 配置文件详解

### HU配置示例 (`configs/dev_hu.yaml`)

```yaml
mode: hu                     # 游戏模式: hu 或 sixmax
blinds:
  sb: 50                     # 小盲注
  bb: 100                    # 大盲注
stacks_bb: 100               # 起始筹码(以大盲注为单位)
seeds: [101, 102, 103]       # 随机种子列表
hands_per_seed: 500          # 每个种子的手数
replicas: 2                  # 副本数量(HU模式必须为2)
opponent_mix:                # 对手组合
  random-hu: 0.3             # 30% Random代理
  tag-hu: 0.5                # 50% TAG代理
  cfr-lite-hu: 0.2           # 20% CFR-lite代理
```

### 6-Max配置示例 (`configs/dev_6max.yaml`)

```yaml
mode: sixmax                 # 6-Max模式
blinds:
  sb: 50
  bb: 100
stacks_bb: 100
seeds: [201, 202, 203]
hands_per_replica: 200       # 每个副本的手数
seat_replicas: 6             # 座位副本数量(必须为6)
opponent_pool:               # 对手池
  random-6: 0.3
  tag-6: 0.4
  cfr-lite-6: 0.3
population_mirroring: true   # 群体镜像(保持对手一致性)
```

### 完整Lineup配置

```yaml
mode: sixmax
lineup:                      # 直接指定所有6个座位
  - baseline:gpt5-6
  - baseline:deepseek-6
  - baseline:gemini-6
  - baseline:kimi-6
  - baseline:qwen-6
  - baseline:doubao-6
# 使用lineup时不需要opponent_pool
```

### 高级参数

```yaml
# 系统级设置
time_per_decision_ms: 60000  # 每次决策时间限制
auto_top_up: true            # 自动补满筹码
system_prompt_override: |    # 覆盖系统提示词
  You are a poker expert...

# 实验控制
max_illegal_actions: 50      # 最大非法动作数
max_timeouts: 10             # 最大超时次数
```

---

## 👨‍💻 代理开发

### 基础代理接口

创建自定义代理需要实现以下接口：

```python
from green_agent_benchmark.schemas import ActionRequest, ActionResponse

class MyAgent:
    name = "MyCustomAgent"  # 代理名称
    
    def reset(self, seat_id: int, table_config: dict) -> None:
        """每手开始前的重置(可选)"""
        self.seat_id = seat_id
        self.starting_stack = table_config.get('starting_stack', 10000)
    
    def act(self, request: ActionRequest) -> ActionResponse:
        """根据游戏状态做出决策"""
        # 获取游戏信息
        hole_cards = request.hole_cards      # 底牌 ['As', 'Kd']
        board = request.board                # 公共牌
        pot = request.pot                    # 底池大小
        to_call = request.to_call           # 需要跟注的金额
        legal_actions = request.legal_actions # 合法动作列表
        
        # 简单策略示例
        if "fold" in legal_actions and to_call > 200:
            return ActionResponse(action="fold")
        elif "call" in legal_actions:
            return ActionResponse(action="call")
        elif "check" in legal_actions:
            return ActionResponse(action="check")
        else:
            return ActionResponse(action="fold")
```

### ActionRequest 详细字段

```python
@dataclass
class ActionRequest:
    # 基础信息
    seat_count: int          # 座位数 (2或6)
    table_id: str           # 桌子ID
    hand_id: str            # 手牌ID
    seat_id: int            # 当前座位号
    button_seat: int        # 按钮位座位号
    
    # 盲注信息
    blinds: dict           # {"sb": 50, "bb": 100}
    stacks: dict           # {seat_id: chips} 所有玩家筹码
    
    # 底池信息
    pot: int               # 当前底池大小
    to_call: int           # 需要跟注的金额
    min_raise_to: int      # 最小加注到多少
    
    # 牌面信息
    hole_cards: list       # 自己的底牌 ['As', 'Kd']
    board: list            # 公共牌 ['Jh', '9c', '2d']
    
    # 动作信息
    action_history: list   # 历史动作记录
    legal_actions: list    # 当前合法动作 ['fold', 'call', 'raise_to']
    
    # 时间和其他
    timebank_ms: int       # 剩余思考时间
    rng_tag: str           # 随机种子标签
```

### ActionResponse 详细字段

```python
@dataclass  
class ActionResponse:
    action: str            # 动作类型
    amount: Optional[int] = None   # 加注金额(仅raise_to需要)
    metadata: Optional[dict] = None # 额外信息(可选)
```

### 动作类型说明

| 动作 | 说明 | 何时可用 | amount参数 |
|------|------|----------|-----------|
| `fold` | 弃牌 | 面临下注时 | 不需要 |
| `check` | 过牌 | 无人下注时 | 不需要 |
| `call` | 跟注 | 面临下注时 | 不需要 |
| `raise_to` | 加注到指定金额 | 有足够筹码时 | **必需** |

### 高级代理示例

```python
import random
from green_agent_benchmark.schemas import ActionRequest, ActionResponse

class SmartAgent:
    name = "SmartAgent"
    
    def __init__(self):
        self.hand_count = 0
        self.opponent_stats = {}
    
    def reset(self, seat_id: int, table_config: dict):
        self.seat_id = seat_id
        self.hand_count += 1
    
    def act(self, request: ActionRequest) -> ActionResponse:
        # 记录对手统计
        self._update_opponent_stats(request)
        
        # 计算底池赔率
        pot_odds = self._calculate_pot_odds(request)
        
        # 估算手牌强度
        hand_strength = self._evaluate_hand_strength(
            request.hole_cards, request.board
        )
        
        # 决策逻辑
        if hand_strength > 0.8:
            # 强牌：加注
            if "raise_to" in request.legal_actions:
                raise_size = min(request.pot, request.stacks[self.seat_id])
                return ActionResponse(
                    action="raise_to", 
                    amount=request.to_call + raise_size
                )
            elif "call" in request.legal_actions:
                return ActionResponse(action="call")
        
        elif hand_strength > 0.4 and pot_odds > 0.25:
            # 中等牌：根据底池赔率决定
            if "call" in request.legal_actions:
                return ActionResponse(action="call")
        
        # 弱牌或赔率不好：弃牌/过牌
        if "check" in request.legal_actions:
            return ActionResponse(action="check")
        else:
            return ActionResponse(action="fold")
    
    def _calculate_pot_odds(self, request: ActionRequest) -> float:
        """计算底池赔率"""
        if request.to_call == 0:
            return 1.0
        return request.pot / (request.pot + request.to_call)
    
    def _evaluate_hand_strength(self, hole_cards: list, board: list) -> float:
        """估算手牌强度(简化版)"""
        # 这里可以接入更复杂的equity计算
        # 简化示例：基于高牌
        card_values = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, 
                      '8': 8, '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
        
        if not hole_cards:
            return 0.0
            
        max_value = max(card_values.get(card[0], 0) for card in hole_cards)
        return min(max_value / 14.0, 1.0)
    
    def _update_opponent_stats(self, request: ActionRequest):
        """更新对手统计信息"""
        # 分析action_history来统计对手行为
        pass
```

### 代理测试

```python
# test_my_agent.py
from green_agent_benchmark.runner import BenchmarkRunner, SeriesConfig
from my_agent import SmartAgent

def test_agent():
    config = SeriesConfig.from_file("configs/demo_hu_10hands.yaml")
    runner = BenchmarkRunner(config, "test_output")
    
    result = runner.run(SmartAgent())
    
    # 查看结果
    print(f"BB/100: {result.metrics['SmartAgent']['bb_per_100']}")
    print(f"VPIP: {result.metrics['SmartAgent']['behavior']['vpip']['rate']}")
    
if __name__ == "__main__":
    test_agent()
```

---

## 📊 排行榜系统

### 自动生成排行榜

```bash
# 扫描artifacts目录并生成排行榜数据
python leaderboard/leaderboard_generator.py

# 启动Web服务器
python leaderboard/server.py

# 或使用便捷脚本
chmod +x start_leaderboard.sh
./start_leaderboard.sh
```

### 排行榜指标说明

| 指标 | 说明 | 范围 |
|------|------|------|
| **Composite Rating** | 综合评分 | 1000-2500+ |
| **BB/100** | 每100手赢取的大盲注数 | -∞ to +∞ |
| **Win Rate** | 胜率 | 0.0-1.0 |
| **VPIP** | 自愿入池率 | 0%-100% |
| **PFR** | 翻牌前加注率 | 0%-100% |
| **AF** | 攻击频率 | 0-∞ |
| **WTSD** | 摊牌率 | 0%-100% |

### 排行榜API

排行榜提供REST API接口：

```bash
# 获取排行榜数据
curl http://localhost:8000/api/leaderboard

# 刷新排行榜
curl http://localhost:8000/api/refresh

# 获取特定代理信息
curl http://localhost:8000/api/agent/{agent_name}
```

### 自定义排行榜

修改 `leaderboard/leaderboard_generator.py` 来自定义指标计算：

```python
def calculate_composite_rating(agent_data):
    """自定义评分计算"""
    bb_100 = agent_data['weighted_bb_per_100']
    win_rate = agent_data['win_rate'] 
    consistency = agent_data['consistency']
    
    # 基础分数
    base_score = 1500
    
    # BB/100贡献 (主要因素)
    bb_score = bb_100 * 4  # 每1 bb/100 = 4分
    
    # 胜率贡献
    win_score = (win_rate - 0.5) * 200  # 50%基准
    
    # 稳定性贡献  
    consistency_score = (1 - consistency) * 100
    
    return base_score + bb_score + win_score + consistency_score
```

---

## 📈 数据分析

### 查看实验结果

```python
import json
import pandas as pd

# 读取聚合指标
with open('artifacts/my_experiment/metrics/metrics.json') as f:
    metrics = json.load(f)

print("所有代理表现:")
for agent_name, stats in metrics.items():
    bb_100 = stats['bb_per_100']
    ci_low, ci_high = stats['bb_per_100_ci']
    vpip = stats['behavior']['vpip']['rate']
    pfr = stats['behavior']['pfr']['rate']
    
    print(f"{agent_name}:")
    print(f"  BB/100: {bb_100:.2f} [{ci_low:.2f}, {ci_high:.2f}]")
    print(f"  VPIP: {vpip:.1%}, PFR: {pfr:.1%}")

# 读取逐手数据
df = pd.read_json(
    'artifacts/my_experiment/metrics/per_hand_metrics.ndjson',
    lines=True
)

print(f"\n总手数: {len(df)}")
print(f"平均每手赢利: {df['delta'].mean():.2f} chips")
print(f"最大单手赢利: {df['delta'].max()} chips")
print(f"最大单手亏损: {df['delta'].min()} chips")
```

### 高级分析

```python
# 分析不同位置的表现
position_stats = df.groupby('position')['delta'].agg(['mean', 'std', 'count'])
print("按位置统计:")
print(position_stats)

# 分析时间趋势
df['cumulative_bb100'] = (df['delta'].cumsum() / df.index * 100) / 100
print(f"最终BB/100: {df['cumulative_bb100'].iloc[-1]:.2f}")

# 分析对手影响
opponent_stats = df.groupby('opponent')['delta'].agg(['mean', 'count'])
print("对不同对手的表现:")
print(opponent_stats)
```

### 导出分析报告

```python
def generate_report(metrics_file, output_file):
    """生成HTML分析报告"""
    with open(metrics_file) as f:
        metrics = json.load(f)
    
    html = f"""
    <html>
    <head><title>扑克代理分析报告</title></head>
    <body>
        <h1>实验结果分析</h1>
        <table border="1">
            <tr>
                <th>代理</th>
                <th>BB/100</th>
                <th>置信区间</th>
                <th>VPIP</th>
                <th>PFR</th>
                <th>决策时间(ms)</th>
            </tr>
    """
    
    for name, stats in metrics.items():
        bb100 = stats['bb_per_100']
        ci = stats['bb_per_100_ci']
        vpip = stats['behavior']['vpip']['rate']
        pfr = stats['behavior']['pfr']['rate']
        decision_time = stats['behavior']['decision_time_ms']['mean']
        
        html += f"""
            <tr>
                <td>{name}</td>
                <td>{bb100:.2f}</td>
                <td>[{ci[0]:.2f}, {ci[1]:.2f}]</td>
                <td>{vpip:.1%}</td>
                <td>{pfr:.1%}</td>
                <td>{decision_time:.0f}</td>
            </tr>
        """
    
    html += """
        </table>
    </body>
    </html>
    """
    
    with open(output_file, 'w') as f:
        f.write(html)

# 使用
generate_report(
    'artifacts/my_experiment/metrics/metrics.json',
    'analysis_report.html'
)
```

---

## 🔧 高级用法

### 批量实验

```bash
# 使用脚本运行多个实验
python scripts/run_series.py
```

创建批量实验脚本：

```python
# batch_experiments.py
import subprocess
import os

experiments = [
    {
        'name': 'gpt5_vs_random',
        'config': 'configs/dev_hu.yaml',
        'agent': 'green_agent_benchmark.agents.gpt5_agent:GPT5Agent',
        'agent_name': 'GPT5'
    },
    {
        'name': 'gpt5_vs_tag', 
        'config': 'configs/dev_hu.yaml',
        'agent': 'green_agent_benchmark.agents.gpt5_agent:GPT5Agent',
        'agent_name': 'GPT5'
    }
]

for exp in experiments:
    output_dir = f"artifacts/{exp['name']}"
    cmd = [
        'python', '-m', 'green_agent_benchmark.cli',
        '--config', exp['config'],
        '--agent', exp['agent'],
        '--agent-name', exp['agent_name'],
        '--output', output_dir
    ]
    
    print(f"运行实验: {exp['name']}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"✅ {exp['name']} 完成")
    else:
        print(f"❌ {exp['name']} 失败: {result.stderr}")
```

### 自定义指标

扩展 `metrics.py` 添加新指标：

```python
def calculate_custom_metrics(hand_records):
    """计算自定义指标"""
    metrics = {}
    
    # 计算最大回撤
    deltas = [r['delta'] for r in hand_records]
    cumulative = np.cumsum(deltas)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = running_max - cumulative
    metrics['max_drawdown'] = float(np.max(drawdown))
    
    # 计算夏普比率
    if len(deltas) > 1:
        returns = np.array(deltas)
        metrics['sharpe_ratio'] = float(np.mean(returns) / np.std(returns))
    
    # 计算连胜/连败
    win_streak = 0
    lose_streak = 0
    current_win_streak = 0
    current_lose_streak = 0
    
    for delta in deltas:
        if delta > 0:
            current_win_streak += 1
            current_lose_streak = 0
            win_streak = max(win_streak, current_win_streak)
        elif delta < 0:
            current_lose_streak += 1
            current_win_streak = 0
            lose_streak = max(lose_streak, current_lose_streak)
    
    metrics['max_win_streak'] = win_streak
    metrics['max_lose_streak'] = lose_streak
    
    return metrics
```

### 多进程实验

```python
# parallel_runner.py
from concurrent.futures import ProcessPoolExecutor
import subprocess

def run_experiment(config):
    """运行单个实验"""
    cmd = [
        'python', '-m', 'green_agent_benchmark.cli',
        '--config', config['config_file'],
        '--agent', config['agent'],
        '--output', config['output_dir']
    ]
    return subprocess.run(cmd, capture_output=True, text=True)

def run_parallel_experiments(experiments, max_workers=4):
    """并行运行多个实验"""
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(run_experiment, exp): exp 
                  for exp in experiments}
        
        for future in futures:
            exp = futures[future]
            try:
                result = future.result()
                print(f"✅ {exp['name']} 完成")
            except Exception as e:
                print(f"❌ {exp['name']} 失败: {e}")
```

### Docker部署

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["python", "leaderboard/server.py"]
```

```bash
# 构建并运行
docker build -t green-agent-benchmark .
docker run -p 8000:8000 -v $(pwd)/artifacts:/app/artifacts green-agent-benchmark
```

---

## 🚨 故障排除

### 常见问题

#### 1. 安装问题

**问题**: `ModuleNotFoundError: No module named 'green_agent_benchmark'`

**解决**:
```bash
# 确保在项目根目录
pwd  # 应该显示 .../Project1_Texas

# 重新安装
pip install -e .

# 或者设置PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

#### 2. API密钥问题

**问题**: `OpenAI API error: Invalid API key`

**解决**:
```bash
# 检查环境变量
echo $OPENAI_API_KEY

# 重新设置
export OPENAI_API_KEY=sk-your-actual-key

# 或创建.env文件
echo "OPENAI_API_KEY=sk-your-actual-key" > .env
```

#### 3. 内存不足

**问题**: 6-Max实验占用内存过多

**解决**:
```yaml
# 减少实验规模 (configs/dev_6max.yaml)
hands_per_replica: 50  # 从200减少到50
seeds: [201]           # 只用1个种子
```

#### 4. 超时问题

**问题**: LLM代理响应超时

**解决**:
```yaml
# 增加超时时间 (config文件)
time_per_decision_ms: 120000  # 2分钟

# 或在代理中设置
class MyAgent:
    def act(self, request):
        if request.timebank_ms < 5000:  # 时间不足时快速决策
            return ActionResponse(action="fold")
        # 正常决策逻辑...
```

#### 5. 排行榜显示问题

**问题**: 排行榜显示"No data available"

**解决**:
```bash
# 1. 检查数据文件
ls leaderboard/data/
cat leaderboard/data/leaderboard.json

# 2. 重新生成
python leaderboard/leaderboard_generator.py

# 3. 检查artifacts目录
ls artifacts/*/metrics/metrics.json
```

#### 6. 端口占用

**问题**: `OSError: [Errno 48] Address already in use`

**解决**:
```bash
# 查找占用端口8000的进程
lsof -i :8000

# 终止进程
kill -9 <PID>

# 或使用不同端口
python leaderboard/server.py --port 8001
```

### 日志调试

#### 启用详细日志

```bash
# 设置日志级别
export LOG_LEVEL=DEBUG

# 运行实验
python -m green_agent_benchmark.cli \
  --config configs/dev_hu.yaml \
  --agent baseline:random-hu \
  --output artifacts/debug_run \
  --verbose
```

#### 检查游戏日志

```bash
# 查看最近的手牌日志
tail -n 50 artifacts/my_experiment/logs/hu/random-hu/seed101_rep0.ndjson

# 解析JSON格式
cat artifacts/my_experiment/logs/hu/random-hu/seed101_rep0.ndjson | \
  python -m json.tool | less
```

#### 检查指标异常

```python
# debug_metrics.py
import json

with open('artifacts/my_experiment/metrics/metrics.json') as f:
    metrics = json.load(f)

for agent, stats in metrics.items():
    bb_100 = stats['bb_per_100']
    
    # 检查异常值
    if abs(bb_100) > 1000:
        print(f"⚠️ {agent} BB/100异常: {bb_100}")
    
    # 检查置信区间
    ci_low, ci_high = stats['bb_per_100_ci']
    if ci_high - ci_low > 200:
        print(f"⚠️ {agent} 置信区间过宽: [{ci_low:.2f}, {ci_high:.2f}]")
```

### 性能优化

#### 1. 减少API调用延迟

```python
class OptimizedLLMAgent:
    def __init__(self):
        self.decision_cache = {}  # 缓存相似情况的决策
    
    def act(self, request):
        # 生成状态哈希
        state_hash = self._hash_state(request)
        
        # 检查缓存
        if state_hash in self.decision_cache:
            return self.decision_cache[state_hash]
        
        # 调用LLM
        response = self._call_llm(request)
        
        # 缓存结果
        self.decision_cache[state_hash] = response
        return response
```

#### 2. 并行运行实验

```bash
# 同时运行多个独立实验
python -m green_agent_benchmark.cli --config configs/exp1.yaml --output artifacts/exp1 &
python -m green_agent_benchmark.cli --config configs/exp2.yaml --output artifacts/exp2 &
python -m green_agent_benchmark.cli --config configs/exp3.yaml --output artifacts/exp3 &
wait  # 等待所有后台任务完成
```

#### 3. 优化配置

```yaml
# 开发期间使用小规模配置
seeds: [101, 102]        # 只用2个种子
hands_per_seed: 100      # 减少手数
hands_per_replica: 50    # 6-max模式

# 生产环境使用完整配置
seeds: [101, 102, 103, 104, 105, 106, 107, 108, 109, 110]
hands_per_seed: 1000
hands_per_replica: 300
```

---

## 📚 更多资源

### 文档链接
- [架构文档](docs/ARCHITECTURE.md)
- [API参考](docs/API_REFERENCE.md)
- [AgentBeats集成](docs/AGENTBEATS.md)

### 社区支持
- GitHub Issues: 报告bug和功能请求
- Discussions: 技术讨论和经验分享

### 相关论文
- "Green Agent Benchmark: A Framework for Evaluating LLMs in Strategic Environments"
- "Variance Reduction Techniques in Multi-Agent Poker Evaluation"

---

## 🎯 下一步计划

1. **扩展游戏变体**: PLO (Pot-Limit Omaha)支持
2. **锦标赛模式**: MTT (Multi-Table Tournament)
3. **更多LLM集成**: Claude, GPT-4等
4. **高级分析**: 对手建模、可解释性分析
5. **云端部署**: AWS/GCP自动化部署

---

**祝你在Green Agent Benchmark的探索之旅中收获满满！** 🎰♠️♥️♣️♦️

如有任何问题，请参考故障排除章节或提交GitHub Issue。