#!/bin/bash
# E2E Test via curl (替代 Playwright，节省 ~300MB 内存)
# 流程：登录 → 触发 orchestrate/stream SSE → 等待完成 → 验证文件生成

set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
EMAIL="admin@example.com"
PASSWORD="admin123"
REQUIREMENT="创建一个记账本应用，功能：1. 用户可以添加收支记录（金额、分类、备注、日期）2. 显示所有记录列表 3. 显示本月收支总览 4. 数据持久化到 localStorage 5. 响应式设计，支持手机和桌面 6. 现代 UI 设计，包含渐变色和卡片式布局"
MAX_WAIT=7200  # 最长等待 2 小时
LOG_FILE="/tmp/curl_e2e_test.log"

log() {
    local ts
    ts=$(date '+%H:%M:%S')
    echo "[$ts] $*" | tee -a "$LOG_FILE"
}

# 清空日志
> "$LOG_FILE"

# ========== 1. 健康检查 ==========
log "=== 步骤 1: 健康检查 ==="
HEALTH=$(curl -sf --max-time 5 "$BASE_URL/api/v1/health" 2>/dev/null || echo "FAIL")
if echo "$HEALTH" | grep -q "healthy"; then
    log "后端健康检查通过"
else
    log "ERROR: 后端不健康: $HEALTH"
    exit 1
fi

# ========== 2. 获取 CSRF Token ==========
log "=== 步骤 2: 获取 CSRF Token ==="
CSRF_RESP=$(curl -sf --max-time 5 -c /tmp/e2e_cookies.txt "$BASE_URL/api/v1/csrf-token")
CSRF_TOKEN=$(echo "$CSRF_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['csrf_token'])")
log "CSRF Token: ${CSRF_TOKEN:0:20}..."

# ========== 3. 登录 ==========
log "=== 步骤 3: 登录 ==="
LOGIN_RESP=$(curl -sf --max-time 10 -b /tmp/e2e_cookies.txt -c /tmp/e2e_cookies.txt \
    -H "Content-Type: application/json" \
    -H "X-CSRF-Token: $CSRF_TOKEN" \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" \
    "$BASE_URL/api/v1/login")

ACCESS_TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null || echo "")
if [ -z "$ACCESS_TOKEN" ]; then
    log "ERROR: 登录失败: $LOGIN_RESP"
    exit 1
fi
log "登录成功，token: ${ACCESS_TOKEN:0:20}..."

# ========== 4. 触发 SSE 生成（带 RATE_LIMITED 重试） ==========
log "=== 步骤 4: 触发 orchestrate/stream SSE ==="
SSE_LOG="/tmp/curl_e2e_sse.log"
> "$SSE_LOG"

REQUIREMENT_JSON=$(echo "$REQUIREMENT" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read().strip()))")

trigger_sse() {
    curl -sS --max-time "$MAX_WAIT" --no-buffer \
        -H "Authorization: Bearer $ACCESS_TOKEN" \
        -H "Content-Type: application/json" \
        -H "Accept: text/event-stream" \
        -d "{
            \"requirement\": $REQUIREMENT_JSON,
            \"enable_review\": true,
            \"enable_validation\": true,
            \"enable_error_recovery\": true,
            \"spec_first\": true,
            \"dependency_graph\": true
        }" \
        "$BASE_URL/api/v1/agent/orchestrate/stream"
}

# 后台启动 SSE 请求
trigger_sse > "$SSE_LOG" 2>&1 &
SSE_PID=$!
log "SSE 请求已发出，PID: $SSE_PID"

# 等待几秒检查是否有 RATE_LIMITED 错误
sleep 3
if grep -q "RATE_LIMITED" "$SSE_LOG" 2>/dev/null; then
    log "检测到 RATE_LIMITED，尝试停止旧 session..."
    OLD_SESSION=$(grep "RATE_LIMITED" "$SSE_LOG" | grep -o "'session_id': '[^']*'" | cut -d"'" -f4)
    if [ -n "$OLD_SESSION" ]; then
        log "停止旧 session: $OLD_SESSION"
        curl -sf --max-time 10 \
            -H "Authorization: Bearer $ACCESS_TOKEN" \
            -X POST "$BASE_URL/api/v1/agent/stop/$OLD_SESSION" 2>&1 || true
        sleep 2
    fi
    # 清空日志并重试
    > "$SSE_LOG"
    kill "$SSE_PID" 2>/dev/null || true
    wait "$SSE_PID" 2>/dev/null || true
    log "重试 SSE 请求..."
    trigger_sse > "$SSE_LOG" 2>&1 &
    SSE_PID=$!
fi
log "SSE 请求已发出，PID: $SSE_PID"

# ========== 5. 监控 SSE 流 ==========
log "=== 步骤 5: 监控 SSE 流 ==="
START_TIME=$(date +%s)
DONE=false
LAST_ACTIVITY=$START_TIME
FILE_COUNT=0
STEP_COUNT=0
THINKING_COUNT=0
DECISION_SUBMITTED=false

