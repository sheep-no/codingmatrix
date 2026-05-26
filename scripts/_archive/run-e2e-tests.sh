#!/bin/bash
# E2E 测试运行脚本
# 自动启动后端和前端服务，运行 Playwright 测试

set -e

echo "=== MonkeyCode E2E 测试运行器 ==="

# 清理函数
cleanup() {
  echo ""
  echo "清理测试环境..."
  if [ ! -z "$BACKEND_PID" ]; then
    echo "停止后端服务 (PID: $BACKEND_PID)"
    kill $BACKEND_PID 2>/dev/null || true
  fi
  if [ ! -z "$FRONTEND_PID" ]; then
    echo "停止前端服务 (PID: $FRONTEND_PID)"
    kill $FRONTEND_PID 2>/dev/null || true
  fi
  echo "清理完成"
}

trap cleanup EXIT

# 检查必要服务是否已运行
check_service() {
  local name=$1
  local url=$2
  local max_attempts=$3
  local attempt=1
  
  echo "等待 $name 启动..."
  while [ $attempt -le $max_attempts ]; do
    if curl -s -o /dev/null -w "%{http_code}" "$url" | grep -q "200\|302"; then
      echo "$name 已就绪 (尝试 $attempt/$max_attempts)"
      return 0
    fi
    echo "  尝试 $attempt/$max_attempts - $name 未就绪，等待 2 秒..."
    sleep 2
    attempt=$((attempt + 1))
  done
  
  echo "错误：$name 在 $max_attempts 次尝试后仍未就绪"
  return 1
}

# 主流程
echo ""
echo "1. 检查后端服务 (端口 8002)..."
export BACKEND_HOST="http://localhost:8002"

if ! check_service "后端 API" "$BACKEND_HOST/health" 15; then
  echo "警告：后端服务未响应，请手动启动"
  echo "运行：python app/main.py"
  exit 1
fi

echo ""
echo "2. 检查前端服务 (端口 3000)..."
export BASE_URL="http://localhost:3000"

if ! check_service "前端服务" "$BASE_URL" 15; then
  echo "警告：前端服务未响应，请手动启动"
  echo "运行：npm run dev"
  exit 1
fi

echo ""
echo "3. 运行 Playwright 测试..."

# 确保 Playwright 已安装
if ! command -v npx &> /dev/null || ! npx playwright --version &> /dev/null; then
  echo "错误：Playwright 未安装"
  echo "运行：npm install -D @playwright/test && npx playwright install chromium"
  exit 1
fi

# 等待额外 5 秒确保服务完全就绪
echo "等待服务完全就绪..."
sleep 5

# 运行测试
TEST_ARGS="${@:---list}"
echo "执行：npx playwright test $TEST_ARGS"
npx playwright test $TEST_ARGS

TEST_EXIT_CODE=$?

echo ""
if [ $TEST_EXIT_CODE -eq 0 ]; then
  echo "✓ 所有测试通过!"
else
  echo "✗ 测试失败 (退出码：$TEST_EXIT_CODE)"
  echo ""
  echo "查看测试报告：npx playwright show-report"
fi

exit $TEST_EXIT_CODE
