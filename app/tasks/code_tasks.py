"""
Code Generation Tasks

Celery tasks for AI code generation and execution.
"""
import asyncio
import json
import logging
import subprocess
import yaml
from pathlib import Path
from typing import Dict, List
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from app.celery_app import celery_app
from app.tasks.base import BaseTask
from app.core.config import settings

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.tasks.code_tasks.generate_code",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True
)
def generate_code(self, task_id: str, prompt: str, language: str, user_id: int, **kwargs):
    """
    Generate code based on prompt.

    Args:
        task_id: Unique task identifier
        prompt: Code generation prompt
        language: Programming language
        user_id: User ID for WebSocket notifications
        **kwargs: Additional parameters

    Returns:
        dict with generated code
    """
    async def _execute():
        from app.api.v1.Aicode import call_siliconflow_api
        from app.utils.web_search import FreeWebSearch

        progress_cb = self._get_progress_callback(task_id, user_id)

        await progress_cb.update(20, "正在生成代码...")

        search_enabled = kwargs.get("search_enabled", False)
        if search_enabled:
            await progress_cb.update(40, "搜索相关信息...")
            searcher = FreeWebSearch()
            context = await searcher.search_and_format(prompt, count=3)
            full_prompt = f"上下文信息:\n{context}\n\n用户需求:\n{prompt}"
        else:
            full_prompt = prompt

        await progress_cb.update(60, "调用 AI 模型...")
        result = await call_siliconflow_api(full_prompt)

        await progress_cb.update(100, "生成完成")
        return {
            "code": result.get("content", ""),
            "language": language,
            "prompt": prompt
        }

    try:
        return asyncio.run(_execute())
    except SoftTimeLimitExceeded:
        logger.error(f"Task {task_id} soft time limit exceeded")
        raise Exception("代码生成超时")


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.tasks.code_tasks.execute_code",
    max_retries=2,
    default_retry_delay=30,
    acks_late=True
)
def execute_code(self, task_id: str, code: str, language: str, user_id: int, **kwargs):
    """
    Execute code in Docker sandbox.

    Args:
        task_id: Unique task identifier
        code: Code to execute
        language: Programming language
        user_id: User ID for WebSocket notifications
        **kwargs: Additional parameters (timeout, etc.)

    Returns:
        dict with execution result
    """
    async def _execute():
        from app.utils.docker_runner import DockerRunner

        progress_cb = self._get_progress_callback(task_id, user_id)

        await progress_cb.update(10, "准备执行环境...")

        runner = DockerRunner()
        timeout = kwargs.get("timeout", 60)

        await progress_cb.update(30, "执行代码...")
        result = await runner.run_validation(
            code=code,
            language=language,
            timeout=timeout
        )

        await progress_cb.update(100, "执行完成")
        return result

    try:
        return asyncio.run(_execute())
    except SoftTimeLimitExceeded:
        logger.error(f"Task {task_id} soft time limit exceeded")
        raise Exception("代码执行超时")
    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}")
        raise


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.tasks.code_tasks.modify_with_test",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True
)
def modify_with_test(
    self,
    task_id: str,
    user_id: int,
    requirement: str,
    target_files: List[str] = None,
    max_retry_loops: int = None,
    **kwargs
):
    """
    修改代码并自动运行关联测试（P1 新增）

    流程:
    1. 查询依赖图谱，输出影响报告
    2. Agent 执行修改
    3. 自动运行关联测试
    4. 测试失败则收集日志回传 Agent 修复（最多 N 轮）
    5. 守护合约分级警告

    Args:
        task_id: 任务 ID
        user_id: 用户 ID
        requirement: 修改需求描述
        target_files: 目标文件列表
        max_retry_loops: 最大重试次数（默认取配置值）
        **kwargs: 额外参数

    Returns:
        dict with modification results
    """
    async def _execute():
        from app.utils.guard_contracts import get_guard_contracts, check_file_against_contracts
        from app.api.v1.ai_agent import load_dependency_graph, get_agent_knowledge_base
        from app.core.config import settings

        progress_cb = self._get_progress_callback(task_id, user_id)
        max_retries = max_retry_loops or settings.MAX_RETRY_LOOPS

        # Step 1: 查询依赖图谱
        await progress_cb.update(5, "查询依赖图谱...")
        dep_graph = load_dependency_graph()
        affected_files = _find_affected_files(dep_graph, target_files or [])
        await progress_cb.update(10, f"影响分析完成，波及 {len(affected_files)} 个文件")

        # Step 2: 加载测试映射
        test_files = _get_related_tests(target_files or [])
        await progress_cb.update(15, f"找到 {len(test_files)} 个关联测试文件")

        # Step 3: Agent 执行修改（调用 AI 生成代码）
        await progress_cb.update(20, "执行代码修改...")
        modification_result = await _agent_modify(
            requirement=requirement,
            target_files=target_files,
            affected_files=affected_files,
            progress_cb=progress_cb,
            **kwargs
        )

        # Step 4: 运行关联测试
        retry_count = 0
        test_logs = []
        while retry_count <= max_retries:
            await progress_cb.update(
                50 + int(40 * retry_count / max_retries),
                f"运行测试 (第 {retry_count + 1}/{max_retries + 1} 轮)..."
            )

            test_result = _run_tests(test_files)
            test_logs.append(test_result)

            if test_result.get("success", False):
                await progress_cb.update(95, "测试全部通过")
                break

            # 测试失败，收集日志回传 Agent 修复
            if retry_count < max_retries:
                await progress_cb.update(
                    50 + int(40 * retry_count / max_retries),
                    f"测试失败，正在修复 ({retry_count + 1}/{max_retries})..."
                )
                modification_result = await _agent_fix_from_test_logs(
                    test_logs=test_logs,
                    original_result=modification_result,
                    progress_cb=progress_cb,
                    **kwargs
                )
                retry_count += 1
            else:
                await progress_cb.update(90, f"测试失败，已达最大重试次数 {max_retries}")

        # Step 5: 守护合约检查
        await progress_cb.update(95, "守护合约检查...")
        guard_violations = []
        contracts = get_guard_contracts()
        for file_path in (target_files or []):
            full_path = Path(file_path)
            if full_path.exists():
                content = full_path.read_text(encoding='utf-8')
                violations = contracts.check_file(file_path, content)
                guard_violations.extend([v.__dict__ for v in violations])

        return {
            "success": all(t.get("success", False) for t in test_logs) if test_logs else True,
            "modification": modification_result,
            "test_results": test_logs,
            "guard_violations": guard_violations,
            "affected_files": affected_files,
            "retry_count": retry_count,
        }

    try:
        return asyncio.run(_execute())
    except SoftTimeLimitExceeded:
        logger.error(f"Task {task_id} soft time limit exceeded")
        raise Exception("修改+测试任务超时")
    except Exception as e:
        logger.error(f"Task {task_id} failed: {e}")
        raise


