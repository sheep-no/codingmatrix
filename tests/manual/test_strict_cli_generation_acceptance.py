"""Real SSE acceptance for a strict three-file CLI generation plan."""

from __future__ import annotations

import ast
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, "/workspace")
from app.utils.security import create_access_token


URL = "http://127.0.0.1:8000/api/v1/agent/orchestrate/stream"
EXPECTED_FILES = {"main.py", "todo.py", "test_main.py"}
REQUIREMENT = """
创建一个纯 Python 命令行待办事项应用，只使用 Python 标准库。
只生成以下 3 个文件：main.py、todo.py、test_main.py。
main.py 是命令行入口并且只能导入 todo.py；todo.py 实现待办事项的数据模型、JSON 文件持久化以及新增、列出、完成、删除功能；test_main.py 使用 pytest 覆盖核心功能。
跨文件接口必须保持一致：todo.py 的 list_todos 返回 Todo 对象列表；add_todo 必须分配稳定的正整数 ID；add、complete、delete 每次成功后都必须保存 JSON 文件。
main.py 必须导出 main()，所有成功命令都返回整数 0，参数或业务错误返回非零整数；直接执行 main.py 时以 main() 返回值退出。
test_main.py 必须使用 pytest 的 tmp_path 和 monkeypatch 隔离 JSON 存储与命令行参数，并按 add、list、complete、delete 的完整顺序验证持久化结果。
严格遵循这三个文件组成的冻结文件计划。禁止添加任何其他文件、第三方依赖或计划外模块；禁止引用 typer、src.models、src.utils 或其他未列出的模块。
""".strip()


async def main() -> int:
    project_name = f"acceptance_cli_qwen35_strict_{int(time.time())}"
    output_dir = Path("/workspace/projects/1") / project_name
    token = create_access_token(sub="1", permission_level="super", expires_delta=None)
    request = {
        "requirement": REQUIREMENT,
        "project_name": project_name,
        "enable_review": False,
        "enable_validation": True,
        "enable_error_recovery": True,
        "enable_memory": False,
        "spec_first": False,
        "dependency_graph": True,
    }
    events = []
    started = time.monotonic()

    async with httpx.AsyncClient(timeout=httpx.Timeout(900.0)) as client:
        async with client.stream(
            "POST",
            URL,
            json=request,
            headers={"Authorization": f"Bearer {token}", "Accept": "text/event-stream"},
        ) as response:
            print(f"http_status={response.status_code}")
            if response.status_code != 200:
                print((await response.aread()).decode(errors="replace"))
                return 1

            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    event = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                events.append(event)
                if event.get("type") in {"file", "done", "error"}:
                    print(
                        f"event={event.get('type')} "
                        f"path={event.get('path', '')} "
                        f"data={event.get('data', '')}"
                    )

    done_events = [event for event in events if event.get("type") == "done"]
    error_events = [event for event in events if event.get("type") == "error"]
    disk_files = {
        path.relative_to(output_dir).as_posix()
        for path in output_dir.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and not any(part.startswith(".") for part in path.relative_to(output_dir).parts)
    }
    print(f"project_dir={output_dir}")
    print(f"elapsed_seconds={time.monotonic() - started:.1f}")
    print(f"done_events={len(done_events)} error_events={len(error_events)}")
    print(f"disk_files={sorted(disk_files)}")

    if len(done_events) != 1 or error_events or disk_files != EXPECTED_FILES:
        return 1

    for relative_path in sorted(EXPECTED_FILES):
        source = (output_dir / relative_path).read_text(encoding="utf-8")
        ast.parse(source, filename=relative_path)

    test_run = subprocess.run(
        [sys.executable, "-m", "pytest", "test_main.py", "-q"],
        cwd=output_dir,
        capture_output=True,
        text=True,
        timeout=180,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    print(f"generated_test_exit_code={test_run.returncode}")
    if test_run.stdout:
        print(test_run.stdout[-2000:])
    if test_run.stderr:
        print(test_run.stderr[-2000:])
    return test_run.returncode


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
