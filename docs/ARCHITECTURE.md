# Project1_Texas / Green Agent Benchmark — 架构与逐文件解读

本文从自顶向下梳理项目整体思路与关键流程，并对每个源码文件逐一说明其职责、主要类/函数、关键数据结构与注意点，帮助你完整理解整个工程。

## 一、整体概览（Top-down）

- 项目目标：评测语言模型（LLM）与规则/启发式德州扑克（NLHE）智能体的对战表现，在可复现、可度量、可治理的环境中产出稳定指标（如 bb/100、置信区间、行为特征等）。
- 运行形态：
  - Heads- 快速运行（无需外网/Key，随机基线）：参见 `PROJECT_OVERVIEW.md` 的"10 手冒烟测试"示例。up（HU，2人桌）：支持“复制赛局”（duplicate）与左右手位轮换，控制方差。
  - 6-max（6人桌）：支持座位复制（seat replicas）与对手池/阵容配置。
- 关键模块：
  - 引擎（`engine.py`）：完整的 NLHE 状态机（发牌、押注轮次、全下、边池、摊牌、结算）+ 治理（超时/非法动作替换和记分）。
  - 跑批器（`runner.py`）：按 YAML 配置组织一系列对局，产生 NDJSON 日志和聚合指标。
  - 指标（`metrics.py`）：从日志解析行为统计，结合每手输赢计算 bb/100、CI、超时/非法率等。
  - 代理（`agents/`）：规则/启发式基线（Random/TAG/CFR-lite）与各 LLM 包装器（OpenAI/Gemini/DeepSeek/Kimi/Qwen/Cohere）。
  - CLI（`cli.py` + `scripts/run_series.py`）：命令行入口，加载 `.env`，解析配置，打印摘要并输出到 `artifacts/`。
  - 配置/加载（`config_loader.py`、`env_loader.py`、`schemas.py`）：YAML/JSON 配置解析，A2A 协议的数据结构。
  - 牌与评估（`cards.py`）：卡牌结构与 7 选 5 手牌评估。
  - 日志（`logging_utils.py`）：稳定的 NDJSON 记录器。

- 输入/输出：
  - 输入：`configs/*.yaml` 定义模式、盲注、起始筹码、种子、对手组合/阵容等。
  - 输出：`artifacts/<run>/logs/.../*.ndjson`（逐事件日志）与 `artifacts/<run>/metrics/metrics.json`（聚合指标）、`per_hand_metrics.ndjson`（逐手摘要）。

- 数据与契约：
  - Agent 契约：`reset(seat_id, table_config)` 和 `act(ActionRequest) -> ActionResponse`。
  - 行为治理：非法/超时动作被替换为安全动作（过牌/弃牌/跟注），并记罚（timeouts/illegal_actions）。

## 二、核心执行流（From CLI to Metrics）

1) CLI（`green_agent_benchmark/cli.py`）
   - 解析参数：`--config`、`--agent`（或在配置中定义完整阵容）、`--agent-name`、`--output`。
   - `SeriesConfig.from_file` 读取 YAML -> 构建配置对象。
   - 如果未提供完整 `lineup`：通过 `baseline_registry.make_baseline` 或 `agents.base.load_agent` 加载一个被评测的 agent。
   - 构造 `BenchmarkRunner` 并调用 `run()`。

2) Runner（`runner.py`）
   - 根据 `mode`（hu/sixmax）进入 `_run_hu` 或 `_run_sixmax`。
   - 为每个 `seed` 与 `replica` 组合：
     - 确定按钮位置与座位轮换（控制左右位对称）。
     - 创建 `HoldemEngine`，为每个座位构建 `PlayerRuntimeState` 与 `AgentInterface`。
     - 为每手：按 `(seed, hand_index, replica_id)` 确定性的洗牌，调用 `engine.play_hand(...)`。
     - 收集每手的收益（delta）、超时/非法动作增量、位置、对手名等为 `HandRecord`。
   - 写出 `per_hand_metrics.ndjson`，并调用 `aggregate_run_metrics(...)` 聚合。

3) Engine（`engine.py`）
   - `EngineConfig` 配置盲注、起始筹码、决策时长限制等。
   - `play_hand(...)`：
     - `hand_start` 日志 -> 发底牌 -> 盲注 -> 每个街道的下注轮（`betting_round`）-> 发公牌并重复 -> 摊牌与边池结算。
     - 每次 `act(...)` 计时，超时/非法动作即刻替换并写入 `penalty` 日志。
     - 结尾写入 `showdown` 与 `hand_end`。

