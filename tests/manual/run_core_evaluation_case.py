"""Run one fixed CRUD case through the production Core endpoint."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, "/workspace")

from app.agent.evaluation_matrix import FIXED_CRUD_CASES
from app.utils.security import create_access_token


DEFAULT_URL = "http://127.0.0.1:8000/api/v1/agent/orchestrate"
MAX_REPAIR_ATTEMPTS = 3


def normalize_response_errors(payload: dict[str, Any]) -> list[Any]:
    """Preserve structured endpoint failures in the evaluation summary."""
    errors = payload.get("errors") or payload.get("detail")
    if errors:
        return errors if isinstance(errors, list) else [errors]
    if payload.get("message"):
        return [{"code": payload.get("code", "HTTP_ERROR"), "message": payload["message"]}]
    return []


def build_requirement(case_id: str) -> str:
    case = next(case for case in FIXED_CRUD_CASES if case.case_id == case_id)
    files = ", ".join(case.required_files)
    return (
        f"{case.request} Use {case.language} and {case.framework}. "
        "Implement create, list, get, update, and delete at /api/v1/todos. "
        "Use a real SQLite database and include executable tests that verify persistence. "
        f"Generate exactly these files and no others: {files}. "
        "Keep every local import inside this frozen file set. For Java, make the Maven project self-contained and use the standard spring-boot Maven layout."
    )


def run_compile_check(output_dir: Path, language: str, required_files: tuple[str, ...] = ()) -> dict[str, Any]:
    """Run the local compiler check and retain bounded diagnostics."""
    if language == "python":
        command = [sys.executable, "-m", "compileall", "-q", "."]
    elif language == "java":
        command = ["mvn", "-q", "-DskipTests", "compile"]
    elif language == "typescript":
        command = ["tsc", "--noEmit", "--target", "ES2022", "--module", "NodeNext", "--moduleResolution", "NodeNext", "--experimentalDecorators", "--skipLibCheck", *required_files]
    elif language == "go":
        command = ["go", "test", "./..."]
    else:
        return {
            "passed": False,
            "supported": False,
            "command": [],
            "stdout": "",
            "stderr": "unsupported language",
        }
    try:
        completed = subprocess.run(
            command,
            cwd=output_dir,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "passed": False,
            "supported": True,
            "command": command,
            "stdout": "",
            "stderr": str(exc),
        }
    return {
        "passed": completed.returncode == 0,
        "supported": True,
        "command": command,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def check_required_files(output_dir: Path, required_files: tuple[str, ...]) -> dict[str, Any]:
    """Report missing frozen-plan files before runtime validation begins."""
    missing = [path for path in required_files if not (output_dir / path).is_file()]
    return {"passed": not missing, "missing": missing}


def run_generated_tests(output_dir: Path, required_files: tuple[str, ...], language: str = "python") -> dict[str, Any]:
    """Run the generated test suite with the project root on the import path."""
    if language == "java":
        command = ["mvn", "-q", "test"]
        test_files = [path for path in required_files if path.startswith("src/test/")]
    elif language == "go":
        command = ["go", "test", "./..."]
        test_files = [path for path in required_files if path.endswith("_test.go")]
    elif language == "typescript":
        test_files = [path for path in required_files if path.startswith(("test/", "tests/"))]
        if "src/main.ts" in required_files:
            with tempfile.TemporaryDirectory() as compiled_dir:
                compile_command = ["tsc", "--target", "ES2022", "--module", "Node16", "--moduleResolution", "Node16", "--experimentalDecorators", "--emitDecoratorMetadata", "--esModuleInterop", "--skipLibCheck", "--outDir", compiled_dir, "--rootDir", ".", *required_files]
                compiled = subprocess.run(compile_command, cwd=output_dir, capture_output=True, text=True, timeout=120, check=False)
                if compiled.returncode != 0:
                    return {"passed": False, "supported": True, "stdout": compiled.stdout[-4000:], "stderr": compiled.stderr[-4000:]}
                environment = os.environ.copy()
                environment["NODE_PATH"] = "/usr/local/lib/node_modules"
                command = ["node", str(Path(compiled_dir) / "test/todos.e2e-spec.js")]
                completed = subprocess.run(command, cwd=output_dir, env=environment, capture_output=True, text=True, timeout=120, check=False)
                return {"passed": completed.returncode == 0, "supported": True, "stdout": completed.stdout[-4000:], "stderr": completed.stderr[-4000:]}
        command = ["node", "--experimental-strip-types", *test_files]
    else:
        test_files = [path for path in required_files if path.startswith(("test/", "tests/"))]
        command = [sys.executable, "-m", "pytest", "-q", *test_files]
    if not test_files:
        return {"passed": False, "supported": True, "stdout": "", "stderr": "no test file"}
    environment = os.environ.copy()
    environment["PYTHONPATH"] = "."
    try:
        completed = subprocess.run(
            command,
            cwd=output_dir,
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"passed": False, "supported": True, "stdout": "", "stderr": str(exc)}
    return {
        "passed": completed.returncode == 0,
        "supported": True,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def run_runtime_probe(output_dir: Path, framework: str) -> dict[str, Any]:
    """Exercise health and CRUD persistence through the generated application."""
    if framework == "net/http":
        command = ["go", "run", "./cmd/server"]
        port = "3198"
        base_url = f"http://127.0.0.1:{port}"
        environment = os.environ.copy()
        environment.update({"PORT": port, "DB_PATH": "todos.db"})

        def stop_go(process: subprocess.Popen[str]) -> None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

        def wait_go(process: subprocess.Popen[str]) -> None:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"application exited with code {process.returncode}")
                try:
                    if httpx.get(f"{base_url}/health", timeout=1).status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(0.25)
            raise RuntimeError("application did not become ready")

        process = None
        with tempfile.TemporaryFile(mode="w+") as log_file:
            try:
                process = subprocess.Popen(command, cwd=output_dir, env=environment, stdout=log_file, stderr=subprocess.STDOUT, text=True)
                wait_go(process)
                created = httpx.post(f"{base_url}/api/v1/todos", json={"title": "evaluation", "description": "persist"}, timeout=5)
                todo_id = created.json().get("id") if created.status_code in (200, 201) else None
                listed = httpx.get(f"{base_url}/api/v1/todos", timeout=5)
                read = httpx.get(f"{base_url}/api/v1/todos/{todo_id}", timeout=5)
                updated = httpx.put(f"{base_url}/api/v1/todos/{todo_id}", json={"title": "updated"}, timeout=5)
                if created.status_code != 201 or listed.status_code != 200 or read.status_code != 200 or updated.status_code != 200:
                    raise RuntimeError(json.dumps({"create": created.status_code, "list": listed.status_code, "get": read.status_code, "update": updated.status_code}))
                stop_go(process)
                process = subprocess.Popen(command, cwd=output_dir, env=environment, stdout=log_file, stderr=subprocess.STDOUT, text=True)
                wait_go(process)
                persisted = httpx.get(f"{base_url}/api/v1/todos/{todo_id}", timeout=5)
                deleted = httpx.delete(f"{base_url}/api/v1/todos/{todo_id}", timeout=5)
                if persisted.status_code != 200 or persisted.json().get("title") != "updated" or deleted.status_code != 204:
                    raise RuntimeError(json.dumps({"restart_get": persisted.status_code, "delete": deleted.status_code}))
                return {"passed": True, "supported": True, "command": command, "crud_status": {"create": created.status_code, "list": listed.status_code, "get": read.status_code, "update": updated.status_code, "persisted_get": persisted.status_code, "delete": deleted.status_code}, "stdout": "", "stderr": ""}
            except (OSError, RuntimeError, ValueError, httpx.HTTPError) as exc:
                log_file.flush(); log_file.seek(0)
                return {"passed": False, "supported": True, "command": command, "stdout": log_file.read()[-4000:], "stderr": str(exc)}
            finally:
                if process is not None:
                    stop_go(process)
    if framework == "spring-boot":
        command = ["mvn", "-q", "spring-boot:run"]
        base_url = "http://127.0.0.1:8080"

        def stop(process: subprocess.Popen[str]) -> None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

        def wait_until_ready(process: subprocess.Popen[str]) -> str:
            deadline = time.monotonic() + 60
            last_error = "application did not become ready"
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"application exited with code {process.returncode}")
                for path in ("/health", "/actuator/health"):
                    try:
                        response = httpx.get(f"{base_url}{path}", timeout=1.0)
                        if response.status_code == 200:
                            return path
                        last_error = f"{path} returned HTTP {response.status_code}"
                    except httpx.HTTPError as exc:
                        last_error = str(exc)
                time.sleep(0.5)
            raise RuntimeError(last_error)

        process = None
        with tempfile.TemporaryFile(mode="w+") as log_file:
            try:
                process = subprocess.Popen(
                    command,
                    cwd=output_dir,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                health_path = wait_until_ready(process)
                created = httpx.post(
                    f"{base_url}/api/v1/todos",
                    json={"title": "evaluation", "description": "persist"},
                    timeout=5.0,
                )
                if created.status_code not in (200, 201):
                    raise RuntimeError(f"create returned HTTP {created.status_code}: {created.text[:500]}")
                todo_id = created.json().get("id")
                if todo_id is None:
                    raise RuntimeError("create response has no id")
                listed = httpx.get(f"{base_url}/api/v1/todos", timeout=5.0)
                updated = httpx.put(
                    f"{base_url}/api/v1/todos/{todo_id}",
                    json={"title": "updated", "description": "persist"},
                    timeout=5.0,
                )
                if listed.status_code != 200 or updated.status_code != 200:
                    raise RuntimeError(f"CRUD status list={listed.status_code} update={updated.status_code}")

                stop(process)
                process = subprocess.Popen(
                    command,
                    cwd=output_dir,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                wait_until_ready(process)
                persisted = httpx.get(f"{base_url}/api/v1/todos/{todo_id}", timeout=5.0)
                deleted = httpx.delete(f"{base_url}/api/v1/todos/{todo_id}", timeout=5.0)
                if persisted.status_code != 200 or deleted.status_code not in (200, 204):
                    raise RuntimeError(
                        f"persistence status get={persisted.status_code} delete={deleted.status_code}"
                    )
                return {
                    "passed": True,
                    "supported": True,
                    "command": command,
                    "health_path": health_path,
                    "crud_status": {
                        "create": created.status_code,
                        "list": listed.status_code,
                        "update": updated.status_code,
                        "persisted_get": persisted.status_code,
                        "delete": deleted.status_code,
                    },
                    "stdout": "",
                    "stderr": "",
                }
            except (OSError, RuntimeError, ValueError, httpx.HTTPError) as exc:
                log_file.flush()
                log_file.seek(0)
                return {
                    "passed": False,
                    "supported": True,
                    "command": command,
                    "stdout": log_file.read()[-4000:],
                    "stderr": str(exc),
                }
            finally:
                if process is not None:
                    stop(process)
    if framework in {"express", "nestjs"}:
        port = "3199"
        compiled_dir = None
        if framework == "nestjs":
            compiled_dir = tempfile.TemporaryDirectory()
            source_files = ["src/main.ts", "src/todos/todos.controller.ts", "src/todos/todos.service.ts"]
            compile_command = ["tsc", "--target", "ES2022", "--module", "Node16", "--moduleResolution", "Node16", "--experimentalDecorators", "--emitDecoratorMetadata", "--esModuleInterop", "--skipLibCheck", "--outDir", compiled_dir.name, "--rootDir", ".", *source_files]
            compiled = subprocess.run(compile_command, cwd=output_dir, capture_output=True, text=True, timeout=120, check=False)
            if compiled.returncode != 0:
                compiled_dir.cleanup()
                return {"passed": False, "supported": True, "command": compile_command, "stdout": compiled.stdout[-4000:], "stderr": compiled.stderr[-4000:]}
            command = ["node", str(Path(compiled_dir.name) / "src/main.js")]
        else:
            command = ["node", "--experimental-strip-types", "src/app.ts"]
        environment = os.environ.copy()
        environment.update({"PORT": port, "NODE_NO_WARNINGS": "1", "PYTHONPATH": "."})
        environment["NODE_PATH"] = "/usr/local/lib/node_modules"

        def stop_node(process: subprocess.Popen[str]) -> None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

        def wait_node(process: subprocess.Popen[str]) -> None:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"application exited with code {process.returncode}")
                try:
                    if httpx.get(f"http://127.0.0.1:{port}/health", timeout=1).status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(0.25)
            raise RuntimeError("application did not become ready")

        process = None
        with tempfile.TemporaryFile(mode="w+") as log_file:
            try:
                process = subprocess.Popen(command, cwd=output_dir, env=environment, stdout=log_file, stderr=subprocess.STDOUT, text=True)
                wait_node(process)
                base_url = f"http://127.0.0.1:{port}"
                created = httpx.post(f"{base_url}/api/v1/todos", json={"title": "evaluation", "description": "persist"}, timeout=5)
                todo_id = created.json().get("id") if created.status_code in (200, 201) else None
                listed = httpx.get(f"{base_url}/api/v1/todos", timeout=5)
                read = httpx.get(f"{base_url}/api/v1/todos/{todo_id}", timeout=5)
                updated = httpx.put(f"{base_url}/api/v1/todos/{todo_id}", json={"title": "updated"}, timeout=5)
                if created.status_code != 201 or listed.status_code != 200 or read.status_code != 200 or updated.status_code != 200:
                    raise RuntimeError(json.dumps({"create": created.status_code, "list": listed.status_code, "get": read.status_code, "update": updated.status_code}))
                stop_node(process)
                process = subprocess.Popen(command, cwd=output_dir, env=environment, stdout=log_file, stderr=subprocess.STDOUT, text=True)
                wait_node(process)
                persisted = httpx.get(f"{base_url}/api/v1/todos/{todo_id}", timeout=5)
                deleted = httpx.delete(f"{base_url}/api/v1/todos/{todo_id}", timeout=5)
                if persisted.status_code != 200 or persisted.json().get("title") != "updated" or deleted.status_code != 204:
                    raise RuntimeError(json.dumps({"restart_get": persisted.status_code, "delete": deleted.status_code}))
                return {"passed": True, "supported": True, "command": command, "crud_status": {"create": created.status_code, "list": listed.status_code, "get": read.status_code, "update": updated.status_code, "persisted_get": persisted.status_code, "delete": deleted.status_code}, "stdout": "", "stderr": ""}
            except (OSError, RuntimeError, ValueError, httpx.HTTPError) as exc:
                log_file.flush()
                log_file.seek(0)
                return {"passed": False, "supported": True, "command": command, "stdout": log_file.read()[-4000:], "stderr": str(exc)}
            finally:
                if process is not None:
                    stop_node(process)
                if compiled_dir is not None:
                    compiled_dir.cleanup()
    if framework == "flask":
        create_probe = """
