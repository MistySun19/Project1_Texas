#!/bin/bash
# Green Agent Leaderboard 快速启动脚本

echo "🏆 Green Agent Leaderboard - 快速启动"
echo "======================================"

# 检查是否在正确的目录
if [ ! -d "artifacts" ] || [ ! -d "leaderboard" ]; then
    echo "❌ 请在Project1_Texas根目录下运行此脚本"
    exit 1
fi

# 安装依赖（如果需要）
echo "📦 检查依赖..."
python -c "import watchdog" 2>/dev/null || {
    echo "📦 安装watchdog..."
    pip install watchdog
}

# 显示选项
echo ""
echo "请选择启动模式:"
echo "1. 完整系统 (推荐) - Web服务器 + 自动监控"
echo "2. 仅Web服务器 - 手动刷新数据"
echo "3. 生成数据后退出"
echo ""

read -p "请输入选择 (1-3): " choice

case $choice in
    1)
        echo "🚀 启动完整系统..."
        python leaderboard/launcher.py
        ;;
    2)
        echo "🌐 启动Web服务器..."
        python leaderboard/launcher.py --server-only
        ;;
    3)
        echo "📊 生成排行榜数据..."
        python leaderboard/leaderboard_generator.py
        echo "✅ 数据已生成到 leaderboard/data/leaderboard.json"
        ;;
    *)
        echo "❌ 无效选择"
        exit 1
        ;;
esac