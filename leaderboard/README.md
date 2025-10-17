# 🏆 Green Agent Leaderboard

一个实时的德州扑克AI代理排行榜系统，类似于[werewolf.foaster.ai](https://werewolf.foaster.ai/)的Elo排行榜。

## 🌟 特性

- **🔄 实时更新**: 自动监控`artifacts/`目录，当新的metrics文件生成时自动更新排行榜
- **📊 综合评分**: 基于BB/100、一致性、技术质量等多维度的Elo风格评分系统
- **🎨 现代化界面**: 响应式设计，支持表格和卡片两种视图
- **📈 可视化图表**: 评分分布和散点图分析
- **🔍 搜索和筛选**: 支持按代理名称搜索和多种筛选条件
- **📱 移动端友好**: 完全响应式设计，支持移动设备

## 🚀 快速开始

### 方法1: 一键启动完整系统

```bash
# 启动完整系统（带自动监控）
python leaderboard/launcher.py

# 仅启动Web服务器（不监控文件变化）
python leaderboard/launcher.py --server-only

# 自定义端口
python leaderboard/launcher.py --port 8080
```

### 方法2: 分步启动

```bash
# 1. 生成初始排行榜数据
python leaderboard/leaderboard_generator.py

# 2. 启动Web服务器
python leaderboard/server.py --port 8000

# 3. (可选) 启动自动监控
python leaderboard/auto_updater.py
```

### 方法3: 手动更新

```bash
# 手动生成排行榜
python leaderboard/leaderboard_generator.py

# 启动静态服务器
cd leaderboard
python -m http.server 8000
```

## 📊 评分系统

### 综合评分 (Composite Rating)

基础评分 1500 + 以下组件：

- **BB/100 因子**: 每个BB/100 = 2评分点
- **一致性奖励**: 基于表现稳定性，最高100点
- **技术质量奖励**: 基于非法动作和超时率，最高50点
- **行为评分奖励**: 基于扑克策略合理性，最高100点
- **手数奖励**: 基于参与手数的对数奖励，最高100点

### 评价指标说明

#### 盈利能力指标
- **BB/100**: 每100手的大盲注单位盈亏，最重要的评估指标
- **置信区间**: 95%置信区间，评估结果的统计显著性
- **Match Points**: +1(显著盈利)、0(无显著差异)、-1(显著亏损)

#### 行为分析指标
- **VPIP**: 主动入池率，反映松紧程度
- **PFR**: 翻牌前加注率，反映攻击性
- **AF**: 攻击性系数 = 翻牌后加注次数/跟注次数
- **WTSD**: 摊牌率，反映打到河牌的频率

#### 执行质量指标
- **超时率**: 每手平均超时次数
- **非法动作率**: 每手平均非法动作次数
- **决策时间**: 平均决策时间和样本数

## 🗂️ 项目结构

```
leaderboard/
├── index.html              # 主页面
├── styles.css              # 样式文件
├── script.js               # 前端JavaScript
├── leaderboard_generator.py # 数据生成器
├── auto_updater.py         # 自动更新监控
├── server.py               # Web服务器
├── launcher.py             # 一键启动器
└── data/
    └── leaderboard.json    # 排行榜数据文件
```

## 🔧 配置和自定义

### 修改评分算法

编辑 `leaderboard_generator.py` 中的 `calculate_composite_score()` 方法：

```python
def calculate_composite_score(self, agent_data: List[Dict]) -> Dict[str, Any]:
    # 修改评分权重
    bb_factor = weighted_bb * 3  # 增加BB/100权重
    consistency_bonus = consistency * 150  # 增加一致性权重
    # ... 其他修改
```

### 添加新的筛选条件

在 `script.js` 中的 `filterByCategory()` 函数添加新条件：

```javascript
case 'new-category':
    filteredData = agents.filter(agent => /* 你的筛选逻辑 */);
    break;
```

### 自定义样式

修改 `styles.css` 中的CSS变量：

```css
:root {
    --primary-color: #your-color;
    --secondary-color: #your-color;
    /* ... 其他颜色 */
}
```

## 📈 API接口

### GET /api/leaderboard
返回完整的排行榜数据（JSON格式）

### GET /api/refresh
触发排行榜数据刷新

## 🔍 使用示例

### 查看排行榜
1. 访问 `http://localhost:8000`
2. 查看实时排名和详细统计
3. 使用搜索框查找特定代理
4. 点击"Details"查看详细信息

### 筛选功能
- **All**: 显示所有代理
- **Profitable**: 只显示盈利的代理（BB/100 > 0）
- **Improving**: 只显示近期表现改善的代理
- **High Volume**: 只显示高手数的代理

### 视图切换
- **Table View**: 传统表格显示，信息密度高
- **Cards View**: 卡片式显示，更适合移动设备

## 🛠️ 故障排除

### 常见问题

1. **排行榜数据为空**
   - 确保`artifacts/`目录存在且包含`metrics.json`文件
   - 运行 `python leaderboard/leaderboard_generator.py` 手动生成数据

2. **服务器启动失败**
   - 检查端口是否被占用，尝试不同端口
   - 确保在项目根目录运行

3. **自动更新不工作**
   - 安装watchdog: `pip install watchdog`
   - 检查文件权限和路径

4. **图表不显示**
   - 确保网络连接正常（Chart.js从CDN加载）
   - 检查浏览器控制台错误信息

## 🔮 未来改进

- [ ] 支持更多评分算法（真实Elo系统）
- [ ] 历史趋势图和时间序列分析
- [ ] 代理对比功能
- [ ] 导出数据功能
- [ ] 更多可视化图表类型
- [ ] 实时WebSocket更新
- [ ] 移动端App支持

## 📄 许可证

本项目遵循与Green Agent Benchmark相同的许可证。

---

**Enjoy your poker AI leaderboard! 🃏🏆**