#!/bin/bash
# API路径持续监控脚本

echo "=== API端点健康监控 ==="
echo "监控时间: $(date)"
echo ""

BACKEND_URL="${BACKEND_URL:-http://localhost:8002}"

# 要监控的API端点
ENDPOINTS=(
  "/api/v1/agent/saved"
  "/api/v1/agent/orchestrate/stream"
  "/api/v1/agent/session/test_123/decision"
  "/api/v1/agent/session/test_123/action?action=cancel"
  "/api/v1/agent/sessions/test_123"
  "/api/v1/agent/saved/test_project"
  "/api/v2/system/get_system_info"
)

# 监控结果
RESULTS=()
FAILED=0
TOTAL=${#ENDPOINTS[@]}

echo "端点健康检查:"
for endpoint in "${ENDPOINTS[@]}"; do
  status_code=$(curl -s -w "%{http_code}" -o /dev/null -X POST "$BACKEND_URL$endpoint" \
    -H "Content-Type: application/json" -d '{}' 2>/dev/null)
  
  if [ "$status_code" = "401" ] || [ "$status_code" = "404" ] || [ "$status_code" = "405" ] || [ "$status_code = "200" ]; then
    status_icon="✓"
    if [ "$status_code" = "404" ]; then
      FAILED=$((FAILED + 1))
      status_icon="✗"
    fi
  else
    FAILED=$((FAILED + 1))
    status_icon="✗"
  fi
  
  echo "$status_icon $endpoint ($status_code)"
  RESULTS+=("$endpoint|$status_code")
done

echo ""
echo "监控摘要:"
echo "  总端点数: $TOTAL"
echo "  健康端点: $((TOTAL - FAILED))"
echo "  问题端点: $FAILED"
echo ""

# 检查前端服务
FRONTEND_URL="${FRONTEND_URL:-http://localhost:3000}"
FRONTEND_STATUS=$(curl -s -w "%{http_code}" -o /dev/null "$FRONTEND_URL/" 2>/dev/null)

if [ "$FRONTEND_STATUS" = "200" ]; then
  echo "✓ 前端服务正常"
else
  echo "✗ 前端服务异常 (HTTP $FRONTEND_STATUS)"
fi

# 检查后端服务
BACKEND_STATUS=$(curl -s -w "%{http_code}" -o /dev/null "$BACKEND_URL/docs" 2>/dev/null)

if [ "$BACKEND_STATUS" = "200" ]; then
  echo "✓ 后端服务正常"
else
  echo "✗ 后端服务异常 (HTTP $BACKEND_STATUS)"
fi

echo ""
echo "健康检查完成"
echo "详情请查看: test-report.md"