"""Generate and smoke-test a Pygame Snake game through the Core endpoint."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, "/workspace")

from app.utils.security import create_access_token


URL = "http://127.0.0.1:8000/api/v1/agent/orchestrate"
REQUIRED_FILES = (
    "main.py",
    "game/rules.py",
    "game/renderer.py",
    "game/input_loop.py",
    "tests/test_game.py",
)


def main() -> int:
    project_name = f"evaluation_pygame-snake_{int(time.time())}"
    requested_output_dir = Path("projects/1") / project_name
    requirement = (
        "Generate a playable Pygame Snake game in Python. "
        "The game SHALL render a visible 640x480 window with a snake, food, score, and grid. "
        "The game SHALL process keyboard direction input, food consumption, wall collision, "
        "self collision, restart, and quit events. "
        "The game SHALL support --headless --frames N and --screenshot PATH for deterministic smoke testing. "
        "Keep game rules independent from rendering and provide executable tests for movement, "
        "food consumption, collision, headless startup, and screenshot creation. "
        f"Generate exactly these files and no others: {', '.join(REQUIRED_FILES)}."
    )
    token = create_access_token(sub="1", permission_level="super", expires_delta=None)
    response = httpx.post(
        URL,
        json={
            "requirement": requirement,
            "project_name": project_name,
            "output_dir": str(requested_output_dir),
            "enable_review": False,
            "enable_validation": False,
            "enable_error_recovery": False,
            "enable_memory": False,
            "spec_first": True,
            "dependency_graph": True,
            "allowed_files": list(REQUIRED_FILES),
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=1200,
    )
    payload = response.json()
    output_dir = Path(payload.get("output_dir") or requested_output_dir)
    prefixed_output_dir = Path("projects") / output_dir
    if not output_dir.exists() and prefixed_output_dir.exists():
        output_dir = prefixed_output_dir
    missing = [path for path in REQUIRED_FILES if not (output_dir / path).is_file()]
    environment = os.environ.copy()
    environment.update({"SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy", "PYTHONPATH": "."})
    compile_result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", "."],
        cwd=output_dir,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    ) if not missing else None
    tests_result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_game.py"],
        cwd=output_dir,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    ) if not missing and compile_result and compile_result.returncode == 0 else None
    screenshot = output_dir / "snake-effect.png"
    smoke_result = subprocess.run(
        [sys.executable, "main.py", "--headless", "--frames", "3", "--screenshot", str(screenshot.resolve())],
        cwd=output_dir,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    ) if not missing and compile_result and compile_result.returncode == 0 else None
    result = {
        "case_id": "pygame-snake",
        "http_status": response.status_code,
        "generation_success": bool(payload.get("success")),
        "output_dir": str(output_dir),
        "files_complete": not missing,
        "missing": missing,
        "compile_passed": bool(compile_result and compile_result.returncode == 0),
        "tests_passed": bool(tests_result and tests_result.returncode == 0),
        "headless_smoke_passed": bool(smoke_result and smoke_result.returncode == 0 and screenshot.is_file()),
        "screenshot": str(screenshot) if screenshot.is_file() else None,
        "stdout": "\n".join(
            item.stdout[-2000:] for item in (tests_result, smoke_result) if item is not None
        ),
        "stderr": "\n".join(
            item.stderr[-2000:] for item in (compile_result, tests_result, smoke_result) if item is not None
        ),
    }
    result["success"] = all(
        (result["http_status"] == 200, result["generation_success"], result["files_complete"],
         result["compile_passed"], result["tests_passed"], result["headless_smoke_passed"])
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
