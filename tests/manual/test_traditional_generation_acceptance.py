"""Manual task 11.1 acceptance for the traditional generation path."""

from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, "/workspace")
from app.utils.security import create_access_token


URL = "http://127.0.0.1:8000/api/v1/agent/orchestrate/stream"
RENAMED_MODE = "--renamed" in sys.argv
FILE_NAMES = (
    {
        "entry": "app_entry.py",
        "model": "entities.py",
        "database": "persistence.py",
        "schema": "dto.py",
        "repository": "repository.py",
        "test": "api_test.py",
    }
    if RENAMED_MODE
    else {
        "entry": "main.py",
        "model": "models.py",
        "database": "database.py",
        "schema": "schemas.py",
        "repository": "crud.py",
        "test": "test_main.py",
    }
)
EXPECTED_FILES = set(FILE_NAMES.values())
ENTRY_MODULE = FILE_NAMES["entry"].removesuffix(".py")
REQUIREMENT = (
    "创建一个 FastAPI + SQLite 待办事项 CRUD 项目，包含创建、查询、更新、删除接口，"
    "API 使用 /api/v1/todos 路径，创建返回 201、查询和更新返回 200、删除返回 204、资源不存在返回 404。"
    "数据必须真实持久化到 todos.db；单元测试必须使用 TestClient 和真实临时 SQLite 数据库覆盖完整 CRUD，禁止 mock CRUD。"
    f"只需要 {', '.join(FILE_NAMES.values())} 六个文件，并严格按照职责使用这些文件名。"
)


async def main() -> int:
    mode = "renamed" if RENAMED_MODE else "standard"
    project_name = f"traditional_acceptance_{mode}_{int(time.time())}"
    output_dir = Path("/workspace/projects/1") / project_name
    token = create_access_token(sub="1", permission_level="super", expires_delta=None)
    request = {
        "requirement": REQUIREMENT,
        "project_name": project_name,
        "enable_review": False,
        "enable_validation": False,
        "enable_error_recovery": False,
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
                print(await response.aread())
                return 1
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    event = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                events.append(event)
                event_type = event.get("type")
                if event_type in {"file", "done", "error"}:
                    print(f"event={event_type} path={event.get('path', '')}")

    elapsed = time.monotonic() - started
    done_events = [event for event in events if event.get("type") == "done"]
    error_events = [event for event in events if event.get("type") == "error"]
    disk_files = {
        path.relative_to(output_dir).as_posix()
        for path in output_dir.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and not any(part.startswith(".") for part in path.relative_to(output_dir).parts)
    }
    print(f"elapsed_seconds={elapsed:.1f}")
    print(f"disk_files={sorted(disk_files)}")
    print(f"done_events={len(done_events)} error_events={len(error_events)}")
    if error_events:
        print(f"error={error_events[-1].get('data')}")
    if len(done_events) != 1:
        return 1
    if disk_files != EXPECTED_FILES:
        print(f"strict_file_set_mismatch expected={sorted(EXPECTED_FILES)}")
        return 1

    hashes = {}
    for relative_path in sorted(EXPECTED_FILES):
        path = output_dir / relative_path
        content = path.read_text(encoding="utf-8")
        ast.parse(content, filename=relative_path)
        hashes[relative_path] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    print(f"sha256={json.dumps(hashes, sort_keys=True)}")
    print("syntax=passed")
    test_file = output_dir / FILE_NAMES["test"]
    runtime = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_file), "-q"],
        cwd=output_dir,
        capture_output=True,
        text=True,
        timeout=180,
    )
    print(f"crud_test_exit_code={runtime.returncode}")
    if runtime.stdout:
        print(runtime.stdout[-2000:])
    if runtime.returncode != 0:
        if runtime.stderr:
            print(runtime.stderr[-2000:])
        return 1
    print("crud=passed")

    persistence_probe = """
import sqlite3
from fastapi.testclient import TestClient
from __ENTRY_MODULE__ import app

with TestClient(app) as client:
    created = client.post('/api/v1/todos', json={'title': 'persisted', 'description': 'probe'})
    assert created.status_code == 201, created.text
    todo_id = created.json()['id']
    fetched = client.get(f'/api/v1/todos/{todo_id}')
    assert fetched.status_code == 200, fetched.text
    updated = client.put(f'/api/v1/todos/{todo_id}', json={'title': 'updated', 'completed': True})
    assert updated.status_code == 200, updated.text

with sqlite3.connect('todos.db') as connection:
    row = connection.execute('SELECT title, completed FROM todos WHERE id = ?', (todo_id,)).fetchone()
    assert row == ('updated', 1), row

with TestClient(app) as client:
    deleted = client.delete(f'/api/v1/todos/{todo_id}')
    assert deleted.status_code == 204, deleted.text
    missing = client.get(f'/api/v1/todos/{todo_id}')
    assert missing.status_code == 404, missing.text
""".replace("__ENTRY_MODULE__", ENTRY_MODULE)
    persistence = subprocess.run(
        [sys.executable, "-c", persistence_probe],
        cwd=output_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    print(f"sqlite_persistence_exit_code={persistence.returncode}")
    if persistence.returncode != 0:
        if persistence.stdout:
            print(persistence.stdout[-2000:])
        if persistence.stderr:
            print(persistence.stderr[-2000:])
        return 1
    print("sqlite_persistence=passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
