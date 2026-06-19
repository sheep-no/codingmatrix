#!/bin/bash
# E2E 测试：浏览器断开重连场景
# 验证生成任务在 SSE 断开后继续运行，重连后能接上进度

set -e

BASE_URL="http://localhost:8000"
LOG_DIR="/workspace/logs"
TEST_LOG="/tmp/reconnect_test.log"
MAX_WAIT=3600

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$TEST_LOG"; }

> "$TEST_LOG"

log "=== 步骤 1: 健康检查 ==="
HEALTH=$(curl -s "$BASE_URL/health" | head -1)
if echo "$HEALTH" | grep -q "html"; then
    log "后端健康检查通过"
else
    log "后端健康检查失败"; exit 1
fi

log "=== 步骤 2: 获取 CSRF Token ==="
CSRF_RESPONSE=$(curl -s -c /tmp/reconnect_cookies.txt "$BASE_URL/api/v1/csrf-token")
CSRF_TOKEN=$(echo "$CSRF_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['csrf_token'])" 2>/dev/null)
if [ -z "$CSRF_TOKEN" ]; then
    log "CSRF Token 获取失败: $CSRF_RESPONSE"; exit 1
fi
log "CSRF Token: ${CSRF_TOKEN:0:20}..."

log "=== 步骤 3: 登录 ==="
LOGIN_RESPONSE=$(curl -s -b /tmp/reconnect_cookies.txt -c /tmp/reconnect_cookies.txt \
    -X POST "$BASE_URL/api/v1/login" \
    -H "Content-Type: application/json" \
    -H "X-CSRF-Token: $CSRF_TOKEN" \
    -d '{"email":"admin@example.com","password":"admin123"}')
TOKEN=$(echo "$LOGIN_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)
if [ -z "$TOKEN" ]; then
    log "登录失败: $LOGIN_RESPONSE"; exit 1
fi
log "登录成功"

log "=== 步骤 4: 触发 SSE 生成 ==="
SESSION_ID=""
SSE_PID_FILE="/tmp/reconnect_sse_pid.txt"

# 后台启动 SSE
curl -s -N -X POST "$BASE_URL/api/v1/agent/orchestrate/stream" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"requirement":"创建一个记账本web应用，包含收支记录、分类统计、图表展示功能。后端用FastAPI+SQLite，前端用原生HTML/CSS/JS。","provider_id":"siliconflow"}' \
    > /tmp/reconnect_sse_output.txt 2>&1 &
SSE_PID=$!
echo $SSE_PID > "$SSE_PID_FILE"
log "SSE 请求已发出, PID: $SSE_PID"

# 等待获取 session_id
for i in $(seq 1 30); do
    if grep -q "session_id" /tmp/reconnect_sse_output.txt 2>/dev/null; then
        SESSION_ID=$(grep -o '"session_id":"[^"]*"' /tmp/reconnect_sse_output.txt | head -1 | cut -d'"' -f4)
        break
    fi
    # 检查 critical_decisions
    if grep -q "critical_decisions" /tmp/reconnect_sse_output.txt 2>/dev/null; then
        log "检测到 critical_decisions，自动提交..."
        DECISIONS_EVENT=$(grep "critical_decisions" /tmp/reconnect_sse_output.txt | head -1 | sed 's/^data: //')
        curl -s -X POST "$BASE_URL/api/v1/agent/orchestrate/decision" \
            -H "Content-Type: application/json" \
            -H "Authorization: Bearer $TOKEN" \
            -d "{\"session_id\":\"$SESSION_ID\",\"decisions\":{\"auth_strategy\":\"JWT\",\"database_choice\":\"PostgreSQL\",\"frontend_framework\":\"Vue 3\"}}" > /dev/null 2>&1
    fi
    sleep 2
done

if [ -z "$SESSION_ID" ]; then
    # 尝试从 SSE 输出中提取
    SESSION_ID=$(grep -o '"session_id":"[^"]*"' /tmp/reconnect_sse_output.txt 2>/dev/null | head -1 | cut -d'"' -f4)
fi

if [ -z "$SESSION_ID" ]; then
    log "无法获取 session_id"
    cat /tmp/reconnect_sse_output.txt | head -20
    exit 1
fi
log "Session ID: $SESSION_ID"

