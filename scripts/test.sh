#!/bin/bash
# 测试运行脚本

set -e

echo "======================================"
echo "运行测试套件"
echo "======================================"

# 检查 pytest 是否安装
if ! command -v pytest &> /dev/null; then
    echo "错误：pytest 未安装，请先安装依赖"
    exit 1
fi

# 运行测试
echo "运行所有测试..."
pytest tests/ -v --tb=short

echo ""
echo "✅ 所有测试通过"
