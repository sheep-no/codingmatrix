"""轻量单文件生成流程。"""

import os
import re
import resource
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from app.agent.dynamic_model_router import get_dynamic_router
from app.agent.utils import clean_code_block, validate_syntax_for_extension
from app.utils.aicloud.llm_caller import call_llm


_LANGUAGE_EXTENSIONS = {
    "python": ".py",
    "python3": ".py",
    "javascript": ".js",
    "js": ".js",
    "typescript": ".ts",
    "ts": ".ts",
}
_EXPLICIT_FILE_RE = re.compile(r"\b([A-Za-z0-9_-]+\.(?:py|pyw|js|mjs|ts))\b")
_SIMPLE_REQUEST_RE = re.compile(r"(?:写|创建|生成)\s*(?:一个|一份)?")


def infer_single_file_request(requirement: str) -> dict[str, str] | None:
    """识别明确的单文件请求并推断语言、文件名和项目名。"""
    if not _SIMPLE_REQUEST_RE.search(requirement):
        return None
    if re.search(r"项目|系统|应用|网站|多个文件|多文件", requirement):
        return None

    language_match = re.search(
        r"\b(python3?|javascript|js|typescript|ts)\b", requirement, re.IGNORECASE
    )
    if not language_match:
        return None
    language = language_match.group(1).lower()
    extension = _LANGUAGE_EXTENSIONS[language]

    explicit = _EXPLICIT_FILE_RE.search(requirement)
    if explicit:
        filename = explicit.group(1)
    else:
        subject = re.search(r"(?:输出|打印|显示|返回)\s+([A-Za-z0-9_-]+)", requirement)
        stem = subject.group(1).lower() if subject else "main"
        filename = f"{stem}{extension}"
    return {"language": language, "extension": extension, "filename": filename}


def _response_text(response: Any) -> str:
    if isinstance(response, str):
        return response
    choices = response.get("choices", []) if isinstance(response, dict) else []
    message = choices[0].get("message", {}) if choices else {}
    return message.get("content", "") if isinstance(message, dict) else ""


def _safe_project_name(project_name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_-]+", "-", project_name).strip("-_")
    return value[:50] or "single-file"


def _resource_limits() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2 * 1024 * 1024, 2 * 1024 * 1024))


def _run_generated_file(file_path: Path, language: str) -> dict[str, Any]:
    if language in {"python", "python3"}:
        command = [sys.executable, file_path.name]
    elif language in {"javascript", "js"}:
        command = ["node", file_path.name]
    else:
        return {"ran": False, "stdout": "", "stderr": "", "error": "暂不支持该语言的运行验证"}

    with tempfile.TemporaryDirectory(prefix="single-file-run-") as temp_dir:
        temp_file = Path(temp_dir) / file_path.name
        temp_file.write_text(file_path.read_text(encoding="utf-8"), encoding="utf-8")
        try:
            completed = subprocess.run(
                command,
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=10,
                env={"PATH": os.environ.get("PATH", ""), "PYTHONPATH": ""},
                preexec_fn=_resource_limits,
            )
        except subprocess.TimeoutExpired:
            return {"ran": False, "stdout": "", "stderr": "执行超时", "error": "执行超时"}
        except OSError as error:
            return {"ran": False, "stdout": "", "stderr": str(error), "error": "运行时环境不可用"}
        return {
            "ran": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "error": completed.stderr if completed.returncode else "",
        }


async def generate_single_file(
    requirement: str,
    project_name: str | None = None,
    api_key_token: str | None = None,
    provider_id: str | None = None,
) -> dict[str, Any] | None:
    request_info = infer_single_file_request(requirement)
    if request_info is None:
        return None

    filename = request_info["filename"]
    resolved_project = _safe_project_name(project_name or Path(filename).stem)
    output_dir = Path("./projects") / resolved_project
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / filename

    assignment = (await get_dynamic_router()).get_assignment("simple")
    model = assignment.backend_model
    response = await call_llm(
        model=model,
        prompt=(
            f"用户需求：{requirement}\n\n"
            f"请只返回 {filename} 的完整源代码。语言为 {request_info['language']}。"
            "不要返回 Markdown、解释、多个文件或代码围栏。"
        ),
        system_prompt="你是单文件代码生成器。严格输出一个可直接运行的源文件。",
        stream=False,
        temperature=0.2,
        max_tokens=1200,
        thinking_budget=0,
        timeout=60,
        api_key_token=api_key_token,
        provider_id=provider_id,
    )
    content = clean_code_block(_response_text(response))
    file_path.write_text(content + "\n", encoding="utf-8")

    syntax_ok = bool(content.strip())
    syntax_error = "模型未返回有效源代码" if not syntax_ok else ""
    if syntax_ok:
        syntax_ok, syntax_error = validate_syntax_for_extension(filename, content)
    validation: dict[str, Any] = {
        "syntax_ok": syntax_ok,
        "syntax_errors": [] if syntax_ok else [syntax_error],
    }
    run_result = _run_generated_file(file_path, request_info["language"]) if syntax_ok else {
        "ran": False,
        "stdout": "",
        "stderr": "语法检查失败，跳过运行",
        "error": "语法检查失败",
    }
    validation["run"] = run_result
    success = syntax_ok and run_result.get("ran", False)
    return {
        "success": success,
        "output_dir": str(output_dir),
        "total_files_created": 1,
        "total_files_failed": 0 if success else 1,
        "complexity": "simple",
        "models_used": {"backend": model},
        "files": [{"path": filename, "content": content}],
        "validation": validation,
        "test_results": run_result,
        "specs_generated": [],
        "context_summary": "轻量单文件生成",
        "errors": [] if success else [run_result.get("error") or syntax_error],
        "warnings": [],
        "elapsed_time": 0,
        "fix_attempts": [],
        "session_id": None,
    }
