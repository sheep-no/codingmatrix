"""
AI Agent - 多模型 Agent 架构

使用以下模型：
- deepseek-ai/DeepSeek-R1-0528-Qwen3-8B - 主力推理模型
- deepseek-ai/DeepSeek-OCR - OCR/视觉理解
- Qwen/Qwen3.5-4B - 轻量快速响应
- Qwen/Qwen3-8B - 通用对话
- Qwen/Qwen2.5-7B-Instruct - 指令跟随
- THUDM/GLM-4.1V-9B-Thinking - 视觉推理
- Kwai-Kolors/Kolors - 图像生成
- THUDM/GLM-4-9B-0414 - 快速任务
- THUDM/GLM-Z1-9B-0414 - 深度推理
- netease-youdao/bce-embedding-base_v1 - 嵌入/相似度

架构：
- Router: 任务路由，根据任务类型选择模型
- Planner: 任务规划，将复杂任务拆解
- Executor: 执行器，调用工具执行
- Reviewer: 审查器，验证执行结果
- FileContract: 文件契约，确保文件操作安全

v5.14 重构：拆分为独立模块，此文件保留 MultiModelAgent + 向后兼容 re-export。
"""

import json
import logging
from typing import Optional, Dict, Any, List, Callable

from app.utils import call_llm
from app.utils.file_operator import FileOperator

# 向后兼容：从子模块 re-export 所有公开符号
from app.agent.models import (  # noqa: F401
    TaskType, AgentRole, ModelCapability, ModelInfo, ModelRegistry, ModelRouter,
    COMPLEXITY_LEVELS,
)
from app.agent.file_contract import (  # noqa: F401
    FileContract, ReviewResult, TaskStep, _degrade_step,
)
from app.agent.ai_reviewer import AIReviewer  # noqa: F401
from app.agent.task_planner import TaskPlanner  # noqa: F401
from app.agent.agent_executor import AgentExecutor, ANALYSIS_TOOLS  # noqa: F401

logger = logging.getLogger(__name__)


