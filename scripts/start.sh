#!/bin/bash

echo "======================================================================"
echo "          FastAPI 后端服务启动脚本 (Linux/Mac)"
echo "======================================================================"
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "[错误] 未检测到 Python3，请先安装 Python 3.10+"
    exit 1
fi

echo "[1/4] 检查 Python 环境..."
python3 --version
echo ""

# 检查并安装依赖
echo "[2/4] 检查依赖..."
if ! pip3 show python-dotenv &> /dev/null; then
    echo "安装 python-dotenv..."
    pip3 install python-dotenv
else
    echo "python-dotenv 已安装"
fi
echo ""

# 检查 .env 文件
echo "[3/4] 检查配置文件..."
if [ -f ".env" ]; then
    echo "找到.env 配置文件"
else
    echo "[警告] 未找到.env 文件，请从.env.example 创建"
    echo "按回车继续使用默认配置..."
    read
fi
echo ""

# 启动服务
echo "[4/4] 启动 FastAPI 服务..."
echo "======================================================================"
echo ""
echo "服务地址：http://localhost:8000"
echo "API 文档：http://localhost:8000/docs"
echo "按 Ctrl+C 停止服务"
echo "======================================================================"
echo ""

cd "$(dirname "$0")"
python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

echo ""
echo "服务已停止"