import json
from app import app

with app.test_client() as client:
    headers = {"Authorization": "Bearer evaluation-token"}
    health = client.get("/health")
    created = client.post("/api/v1/todos", json={"title": "evaluation", "description": "persist"}, headers=headers)
    if created.status_code not in (200, 201):
        raise RuntimeError(f"create status={created.status_code} body={created.get_data(as_text=True)[:500]}")
    todo_id = created.get_json()["id"]
    listed = client.get("/api/v1/todos", headers=headers)
    read = client.get(f"/api/v1/todos/{todo_id}", headers=headers)
    updated = client.put(f"/api/v1/todos/{todo_id}", json={"title": "updated"}, headers=headers)
    if health.status_code != 200 or listed.status_code != 200 or read.status_code != 200 or updated.status_code != 200:
        raise RuntimeError(json.dumps({"health": health.status_code, "list": listed.status_code, "get": read.status_code, "update": updated.status_code}))
    print(json.dumps({"todo_id": todo_id, "health": health.status_code, "create": created.status_code, "list": listed.status_code, "get": read.status_code, "update": updated.status_code}))
"""
    elif framework == "fastapi":
        create_probe = """
import json
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
headers = {"Authorization": "Bearer evaluation-token"}
health = client.get("/health")
created = client.post("/api/v1/todos", json={"title": "evaluation", "description": "persist"}, headers=headers)
if created.status_code not in (200, 201):
    raise RuntimeError(f"create status={created.status_code} body={created.text[:500]}")
