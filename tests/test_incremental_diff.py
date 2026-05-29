#!/usr/bin/env python3
"""增量修改测试 - 测试 diff 和文件预览"""
import asyncio, json, sys, time, os, difflib
sys.path.insert(0, "/workspace")
import httpx
from app.utils.security import create_access_token

TOKEN = create_access_token(sub="1", permission_level="super", expires_delta=None)
URL = "http://localhost:8000/api/v1/agent/orchestrate/stream"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
OUTPUT_DIR = "/tmp/test_stream_output"

C = {
    "p": "\033[36m", "f": "\033[32m", "d": "\033[33m",
    "t": "\033[90m", "m": "\033[35m", "e": "\033[31m",
    "done": "\033[1;32m", "r": "\033[0m",
}

def read_files():
    result = {}
    for root, dirs, fnames in os.walk(OUTPUT_DIR):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "node_modules")]
        for f in fnames:
            fp = os.path.join(root, f)
            rel = os.path.relpath(fp, OUTPUT_DIR)
            try:
                with open(fp) as fh:
                    result[rel] = fh.read()
            except:
                pass
    return result

def show_diff(path, old, new):
    ol = old.splitlines(keepends=True)
    nl = new.splitlines(keepends=True)
    diff = list(difflib.unified_diff(ol, nl, fromfile=f"BEFORE/{path}", tofile=f"AFTER/{path}", lineterm=""))
    if diff:
        print(f"  {C['d']}=== DIFF: {path} ({len(diff)} lines) ==={C['r']}")
        for dl in diff[:40]:
            if dl.startswith("+"): print(f"    \033[32m{dl.rstrip()}\033[0m")
            elif dl.startswith("-"): print(f"    \033[31m{dl.rstrip()}\033[0m")
            elif dl.startswith("@"): print(f"    \033[36m{dl.rstrip()}\033[0m")
            else: print(f"    {dl.rstrip()}")
        if len(diff) > 40:
            print(f"    ... ({len(diff)-40} more)")

def show_preview(path, content, max_lines=12):
    lines = content.split("\n")
    print(f"  {C['f']}=== PREVIEW: {path} ({len(lines)} lines) ==={C['r']}")
    for i, l in enumerate(lines[:max_lines]):
        print(f"    {i+1:4d}| {l}")
    if len(lines) > max_lines:
        print(f"    ... ({len(lines)-max_lines} more)")

async def main():
    t0 = time.time()
    before = read_files()
    print(f"Files BEFORE modification: {len(before)}")
    for p in sorted(before):
        print(f"  {p} ({len(before[p].split(chr(10)))} lines)")

    # First, get the session ID from the previous run
    session_id = None
    for d in sorted(os.listdir("/workspace/projects/orchestrator/"), reverse=True):
        if d.startswith("project_1_"):
            session_id = d
            break

    REQ = {
        "requirement": "对已有的待办事项 API 进行增量修改：\n1. 给 main.py 添加 CORS 中间件支持\n2. 给 models.py 的 Todo 模型添加 priority 字段（low/medium/high）\n3. 在 routers.py 中添加按优先级筛选的接口",
        "session_id": session_id,
        "output_dir": OUTPUT_DIR,
        "incremental": True,
        "enable_review": False,
        "enable_validation": False,
        "spec_first": False,
        "dependency_graph": True,
    }

    print(f"\n{'='*60}")
    print(f"Starting incremental modification...")
    print(f"Session: {session_id}")
    print(f"{'='*60}\n")

    async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as c:
        async with c.stream("POST", URL, json=REQ, headers=HEADERS) as r:
            print(f"Status: {r.status_code}\n")
            buf = ""
            async for chunk in r.aiter_text():
                buf += chunk
                while "\n\n" in buf:
                    raw, buf = buf.split("\n\n", 1)
                    for line in raw.split("\n"):
                        if not line.startswith("data: "):
                            continue
                        try:
                            ev = json.loads(line[6:])
                        except:
                            continue

                        t = ev.get("type", "?")
                        el = f"{time.time()-t0:.1f}s"

                        if t == "progress":
                            d = ev.get("data", ev)
                            step = d.get("step", "")
                            fp = d.get("file_path", "")
                            extra = f" file={fp}" if fp else ""
                            print(f"  {C['p']}[{el}] {step}{extra}{C['r']}")

                        elif t == "file_diff":
                            path = ev.get("path","")
                            old_c = ev.get("old_content","")
                            new_c = ev.get("new_content","")
                            print(f"\n  {C['d']}[{el}] FILE_DIFF {path}{C['r']}")
                            show_diff(path, old_c, new_c)

                        elif t == "file":
                            path = ev.get("path","")
                            content = ev.get("content","")
                            action = ev.get("action","create")
                            print(f"\n  {C['f']}[{el}] FILE {action.upper()} {path}{C['r']}")
                            show_preview(path, content)

                        elif t == "error":
                            err = ev.get("data",{}).get("error","") or str(ev)
                            print(f"  {C['e']}[{el}] ERROR {err[:200]}{C['r']}")

                        elif t == "done":
                            d = ev.get("data", ev)
                            print(f"\n  {C['done']}{'='*50}")
                            print(f"  [{el}] DONE!")
                            for k in ("total_files_created","total_files","elapsed_time","success"):
                                if k in d:
                                    print(f"    {k}: {d[k]}")
                            print(f"  {C['r']}")

                        else:
                            pass  # skip other events

    # After modification, show diff
    after = read_files()
    print(f"\n{'='*60}")
    print(f"COMPARISON: Before vs After")
    print(f"{'='*60}")

    for path in sorted(set(list(before.keys()) + list(after.keys()))):
        old_c = before.get(path, "")
        new_c = after.get(path, "")
        if old_c != new_c:
            if not old_c:
                print(f"\n  NEW FILE: {path}")
                show_preview(path, new_c)
            elif not new_c:
                print(f"\n  DELETED: {path}")
            else:
                show_diff(path, old_c, new_c)

    print(f"\nTotal time: {time.time()-t0:.1f}s")

asyncio.run(main())
