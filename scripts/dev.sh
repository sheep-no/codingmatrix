#!/bin/bash
# 开发服务器启动脚本

set -e

echo "======================================"
echo "启动开发服务器"
echo "======================================"

# 检查环境变量
if [ ! -f .env ]; then
    echo "警告：.env 文件不存在，从 .env.example 复制"
    cp .env.example .env
    echo "请编辑 .env 文件配置环境变量"
fi

# 创建日志目录
mkdir -p logs

# 启动应用
echo "启动 FastAPI 应用..."
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
