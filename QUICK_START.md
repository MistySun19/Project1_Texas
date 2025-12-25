# Green Agent Benchmark - Quick Start Guide

## 🚀 5分钟快速开始

### 1. 安装 (1分钟)
```bash
git clone https://github.com/lusunjia/Project1_Texas.git
cd Project1_Texas
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 运行第一个测试 (2分钟)
```bash
# 快速10手测试
python -m green_agent_benchmark.cli \
  --config configs/demo_hu_10hands.yaml \
  --agent baseline:random-hu \
  --output artifacts/quick_test
```

### 3. 查看结果 (1分钟)
```bash
# 生成排行榜
python leaderboard/leaderboard_generator.py

# 启动Web界面
python leaderboard/server.py
# 打开浏览器访问: http://localhost:8000
```

### 4. LLM测试 (1分钟配置)
```bash
# 创建.env文件
echo "OPENAI_API_KEY=your-api-key-here" > .env

# 运行GPT-5测试
python -m green_agent_benchmark.cli \
  --config configs/demo_hu_10hands.yaml \
  --agent green_agent_benchmark.agents.gpt5_agent:GPT5Agent \
  --agent-name GPT5 \
  --output artifacts/gpt5_test
```

## 📚 完整文档
详细使用说明请参考 [USAGE_GUIDE.md](USAGE_GUIDE.md)

## 🆘 需要帮助?
- 常见问题: 查看 [USAGE_GUIDE.md#故障排除](USAGE_GUIDE.md#故障排除)
- Bug报告: GitHub Issues
- 技术讨论: GitHub Discussions