# ==================== 辅助函数 ====================

def _find_affected_files(dep_graph: Dict, target_files: List[str]) -> List[str]:
    """通过依赖图谱查找受影响的文件"""
    if not dep_graph:
        return []

    affected = set(target_files)
    reverse_index = dep_graph.get("reverse_index", {})

    for file_path in target_files:
        # 查找依赖此文件的其他文件
        for target, sources in reverse_index.items():
            if target in file_path:
                affected.update(sources)

    # 排除目标文件本身
    affected -= set(target_files)
    return list(affected)


def _get_related_tests(target_files: List[str]) -> List[str]:
    """获取关联的测试文件"""
    test_map_path = Path(settings.FILE_TO_TEST_MAP_PATH)
    if not test_map_path.exists():
        return []

    try:
        with open(test_map_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        mapping = config.get("mapping", {})
        test_files = set()

        for target in target_files:
            for pattern, tests in mapping.items():
                if pattern.replace('*', '') in target or target in pattern:
                    test_files.update(tests)

        # 添加全局测试
        global_tests = config.get("global_tests", [])
        test_files.update(global_tests)

        return list(test_files)
    except Exception as e:
        logger.error(f"加载测试映射失败: {e}")
        return []


async def _agent_modify(requirement: str, target_files: List[str], affected_files: List[str],
                        progress_cb, **kwargs) -> Dict:
    """调用 Agent 执行代码修改"""
    # 这里调用 AI 模型生成代码
    # 简化版：实际应调用 MultiModelAgent 或 ProjectGeneratorAgent
    from app.api.v1.Aicode import call_siliconflow_api

    prompt = f"""
    需求: {requirement}
    目标文件: {', '.join(target_files)}
    受影响文件: {', '.join(affected_files)}

    请修改目标文件以满足需求。注意：
    1. 保持向后兼容
    2. 遵循守护合约规则
    3. 不要遗漏关联文件的修改
    """

    result = await call_siliconflow_api(prompt)
    return {"content": result.get("content", ""), "status": "completed"}


async def _agent_fix_from_test_logs(test_logs: List[Dict], original_result: Dict,
                                    progress_cb, **kwargs) -> Dict:
    """根据测试日志调用 Agent 修复"""
    from app.api.v1.Aicode import call_siliconflow_api

    last_log = test_logs[-1]
    error_info = last_log.get("error", "未知错误")

    prompt = f"""
    上次修改后测试失败，请修复。

    错误信息:
    {error_info}

    请分析错误原因并重新修改代码。
    """

    result = await call_siliconflow_api(prompt)
    return {"content": result.get("content", ""), "status": "fixed", "retry": len(test_logs)}


def _run_tests(test_files: List[str]) -> Dict:
    """运行测试文件"""
    if not test_files:
        return {"success": True, "message": "无测试文件"}

    test_config = {
        "command": "pytest",
        "args": ["-v", "--tb=short", "--maxfail=3"],
        "timeout": 120,
    }

    cmd = [test_config["command"]] + test_config["args"] + test_files

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=test_config["timeout"],
            cwd=str(Path(__file__).parent.parent.parent)
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[:2000],
            "stderr": result.stderr[:2000],
            "returncode": result.returncode,
            "error": result.stderr if result.returncode != 0 else "",
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"测试超时 ({test_config['timeout']}s)",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