# 等待一些文件生成
log "=== 步骤 5: 等待文件生成 ==="
PROJECT_DIR=""
for i in $(seq 1 60); do
    # 检查 critical_decisions
    if grep -q "critical_decisions" /tmp/reconnect_sse_output.txt 2>/dev/null; then
        if ! grep -q "submitted" /tmp/reconnect_sse_output.txt 2>/dev/null; then
            log "提交决策..."
            curl -s -X POST "$BASE_URL/api/v1/agent/orchestrate/decision" \
                -H "Content-Type: application/json" \
                -H "Authorization: Bearer $TOKEN" \
                -d "{\"session_id\":\"$SESSION_ID\",\"decisions\":{\"auth_strategy\":\"JWT\",\"database_choice\":\"PostgreSQL\",\"frontend_framework\":\"Vue 3\"}}" > /dev/null 2>&1
        fi
    fi
    
    # 查找项目目录
    if [ -z "$PROJECT_DIR" ]; then
        PROJECT_DIR=$(find /workspace/projects -type d -name "*${SESSION_ID}*" 2>/dev/null | head -1)
        if [ -z "$PROJECT_DIR" ]; then
            PROJECT_DIR=$(find /workspace/projects -maxdepth 2 -type d -newer /tmp/reconnect_cookies.txt 2>/dev/null | tail -1)
        fi
    fi
    
    if [ -n "$PROJECT_DIR" ]; then
        FILE_COUNT=$(find "$PROJECT_DIR" -type f -not -name ".dep_graph.json" -not -path "*__pycache__*" 2>/dev/null | wc -l)
        if [ "$FILE_COUNT" -ge 3 ]; then
            log "已生成 $FILE_COUNT 个文件，准备断开 SSE"
            break
        fi
    fi
    sleep 5
done

if [ -z "$PROJECT_DIR" ]; then
    log "未找到项目目录"; exit 1
fi

FILE_COUNT_BEFORE=$(find "$PROJECT_DIR" -type f -not -name ".dep_graph.json" -not -path "*__pycache__*" 2>/dev/null | wc -l)
log "断开前文件数: $FILE_COUNT_BEFORE"
log "项目目录: $PROJECT_DIR"

log "=== 步骤 6: 断开 SSE 连接 ==="
kill $SSE_PID 2>/dev/null || true
wait $SSE_PID 2>/dev/null || true
log "SSE 连接已断开 (PID: $SSE_PID)"

log "=== 步骤 7: 等待后台生成（无 SSE 连接）==="
log "等待 120 秒，让后台任务继续生成..."
sleep 120

FILE_COUNT_DURING=$(find "$PROJECT_DIR" -type f -not -name ".dep_graph.json" -not -path "*__pycache__*" 2>/dev/null | wc -l)
log "后台生成期间文件数: $FILE_COUNT_DURING (断开前: $FILE_COUNT_BEFORE)"

if [ "$FILE_COUNT_DURING" -gt "$FILE_COUNT_BEFORE" ]; then
    log "SUCCESS: 后台生成了新文件！($FILE_COUNT_BEFORE -> $FILE_COUNT_DURING)"
else
    log "WARNING: 后台未生成新文件"
fi

log "=== 步骤 8: 重新连接 SSE ==="
# 重新发起 SSE 请求（应该重连到现有任务）
curl -s -N -X POST "$BASE_URL/api/v1/agent/orchestrate/stream" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"requirement":"继续"}' \
    > /tmp/reconnect_sse_output2.txt 2>&1 &
SSE_PID2=$!
log "重连 SSE 请求已发出, PID: $SSE_PID2"

# 等待重连成功或超时
RECONNECTED=false
for i in $(seq 1 30); do
    if grep -q "heartbeat\|progress\|file_generated" /tmp/reconnect_sse_output2.txt 2>/dev/null; then
        RECONNECTED=true
        log "重连成功！收到 SSE 事件"
        break
    fi
    if grep -q "429\|error" /tmp/reconnect_sse_output2.txt 2>/dev/null; then
        log "重连返回错误: $(head -3 /tmp/reconnect_sse_output2.txt)"
        break
    fi
    sleep 2
done

if [ "$RECONNECTED" = true ]; then
    log "SUCCESS: 重连成功"
else
    log "WARNING: 重连可能失败，检查输出..."
    head -10 /tmp/reconnect_sse_output2.txt
fi

# 等待一段时间看是否能收到更多事件
sleep 30

# 最终统计
log "=== 步骤 9: 最终统计 ==="
FILE_COUNT_FINAL=$(find "$PROJECT_DIR" -type f -not -name ".dep_graph.json" -not -path "*__pycache__*" 2>/dev/null | wc -l)
log "最终文件数: $FILE_COUNT_FINAL"
log "文件列表:"
find "$PROJECT_DIR" -type f -not -name ".dep_graph.json" -not -path "*__pycache__*" 2>/dev/null | sort | while read f; do
    log "  $(basename $f) ($(wc -l < "$f") 行)"
done

# 检查后端日志中的重连记录
log "=== 步骤 10: 检查后端日志 ==="
grep -i "重连\|reconnect\|活跃任务\|后台模式\|active_task" /workspace/logs/app.log | tail -10 | while read line; do
    log "  $line"
done

# 清理
kill $SSE_PID2 2>/dev/null || true

log "=== 测试完成 ==="
log "断开前: $FILE_COUNT_BEFORE 文件"
log "后台期间: $FILE_COUNT_DURING 文件"
log "最终: $FILE_COUNT_FINAL 文件"
