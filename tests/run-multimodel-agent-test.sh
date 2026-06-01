#!/bin/bash
# 多模型 Agent 测试启动脚本

set -e

echo "=== 多模型 Agent 修改能力测试 ==="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查是否在正确的目录
if [ ! -f "package.json" ]; then
    echo -e "${RED}错误：请在项目根目录运行此脚本${NC}"
    exit 1
fi

# 函数：清理后台进程
cleanup() {
    echo -e "${YELLOW}清理后台进程...${NC}"
    if [ ! -z "$BACKEND_PID" ]; then
        kill $BACKEND_PID 2>/dev/null || true
    fi
    if [ ! -z "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID 2>/dev/null || true
    fi
}

# 设置退出时清理
trap cleanup EXIT

# 检查依赖
echo -e "${YELLOW}检查依赖...${NC}"
if ! command -v node &> /dev/null; then
    echo -e "${RED}错误：未找到 node 命令${NC}"
    exit 1
fi

if ! command -v python &> /dev/null && ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误：未找到 python 命令${NC}"
    exit 1
fi

# 检查 Playwright 是否安装
if ! npx playwright --version &> /dev/null; then
    echo -e "${YELLOW}安装 Playwright...${NC}"
    npm install
    npx playwright install chromium
fi

# 启动后端服务
echo -e "${YELLOW}启动后端服务...${NC}"
cd /workspace
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# 等待后端启动
echo -e "${YELLOW}等待后端服务启动...${NC}"
for i in {1..30}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}后端服务已启动${NC}"
        break
    fi
    sleep 1
done

# 检查后端是否启动成功
if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${RED}错误：后端服务启动失败${NC}"
    exit 1
fi

# 启动前端服务
echo -e "${YELLOW}启动前端服务...${NC}"
cd /workspace/src
npm run dev &
FRONTEND_PID=$!

# 等待前端启动
echo -e "${YELLOW}等待前端服务启动...${NC}"
for i in {1..60}; do
    if curl -s http://localhost:3000 > /dev/null 2>&1; then
        echo -e "${GREEN}前端服务已启动${NC}"
        break
    fi
    sleep 1
done

# 检查前端是否启动成功
if ! curl -s http://localhost:3000 > /dev/null 2>&1; then
    echo -e "${RED}错误：前端服务启动失败${NC}"
    exit 1
fi

# 运行测试
echo -e "${YELLOW}开始运行测试...${NC}"
cd /workspace

# 运行指定的测试或所有测试
if [ "$1" == "full" ]; then
    echo -e "${GREEN}运行完整测试...${NC}"
    npx playwright test tests/e2e/multimodel-agent-modify.spec.js --reporter=list
elif [ "$1" == "quick" ]; then
    echo -e "${GREEN}运行快速测试...${NC}"
    npx playwright test tests/e2e/multimodel-agent-modify.spec.js --grep "单元测试" --reporter=list
elif [ "$1" == "performance" ]; then
    echo -e "${GREEN}运行性能测试...${NC}"
    npx playwright test tests/e2e/multimodel-agent-modify.spec.js --grep "性能测试" --reporter=list
else
    echo -e "${GREEN}运行完整测试...${NC}"
    npx playwright test tests/e2e/multimodel-agent-modify.spec.js --reporter=list
fi

TEST_EXIT_CODE=$?

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ 测试通过${NC}"
else
    echo -e "${RED}✗ 测试失败${NC}"
fi

exit $TEST_EXIT_CODE
