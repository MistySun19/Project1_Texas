# Green Agent Benchmark API Reference

## 核心API

### BenchmarkRunner

主要的实验运行器类。

```python
from green_agent_benchmark.runner import BenchmarkRunner, SeriesConfig

# 创建配置
config = SeriesConfig.from_file("configs/dev_hu.yaml")

# 创建运行器
runner = BenchmarkRunner(config, output_dir="artifacts/my_run")

# 运行实验
result = runner.run(agent=MyAgent())
```

#### SeriesConfig

实验配置类，支持从YAML文件加载或代码创建。

```python
# 从文件加载
config = SeriesConfig.from_file("config.yaml")

# 代码创建
config = SeriesConfig(
    mode="hu",                    # "hu" 或 "sixmax" 
    blinds={"sb": 50, "bb": 100},
    stacks_bb=100,
    seeds=[101, 102, 103],
    hands_per_seed=500,          # HU模式
    replicas=2,                  # HU模式
    # hands_per_replica=200,     # 6-max模式
    # seat_replicas=6,           # 6-max模式
    opponent_mix={               # HU对手配置
        "random-hu": 0.5,
        "tag-hu": 0.5
    }
)
```

### Agent Interface

所有代理必须实现的接口。

```python
from green_agent_benchmark.schemas import ActionRequest, ActionResponse

class MyAgent:
    name = "MyAgent"  # 必需: 代理名称
    
    def reset(self, seat_id: int, table_config: dict) -> None:
        """可选: 每手开始前重置"""
        pass
    
    def act(self, request: ActionRequest) -> ActionResponse:
        """必需: 根据游戏状态做决策"""
        return ActionResponse(action="fold")
```

## 数据结构

### ActionRequest

游戏状态信息，传递给代理的act方法。

```python
@dataclass
class ActionRequest:
    # 基础信息
    seat_count: int          # 座位数量 (2 或 6)
    table_id: str           # 桌子标识符  
    hand_id: str            # 手牌标识符
    seat_id: int            # 当前代理座位号 (0-based)
    button_seat: int        # 按钮位座位号
    
    # 盲注和筹码
    blinds: Dict[str, int]  # {"sb": 50, "bb": 100}
    stacks: Dict[int, int]  # {seat_id: chips} 所有玩家筹码
    pot: int                # 当前底池大小
    to_call: int            # 需要跟注的筹码数
    min_raise_to: int       # 最小加注到的数额
    
    # 牌面信息
    hole_cards: List[str]   # 自己的底牌 ["As", "Kd"] 
    board: List[str]        # 公共牌 ["Jh", "9c", "2d"]
    
    # 历史和合法动作
    action_history: List[ActionHistoryEntry]  # 本手历史动作
    legal_actions: List[str]  # 当前可执行的动作
    
    # 时间和其他
    timebank_ms: int        # 剩余思考时间(毫秒)
    rng_tag: str           # 随机数生成器标签
```

### ActionResponse

代理决策的返回值。

```python
@dataclass 
class ActionResponse:
    action: str                    # 动作类型
    amount: Optional[int] = None   # 加注数额(仅raise_to需要)
    metadata: Optional[dict] = None # 可选的额外信息
```

#### 动作类型

| 动作 | 描述 | 何时可用 | amount参数 |
|------|------|----------|-----------|
| `"fold"` | 弃牌 | 面临下注时 | 不需要 |
| `"check"` | 过牌 | 无人下注时 | 不需要 |
| `"call"` | 跟注 | 面临下注时 | 不需要 |
| `"raise_to"` | 加注到指定数额 | 筹码充足时 | **必需** |

### ActionHistoryEntry

历史动作记录。

```python
@dataclass
class ActionHistoryEntry:
    seat_id: int           # 执行动作的座位
    action: str            # 动作类型
    amount: Optional[int]  # 涉及筹码数(如有)
    street: str            # 街道 ("preflop", "flop", "turn", "river")
    to_call: int           # 当时的跟注数额
    min_raise_to: int      # 当时的最小加注数额
```

## 指标系统

### 核心指标

```python
# 从结果中读取指标
result = runner.run(agent)
metrics = result.metrics

# 获取特定代理的指标
agent_stats = metrics["MyAgent"]

# 主要指标
bb_per_100 = agent_stats["bb_per_100"]           # 每100手大盲数收益
confidence_interval = agent_stats["bb_per_100_ci"] # 95%置信区间
vpip_rate = agent_stats["behavior"]["vpip"]["rate"] # 自愿入池率
pfr_rate = agent_stats["behavior"]["pfr"]["rate"]   # 翻牌前加注率
aggression = agent_stats["behavior"]["af"]          # 攻击频率
```

