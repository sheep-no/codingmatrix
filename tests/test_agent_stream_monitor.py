#!/usr/bin/env python3
"""
多模型 Agent 流式生成 + 实时监控 + Diff/预览 测试

功能：
1. 调用 /api/v1/agent/orchestrate/stream 流式接口
2. 实时解析 SSE 事件，展示进度、文件生成、diff
3. 监控 session 状态，验证推送信息完整性
4. 测试文件预览和 diff 对比功能
"""

import asyncio
import json
import sys
import time
import difflib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.utils.security import create_access_token

# ========================================
# 配置
# ========================================
BASE_URL = "http://localhost:8000"
STREAM_ENDPOINT = f"{BASE_URL}/api/v1/agent/orchestrate/stream"
SESSION_ACTION_ENDPOINT = f"{BASE_URL}/api/v1/agent/session"

# 复杂项目需求（测试用）
COMPLEX_REQUIREMENT = """
创建一个任务管理看板系统（类似 Trello），包含以下功能：

1. 用户系统：用户注册、登录（JWT 认证）、角色区分
2. 看板管理：创建、编辑、删除看板，成员管理
3. 任务卡片：创建、编辑、删除，标签、优先级、截止日期
4. 列管理：创建、编辑、删除列（待办、进行中、已完成）
5. 拖拽排序和实时通知

技术栈：Python FastAPI + Vue 3 + SQLite
请生成完整项目结构和代码文件。
"""


class StreamMonitor:
    """流式事件监控器"""

    def __init__(self):
        self.events: List[Dict[str, Any]] = []
        self.files_created: Dict[str, str] = {}  # path -> content
        self.files_modified: Dict[str, str] = {}
        self.file_diffs: List[Dict[str, Any]] = []
        self.progress_history: List[Dict[str, Any]] = []
        self.errors: List[str] = []
        self.thinking_entries: List[str] = []
        self.model_info_entries: List[str] = []
        self.session_id: Optional[str] = None
        self.start_time: float = 0
        self.end_time: float = 0
        self.done: bool = False
        self.done_data: Optional[Dict] = None

    def process_event(self, event_data: Dict[str, Any]):
        """处理单个 SSE 事件"""
        self.events.append(event_data)
        msg_type = event_data.get("type", "")

        if msg_type == "thinking":
            content = event_data.get("content", "")
            self.thinking_entries.append(content)
            print(f"\n  [THINKING] {content[:120]}...")

        elif msg_type == "model_info":
            model = event_data.get("model", "unknown")
            self.model_info_entries.append(model)
            print(f"\n  [MODEL] {model}")

        elif msg_type == "file":
            path = event_data.get("path", "")
            content = event_data.get("content", "")
            action = event_data.get("action", "create")
            if action == "create":
                self.files_created[path] = content
                print(f"\n  [FILE CREATE] {path}")
                self._preview_file(path, content)
            elif action == "modify":
                if path in self.files_created:
                    old = self.files_created[path]
                    self._show_diff(path, old, content)
                self.files_modified[path] = content
                self.files_created[path] = content
                print(f"\n  [FILE MODIFY] {path}")

        elif msg_type == "file_diff":
            path = event_data.get("path", "")
            old_content = event_data.get("old_content", "")
            new_content = event_data.get("new_content", "")
            self.file_diffs.append({
                "path": path,
                "old": old_content,
                "new": new_content
            })
            print(f"\n  [DIFF] {path}")
            self._show_diff(path, old_content, new_content)

        elif msg_type == "progress":
            data = event_data.get("data", event_data)
            self.progress_history.append(data)
            step = data.get("step", "")
            message = data.get("message", "")
            total = data.get("total_steps", "")
            print(f"\n  [PROGRESS] {message} {f'({step}/{total})' if step else ''}")

        elif msg_type == "critical_decisions":
            data = event_data.get("data", {})
            decisions = data.get("decisions", [])
            print(f"\n  [DECISIONS] {json.dumps(decisions, ensure_ascii=False)[:200]}")

        elif msg_type == "pause_for_approval":
            data = event_data.get("data", {})
            file_path = data.get("file_path", "")
            print(f"\n  [APPROVAL NEEDED] {file_path}")

        elif msg_type == "error":
            data = event_data.get("data", event_data)
            error = data.get("error", str(data))
            self.errors.append(error)
            print(f"\n  [ERROR] {error}")

        elif msg_type == "done":
            self.done = True
            self.done_data = event_data.get("data", event_data)
            self.end_time = time.time()
            print(f"\n  [DONE] Generation complete!")

        elif msg_type == "log":
            data = event_data.get("data", {})
            msg = data.get("message", "")
            print(f"\n  [LOG] {msg[:150]}")

    def _preview_file(self, path: str, content: str, max_lines: int = 20):
        """预览文件内容"""
        lines = content.split("\n")
        print(f"  {'─' * 50}")
        print(f"  Preview: {path} ({len(lines)} lines)")
        print(f"  {'─' * 50}")
        for i, line in enumerate(lines[:max_lines]):
            print(f"  {i+1:4d} | {line}")
        if len(lines) > max_lines:
            print(f"  ... ({len(lines) - max_lines} more lines)")
        print(f"  {'─' * 50}")

    def _show_diff(self, path: str, old_content: str, new_content: str):
        """显示文件差异"""
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff = list(difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"old/{path}",
            tofile=f"new/{path}",
            lineterm=""
        ))
        if diff:
            print(f"  {'─' * 50}")
            print(f"  Diff: {path}")
            print(f"  {'─' * 50}")
            for line in diff[:60]:
                if line.startswith("+"):
                    print(f"  \033[32m{line}\033[0m")
                elif line.startswith("-"):
                    print(f"  \033[31m{line}\033[0m")
                elif line.startswith("@@"):
                    print(f"  \033[36m{line}\033[0m")
                else:
                    print(f"  {line}")
            if len(diff) > 60:
                print(f"  ... ({len(diff) - 60} more diff lines)")
            print(f"  {'─' * 50}")

    def print_summary(self):
        """打印测试摘要"""
        elapsed = self.end_time - self.start_time if self.end_time else 0
        print(f"\n{'=' * 70}")
        print(f"  STREAM MONITOR SUMMARY")
        print(f"{'=' * 70}")
        print(f"  Session ID:     {self.session_id}")
        print(f"  Duration:       {elapsed:.1f}s")
        print(f"  Total events:   {len(self.events)}")
        print(f"  Event types:")
        type_counts = {}
        for e in self.events:
            t = e.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1
        for t, c in sorted(type_counts.items()):
            print(f"    {t}: {c}")
        print(f"  Files created:  {len(self.files_created)}")
        print(f"  Files modified: {len(self.files_modified)}")
        print(f"  Diffs received: {len(self.file_diffs)}")
        print(f"  Progress steps: {len(self.progress_history)}")
        print(f"  Thinking:       {len(self.thinking_entries)}")
        print(f"  Model calls:    {len(self.model_info_entries)}")
        print(f"  Errors:         {len(self.errors)}")
        if self.done_data:
            print(f"  Done data:      {json.dumps(self.done_data, ensure_ascii=False)[:300]}")
        print(f"{'=' * 70}")

    def validate_events(self) -> List[str]:
        """验证事件完整性"""
        issues = []
        if not self.session_id:
            issues.append("No session_id received")
        if not self.done:
            issues.append("Stream did not complete (no 'done' event)")
        if not self.files_created:
            issues.append("No files were created")
        if not self.progress_history:
            issues.append("No progress events received")
        if self.errors:
            issues.append(f"{len(self.errors)} error(s) occurred")
        # Check that we got thinking/model_info events
        if not self.thinking_entries:
            issues.append("No thinking events received")
        if not self.model_info_entries:
            issues.append("No model_info events received")
        return issues


