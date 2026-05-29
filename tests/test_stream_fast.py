#!/usr/bin/env python3
"""快速流式测试 - 实时显示 SSE 事件 + 文件预览 + diff"""
import asyncio, json, sys, time, os, difflib
sys.path.insert(0, "/workspace")
import httpx
from app.utils.security import create_access_token

TOKEN = create_access_token(sub="1", permission_level="super", expires_delta=None)
URL = "http://localhost:8000/api/v1/agent/orchestrate/stream"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

REQ = {
    "requirement": "创建一个简单的待办事项 API，使用 FastAPI + SQLite，包含增删改查接口。只需要 main.py 和 models.py 两个文件。",
    "output_dir": "/tmp/test_stream_output",
    "enable_review": False,
    "enable_validation": False,
    "enable_error_recovery": False,
    "enable_memory": False,
    "spec_first": False,
    "dependency_graph": True,
}

C = {
    "p": "\033[36m", "f": "\033[32m", "d": "\033[33m",
    "t": "\033[90m", "m": "\033[35m", "e": "\033[31m",
    "done": "\033[1;32m", "dec": "\033[1;33m", "r": "\033[0m",
}

snapshot = {}  # last known file contents on disk
OUTPUT_DIR = None

def scan_files():
    """Scan output dir for generated files"""
    if not OUTPUT_DIR or not os.path.isdir(OUTPUT_DIR):
        return {}
    result = {}
    for root, dirs, fnames in os.walk(OUTPUT_DIR):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", "node_modules", ".venv")]
        for f in fnames:
            fp = os.path.join(root, f)
            rel = os.path.relpath(fp, OUTPUT_DIR)
            try:
                with open(fp, "r") as fh:
                    result[rel] = fh.read()
            except:
                pass
    return result

def show_diff(path, old, new):
    ol = old.splitlines(keepends=True)
    nl = new.splitlines(keepends=True)
    diff = list(difflib.unified_diff(ol, nl, fromfile=f"old/{path}", tofile=f"new/{path}", lineterm=""))
    if diff:
        print(f"    {C['d']}--- DIFF {path} ---{C['r']}")
        for dl in diff[:30]:
            if dl.startswith("+"): print(f"      \033[32m{dl.rstrip()}\033[0m")
            elif dl.startswith("-"): print(f"      \033[31m{dl.rstrip()}\033[0m")
            elif dl.startswith("@"): print(f"      \033[36m{dl.rstrip()}\033[0m")
            else: print(f"      {dl.rstrip()}")
        if len(diff) > 30:
            print(f"      ... ({len(diff)-30} more)")

def show_preview(path, content, max_lines=10):
    lines = content.split("\n")
    print(f"    {C['f']}--- PREVIEW {path} ({len(lines)} lines) ---{C['r']}")
    for i, l in enumerate(lines[:max_lines]):
        print(f"      {i+1:4d}| {l}")
    if len(lines) > max_lines:
        print(f"      ... ({len(lines)-max_lines} more)")

async def main():
    global OUTPUT_DIR
    OUTPUT_DIR = "/tmp/test_stream_output"
    t0 = time.time()
    file_events = []

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
                            # Progress events are nested: {"type":"progress","data":{...}}
                            d = ev.get("data", ev)
                            step = d.get("step", "")
                            msg = d.get("message", "")
                            pct = d.get("percentage", 0)
                            cur = d.get("current", "")
                            tot = d.get("total", "")
                            fp = d.get("file_path", "")
                            extra = f" file={fp}" if fp else ""
                            print(f"  {C['p']}[{el}] PROGRESS {step} {pct}% ({cur}/{tot}){extra}{C['r']}")

                            # Detect output_dir from first file event
                            if fp and not OUTPUT_DIR:
                                # output_dir is set in the request or derived from session
                                pass

                        elif t == "file":
                            path = ev.get("path","")
                            content = ev.get("content","")
                            action = ev.get("action","create")
                            file_events.append({"path": path, "action": action, "time": el})
                            print(f"  {C['f']}[{el}] FILE {action.upper()} {path} ({len(content.split(chr(10)))} lines){C['r']}")
                            show_preview(path, content)

                        elif t == "file_diff":
                            path = ev.get("path","")
                            old_c = ev.get("old_content","")
                            new_c = ev.get("new_content","")
                            print(f"  {C['d']}[{el}] FILE_DIFF {path}{C['r']}")
                            show_diff(path, old_c, new_c)

                        elif t == "thinking":
                            agent = ev.get("agent","")
                            msg = ev.get("message","")[:200]
                            print(f"  {C['t']}[{el}] THINK[{agent}] {msg}{C['r']}")

                        elif t == "model_info":
                            model = ev.get("model","")
                            print(f"  {C['m']}[{el}] MODEL {model}{C['r']}")

                        elif t == "critical_decisions":
                            decisions = ev.get("data",{}).get("decisions",[])
                            for d in decisions[:3]:
                                print(f"  {C['dec']}[{el}] DECISION {d.get('question','')[:100]}{C['r']}")

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

                        elif t == "log":
                            msg = ev.get("data",{}).get("message","")
                            print(f"  [{el}] LOG {msg[:150]}")

                        else:
                            print(f"  [{el}] {t}: {str(ev)[:150]}")

    # After stream ends, scan output dir for files
    if OUTPUT_DIR and os.path.isdir(OUTPUT_DIR):
        print(f"\n{'='*50}")
        print(f"Files on disk in {OUTPUT_DIR}:")
        disk_files = scan_files()
        for p in sorted(disk_files):
            lines = len(disk_files[p].split("\n"))
            print(f"  {p} ({lines} lines)")

    print(f"\n{'='*50}")
    print(f"Stream events: {len(file_events)} file events")
    for fe in file_events:
        print(f"  [{fe['time']}] {fe['action']} {fe['path']}")
    print(f"Total time: {time.time()-t0:.1f}s")

asyncio.run(main())