todo_id = created.json()["id"]
listed = client.get("/api/v1/todos", headers=headers)
read = client.get(f"/api/v1/todos/{todo_id}", headers=headers)
updated = client.put(f"/api/v1/todos/{todo_id}", json={"title": "updated"}, headers=headers)
if health.status_code != 200 or listed.status_code != 200 or read.status_code != 200 or updated.status_code != 200:
    raise RuntimeError(json.dumps({"health": health.status_code, "list": listed.status_code, "get": read.status_code, "update": updated.status_code}))
print(json.dumps({"todo_id": todo_id, "health": health.status_code, "create": created.status_code, "list": listed.status_code, "get": read.status_code, "update": updated.status_code}))
"""
    else:
        return {"passed": False, "supported": False, "error": "runtime probe unavailable"}
    environment = os.environ.copy()
    environment["PYTHONPATH"] = "."
    try:
        created = subprocess.run(
            [sys.executable, "-c", create_probe],
            cwd=output_dir,
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"passed": False, "supported": True, "stdout": "", "stderr": str(exc)}
    if created.returncode != 0:
        return {
            "passed": False,
            "supported": True,
            "stdout": created.stdout[-4000:],
            "stderr": created.stderr[-4000:],
        }
    try:
        creation_result = json.loads(created.stdout.strip().splitlines()[-1])
        environment["EVALUATION_TODO_ID"] = str(creation_result["todo_id"])
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        return {
            "passed": False,
            "supported": True,
            "stdout": created.stdout[-4000:],
            "stderr": f"invalid create probe output: {exc}",
        }
    if framework == "flask":
        restart_probe = """