class MultiModelAgent:
    """
    多模型 Agent - 整合路由、规划、执行、审查

    v5.12.x 增强：
    - 接入 DynamicModelRouter 5×5 矩阵（按角色 + 复杂度路由）
    - 所有 LLM 调用统一走全局信号量（get_global_llm_semaphore）
    - 可选 complexity 参数：SIMPLE/SMALL/MEDIUM/LARGE/ENTERPRISE
    - 代码生成任务可委托给 OrchestratorAgent（通过 orchestrator_factory）
    """

    def __init__(
        self,
        default_model: str = "deepseek-r1-qwen3-8b",
        enable_review: bool = True,
        enable_file_contract: bool = True,
        complexity: str = "MEDIUM",
        orchestrator_factory: Optional[Callable] = None,
        api_key_token: str = None,
    ):
        self.router = ModelRouter()
        self.planner = TaskPlanner(default_model)
        self.reviewer = AIReviewer(default_model) if enable_review else None
        self.executor = AgentExecutor(FileOperator())
        self.enable_review = enable_review
        self.enable_file_contract = enable_file_contract
        self.complexity = complexity
        self._semaphore = None
        self._orchestrator_factory = orchestrator_factory
        self._orchestrator = None
        self._api_key_token = api_key_token

    def _get_semaphore(self):
        """延迟获取全局 LLM 信号量"""
        if self._semaphore is None:
            try:
                from app.agent.specialist_base import get_global_llm_semaphore
                self._semaphore = get_global_llm_semaphore()
            except Exception:
                self._semaphore = None
        return self._semaphore

    async def process(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        task_type: Optional[TaskType] = None,
        files: Optional[List[str]] = None,
        stream_callback: Optional[Callable] = None,
        use_dynamic_routing: bool = True,
        complexity: Optional[str] = None,
        dependency_hints: Optional[str] = None,
        output_dir: Optional[str] = None
    ) -> Dict:
        """
        处理任务

        v5.12.x 增强：
        - complexity: 显式指定项目复杂度（SIMPLE/SMALL/MEDIUM/LARGE/ENTERPRISE）
                     传入后，planner/reviewer 走 5×5 矩阵按角色路由
        - dependency_hints: 来自 DependencyGraph 的结构化提示，会注入到规划 prompt
        - output_dir: 项目输出目录（代码生成任务委托给 OrchestratorAgent 时必需）
        """
        async def emit(event_type: str, data: Dict):
            if stream_callback:
                try:
                    await stream_callback(event_type, data)
                except Exception as e:
                    logger.warning(f"流式回调失败: {e}")

        effective_complexity = complexity or self.complexity

        if task_type is None:
            task_type = self.router.route_by_content(task, files)
            await emit("task_routed", {"task_type": task_type.value})

        # 代码生成任务委托给 OrchestratorAgent
        if task_type == TaskType.CODE_GENERATION and self._orchestrator_factory and output_dir:
            await emit("delegating", {"message": "代码生成任务委托给 OrchestratorAgent", "task_type": task_type.value})
            try:
                orchestrator = self._orchestrator_factory(
                    output_dir=output_dir,
                    enable_review=True,
                    enable_validation=True,
                    enable_error_recovery=True,
                    dependency_graph=True,
                    callback=lambda msg: logger.info(f"Orchestrator 进度: {msg[:200]}")
                )
                result = await orchestrator.generate(requirement=task)
                await emit("delegation_complete", {"success": result.get("success", False)})
                return result
            except Exception as e:
                logger.error(f"OrchestratorAgent 委托失败: {e}")
                await emit("delegation_failed", {"error": str(e)})
                # 降级到 MultiModelAgent 自己处理

        # 分析类任务：使用 AgentExecutor 的 ReAct 工具调用
        if task_type in (TaskType.GENERAL, TaskType.CODE_REVIEW, TaskType.REACT, TaskType.PLANNING, TaskType.REASONING) and output_dir:
            await emit("analyzing", {"message": "正在分析项目...", "task_type": task_type.value})
            try:
                model_info = await self.router.route_dynamic(task_type) if use_dynamic_routing else self.router.route(task_type)
                api_key_token = getattr(self, '_api_key_token', None)
                result = await self.executor.execute_analysis(
                    task=task,
                    project_path=str(output_dir),
                    model_name=model_info.name,
                    api_key_token=api_key_token,
                )
                await emit("analysis_complete", {"success": result.get("success", False)})
                return result
            except Exception as e:
                logger.error(f"分析任务失败: {e}")
                await emit("analysis_failed", {"error": str(e)})
                return {"success": False, "error": f"分析失败: {str(e)}"}

        async def call_with_semaphore(coro_factory, *args, **kwargs):
            sem = self._get_semaphore()
            if sem is None:
                return await coro_factory(*args, **kwargs)
            async with sem:
                return await coro_factory(*args, **kwargs)

        if task_type is None:
            task_type = self.router.route_by_content(task, files)
            await emit("task_routed", {"task_type": task_type.value})

        if use_dynamic_routing:
            model = await self.router.route_dynamic(task_type)
        else:
            model = self.router.route(task_type)
        await emit("model_selected", {"model": model.display_name, "model_key": model.key})

        logger.info(f"任务类型: {task_type.value}, 使用模型: {model.display_name}, 复杂度: {effective_complexity}")

        steps = await call_with_semaphore(
            self.planner.decompose, task, context, dependency_hints,
            project_path=output_dir, tools=ANALYSIS_TOOLS,
        )
        await emit("plan_created", {"steps_count": len(steps), "steps": steps})

        if self.reviewer:
            await emit("review_start", {"message": "正在审查执行计划..."})
            try:
                from app.agent.dynamic_model_router import get_dynamic_router
                router = await get_dynamic_router()
                assignment = await router.get_assignment_with_learning(effective_complexity)
                reviewer_model = ModelRegistry.get(assignment.reviewer_model)
                if reviewer_model and reviewer_model != self.reviewer.model:
                    self.reviewer.model = reviewer_model
                    logger.info(f"按 5×5 矩阵切换 reviewer 模型为 {reviewer_model.display_name}")
            except Exception as e:
                logger.warning(f"reviewer 模型切换失败，使用默认: {e}")

            review_result = await call_with_semaphore(self.reviewer.review_plan, steps)
            if not review_result.approved:
                await emit("review_failed", {"issues": review_result.issues})
                return {
                    "success": False,
                    "error": "计划审查未通过",
                    "issues": review_result.issues,
                    "suggestions": review_result.suggestions
                }
            await emit("review_passed", {"message": "计划审查通过"})

        results = []
        for i, step in enumerate(steps):
            await emit("step_start", {"step_index": i, "step": step})

            # FileContract 前置验证：执行前检查路径安全性
            if step.get("type") == "file_operation" and self.enable_file_contract:
                contract = FileContract(
                    operation=step["params"].get("operation"),
                    file_path=step["params"].get("path", "")
                )
                if not contract.validate_path():
                    await emit("contract_failed", {"message": f"文件契约验证失败: {step['params'].get('path')}"})
                    return {
                        "success": False,
                        "error": f"文件契约验证失败: {step['params'].get('path')}",
                        "failed_step": i,
                    }

            result = await self.executor.execute(step)
            results.append(result)
            await emit("step_complete", {"step_index": i, "result": result})

        await emit("complete", {"message": "任务处理完成"})

        return {
            "success": True,
            "task_type": task_type.value,
            "model_used": model.display_name,
            "complexity": effective_complexity,
            "steps": len(steps),
            "results": results
        }