while [ "$DONE" = "false" ]; do
    # 检查 curl 进程是否还在运行
    if ! kill -0 "$SSE_PID" 2>/dev/null; then
        log "SSE 进程已结束"
        DONE=true
        break
    fi

    # 检查超时
    NOW=$(date +%s)
    ELAPSED=$((NOW - START_TIME))
    if [ "$ELAPSED" -ge "$MAX_WAIT" ]; then
        log "ERROR: 超时 (${MAX_WAIT}s)"
        kill "$SSE_PID" 2>/dev/null || true
        break
    fi

    # 解析 SSE 日志中的事件
    if [ -f "$SSE_LOG" ]; then
        # 统计事件（使用 grep -c || true 避免 set -e 退出）
        NEW_FILES=$(grep -c '"type": "file"\|"type":"file"' "$SSE_LOG" 2>/dev/null || true)
        NEW_FILES=${NEW_FILES:-0}
        NEW_STEPS=$(grep -c '"type": "step_detail"\|"type":"step_detail"' "$SSE_LOG" 2>/dev/null || true)
        NEW_STEPS=${NEW_STEPS:-0}
        
        if [ "$NEW_FILES" -gt "$FILE_COUNT" ] 2>/dev/null; then
            log "新文件生成! 总计: $NEW_FILES 个文件 (${ELAPSED}s)"
            FILE_COUNT=$NEW_FILES
        fi
        if [ "$NEW_STEPS" -gt "$((STEP_COUNT + 10))" ] 2>/dev/null; then
            log "步骤进展: $NEW_STEPS 个步骤 (${ELAPSED}s)"
            STEP_COUNT=$NEW_STEPS
        fi

        # 检测 critical_decisions 事件并自动提交默认决策
        if [ "$DECISION_SUBMITTED" = "false" ] && grep -q '"type": "critical_decisions"\|"type":"critical_decisions"' "$SSE_LOG" 2>/dev/null; then
            log "检测到 critical_decisions，自动提交默认决策..."
            # 提取 session_id
            DECISION_SESSION=$(grep -o '"session_id": "[^"]*"' "$SSE_LOG" | tail -1 | cut -d'"' -f4)
            if [ -n "$DECISION_SESSION" ]; then
                # 提交默认决策（使用所有 default 值）
                DECISION_RESP=$(curl -sf --max-time 10 \
                    -H "Authorization: Bearer $ACCESS_TOKEN" \
                    -H "Content-Type: application/json" \
                    -d '{"auth_strategy":"JWT","database_choice":"PostgreSQL","frontend_framework":"Vue 3"}' \
                    "$BASE_URL/api/v1/agent/session/$DECISION_SESSION/decision" 2>&1)
                log "决策提交结果: $DECISION_RESP"
                DECISION_SUBMITTED=true
            fi
        fi

        # 检测完成事件
        if grep -q '"type": "done"\|"type":"done"' "$SSE_LOG" 2>/dev/null; then
            log "收到 done 事件! (${ELAPSED}s)"
            DONE=true
        fi
        if grep -q '"type": "error"\|"type":"error"' "$SSE_LOG" 2>/dev/null; then
            ERROR_MSG=$(grep '"type":"error"' "$SSE_LOG" | tail -1)
            log "收到错误事件: $ERROR_MSG"
            DONE=true
        fi
    fi

    sleep 5
done

END_TIME=$(date +%s)
TOTAL_TIME=$((END_TIME - START_TIME))
log "SSE 流结束，总耗时: ${TOTAL_TIME}s"

# 等待 curl 进程退出
wait "$SSE_PID" 2>/dev/null || true

# ========== 6. 分析 SSE 结果 ==========
log "=== 步骤 6: 分析 SSE 结果 ==="
if [ -f "$SSE_LOG" ]; then
    TOTAL_EVENTS=$(wc -l < "$SSE_LOG" 2>/dev/null || true); TOTAL_EVENTS=${TOTAL_EVENTS:-0}
    FILE_EVENTS=$(grep -c '"type": "file"\|"type":"file"' "$SSE_LOG" 2>/dev/null || true); FILE_EVENTS=${FILE_EVENTS:-0}
    THINKING_EVENTS=$(grep -c '"type": "thinking"\|"type":"thinking"' "$SSE_LOG" 2>/dev/null || true); THINKING_EVENTS=${THINKING_EVENTS:-0}
    STEP_EVENTS=$(grep -c '"type": "step_detail"\|"type":"step_detail"' "$SSE_LOG" 2>/dev/null || true); STEP_EVENTS=${STEP_EVENTS:-0}
    DONE_EVENTS=$(grep -c '"type": "done"\|"type":"done"' "$SSE_LOG" 2>/dev/null || true); DONE_EVENTS=${DONE_EVENTS:-0}
    ERROR_EVENTS=$(grep -c '"type": "error"\|"type":"error"' "$SSE_LOG" 2>/dev/null || true); ERROR_EVENTS=${ERROR_EVENTS:-0}
    
    log "SSE 事件统计:"
    log "  总行数: $TOTAL_EVENTS"
    log "  文件生成: $FILE_EVENTS"
    log "  thinking: $THINKING_EVENTS"
    log "  步骤详情: $STEP_EVENTS"
    log "  完成事件: $DONE_EVENTS"
    log "  错误事件: $ERROR_EVENTS"
    
    # 提取 session_id
    SESSION_ID=$(grep -o '"session_id":"[^"]*"' "$SSE_LOG" | tail -1 | cut -d'"' -f4)
    if [ -n "$SESSION_ID" ]; then
        log "  Session ID: $SESSION_ID"
    fi
    
    # 提取项目路径
    PROJECT_PATH=$(grep -o '"project_path":"[^"]*"' "$SSE_LOG" | tail -1 | cut -d'"' -f4)
    if [ -z "$PROJECT_PATH" ]; then
        PROJECT_PATH=$(grep -o '"path":"[^"]*"' "$SSE_LOG" | tail -1 | cut -d'"' -f4)
    fi
    if [ -n "$PROJECT_PATH" ]; then
        log "  项目路径: $PROJECT_PATH"
    fi
