#!/bin/bash
# SSE 流式推送验证脚本
# 测试后端是否成功推送事件，以及事件是否丰富
set -e

BASE="http://127.0.0.1:8000"
COOKIE_JAR="/tmp/sse-test-cookies.txt"
EVENT_LOG="/tmp/sse-test-events.jsonl"
REPORT="/tmp/sse-test-report.txt"

rm -f "$COOKIE_JAR" "$EVENT_LOG" "$REPORT"

echo "=========================================="
echo "  SSE 流式推送验证测试"
echo "=========================================="
echo ""

# 1. 获取 CSRF Token
echo "[1/4] 获取 CSRF Token..."
CSRF_RESP=$(curl -s -c "$COOKIE_JAR" "$BASE/api/v1/csrf-token")
CSRF_TOKEN=$(echo "$CSRF_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['csrf_token'])")
echo "  CSRF Token: ${CSRF_TOKEN:0:20}..."

# 2. 登录
echo "[2/4] 登录..."
LOGIN_RESP=$(curl -s -b "$COOKIE_JAR" -X POST "$BASE/api/v1/login" \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: $CSRF_TOKEN" \
  -d '{"email":"admin@example.com","password":"admin123"}')
TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "  JWT Token: ${TOKEN:0:30}..."

# 3. 发送生成请求并捕获 SSE 流
echo "[3/4] 发送生成请求，捕获 SSE 流（最多 5 分钟）..."
echo "  需求: 创建一个 hello.py 打印 hello world"
echo ""

SESSION_ID="sse-test-$(date +%s)"
START_TIME=$(date +%s%N)

# 使用 timeout 限制最大等待时间，逐行读取事件
timeout 300 curl -sN -X POST "$BASE/api/v1/agent/orchestrate/stream" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "{\"requirement\":\"创建一个 hello.py 文件，打印 hello world，要求包含 main 函数和 if __name__ 保护\",\"session_id\":\"$SESSION_ID\",\"enable_review\":false}" \
  2>/dev/null | while IFS= read -r line; do
    NOW=$(date +%s%N)
    ELAPSED=$(( (NOW - START_TIME) / 1000000 ))
    
    # 只处理 data: 行
    if [[ "$line" == data:* ]]; then
      JSON_DATA="${line#data: }"
      echo "$JSON_DATA" >> "$EVENT_LOG"
      
      # 解析事件类型
      EVENT_TYPE=$(echo "$JSON_DATA" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    t = d.get('type', 'unknown')
    data = d.get('data', {})
    if isinstance(data, dict):
        phase = data.get('phase', '')
        step = data.get('step', '')
        print(f'{t}:{phase}:{step}' if phase else f'{t}:{step}' if step else t)
    else:
        print(t)
except:
    print('parse_error')
" 2>/dev/null)
      
      # 计算事件大小
      EVENT_SIZE=${#JSON_DATA}
      
      printf "  [%6dms] %-45s (%dB)\n" "$ELAPSED" "$EVENT_TYPE" "$EVENT_SIZE"
    elif [[ -n "$line" && "$line" != "" ]]; then
      # 非 data 行（可能是空行或注释）
      :
    fi
  done

echo ""
echo "[4/4] 分析结果..."
echo ""

# 分析事件日志
if [[ -f "$EVENT_LOG" ]]; then
  TOTAL_EVENTS=$(wc -l < "$EVENT_LOG")
  
  python3 << 'PYEOF'
import json
import sys
from collections import Counter

with open("/tmp/sse-test-events.jsonl") as f:
    lines = f.readlines()

if not lines:
    print("  !! 没有捕获到任何 SSE 事件")
    sys.exit(1)

events = []
for line in lines:
    try:
        events.append(json.loads(line.strip()))
    except:
        pass

# 统计事件类型
type_counter = Counter()
phase_counter = Counter()
step_counter = Counter()
has_file_events = False
has_progress = False
has_done = False
has_error = False
file_names = []
model_names = []
total_data_size = 0
max_event_size = 0

for evt in events:
    evt_type = evt.get("type", "unknown")
    data = evt.get("data", {})
    type_counter[evt_type] += 1
    
    size = len(json.dumps(evt))
    total_data_size += size
    max_event_size = max(max_event_size, size)
    
    if isinstance(data, dict):
        phase = data.get("phase", "")
        step = data.get("step", "")
        if phase:
            phase_counter[phase] += 1
        if step:
            step_counter[step] += 1
        
        # 检查文件事件
        if evt_type == "file_event":
            has_file_events = True
            fname = data.get("file_name", data.get("path", ""))
            if fname:
                file_names.append(fname)
        
        # 检查进度事件
        if evt_type == "progress":
            has_progress = True
            if "model" in data or "architect" in data:
                model_names.append(data.get("model", data.get("architect", "")))
        
        # 检查完成事件
        if evt_type == "done":
            has_done = True
        
        # 检查错误事件
        if evt_type == "error":
            has_error = True
            print(f"  !! 错误事件: {data.get('message', 'unknown')}")

print("=" * 50)
print("  SSE 事件分析报告")
print("=" * 50)
print(f"")
print(f"  总事件数:     {len(events)}")
print(f"  总数据量:     {total_data_size:,} bytes")
print(f"  最大事件:     {max_event_size:,} bytes")
print(f"")
print(f"  事件类型分布:")
for t, count in type_counter.most_common():
    print(f"    {t:25s} x {count}")
print(f"")
print(f"  阶段分布:")
for p, count in phase_counter.most_common():
    print(f"    {p:25s} x {count}")
print(f"")
print(f"  步骤分布:")
for s, count in step_counter.most_common(15):
    print(f"    {s:25s} x {count}")

print(f"")
print(f"  关键指标:")
print(f"    有进度事件:     {'YES' if has_progress else 'NO'}")
print(f"    有文件事件:     {'YES' if has_file_events else 'NO'}")
print(f"    有完成事件:     {'YES' if has_done else 'NO'}")
print(f"    有错误事件:     {'YES' if has_error else 'NO'}")

if file_names:
    print(f"")
    print(f"  生成的文件 ({len(file_names)}):")
    for fn in file_names:
        print(f"    - {fn}")

if model_names:
    print(f"")
    print(f"  使用的模型:")
    for mn in set(model_names):
        if mn:
            print(f"    - {mn}")

# 丰富度评分
score = 0
max_score = 10
reasons = []

if len(events) >= 5:
    score += 1
    reasons.append(f"事件数量充足 ({len(events)})")
else:
    reasons.append(f"事件数量不足 ({len(events)} < 5)")

if has_progress:
    score += 2
    reasons.append("有进度推送")
else:
    reasons.append("缺少进度推送")

if has_file_events:
    score += 2
    reasons.append(f"有文件事件 ({len(file_names)} 个文件)")
else:
    reasons.append("缺少文件事件")

if has_done:
    score += 2
    reasons.append("有完成事件")
else:
    reasons.append("缺少完成事件")

if total_data_size > 1000:
    score += 1
    reasons.append(f"数据量充足 ({total_data_size:,}B)")
else:
    reasons.append(f"数据量不足 ({total_data_size:,}B)")

if len(phase_counter) >= 3:
    score += 1
    reasons.append(f"阶段覆盖 ({len(phase_counter)} 个阶段)")
else:
    reasons.append(f"阶段覆盖不足 ({len(phase_counter)} 个阶段)")

if max_event_size > 200:
    score += 1
    reasons.append(f"事件内容丰富 (最大 {max_event_size:,}B)")
else:
    reasons.append(f"事件内容单薄 (最大 {max_event_size:,}B)")

print(f"")
print(f"  丰富度评分: {score}/{max_score}")
if score >= 8:
    grade = "EXCELLENT"
elif score >= 6:
    grade = "GOOD"
elif score >= 4:
    grade = "FAIR"
else:
    grade = "POOR"
print(f"  等级: {grade}")
print(f"")
for r in reasons:
    print(f"    {'[+]' if any(k in r for k in ['充足','有','覆盖','丰富']) else '[!]'} {r}")

print(f"")
print("=" * 50)
PYEOF
else
  echo "  !! 没有捕获到任何 SSE 事件文件"
fi
