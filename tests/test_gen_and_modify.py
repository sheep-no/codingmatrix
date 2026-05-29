#!/usr/bin/env python3
"""完整测试：生成 + 增量修改 + diff 对比"""
import asyncio, json, sys, time, os, difflib
sys.path.insert(0, "/workspace")
import httpx
from app.utils.security import create_access_token

TOKEN = create_access_token(sub="1", permission_level="super", expires_delta=None)
URL = "http://localhost:8000/api/v1/agent/orchestrate/stream"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
OUTPUT_DIR = "/tmp/test_gen_modify"

C = {
    "p": "\033[36m", "f": "\033[32m", "d": "\033[33m",
    "e": "\033[31m", "done": "\033[1;32m", "r": "\033[0m",
}

def read_files(d):
    result = {}
    if not os.path.isdir(d):
        return result
    for root, dirs, fnames in os.walk(d):
        dirs[:] = [x for x in dirs if x not in (".git","__pycache__","node_modules")]
        for f in fnames:
            fp = os.path.join(root, f)
            rel = os.path.relpath(fp, d)
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
        print(f"  {C['d']}=== DIFF: {path} ({len(diff)} hunks) ==={C['r']}")
        for dl in diff[:50]:
            if dl.startswith("+"): print(f"    \033[32m{dl.rstrip()}\033[0m")
            elif dl.startswith("-"): print(f"    \033[31m{dl.rstrip()}\033[0m")
            elif dl.startswith("@"): print(f"    \033[36m{dl.rstrip()}\033[0m")
            else: print(f"    {dl.rstrip()}")
        if len(diff) > 50:
            print(f"    ... ({len(diff)-50} more)")

def show_preview(path, content, n=8):
    lines = content.split("\n")
    print(f"  {C['f']}--- {path} ({len(lines)} lines) ---{C['r']}")
    for i, l in enumerate(lines[:n]):
        print(f"    {i+1:4d}| {l}")
    if len(lines) > n:
        print(f"    ... ({len(lines)-n} more)")

async def stream_request(req, label=""):
    """Send request and collect events"""
    events = []
    t0 = time.time()
    async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as c:
        async with c.stream("POST", URL, json=req, headers=HEADERS) as r:
            print(f"  Status: {r.status_code}")
            if r.status_code != 200:
                body = (await r.aread()).decode()
                print(f"  ERROR: {body[:300]}")
                return events
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
                        t = ev.get("type","?")
                        el = f"{time.time()-t0:.1f}s"
                        events.append(ev)

                        if t == "progress":
                            d = ev.get("data", ev)
                            step = d.get("step","")
                            fp = d.get("file_path","")
                            pct = d.get("percentage",0)
                            xtra = f" file={fp}" if fp else ""
                            print(f"    {C['p']}[{el}] {step} {pct}%{xtra}{C['r']}")
                        elif t == "file":
                            path = ev.get("path","")
                            action = ev.get("action","create")
                            content = ev.get("content","")
                            print(f"    {C['f']}[{el}] FILE {action.upper()} {path}{C['r']}")
                            show_preview(path, content)
                        elif t == "file_diff":
                            path = ev.get("path","")
                            print(f"    {C['d']}[{el}] DIFF {path}{C['r']}")
                            show_diff(path, ev.get("old_content",""), ev.get("new_content",""))
                        elif t == "error":
                            err = ev.get("data",{}).get("error","")
                            print(f"    {C['e']}[{el}] ERROR {err[:200]}{C['r']}")
                        elif t == "done":
                            d = ev.get("data", ev)
                            print(f"    {C['done']}[{el}] DONE! files={d.get('total_files_created',0)} time={d.get('elapsed_time',0):.1f}s{C['r']}")
    return events

async def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    session_id = f"test_gen_mod_{int(time.time())}"

    # Step 1: Generate
    print(f"\n{'='*60}")
    print(f"STEP 1: Generate project")
    print(f"{'='*60}")
    gen_req = {
        "requirement": "创建一个简单的待办事项 API，FastAPI + SQLite，包含增删改查。文件：main.py, app/models.py, app/routers.py",
        "session_id": session_id,
        "output_dir": OUTPUT_DIR,
        "enable_review": False,
        "enable_validation": False,
        "enable_error_recovery": False,
        "enable_memory": False,
        "spec_first": False,
        "dependency_graph": True,
    }
    await stream_request(gen_req, "GENERATE")

    before = read_files(OUTPUT_DIR)
    print(f"\n  Generated {len(before)} files:")
    for p in sorted(before):
        print(f"    {p} ({len(before[p].split(chr(10)))} lines)")

    # Step 2: Incremental modification (new session, same output_dir)
    print(f"\n{'='*60}")
    print(f"STEP 2: Incremental modification")
    print(f"{'='*60}")
    mod_session_id = f"modify_{int(time.time())}"
    mod_req = {
        "requirement": "对已有的待办事项 API 进行修改：\n1. 给 main.py 添加 CORS 中间件\n2. 给 Todo 模型添加 priority 字段\n3. 在 routers.py 添加按优先级筛选的接口",
        "session_id": mod_session_id,
        "output_dir": OUTPUT_DIR,
        "incremental": True,
        "enable_review": False,
        "enable_validation": False,
        "spec_first": False,
        "dependency_graph": True,
    }
    await stream_request(mod_req, "MODIFY")

    after = read_files(OUTPUT_DIR)

    # Step 3: Show diff
    print(f"\n{'='*60}")
    print(f"STEP 3: File diff comparison")
    print(f"{'='*60}")

    changed = 0
    for path in sorted(set(list(before.keys()) + list(after.keys()))):
        old_c = before.get(path, "")
        new_c = after.get(path, "")
        if old_c != new_c:
            changed += 1
            if not old_c:
                print(f"\n  [NEW] {path}")
                show_preview(path, new_c)
            elif not new_c:
                print(f"\n  [DELETED] {path}")
            else:
                show_diff(path, old_c, new_c)

    if changed == 0:
        print("  No files changed")

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"  Session: {session_id}")
    print(f"  Files before: {len(before)}")
    print(f"  Files after:  {len(after)}")
    print(f"  Changed:      {changed}")

asyncio.run(main())