fi

# ========== 7. 验证生成的文件 ==========
log "=== 步骤 7: 验证生成的文件 ==="
if [ -n "${PROJECT_PATH:-}" ] && [ -d "$PROJECT_PATH" ]; then
    log "项目目录存在: $PROJECT_PATH"
    
    # 列出文件
    log "生成的文件:"
    find "$PROJECT_PATH" -type f | sort | while read -r f; do
        SIZE=$(wc -c < "$f")
        log "  $(echo "$f" | sed "s|$PROJECT_PATH/||") ($SIZE bytes)"
    done
    
    # 统计
    TOTAL_FILES=$(find "$PROJECT_PATH" -type f | wc -l)
    HTML_FILES=$(find "$PROJECT_PATH" -name "*.html" | wc -l)
    CSS_FILES=$(find "$PROJECT_PATH" -name "*.css" | wc -l)
    JS_FILES=$(find "$PROJECT_PATH" -name "*.js" | wc -l)
    JSON_FILES=$(find "$PROJECT_PATH" -name "*.json" | wc -l)
    
    log "文件统计: 总计=$TOTAL_FILES, HTML=$HTML_FILES, CSS=$CSS_FILES, JS=$JS_FILES, JSON=$JSON_FILES"
    
    # 检查是否有垃圾文件名
    JUNK_FILES=$(find "$PROJECT_PATH" -type f | grep -cE '\.(json|md)\.' 2>/dev/null || true); JUNK_FILES=${JUNK_FILES:-0}
    if [ "$JUNK_FILES" -gt 0 ]; then
        log "WARNING: 发现 $JUNK_FILES 个垃圾文件名"
        find "$PROJECT_PATH" -type f | grep -E '\.(json|md)\.' | while read -r f; do
            log "  垃圾文件: $f"
        done
    fi
    
    # 检查 index.html 是否存在
    if [ -f "$PROJECT_PATH/index.html" ]; then
        log "index.html 存在"
    else
        log "WARNING: index.html 不存在"
    fi
else
    log "WARNING: 项目路径不存在或未找到: ${PROJECT_PATH:-未获取到}"
    # 尝试在 projects 目录下查找最新目录
    LATEST_PROJECT=$(find /workspace/projects -maxdepth 3 -type d -name "*.html" -o -type f -name "index.html" 2>/dev/null | head -1)
    if [ -n "$LATEST_PROJECT" ]; then
        PROJECT_PATH=$(dirname "$LATEST_PROJECT")
        log "自动发现项目路径: $PROJECT_PATH"
    fi
fi

# ========== 8. 检查后端日志 ==========
log "=== 步骤 8: 检查后端状态 ==="
HEALTH_CHECK=$(curl -sf --max-time 5 "$BASE_URL/api/v1/health" 2>/dev/null || echo "FAIL")
if echo "$HEALTH_CHECK" | grep -q "healthy"; then
    log "后端仍然健康"
else
    log "WARNING: 后端可能已崩溃"
fi

# ========== 总结 ==========
log ""
log "========== 测试总结 =========="
log "总耗时: ${TOTAL_TIME}s"
log "SSE 事件: 总行=$TOTAL_EVENTS, 文件=$FILE_EVENTS, thinking=$THINKING_EVENTS"
log "完成事件: $DONE_EVENTS, 错误事件: $ERROR_EVENTS"
[ -n "${SESSION_ID:-}" ] && log "Session: $SESSION_ID"
[ -n "${PROJECT_PATH:-}" ] && log "项目路径: $PROJECT_PATH"
log "=============================="

# 清理
rm -f /tmp/e2e_cookies.txt

# 返回退出码
if [ "${DONE_EVENTS:-0}" -gt 0 ] && [ "${ERROR_EVENTS:-0}" -eq 0 ] 2>/dev/null; then
    log "RESULT: PASS"
    exit 0
else
    log "RESULT: FAIL"
    exit 1
fi