4) Metrics（`metrics.py`）
   - 按玩家聚合 `HandRecord`，换算到 `bb/100`。
   - 读取日志还原行为统计（VPIP、PFR、AF、WTSD、决策时延样本数），计算 95% 置信区间与 `match_points`（CI>0 记 1，CI<0 记 -1）。
   - 写出 `metrics.json`，CLI 打印摘要。

## 三、配置与工件

- YAML 字段（见 `configs/*.yaml` 示例）：
  - 共通：`mode`, `blinds:{sb,bb}`, `stacks_bb`, `seeds`。
  - HU：`hands_per_seed`, `replicas`, `opponent_mix` 或 `lineup`（2 项）。
  - 6-max：`seat_replicas`, `hands_per_replica`, `opponent_pool` 或 `opponent_lineup`（5 项），或完整 `lineup`（6 项），可通过查询串覆盖基线参数（如 `?model=...&name=...`）。

- 输出目录（`artifacts/<run>/...`）：
  - `logs/hu/<opponent>/*.ndjson`、`logs/sixmax/*.ndjson`。
  - `metrics/per_hand_metrics.ndjson`、`metrics/metrics.json`。

---

## 四、逐文件解读（Bottom-up）

### 1) 顶层与脚本

- `README.md`
  - 说明项目特性/目录/安装/运行样例与扩展点，给出基线与多提供商 LLM 的调用示例。

- `scripts/run_series.py`
  - 仅作为便捷入口：`from green_agent_benchmark.cli import main` 并调用。

- `pyproject.toml` / `requirements.txt`
  - 最低 Python 3.10。依赖 `pyyaml`；`openai` 在 requirements.txt 中列出，便于 LLM agent 调用。

### 2) 命令行与加载

- `green_agent_benchmark/cli.py`
  - 参数解析 -> `load_env()` 读 `.env` -> `SeriesConfig.from_file()` -> 依据是否有 `lineup` 决定加载单个 agent 或整桌阵容 -> `BenchmarkRunner.run()` -> 打印指标摘要（bb/100、CI、超时/非法率、行为特征、决策时延）。

- `green_agent_benchmark/config_loader.py`
  - 读取 YAML 或 JSON；若 `.yaml/.yml` 且安装了 `pyyaml` 则 `yaml.safe_load`，否则走 `json.loads`。

- `green_agent_benchmark/env_loader.py`
  - 简易 `.env` 解析，按 KEY=VALUE 写入 `os.environ`（只在未设定时生效）。

- `green_agent_benchmark/schemas.py`
  - 定义 A2A（Agent-to-Agent）协议的数据类：
    - `ActionRequest`：席位、盲注、池底、到跟注、最小加注到、手牌/公牌、历史、合法动作、时间上限、RNG 标签等。
    - `ActionResponse`：`action` 与可选 `amount`、`metadata`。
    - `ActionHistoryEntry`、`TableEvent` 等辅助结构。

### 3) 引擎与运行器

- `green_agent_benchmark/engine.py`
  - 关键类型：
    - `EngineConfig`：`seat_count/sb/bb/starting_stack/table_id/time_per_decision_ms/auto_top_up`。
    - `PlayerRuntimeState`：席位 ID、名称、栈、底牌、下注、弃牌/全下标志、非法动作/超时计数；`reset_for_hand` 在每手开始重置可变状态。
    - `AgentInterface`：封装 agent，统一 `name`、`reset` 与 `act` 的调用与类型检查。
  - 核心函数：
    - `compute_order`：根据街道与庄位计算行动顺序（HU 翻牌前按钮位先行动，其它街道为按钮后一位先）。
    - `build_deck_from_seed`：按 `(seed, hand_index, replica_id)` 组合决定性洗牌。
  - `HoldemEngine.play_hand(...)`：
    - 记录 `hand_start`，发底牌并记录 `deal_hole`。
    - 张贴盲注（`_post_blind`），进入每个街道的 `betting_round` 循环：
      - 构建 `ActionRequest` 并计时调用 agent；超时写 `penalty` 并回退到安全动作。
      - 非法动作写 `penalty` 并回退。
      - 应用动作（弃牌/过牌/跟注/加注），更新 `pot`、`contributions` 与玩家状态。
      - 一轮结束条件：所有未弃/未全下玩家都匹配到最高下注。
    - 若提早只剩一人未弃，直接分池；否则发翻牌/转牌/河牌，进行后续轮。
    - `showdown`：计算边池与胜者，记录 `showdown` 与 `hand_end`，返回每席位的筹码增减（delta）。