import json
import os
from app import app

with app.test_client() as client:
    headers = {"Authorization": "Bearer evaluation-token"}
    todo_id = os.environ["EVALUATION_TODO_ID"]
    persisted = client.get(f"/api/v1/todos/{todo_id}", headers=headers)
    deleted = client.delete(f"/api/v1/todos/{todo_id}", headers=headers)
    payload = persisted.get_json(silent=True) or {}
    if persisted.status_code != 200 or payload.get("title") != "updated" or deleted.status_code != 204:
        raise RuntimeError(json.dumps({"restart_get": persisted.status_code, "delete": deleted.status_code, "body": persisted.get_data(as_text=True)[:500]}))
    print(json.dumps({"restart_get": persisted.status_code, "delete": deleted.status_code}))
"""
    else:
        restart_probe = """
import json
import os
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
headers = {"Authorization": "Bearer evaluation-token"}
todo_id = os.environ["EVALUATION_TODO_ID"]
persisted = client.get(f"/api/v1/todos/{todo_id}", headers=headers)
deleted = client.delete(f"/api/v1/todos/{todo_id}", headers=headers)
if persisted.status_code != 200 or persisted.json().get("title") != "updated" or deleted.status_code != 204:
    raise RuntimeError(json.dumps({"restart_get": persisted.status_code, "delete": deleted.status_code, "body": persisted.text[:500]}))