### 指标详解

#### bb_per_100
每100手赢取的大盲注数，扑克中的标准盈利指标。
- 正值: 盈利
- 0: 盈亏平衡  
- 负值: 亏损

#### 行为统计
```python
behavior = agent_stats["behavior"]

# VPIP (Voluntarily Put $ In Pot)
vpip = behavior["vpip"]
vpip_rate = vpip["rate"]      # 入池率 (0.0-1.0)
vpip_count = vpip["count"]    # 入池次数

# PFR (Pre-Flop Raise)  
pfr = behavior["pfr"]
pfr_rate = pfr["rate"]        # 翻牌前加注率
pfr_count = pfr["count"]      # 加注次数

# AF (Aggression Factor)
af = behavior["af"]           # (下注+加注) / 跟注

# WTSD (Went To ShowDown)
wtsd = behavior["wt_sd"] 
wtsd_rate = wtsd["rate"]      # 摊牌率
wtsd_count = wtsd["count"]    # 摊牌次数

# 决策时间
decision_time = behavior["decision_time_ms"]
avg_time = decision_time["mean"]     # 平均决策时间(ms)
sample_count = decision_time["samples"] # 决策次数
```

## 基线代理

### 注册的基线代理

```python
from green_agent_benchmark.baseline_registry import make_baseline

# HU模式基线
random_agent = make_baseline("random-hu")
tag_agent = make_baseline("tag-hu") 
cfr_agent = make_baseline("cfr-lite-hu")

# 6-max模式基线
random_6 = make_baseline("random-6")
tag_6 = make_baseline("tag-6")
cfr_6 = make_baseline("cfr-lite-6")

# LLM代理 (需要API密钥)
gpt5_agent = make_baseline("gpt5-hu")
deepseek_agent = make_baseline("deepseek-hu") 
gemini_agent = make_baseline("gemini-hu")
kimi_agent = make_baseline("kimi-hu")
```

### 自定义基线参数

```python
# 带参数的TAG代理
custom_tag = make_baseline("tag-hu", 
                          vpip_threshold=0.25,  # 自定义入池阈值
                          pfr_threshold=0.15)   # 自定义加注阈值

# 自定义名称的GPT-5
custom_gpt5 = make_baseline("gpt5-hu",
                           model="gpt-5-turbo",
                           temperature=0.1,
                           name="GPT5-Custom")
```

## 配置系统

### YAML配置格式

```yaml
# HU配置
mode: hu
blinds:
  sb: 50
  bb: 100
stacks_bb: 100
seeds: [101, 102, 103, 104, 105]
hands_per_seed: 1000
replicas: 2
opponent_mix:
  random-hu: 0.3
  tag-hu: 0.4
  cfr-lite-hu: 0.3

# 可选: 系统设置
time_per_decision_ms: 60000
auto_top_up: true
system_prompt_override: |
  You are an expert poker player...
```

```yaml
# 6-max配置  
mode: sixmax
blinds:
  sb: 50
  bb: 100
stacks_bb: 100
seeds: [201, 202, 203]
hands_per_replica: 300
seat_replicas: 6
opponent_pool:
  random-6: 0.2
  tag-6: 0.5
  cfr-lite-6: 0.3
population_mirroring: true

# 或者使用完整lineup
lineup:
  - baseline:gpt5-6
  - baseline:deepseek-6
  - baseline:gemini-6
  - baseline:kimi-6
  - baseline:tag-6
  - baseline:cfr-lite-6
```

## CLI命令

### 基础命令

```bash
# 查看帮助
python -m green_agent_benchmark.cli --help

# 运行实验
python -m green_agent_benchmark.cli \
  --config CONFIG_FILE \
  --agent AGENT_SPEC \
  --output OUTPUT_DIR \
  [--agent-name DISPLAY_NAME] \
  [--verbose]
```

### Agent规格

```bash
# 基线代理
--agent baseline:random-hu
--agent baseline:tag-6
--agent baseline:gpt5-hu

# 带参数的基线
--agent "baseline:tag-hu?vpip_threshold=0.3&name=CustomTAG"

# 自定义模块
--agent mybot:MyAgent
--agent my.package.agents:AdvancedAgent
```

## 排行榜API

### Web API端点

```bash
# 获取排行榜数据
GET /api/leaderboard

# 刷新排行榜  
POST /api/refresh

# 获取特定代理信息
GET /api/agent/{agent_name}

# 健康检查
GET /api/health
```

### 响应格式

