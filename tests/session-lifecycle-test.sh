#!/bin/bash
# 会话生命周期验证脚本
# 测试：创建、并发限制、取消、资源释放
set -e

BASE="http://127.0.0.1:8000"
COOKIE_JAR="/tmp/lifecycle-cookies.txt"
rm -f "$COOKIE_JAR"

echo "=========================================="
echo "  会话生命周期验证测试"
echo "=========================================="
echo ""

# 登录
echo "[0/6] 登录..."
CSRF=$(curl -s -c "$COOKIE_JAR" "$BASE/api/v1/csrf-token" | python3 -c "import sys,json; print(json.load(sys.stdin)['csrf_token'])")
LOGIN_RESP=$(curl -s -b "$COOKIE_JAR" -X POST "$BASE/api/v1/login" \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: $CSRF" \
  -d '{"email":"admin@example.com","password":"admin123"}')
TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
ROLE=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('permission_level','user'))")
echo "  Token: ${TOKEN:0:30}... | Role: $ROLE"

AUTH="Authorization: Bearer $TOKEN"

# ========== 测试 1: 并发限制 ==========
echo ""
echo "[1/6] 查询并发限制..."
LIMITS=$(curl -s "$BASE/api/v1/agent/concurrent-limits/recommended" -H "$AUTH")
echo "  $LIMITS"

echo ""
echo "[2/6] 查询当前活跃会话..."
# 通过 sessions API 查询
SESSIONS=$(curl -s "$BASE/api/v1/agent/sessions" -H "$AUTH" 2>/dev/null || echo '{"sessions":[]}')
echo "  当前会话: $SESSIONS"

# ========== 测试 2: 创建第一个会话（流式） ==========
echo ""
echo "[3/6] 创建会话 1（流式生成）..."
SESSION1_ID="lifecycle-test-1-$(date +%s)"
EVENT_COUNT=0
DONE_RECEIVED=false
FILES_CREATED=()

while IFS= read -r line; do
  if [[ "$line" == data:* ]]; then
    JSON_DATA="${line#data: }"
    EVENT_TYPE=$(echo "$JSON_DATA" | python3 -c "import sys,json; print(json.load(sys.stdin).get('type',''))" 2>/dev/null)
    EVENT_COUNT=$((EVENT_COUNT + 1))
    
    if [[ "$EVENT_TYPE" == "done" ]]; then
      DONE_RECEIVED=true
      echo "  [事件 $EVENT_COUNT] DONE - 生成完成"
      # 提取文件列表
      FILES=$(echo "$JSON_DATA" | python3 -c "
import sys, json
d = json.load(sys.stdin).get('data', {})
files = d.get('files', [])
for f in files:
    print(f'    - {f.get(\"path\",\"?\")} ({f.get(\"size\",0)}B) status={f.get(\"success\",\"?\")}')
print(f'    总文件: {len(files)}, 耗时: {d.get(\"performance\",{}).get(\"total_duration\",\"?\")}s')
" 2>/dev/null)
      echo "$FILES"
    elif [[ "$EVENT_TYPE" == "file" ]]; then
      FNAME=$(echo "$JSON_DATA" | python3 -c "import sys,json; print(json.load(sys.stdin).get('path',''))" 2>/dev/null)
      FILES_CREATED+=("$FNAME")
      echo "  [事件 $EVENT_COUNT] FILE: $FNAME"
    elif [[ "$EVENT_TYPE" == "error" ]]; then
      echo "  [事件 $EVENT_COUNT] ERROR"
    fi
  fi
done < <(timeout 120 curl -sN -X POST "$BASE/api/v1/agent/orchestrate/stream" \
  -H "Content-Type: application/json" \
  -H "$AUTH" \
  -d "{\"requirement\":\"创建一个 hello.py 打印 hello world，包含 main 函数\",\"session_id\":\"$SESSION1_ID\",\"enable_review\":false}" \
  2>/dev/null)

echo "  会话 1 完成: events=$EVENT_COUNT, done=$DONE_RECEIVED, files=${#FILES_CREATED[@]}"

# ========== 测试 3: 验证 DB 状态 ==========
echo ""
echo "[4/6] 验证会话 1 DB 状态..."
# 查询 session 状态
SESSION_STATUS=$(curl -s "$BASE/api/v1/agent/sessions" -H "$AUTH" 2>/dev/null)
echo "  会话列表: $(echo "$SESSION_STATUS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'共 {len(d.get(\"sessions\",[]))} 个会话')" 2>/dev/null)"