- `green_agent_benchmark/runner.py`
  - 数据类：
    - `SeriesConfig`：运行配置（HU 与 6-max 字段在 `validate()` 中分别校验）。
    - `HandRecord`：逐手摘要（玩家、对手、模式、seed、hand_index、replica_id、座位、位置、delta、超时数、非法数、日志路径）。
    - `RunResult`：收集本次 run 的所有 `HandRecord`、日志路径与指标文件路径与内存中的指标对象。
  - 函数：
    - `seat_positions(seat_count, button_seat)`：把每个座位映射为位置标签（HU：SB/BB；6-max：BTN/SB/BB/UTG/HJ/CO）。
    - `_assignment_cycle(opponent_mix)`：把对手概率 map 展开为一个循环数组（按权重重复）。
    - `_build_lineup(seed, opponent_pool)`：从权重池采样出 5 名对手（6-max）。
    - `_rotate_assignment(assignment, replica_id)`：随 `replica_id` 循环旋转，用于左右位/按钮轮换与六人席位轮换。
    - `_create_agent_from_spec(spec)`：支持 `baseline:<name>?k=v` 参数覆写与 `pkg.module:Class` 动态加载。
  - 执行：
    - HU：如果配置给定了 `lineup`，则按两人阵容轮换；否则需要 CLI 提供一个 agent，按 `opponent_mix` 选择对手并进行 `replicas`（座位互换）与 `hands_per_seed` 的重复。
    - 6-max：若配置 `lineup` 则整桌由配置提供；否则 `opponent_lineup`（5 名）或由 `opponent_pool` 采样（5 名）+ CLI 提供的主角 agent 构成 6 人桌，随后进行座位复制与每复制的多手数。

  - 小提示：代码中用到一个标记 `CLI_AGENT_SENTINEL` 来在 6-max 场景标识“由 CLI 提供的主角”位置，用于在 `records` 里区分对手标签；该常量已在文件内定义。

### 4) 指标与日志

- `green_agent_benchmark/logging_utils.py`
  - `NDJSONLogger`：写一行一 JSON，加入 ISO 时间戳，`sort_keys=True` 以稳定字段顺序。

- `green_agent_benchmark/metrics.py`
  - `aggregate_run_metrics(hand_records, log_paths, big_blind)`：
    - 按玩家聚合 `HandRecord` 列表，计算 `bb/100` 与 95% CI（按 seed 的分组方差估计）。
    - 从 NDJSON 日志反解析出行为统计：VPIP、PFR、AF、WTSD、决策时间等。
    - 输出结构与 `PROJECT_OVERVIEW` 示例一致（包含 timeouts/illegal_actions per-hand 率）。

### 5) 牌与评估

- `green_agent_benchmark/cards.py`
  - `Card`、`new_deck()`、`card_from_str()` 等基础类型与构造。
  - `evaluate_five`：5 张牌评估，返回 `(category, kickers)`；
  - `best_hand_rank`：从 7 取 5 的全组合选取最优牌型。

### 6) 代理体系（Agents）

- 接口与加载：`green_agent_benchmark/agents/base.py`
  - `AgentProtocol`：约定 `name`、`reset`、`act`；
  - `load_agent('pkg.module:Class')`：动态加载 Agent 类并实例化（支持传参）。

- 基线工厂：`green_agent_benchmark/baseline_registry.py`
  - `BASELINE_FACTORIES`：名称到类的映射；
  - `make_baseline(name, **kwargs)`：创建对应的基线实例；
  - 已注册：`random`、`tag`、`cfrlite` 及各 LLM 封装（gpt5/gemini/deepseek/kimi/qwen/cohere），分别有 `-hu` 与 `-6` 变体。

- 规则/启发式：
  - `random_agent.py`：随机在 `legal_actions` 中选；若加注则做简单的金额裁剪。
  - `tag_agent.py`：紧凶（TAG）策略，按口袋对子/同花/高张等粗略规则决定激进行为。
  - `cfr_lite_agent.py`：轻量 CFR 风格，翻牌前规则 + 翻牌后用简化的胜率代理（抽样/评估）。