```json
{
  "last_updated": "2023-10-20T15:30:00Z",
  "agents": {
    "GPT5": {
      "composite_rating": 1850.5,
      "total_hands": 10000,
      "weighted_bb_per_100": 12.5,
      "win_rate": 0.65,
      "consistency": 0.85,
      "technical_quality": 0.95,
      "behavior_score": 0.88,
      "runs_count": 5,
      "avg_illegal_rate": 0.001,
      "avg_timeout_rate": 0.0,
      "runs_data": [...]
    }
  }
}
```

## 扩展开发

### 自定义指标

```python
# 在metrics.py中添加
def calculate_custom_metrics(hand_records):
    """计算自定义指标"""
    # 实现新的指标计算
    return {
        "custom_metric": value,
        "another_metric": another_value
    }

# 注册到主指标计算流程
def aggregate_run_metrics(hand_records, log_paths, bb_size):
    # 现有逻辑...
    
    # 添加自定义指标
    custom_metrics = calculate_custom_metrics(hand_records)
    result.update(custom_metrics)
    
    return result
```

### 新的代理类型

```python
# 1. 实现代理接口
class NewAgentType:
    name = "NewAgent"
    
    def act(self, request: ActionRequest) -> ActionResponse:
        # 实现决策逻辑
        return ActionResponse(action="fold")

# 2. 注册到基线注册表
from green_agent_benchmark.baseline_registry import register_baseline

@register_baseline("new-agent-hu")
def make_new_agent_hu(**kwargs):
    return NewAgentType(**kwargs)
```

### 自定义游戏引擎修改

```python
# 继承并扩展HoldemEngine
class CustomEngine(HoldemEngine):
    def play_hand(self, ...):
        # 调用父类方法
        result = super().play_hand(...)
        
        # 添加自定义逻辑
        self._custom_post_processing(result)
        
        return result
    
    def _custom_post_processing(self, result):
        # 自定义后处理
        pass
```

## 错误处理

### 常见异常

```python
from green_agent_benchmark.engine import IllegalActionError

class MyAgent:
    def act(self, request: ActionRequest) -> ActionResponse:
        try:
            # 决策逻辑
            action = self._make_decision(request)
            return ActionResponse(action=action)
            
        except Exception as e:
            # 错误处理: 返回安全的默认动作
            if "check" in request.legal_actions:
                return ActionResponse(action="check")
            else:
                return ActionResponse(action="fold")
```

### 超时处理

```python
class TimeAwareAgent:
    def act(self, request: ActionRequest) -> ActionResponse:
        # 检查剩余时间
        if request.timebank_ms < 5000:  # 少于5秒
            # 快速决策
            return self._quick_decision(request)
        else:
            # 深度分析
            return self._detailed_analysis(request)
```

## 性能优化

### 批量实验

```python
from concurrent.futures import ProcessPoolExecutor

def run_experiment_batch(configs):
    """并行运行多个实验"""
    with ProcessPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(run_single_experiment, cfg) 
                  for cfg in configs]
        
        results = [future.result() for future in futures]
    
    return results
```

### 内存优化

```python
class MemoryEfficientAgent:
    def __init__(self):
        self._history_limit = 100  # 限制历史记录数量
        
    def act(self, request: ActionRequest) -> ActionResponse:
        # 只保留最近的历史
        recent_history = request.action_history[-self._history_limit:]
        
        # 基于有限历史做决策
        return self._decide_with_limited_history(recent_history)
```

## 测试工具

### 单元测试示例

```python
import pytest
from green_agent_benchmark.schemas import ActionRequest, ActionResponse

def test_agent_basic_functionality():
    agent = MyAgent()
    
    request = ActionRequest(
        seat_count=2,
        seat_id=0,
        hole_cards=["As", "Ks"],
        legal_actions=["fold", "call", "raise_to"],
        to_call=100,
        min_raise_to=200,
        # ... 其他必需字段
    )
    
    response = agent.act(request)
    
    assert isinstance(response, ActionResponse)
    assert response.action in request.legal_actions
```

### 集成测试

```python
def test_full_experiment_run():
    """测试完整实验流程"""
    config = SeriesConfig(
        mode="hu",
        blinds={"sb": 50, "bb": 100},
        stacks_bb=100,
        seeds=[101],
        hands_per_seed=10,  # 少量手数用于测试
        replicas=2,
        opponent_mix={"random-hu": 1.0}
    )
    
    runner = BenchmarkRunner(config, "test_output")
    result = runner.run(TestAgent())
    
    assert result.metrics is not None
    assert "TestAgent" in result.metrics
```

---

更多详细信息请参考源代码和 [完整使用指南](USAGE_GUIDE.md)。