print(json.dumps({"restart_get": persisted.status_code, "delete": deleted.status_code}))
"""
    try:
        restarted = subprocess.run(
            [sys.executable, "-c", restart_probe],
            cwd=output_dir,
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"passed": False, "supported": True, "stdout": created.stdout[-4000:], "stderr": str(exc)}
    return {
        "passed": restarted.returncode == 0,
        "supported": True,
        "stdout": (created.stdout + restarted.stdout)[-4000:],
        "stderr": (created.stderr + restarted.stderr)[-4000:],
    }


def repair_generation_failure(
    url: str,
    token: str,
    request_output_dir: Path,
    case_id: str,
    failure_result: dict[str, Any],
) -> dict[str, Any]:
    """Ask the incremental Core path to repair the existing project in place."""
    case = next(case for case in FIXED_CRUD_CASES if case.case_id == case_id)
    diagnostic = failure_result.get("stderr") or failure_result.get("stdout") or "verification failed"
    requirement = (
        f"Repair the existing {case.language} {case.framework} CRUD project. "
        f"The local compiler reported:\n{diagnostic}\n"
        f"Preserve create, list, get, update, and delete at /api/v1/todos with SQLite persistence. "
        f"Modify only files in this set: "
        f"{', '.join(case.required_files)}. Re-run the compiler mentally and return complete file contents."
    )
    response = httpx.post(
        url,
        json={
            "requirement": requirement,
            "project_name": request_output_dir.name,
            "output_dir": str(request_output_dir),
            "project_path": str(request_output_dir),
            "enable_review": False,
            "enable_validation": True,
            "enable_error_recovery": True,
            "enable_memory": False,
            "spec_first": False,
            "dependency_graph": True,
            "incremental": True,
            "allowed_files": list(case.required_files),
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=900.0,
    )
    try:
        payload = response.json()
    except ValueError:
        payload = {"detail": response.text[:1000]}
    return {"http_status": response.status_code, "response": payload}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_id", choices=[case.case_id for case in FIXED_CRUD_CASES])
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--timeout", type=float, default=900.0)
    args = parser.parse_args()

    project_name = f"evaluation_{args.case_id}_{int(time.time())}"
    request_output_dir = Path("1") / project_name
    output_dir = Path("projects") / request_output_dir
    token = create_access_token(sub="1", permission_level="super", expires_delta=None)
    started = time.monotonic()
    response = httpx.post(
        args.url,
        json={
            "requirement": build_requirement(args.case_id),
            "project_name": project_name,
            "output_dir": str(request_output_dir),
            "enable_review": False,
            "enable_validation": False,
            "enable_error_recovery": False,
            "enable_memory": False,
            "spec_first": True,
            "dependency_graph": True,
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=args.timeout,
    )
    elapsed = time.monotonic() - started
    try:
        payload = response.json()
    except ValueError:
        payload = {"detail": response.text[:1000]}
    files = payload.get("files") or payload.get("generated_files") or []
    generation_succeeded = bool(payload.get("success", False))
    summary = {
        "case_id": args.case_id,
        "http_status": response.status_code,
        "success": payload.get("success", False),
        "elapsed_seconds": round(elapsed, 3),
        "output_dir": str(output_dir),
        "files": [item.get("path") for item in files if isinstance(item, dict)],
        "errors": normalize_response_errors(payload),
    }
    language = next(case.language for case in FIXED_CRUD_CASES if case.case_id == args.case_id)
    case = next(case for case in FIXED_CRUD_CASES if case.case_id == args.case_id)
    files_result = check_required_files(Path(output_dir), case.required_files)
    compile_result = run_compile_check(Path(output_dir), language, case.required_files)
    repair_attempts = []
    for _ in range(MAX_REPAIR_ATTEMPTS):
        if response.status_code != 200:
            break
        if files_result["passed"] and not compile_result.get("supported", True):
            break
        if files_result["passed"] and compile_result["passed"]:
            break
        if not files_result["passed"]:
            compile_result = {
                "passed": False,
                "supported": True,
                "command": [],
                "stdout": "",
                "stderr": f"missing required files: {', '.join(files_result['missing'])}",
            }
        repair_result = repair_generation_failure(
            args.url,
            token,
            request_output_dir,
            args.case_id,
            compile_result,
        )
        repair_attempts.append({"compile": compile_result, "repair": repair_result})
        if repair_result["http_status"] != 200 or not repair_result["response"].get("success", False):
            break
        generation_succeeded = True
        repaired_files = repair_result["response"].get("files") or repair_result["response"].get("generated_files") or []
        if repaired_files:
            summary["files"] = [item.get("path") for item in repaired_files if isinstance(item, dict)]
        files_result = check_required_files(Path(output_dir), case.required_files)
        compile_result = run_compile_check(Path(output_dir), language, case.required_files)
    summary["files_complete"] = files_result
    summary["compile"] = compile_result
    tests_result = run_generated_tests(Path(output_dir), case.required_files, language) if files_result["passed"] else {"passed": False, "stderr": "required files missing"}
    runtime_result = run_runtime_probe(Path(output_dir), case.framework) if files_result["passed"] else {"passed": False, "stderr": "required files missing"}
    while (
        response.status_code == 200
        and files_result["passed"]
        and compile_result["passed"]
        and not (tests_result["passed"] and runtime_result["passed"])
        and len(repair_attempts) < MAX_REPAIR_ATTEMPTS
    ):
        verification_failure = {
            "passed": False,
            "stdout": "\n".join(
                value for value in (tests_result.get("stdout", ""), runtime_result.get("stdout", "")) if value
            ),
            "stderr": "\n".join(
                value for value in (tests_result.get("stderr", ""), runtime_result.get("stderr", "")) if value
            ),
        }
        repair_result = repair_generation_failure(
            args.url,
            token,
            request_output_dir,
            args.case_id,
            verification_failure,
        )
        repair_attempts.append({"verification": verification_failure, "repair": repair_result})
        if repair_result["http_status"] != 200 or not repair_result["response"].get("success", False):
            break
        generation_succeeded = True
        repaired_files = repair_result["response"].get("files") or repair_result["response"].get("generated_files") or []
        if repaired_files:
            summary["files"] = [item.get("path") for item in repaired_files if isinstance(item, dict)]
        files_result = check_required_files(Path(output_dir), case.required_files)
        compile_result = run_compile_check(Path(output_dir), language, case.required_files)
        tests_result = run_generated_tests(Path(output_dir), case.required_files, language)
        runtime_result = run_runtime_probe(Path(output_dir), case.framework)
    summary["files_complete"] = files_result
    summary["compile"] = compile_result
    summary["repair_attempts"] = repair_attempts
    summary["tests"] = tests_result
    summary["runtime"] = runtime_result
    summary["tests_passed"] = tests_result["passed"]
    summary["startup_passed"] = runtime_result["passed"]
    summary["persistence_passed"] = runtime_result["passed"]
    summary["success"] = bool(generation_succeeded and compile_result["passed"] and tests_result["passed"] and runtime_result["passed"])
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if response.status_code == 200 and summary["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
