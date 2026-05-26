#!/bin/bash
# API端点验证脚本

echo "=== API端点验证 ==="
echo ""

# 测试前端路径修复
echo "1. 测试 /api/v1/agent/saved (之前是 /api/v1/agent/generate/projects)"
curl -s -w "\nHTTP Status: %{http_code}\n" http://localhost:8000/api/v1/agent/saved 2>&1 | head -5
echo ""

# 测试新增的决策端点
echo "2. 测试 /api/v1/agent/session/test_session/decision"
curl -s -w "\nHTTP Status: %{http_code}\n" -X POST http://localhost:8000/api/v1/agent/session/test_session/decision \
  -H "Content-Type: application/json" -d '{"auth_strategy": "JWT"}' 2>&1 | head -5
echo ""

# 测试会话操作端点
echo "3. 测试 /api/v1/agent/session/test_session/action?action=cancel"
curl -s -w "\nHTTP Status: %{http_code}\n" -X POST "http://localhost:8000/api/v1/agent/session/test_session/action?action=cancel" 2>&1 | head -5
echo ""

# 测试删除会话端点
echo "4. 测试 DELETE /api/v1/agent/sessions/test_session"
curl -s -w "\nHTTP Status: %{http_code}\n" -X DELETE http://localhost:8000/api/v1/agent/sessions/test_session 2>&1 | head -5
echo ""

# 测试加载项目端点
echo "5. 测试 /api/v1/agent/saved/test_project"
curl -s -w "\nHTTP Status: %{http_code}\n" http://localhost:8000/api/v1/agent/saved/test_project 2>&1 | head -5
echo ""

# 测试orchestrate/stream (POST)
echo "6. 测试 POST /api/v1/agent/orchestrate/stream"
curl -s -w "\nHTTP Status: %{http_code}\n" -X POST http://localhost:8000/api/v1/agent/orchestrate/stream \
  -H "Content-Type: application/json" -d '{"requirement": "test"}' 2>&1 | head -5
echo ""

echo "=== 验证完成 ==="
echo ""
echo "注意：401表示端点存在但需要认证，这是正常的"
echo "404表示端点不存在，需要修复"
echo "422表示缺少必要参数，端点存在"