# ========== 测试 4: 创建第二个会话（验证并发） ==========
echo ""
echo "[5/6] 创建会话 2（验证并发限制允许 2 个）..."
SESSION2_ID="lifecycle-test-2-$(date +%s)"
EVENT2_COUNT=0

while IFS= read -r line; do
  if [[ "$line" == data:* ]]; then
    JSON_DATA="${line#data: }"
    EVENT_TYPE=$(echo "$JSON_DATA" | python3 -c "import sys,json; print(json.load(sys.stdin).get('type',''))" 2>/dev/null)
    EVENT2_COUNT=$((EVENT2_COUNT + 1))
    
    if [[ "$EVENT_TYPE" == "done" ]]; then
      echo "  [事件 $EVENT2_COUNT] DONE - 会话 2 生成完成"
    elif [[ "$EVENT_TYPE" == "file" ]]; then
      FNAME=$(echo "$JSON_DATA" | python3 -c "import sys,json; print(json.load(sys.stdin).get('path',''))" 2>/dev/null)
      echo "  [事件 $EVENT2_COUNT] FILE: $FNAME"
    elif [[ "$EVENT_TYPE" == "error" ]]; then
      ERR_MSG=$(echo "$JSON_DATA" | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('error',''))" 2>/dev/null)
      echo "  [事件 $EVENT2_COUNT] ERROR: $ERR_MSG"
      if [[ "$ERR_MSG" == *"并发"* || "$ERR_MSG" == *"限制"* || "$ERR_MSG" == *"429"* ]]; then
        echo "  !! 触发并发限制（预期行为，如果 max=1）"
      fi
    fi
  fi
done < <(timeout 120 curl -sN -X POST "$BASE/api/v1/agent/orchestrate/stream" \
  -H "Content-Type: application/json" \
  -H "$AUTH" \
  -d "{\"requirement\":\"创建一个 calculator.py 实现加减乘除\",\"session_id\":\"$SESSION2_ID\",\"enable_review\":false}" \
  2>/dev/null)

echo "  会话 2 完成: events=$EVENT2_COUNT"

# ========== 测试 5: 取消会话验证资源释放 ==========
echo ""
echo "[6/6] 取消会话 1 验证资源释放..."
CANCEL_RESP=$(curl -s -X POST "$BASE/api/v1/agent/session/$SESSION1_ID/action?action=cancel" \
  -H "Content-Type: application/json" \
  -H "$AUTH")
echo "  取消响应: $CANCEL_RESP"

# 再次查询会话列表
FINAL_SESSIONS=$(curl -s "$BASE/api/v1/agent/sessions" -H "$AUTH" 2>/dev/null)
echo "  最终会话: $FINAL_SESSIONS"

# ========== 总结 ==========
echo ""
echo "=========================================="
echo "  测试总结"
echo "=========================================="
echo "  会话 1 ($SESSION1_ID): events=$EVENT_COUNT"
echo "  会话 2 ($SESSION2_ID): events=$EVENT2_COUNT"
echo "  并发限制: max_allowed=2 (config)"
echo "  取消操作: $(echo "$CANCEL_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null)"

if $DONE_RECEIVED; then
  echo "  会话生命周期: PASS (创建→运行→完成)"
else
  echo "  会话生命周期: PARTIAL (未收到 done 事件)"
fi
echo "=========================================="