async def run_stream_test():
    """运行流式生成测试"""
    # Generate auth token
    token = create_access_token(sub="1", permission_level="super", expires_delta=None)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream"
    }

    monitor = StreamMonitor()
    monitor.start_time = time.time()

    request_body = {
        "requirement": COMPLEX_REQUIREMENT,
        "enable_review": True,
        "enable_validation": True,
        "enable_error_recovery": True,
        "enable_memory": True,
        "spec_first": True,
        "dependency_graph": True,
        "incremental": False,
        "require_approval": False,
        "evaluation_only": False
    }

    print(f"{'=' * 70}")
    print(f"  Multi-Model Agent Stream Generation Test")
    print(f"  Endpoint: {STREAM_ENDPOINT}")
    print(f"  Time: {datetime.now().isoformat()}")
    print(f"{'=' * 70}")
    print(f"\n  Sending request...")

    event_count = 0
    buffer = ""

    async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=10.0)) as client:
        try:
            async with client.stream(
                "POST",
                STREAM_ENDPOINT,
                json=request_body,
                headers=headers,
            ) as response:
                print(f"  Response status: {response.status_code}")

                if response.status_code != 200:
                    body = await response.aread()
                    print(f"  ERROR: {body.decode()}")
                    return

                print(f"  Streaming events...\n")

                async for chunk in response.aiter_text():
                    buffer += chunk
                    while "\n\n" in buffer:
                        event_str, buffer = buffer.split("\n\n", 1)
                        event_str = event_str.strip()
                        if not event_str:
                            continue

                        # Parse SSE format
                        for line in event_str.split("\n"):
                            if line.startswith("data: "):
                                data_str = line[6:]
                                try:
                                    event_data = json.loads(data_str)
                                    event_count += 1

                                    # Extract session_id from first event
                                    if not monitor.session_id:
                                        sid = event_data.get("session_id") or event_data.get("data", {}).get("session_id")
                                        if sid:
                                            monitor.session_id = sid
                                            print(f"  Session ID: {sid}\n")

                                    monitor.process_event(event_data)

                                    # Periodic status line
                                    if event_count % 10 == 0:
                                        print(f"\n  --- Events: {event_count} | Files: {len(monitor.files_created)} | Progress: {len(monitor.progress_history)} ---")

                                except json.JSONDecodeError:
                                    print(f"  [RAW] {data_str[:200]}")

        except httpx.ConnectError as e:
            print(f"\n  CONNECTION ERROR: {e}")
            print(f"  Is the backend running on {BASE_URL}?")
            return
        except httpx.ReadTimeout:
            print(f"\n  TIMEOUT: Stream timed out after 300s")
        except Exception as e:
            print(f"\n  EXCEPTION: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

    monitor.end_time = time.time()

    # Print summary and validate
    monitor.print_summary()

    issues = monitor.validate_events()
    if issues:
        print(f"\n  VALIDATION ISSUES:")
        for issue in issues:
            print(f"    - {issue}")
    else:
        print(f"\n  ALL VALIDATIONS PASSED!")

    # List all generated files
    if monitor.files_created:
        print(f"\n  Generated Files:")
        for path in sorted(monitor.files_created.keys()):
            content = monitor.files_created[path]
            lines = len(content.split("\n"))
            print(f"    {path} ({lines} lines)")

    return monitor


async def run_incremental_test(monitor: StreamMonitor):
    """在首次生成后，运行增量修改测试"""
    if not monitor or not monitor.files_created:
        print("\n  Skipping incremental test - no files generated")
        return

    token = create_access_token(sub="1", permission_level="super", expires_delta=None)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream"
    }

    incremental_req = {
        "requirement": "对任务管理看板系统进行以下增量修改：\n1. 新增日历视图，支持按日期查看任务\n2. 添加任务统计仪表盘\n3. 优化拖拽体验，添加动画效果\n4. 新增任务导入导出功能（CSV/JSON）",
        "session_id": monitor.session_id,
        "incremental": True,
        "enable_review": True,
        "enable_validation": True,
        "spec_first": True,
        "dependency_graph": True,
    }

    inc_monitor = StreamMonitor()
    inc_monitor.start_time = time.time()
    inc_monitor.session_id = monitor.session_id

    print(f"\n{'=' * 70}")
    print(f"  Incremental Modification Test")
    print(f"  Session: {monitor.session_id}")
    print(f"{'=' * 70}")

    buffer = ""
    event_count = 0

    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
        try:
            async with client.stream(
                "POST",
                STREAM_ENDPOINT,
                json=incremental_req,
                headers=headers,
            ) as response:
                print(f"  Status: {response.status_code}")
                if response.status_code != 200:
                    body = await response.aread()
                    print(f"  ERROR: {body.decode()}")
                    return

                async for chunk in response.aiter_text():
                    buffer += chunk
                    while "\n\n" in buffer:
                        event_str, buffer = buffer.split("\n\n", 1)
                        event_str = event_str.strip()
                        if not event_str:
                            continue
                        for line in event_str.split("\n"):
                            if line.startswith("data: "):
                                data_str = line[6:]
                                try:
                                    event_data = json.loads(data_str)
                                    event_count += 1
                                    inc_monitor.process_event(event_data)
                                except json.JSONDecodeError:
                                    pass
        except Exception as e:
            print(f"\n  EXCEPTION: {type(e).__name__}: {e}")

    inc_monitor.end_time = time.time()
    inc_monitor.print_summary()

    if inc_monitor.file_diffs:
        print(f"\n  Incremental Diffs Received: {len(inc_monitor.file_diffs)}")
        for d in inc_monitor.file_diffs:
            print(f"    - {d['path']}")


async def main():
    """主函数"""
    print(f"\n{'#' * 70}")
    print(f"  Multi-Model Agent Stream + Monitor Test Suite")
    print(f"  {datetime.now().isoformat()}")
    print(f"{'#' * 70}")

    # Step 1: Stream generation test
    monitor = await run_stream_test()

    # Step 2: Incremental modification test (only if step 1 succeeded)
    if monitor and monitor.done and monitor.files_created:
        print(f"\n\n{'#' * 70}")
        print(f"  Phase 2: Incremental Modification")
        print(f"{'#' * 70}")
        await run_incremental_test(monitor)

    print(f"\n{'#' * 70}")
    print(f"  Test Suite Complete")
    print(f"{'#' * 70}")


if __name__ == "__main__":
    asyncio.run(main())