- LLM 适配：
  - 公共基类：`openai_base.py`（OpenAI 兼容 API 的通用封装）
    - 环境变量前缀（默认 `OPENAI`，子类可覆盖）读取 `*_API_KEY`、`*_MODEL`、`*_API_BASE`。
    - `act(...)`：构建结构化提示（system + user），调用 Responses 或 Chat Completions，解析 JSON 动作；失败回退到安全动作（过牌/跟注/弃牌）。
    - `dry_run=True` 时不发请求，直接用安全策略。
  - 具体子类：
    - `gpt5_agent.py`：默认 `OPENAI` 前缀，`gpt-5-mini`（可由 README 中示例覆盖）。
    - `gemini_agent.py`：`GEMINI` 前缀，`gemini-2.5-flash`，默认通过 Google 提供的 OpenAI 兼容网关，使用 Chat 接口。
    - `deepseek_agent.py`：`DEEPSEEK` 前缀，默认 `deepseek-chat`，使用 Chat 接口。
    - `kimi_agent.py`：`KIMI` 前缀，Moonshot API，使用 Chat 接口。
    - `qwen_agent.py`：`QWEN` 前缀，DashScope 兼容端点，使用 Chat 接口。
    - `cohere_agent.py`：`COHERE` 前缀，默认 `command-r`。

### 7) 其他

- `green_agent_benchmark/__init__.py`、`agents/__init__.py`
  - 包初始化（当前未包含复杂逻辑）。

---

## 五、关键数据结构与边界情况

- ActionRequest 输入（简版“契约”）
  - 输入：席位数、座位 ID、庄位、盲注、各栈、底池、到跟注、最小加注到、手牌、公牌、历史、合法动作、时间上限。
  - 输出（ActionResponse）：`action in {fold, check, call, raise_to}`，加注需提供 `amount`。
  - 错误/治理：超时与非法动作分别记 `timeouts`/`illegal_actions`，并即时替换为安全动作，记录 `penalty` 日志事件。

- 引擎边界：
  - 2 人桌翻牌前由按钮位先行动；其他街道为按钮后第一位先。
  - 全下与边池：`_build_side_pots` 逐档构建 eligible 集合，等分并处理余数。
  - 手牌评估：7 选 5 的穷举，性能对基准量级足够。

- 指标边界：
  - `bb_per_100` 的 CI：以种子为分组单位估计方差，若只有 1 个种子，则 CI=点估计。
  - 行为统计从 NDJSON 恢复，若日志缺失则保守返回空统计。

---

## 六、如何扩展与调试

- 新增基线/模型：在 `agents/` 添加类，实现 `act`/`reset`；如需公开为 baseline 名称，记得在 `baseline_registry.py` 注册。
- 自定义阵容：在 YAML 的 `lineup` 使用 `baseline:<name>` 或 `pkg.module:Class`；支持 `?key=value` 传参。
- 增强指标：扩展 `metrics.py` 的聚合逻辑与日志解析（`_parse_behavior_from_logs`）。
- 日志与复现：每手日志带 `rng_tag` 与 `hand_id=seed-hand-replica`，可快速定位复现实验。

---

## 七、已知注意点

- LLM 代理需要在运行环境中安装 `openai` 包并配置相应 API Key；若只做离线测试，可用 `dry_run=True`。
- 6-max 中的“CLI 主角”在内部用一个哨兵常量标记，用于区分记录里的对手标签。
- 如果你在 IDE 中看到某些类型检查的告警（如 dataclass slots 或第三方 SDK 的类型 stub 不一致），不影响运行；如需要，可根据你的类型检查器版本调整（例如移除 `slots=True` 或添加类型注解）。

---

## 八、文件一览（清单）

- 顶层
  - `PROJECT_OVERVIEW.md` 项目说明与指南
  - `pyproject.toml` / `requirements.txt` 构建与依赖
  - `scripts/run_series.py` 便捷入口
- 配置
  - `configs/*.yaml` 示例配置（HU/6-max/多模型对战）
- 核心库 `green_agent_benchmark/`
  - `cli.py` 命令行入口
  - `runner.py` 批量调度与记录
  - `engine.py` NLHE 状态机
  - `metrics.py` 指标聚合
  - `logging_utils.py` NDJSON 记录
  - `config_loader.py`/`env_loader.py`/`schemas.py`
  - `cards.py` 牌面与评估
  - `baseline_registry.py` 基线工厂
  - `agents/` 规则/LLM 智能体

---

## 九、快速上手与验证

- 快速运行（无需外网/Key，随机基线）：参见 `README.md` 的“10 手冒烟测试”示例。
- 带 LLM 的运行：在 `.env` 写入对应 `*_API_KEY` 与可选 `*_API_BASE`，然后按 PROJECT_OVERVIEW 示例选择相应代理。
- 输出核验：查看 `artifacts/<run>/metrics/metrics.json`，比对各玩家的 `bb/100` 与行为统计是否合理。

祝你玩得开心，评测顺利！
