"""Run one fixed CRUD case through the production Core endpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, "/workspace")

from app.agent.evaluation_matrix import (
    EvaluationCase,
    EvaluationRecord,
    FIXED_CRUD_CASES,
    FIXED_EVALUATION_MATRIX,
)
from app.utils.security import create_access_token
from app.agent.code_synthesis_contracts import HttpContract


DEFAULT_URL = "http://127.0.0.1:8000/api/v1/agent/orchestrate"
MAX_REPAIR_ATTEMPTS = 3
MAX_REQUIREMENT_CHARS = 5000


@dataclass(frozen=True)
class CoreEvaluationCase(EvaluationCase):
    runtime: str = ""
    routes: tuple[tuple[str, str, int], ...] = ()


# These HTTP fixtures belong to the evaluator, not the production gate.
CORE_EVALUATION_CASES = tuple(
    CoreEvaluationCase(
        **{**asdict(case), "http_contracts": tuple(
            HttpContract(
                method=method, path=path, status_code=status,
                request_body_schema={"type": "object"},
                serialization_guidance=(
                    "HTTP JSON bodies must be JSON-serializable values. Convert model instances "
                    "using the serializer supported by the installed framework/version "
                    "before passing them to a client's JSON body parameter. For Pydantic v2 "
                    "use model_dump(mode='json'); for v1 use dict() for JSON-native fields "
                    "or a JSON-mode encoder for dates, UUIDs and other custom types."
                ),
            )
            for method, path, status in (
                ("POST", "/api/v1/todos", 201),
                ("PUT", "/api/v1/todos/{todo_id}", 200),
            )
        )},
        runtime={"python": "python", "typescript": "node", "go": "go", "java": "jvm"}[case.language],
        routes=(
            ("GET", "/health", 200),
            ("POST", "/api/v1/todos", 201),
            ("GET", "/api/v1/todos", 200),
            ("GET", "/api/v1/todos/{todo_id}", 200),
            ("PUT", "/api/v1/todos/{todo_id}", 200),
            ("DELETE", "/api/v1/todos/{todo_id}", 204),
        ),
    )
    for case in (*FIXED_EVALUATION_MATRIX, *FIXED_CRUD_CASES)
)


def build_case_contract(case: CoreEvaluationCase) -> dict[str, Any]:
    routes = {
        (method, path): {"method": method, "path": path, "status_code": status_code}
        for method, path, status_code in case.routes
    }
    for contract in case.http_contracts:
        key = (contract.method, contract.path)
        routes[key] = {
            **routes.get(key, {}),
            **contract.model_dump(mode="json", exclude_unset=True),
        }
    return {
        "framework": case.framework,
        "runtime": case.runtime,
        "contracts": {
            "routes": list(routes.values()),
        },
    }


def normalize_response_errors(payload: dict[str, Any]) -> list[Any]:
    """Preserve structured endpoint failures in the evaluation summary."""
    errors = payload.get("errors") or payload.get("detail")
    if errors:
        return errors if isinstance(errors, list) else [errors]
    if payload.get("message"):
        return [{"code": payload.get("code", "HTTP_ERROR"), "message": payload["message"]}]
    return []


def get_case(case_id: str) -> CoreEvaluationCase:
    return next(
        case
        for case in CORE_EVALUATION_CASES
        if case.case_id == case_id
    )


def build_requirement(case_id: str) -> str:
    case = get_case(case_id)
    files = ", ".join(case.required_files)
    fixture_contract = " ".join(case.contract_instructions)
    routes = "; ".join(
        f"{route['method']} {route['path']}"
        + (f" returning HTTP {route['status_code']}" if "status_code" in route else "")
        for route in build_case_contract(case)["contracts"]["routes"]
    )
    return (
        f"{case.request} Build a {case.file_scale} project using {case.language} and {case.framework}. "
        f"Expose these routes: {routes}. Initialize the SQLite schema when the application starts. "
        "Use a real SQLite database and include executable tests that verify persistence. "
        f"Generate exactly these files and no others: {files}. "
        "Keep every local import inside this frozen file set. For Java, make the Maven project self-contained and use the standard spring-boot Maven layout. "
        f"Fixture contract v{case.contract_version}: {fixture_contract}"
    )


def run_compile_check(output_dir: Path, language: str, required_files: tuple[str, ...] = ()) -> dict[str, Any]:
    """Run the local compiler check and retain bounded diagnostics."""
    if language == "python":
        command = [sys.executable, "-m", "compileall", "-q", "."]
    elif language == "java":
        command = (
            ["javac", *required_files]
            if required_files and "pom.xml" not in required_files
            else ["mvn", "-q", "-DskipTests", "compile"]
        )
    elif language == "typescript":
        command = ["tsc", "--noEmit", "--target", "ES2022", "--module", "NodeNext", "--moduleResolution", "NodeNext", "--experimentalDecorators", "--skipLibCheck", *required_files]
    elif language == "go":
        command = ["go", "test", "./..."] if "go.mod" in required_files else ["go", "test", *required_files]
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


def run_generated_tests(
    output_dir: Path,
    required_files: tuple[str, ...],
    language: str = "python",
    framework: str = "",
) -> dict[str, Any]:
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
        return run_runtime_probe(output_dir, framework, required_files)
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


def run_runtime_probe(
    output_dir: Path,
    framework: str,
    required_files: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Exercise health and CRUD persistence through the generated application."""
    if framework == "net/http":
        command = ["go", "run", "./cmd/server"] if "cmd/server/main.go" in required_files else ["go", "run", "main.go"]
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
            entrypoint = "src/app.ts" if "src/app.ts" in required_files else "src/index.ts"
            command = ["node", "--experimental-strip-types", entrypoint]
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
        module_name = "app.main" if "app/main.py" in required_files else "main"
        create_probe = """
import json
from fastapi.testclient import TestClient
from MODULE_NAME import app

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
""".replace("MODULE_NAME", module_name)
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
        module_name = "app.main" if "app/main.py" in required_files else "main"
        restart_probe = """
import json
import os
from fastapi.testclient import TestClient
from MODULE_NAME import app

client = TestClient(app)
headers = {"Authorization": "Bearer evaluation-token"}
todo_id = os.environ["EVALUATION_TODO_ID"]
persisted = client.get(f"/api/v1/todos/{todo_id}", headers=headers)
deleted = client.delete(f"/api/v1/todos/{todo_id}", headers=headers)
if persisted.status_code != 200 or persisted.json().get("title") != "updated" or deleted.status_code != 204:
    raise RuntimeError(json.dumps({"restart_get": persisted.status_code, "delete": deleted.status_code, "body": persisted.text[:500]}))
print(json.dumps({"restart_get": persisted.status_code, "delete": deleted.status_code}))
""".replace("MODULE_NAME", module_name)
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
    case_id: str,
    failure_result: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    """Ask the incremental Core path to repair the existing project in place."""
    from app.api.v1.ai_agent.project_config import PROJECTS_BASE_DIR

    target = output_dir.resolve()
    try:
        repair_path = target.relative_to(Path(PROJECTS_BASE_DIR).resolve())
    except ValueError as exc:
        raise ValueError("repair target must be inside PROJECTS_BASE_DIR") from exc
    if repair_path == Path("."):
        raise ValueError("repair target must be a project directory")
    case = get_case(case_id)
    diagnostic_sections = failure_result.get("diagnostics") or ()
    diagnostic = "\n".join(
        str(section) for section in diagnostic_sections if section
    )
    if not diagnostic:
        diagnostic = "\n".join(
            str(value)
            for value in (failure_result.get("stdout"), failure_result.get("stderr"))
            if value
        )
    diagnostic = (diagnostic or "verification failed")[-6000:]
    requirement_prefix = (
        f"Repair the existing project against this unchanged fixture contract:\n{build_requirement(case_id)}\n"
        "Verification evidence from the current candidate:\n"
    )
    requirement_suffix = (
        "\nTreat every reported validation stage as evidence, restore cross-file consistency, "
        "Failed incremental candidates may have been rolled back; apply the latest candidate diagnostics "
        "to the current disk baseline and avoid reproducing the failed candidate. "
        "Return complete file contents for the declared change set."
    )
    diagnostic_budget = max(
        MAX_REQUIREMENT_CHARS - len(requirement_prefix) - len(requirement_suffix),
        0,
    )
    bounded_diagnostic = diagnostic[-diagnostic_budget:] if diagnostic_budget else ""
    requirement = requirement_prefix + bounded_diagnostic + requirement_suffix
    requirement = requirement[:MAX_REQUIREMENT_CHARS]
    response = httpx.post(
        url,
        json={
            **build_case_contract(case),
            "engine": "core",
            "requirement": requirement,
            "project_name": target.name,
            "output_dir": repair_path.as_posix(),
            "project_path": repair_path.as_posix(),
            "enable_review": False,
            "enable_validation": True,
            "enable_error_recovery": True,
            "enable_memory": False,
            "enable_skills": False,
            "spec_first": case.strategy == "spec_first",
            "dependency_graph": True,
            "incremental": True,
            "allowed_files": list(case.required_files),
            "change_plan": build_repair_change_plan(
                output_dir,
                case.required_files,
                failure_result,
            ),
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=900.0,
    )
    try:
        payload = response.json()
    except ValueError:
        payload = {"detail": response.text[:1000]}
    return {"http_status": response.status_code, "response": payload}


def build_repair_change_plan(
    output_dir: Path,
    required_files: tuple[str, ...],
    failure_result: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Build a repair plan from missing artifacts and path-scoped diagnostics."""
    # Preserve line boundaries when matching paths in serialized diagnostics.
    diagnostics = json.dumps(failure_result or {}, ensure_ascii=False).replace(r"\n", "\n")
    mentioned_paths = {
        path
        for path in required_files
        if re.search(rf"(?<![A-Za-z0-9_./-]){re.escape(path)}(?![A-Za-z0-9_./-])", diagnostics)
    }
    missing_paths = {path for path in required_files if not (output_dir / path).is_file()}
    selected_paths = mentioned_paths | missing_paths
    semantic_failure = any(
        scope in diagnostics
        for scope in ("[tests]", "[runtime]", "tests", "runtime")
    )
    if semantic_failure:
        # Tests and runtime probes exercise the whole application contract. Repairing
        # only the reported leaf file leaves stale imports, schemas, or persistence
        # code in place and causes the next attempt to fail on a different layer.
        selected_paths.update(required_files)
    if failure_result is None or not selected_paths:
        selected_paths = set(required_files)
    return [
        {
            "path": path,
            "action": "modify" if (output_dir / path).is_file() else "add",
            "reason": "repair generated project after evaluator verification failure",
        }
        for path in required_files
        if path in selected_paths
    ]


def _verify_case(output_dir: Path, case: EvaluationCase) -> dict[str, Any]:
    files = check_required_files(output_dir, case.required_files)
    compile_result = run_compile_check(output_dir, case.language, case.required_files)
    if files["passed"]:
        tests = run_generated_tests(
            output_dir, case.required_files, case.language, case.framework
        )
        runtime = run_runtime_probe(output_dir, case.framework, case.required_files)
    else:
        missing = f"required files missing: {', '.join(files['missing'])}"
        tests = {"passed": False, "supported": True, "stderr": missing}
        runtime = {"passed": False, "supported": True, "stderr": missing}
    return {
        "files_complete": files,
        "compile": compile_result,
        "tests": tests,
        "runtime": runtime,
        "passed": bool(
            files["passed"]
            and compile_result["passed"]
            and tests["passed"]
            and runtime["passed"]
        ),
    }


def _failure_diagnostic(verification: dict[str, Any]) -> dict[str, Any]:
    failed = [
        (key, result)
        for key, result in verification.items()
        if key in {"files_complete", "compile", "tests", "runtime"}
        and isinstance(result, dict)
        and not result.get("passed", False)
    ]
    diagnostics = []
    for scope, result in failed:
        details = []
        if result.get("missing"):
            details.append(f"missing={result['missing']}")
        if result.get("stdout"):
            details.append(f"stdout:\n{str(result['stdout'])[-3000:]}")
        if result.get("stderr"):
            details.append(f"stderr:\n{str(result['stderr'])[-3000:]}")
        diagnostics.append(f"[{scope}]\n" + ("\n".join(details) or "verification failed"))
    return {
        "passed": False,
        "diagnostics": diagnostics,
        "stdout": "\n".join(str(item.get("stdout", "")) for _, item in failed if item.get("stdout")),
        "stderr": "\n".join(
            str(item.get("stderr") or item.get("missing") or "verification failed")
            for _, item in failed
        ),
    }


def _metrics(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("generation_metrics") or {}
    return {
        "model_call_count": int(value.get("model_call_count") or 0),
        "token_count": int(value.get("token_count") or 0),
        "node_attempts": {
            str(path): int(attempts)
            for path, attempts in (value.get("node_attempts") or {}).items()
        },
    }


def _repair_failure(payload: dict[str, Any], verification: dict[str, Any]) -> dict[str, Any]:
    """Prefer candidate evidence captured before the incremental rollback."""
    feedback = payload.get("repair_feedback") or {}
    diagnostics = feedback.get("diagnostics") or []
    if not payload.get("success", False) and diagnostics:
        return {
            "passed": False,
            "source": "core_candidate",
            "diagnostics": [json.dumps(item, ensure_ascii=False, sort_keys=True) for item in diagnostics],
        }
    failure = _failure_diagnostic(verification)
    if not failure["diagnostics"] and not payload.get("success", False):
        failure["diagnostics"] = [str(item) for item in normalize_response_errors(payload)] or ["generation failed"]
    return {**failure, "source": "disk_verification"}


def _failure_fingerprint(failure: dict[str, Any]) -> str:
    text = "\n".join(failure["diagnostics"])
    # Timing and object addresses change between equivalent runtime failures.
    text = re.sub(r"\b\d+(?:\.\d+)?\s*(?:seconds?|ms|s)\b", "<duration>", text)
    text = re.sub(r"0x[0-9a-fA-F]+", "<address>", text)
    text = re.sub(r'("attempts"\s*:\s*)\d+', r"\1<count>", text)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def evaluation_status(summary: dict[str, Any]) -> str:
    """Classify transport and service setup failures separately from quality failures."""
    if summary.get("http_status") in {401, 403, 404, 502, 503, 504}:
        return "evaluation_infrastructure_failure"
    return "completed"


def record_from_summary(summary: dict[str, Any]) -> EvaluationRecord:
    """Project one real case result onto the stable report contract."""
    verification = summary["verification"]
    expected_files = set(summary["required_files"])
    project_files = set(summary["project_files"])
    runtime = verification["runtime"]
    persistence_diagnostic = runtime.get("stderr") or runtime.get("error") or ""
    return EvaluationRecord(
        case_id=summary["case_id"],
        plan_consistent=summary["http_status"] == 200 and project_files == expected_files,
        interfaces_consistent=bool(verification["tests"]["passed"] and runtime["passed"]),
        dependency_closure=bool(verification["compile"]["passed"]),
        files_complete=bool(verification["files_complete"]["passed"]),
        compile_passed=bool(verification["compile"]["passed"]),
        tests_passed=bool(verification["tests"]["passed"]),
        startup_passed=bool(runtime["passed"]),
        persistence_passed=bool(runtime["passed"]),
        token_count=summary["token_count"],
        elapsed_seconds=summary["elapsed_seconds"],
        database_diagnostics=(str(persistence_diagnostic),) if persistence_diagnostic else (),
        model_call_count=summary["model_call_count"],
        strategy=summary["strategy"],
        file_scale=summary["file_scale"],
        first_passed=summary["first_passed"],
        candidate_passed=summary["candidate_passed"],
        repaired_passed=summary["repaired_passed"],
        evaluation_status=evaluation_status(summary),
    )


def run_case(case_id: str, *, url: str = DEFAULT_URL, timeout: float = 900.0) -> dict[str, Any]:
    case = get_case(case_id)
    timestamp = str(int(time.time()))
    name_prefix = f"evaluation_{case_id}_"
    project_name = f"{name_prefix[:50 - len(timestamp) - 1]}_{timestamp}"
    request_output_dir = Path("1") / project_name
    output_dir = Path("projects") / request_output_dir
    token = create_access_token(sub="1", permission_level="super", expires_delta=None)
    started = time.monotonic()
    response = httpx.post(
        url,
        json={
            **build_case_contract(case),
            "engine": "core",
            "requirement": build_requirement(case_id),
            "project_name": project_name,
            "output_dir": str(request_output_dir),
            "enable_review": False,
            "enable_validation": False,
            "enable_error_recovery": False,
            "enable_memory": False,
            "enable_skills": False,
            "spec_first": case.strategy == "spec_first",
            "dependency_graph": True,
            "allowed_files": list(case.required_files),
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
    )
    try:
        payload = response.json()
    except ValueError:
        payload = {"detail": response.text[:1000]}
    files = payload.get("files") or payload.get("generated_files") or []
    generation_succeeded = bool(payload.get("success", False))
    initial_metrics = _metrics(payload)
    model_call_count = initial_metrics["model_call_count"]
    token_count = initial_metrics["token_count"]
    output_dir = Path(payload.get("output_dir") or output_dir)
    summary = {
        "case_id": case_id,
        "strategy": case.strategy,
        "file_scale": case.file_scale,
        "required_files": list(case.required_files),
        "http_status": response.status_code,
        "success": payload.get("success", False),
        "output_dir": str(output_dir),
        "files": [item.get("path") for item in files if isinstance(item, dict)],
        "errors": normalize_response_errors(payload),
        "generation_metrics": initial_metrics,
    }
    verification = _verify_case(output_dir, case)
    candidate_passed = bool(generation_succeeded and verification["passed"])
    node_attempts = initial_metrics["node_attempts"]
    first_passed = bool(
        candidate_passed
        and node_attempts
        and set(node_attempts) == set(case.required_files)
        and all(attempts == 1 for attempts in node_attempts.values())
    )
    repair_attempts = []
    failure = _repair_failure(payload, verification)
    seen_failures = {_failure_fingerprint(failure)}
    initial_candidate = (payload.get("repair_feedback") or {}).get("candidate_fingerprint")
    seen_candidates = {initial_candidate} if initial_candidate else set()
    stop_reason = "passed" if candidate_passed else "budget_exhausted"
    if response.status_code != 200:
        stop_reason = "http_error"
    while response.status_code == 200 and not (generation_succeeded and verification["passed"]) and len(repair_attempts) < MAX_REPAIR_ATTEMPTS:
        repair_result = repair_generation_failure(
            url,
            token,
            case_id,
            failure,
            output_dir,
        )
        repair_payload = repair_result["response"]
        repair_metrics = _metrics(repair_payload)
        model_call_count += repair_metrics["model_call_count"]
        token_count += repair_metrics["token_count"]
        repair_attempts.append({
            "attempt": len(repair_attempts) + 1,
            "input_failure": failure,
            "verification": verification,
            "repair": repair_result,
            "generation_metrics": repair_metrics,
        })
        repaired_files = repair_payload.get("files") or repair_payload.get("generated_files") or []
        summary["files"] = [item.get("path") for item in repaired_files if isinstance(item, dict)]
        if repair_result["http_status"] != 200:
            generation_succeeded = False
            stop_reason = "http_error"
            break
        verification = _verify_case(output_dir, case)
        generation_succeeded = bool(repair_payload.get("success", False))
        failure = _repair_failure(repair_payload, verification)
        repair_attempts[-1]["result_verification"] = verification
        repair_attempts[-1]["result_failure"] = failure
        if generation_succeeded and verification["passed"]:
            stop_reason = "passed"
            break
        fingerprint = _failure_fingerprint(failure)
        candidate = (repair_payload.get("repair_feedback") or {}).get("candidate_fingerprint")
        if candidate and candidate in seen_candidates:
            stop_reason = "no_progress_repeated_candidate"
            break
        if fingerprint in seen_failures:
            stop_reason = "no_progress_repeated_diagnostic"
            break
        seen_failures.add(fingerprint)
        if candidate:
            seen_candidates.add(candidate)
    repaired_passed = bool(generation_succeeded and verification["passed"])
    summary["verification"] = verification
    summary["repair_attempts"] = repair_attempts
    summary["repair_stop_reason"] = stop_reason
    summary["latest_failure"] = failure if not repaired_passed else None
    summary["first_passed"] = first_passed
    summary["candidate_passed"] = candidate_passed
    summary["repaired_passed"] = repaired_passed
    summary["model_call_count"] = model_call_count
    summary["token_count"] = token_count
    summary["elapsed_seconds"] = round(time.monotonic() - started, 3)
    summary["success"] = repaired_passed
    ignored_directories = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "target", "dist", "build"}
    project_files = []
    for root, directories, filenames in os.walk(output_dir):
        directories[:] = [name for name in directories if name not in ignored_directories]
        for filename in filenames:
            path = (Path(root) / filename).relative_to(output_dir).as_posix()
            if path in case.required_files or not (
                filename.endswith((".pyc", ".class", ".db", ".db-wal", ".db-shm", ".sqlite", ".sqlite3"))
                or filename == ".coverage"
                or path == ".dep_graph.json"
            ):
                project_files.append(path)
    summary["project_files"] = sorted(project_files)
    summary["record"] = asdict(record_from_summary(summary))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    case_ids = [case.case_id for case in (*FIXED_EVALUATION_MATRIX, *FIXED_CRUD_CASES)]
    parser.add_argument("case_id", choices=case_ids)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--timeout", type=float, default=900.0)
    args = parser.parse_args()

    summary = run_case(args.case_id, url=args.url, timeout=args.timeout)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["http_status"] == 200 and summary["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
