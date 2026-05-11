"""
Orchestrator Agent - 多角色协作架构

架构：
- Orchestrator: 总指挥，负责任务分解、角色分配、进度协调
- Architect: 架构师，负责技术选型和整体架构设计 (app.agent.specialists)
- FrontendEngineer: 前端工程师，专注前端代码生成 (app.agent.specialists)
- BackendEngineer: 后端工程师，专注后端代码生成 (app.agent.specialists)
- Reviewer: 审查员，负责代码质量和安全审查 (app.agent.specialists)
- Validator: 验证器，负责语法、依赖、运行时验证 (app.agent.code_validator)

模型分配策略：
- 架构设计: GLM-Z1-9B (深度推理) / Qwen3-8B (简单任务)
- 前端生成: Qwen2.5-7B-Instruct (CODE+FAST) / Qwen3-8B (企业级)
- 后端生成: DeepSeek-R1-Qwen3-8B (代码推理)
- 代码审查: GLM-Z1-9B + DeepSeek-R1 (双重审查)
- 简单任务: Qwen3-8B (REASONING+FAST)
"""

import re
import sys
import json
import asyncio
import logging
import time
from typing import Optional, Dict, Any, List, Callable, Tuple
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime

# 并发限制：同时进行的 LLM 调用数
MAX_CONCURRENT_LLM_CALLS = 4
# 依赖上下文中保留的最大内容长度（防止大文件导致 OOM）
MAX_CONTENT_FOR_CONTEXT = 3000

from app.utils.AiCodeUtil import call_siliconflow, get_embedding
from app.utils.file_operator import FileOperator, PathSecurityError
from app.utils.retry import retry_on_failure
from app.utils.circuit_breaker import circuit_breaker

# 拆分出的模块
from app.agent.complexity import ProjectComplexity, ComplexityAnalysis, ComplexityAnalyzer
from app.agent.code_validator import CodeValidator
from app.agent.specialists import Specialist, Architect, FrontendEngineer, BackendEngineer, CodeReviewer
from app.agent.error_recovery import ErrorRecoveryLoop, FixAttempt

from app.agent.multi_model_agent import ModelRegistry, ModelInfo, ModelCapability, TaskType
from app.agent.shared_context import SharedContext
from app.agent.api_contract_checker import APIContractChecker, check_api_consistency, generate_frontend_prompt_contract
from app.agent.code_patcher import CodePatcher, apply_incremental_change
from app.agent.spec_first_generator import SpecFirstGenerator
from app.agent.refinement_loop import RefinementLoop, RefinementResult
from app.agent.dependency_graph import DependencyGraph
from app.agent.cross_validator import CrossValidator
from app.agent.session_manager import SessionManager
from app.agent.spec_cache import SpecCache
from app.agent.feedback_learner import FeedbackLearner
from app.agent.memory import ConversationMemory, KnowledgeMemory
from app.agent.test_runner import TestRunner

# 模型路由（从 dynamic_model_router 导入）
from app.agent.dynamic_model_router import LayeredModelRouter, ModelAssignment

logger = logging.getLogger(__name__)


# ==================== 用户友好的阶段标签 ====================

PROGRESS_LABELS = {
    "analyzing_complexity": "分析项目复杂度",
    "assigning_models": "分配 AI 模型",
    "initializing_roles": "初始化专家角色",
    "cost_estimation": "预估生成成本",
    "dependency_graph": "构建文件依赖关系",
    "generating_file": "正在生成文件",
    "file_generated": "文件生成完成",
    "react_fallback": "启用增强生成模式",
    "pause_for_approval": "等待人工确认",
    "file_rejected": "文件已被拒绝",
    "validating_file": "验证文件内容",
    "reviewing_file": "审查代码质量",
    "api_contract_check": "检查 API 一致性",
    "final_validation": "最终项目验证",
    "dependency_graph_built": "依赖关系构建完成",
    "generating_layer": "生成分层文件",
    "layer_completed": "分层生成完成",
    "test_execution": "运行自动化测试",
    "test_passed": "测试全部通过",
    "test_failed": "测试存在失败",
    "auto_repair": "自动修复测试问题",
    "repair_completed": "修复完成",
    "saving_memory": "保存项目经验",
    "generation_complete": "项目生成完成",
    "incremental_analysis": "分析变更内容",
    "incremental_no_changes": "无变更，跳过生成",
    "running_tests": "运行自动化测试",
    "tests_passed": "测试全部通过",
    "tests_failed_recovering": "测试失败，正在自动修复",
    "recovery_success": "自动修复成功",
    "recovery_failed": "自动修复失败",
    "generating_layer": "正在生成分层文件",
    "layer_completed": "分层生成完成",
    "validating_file": "验证文件内容",
    "reviewing_file": "审查代码质量",
    "api_contract_check": "检查 API 一致性",
    "final_validation": "最终项目验证",
    "saving_memory": "保存项目经验",
}

# ==================== Orchestrator Agent ====================

@dataclass
class GenerationProgress:
    """生成进度"""
    current_step: str
    total_steps: int
    completed_files: int
    total_files: int
    current_model: str
    errors: List[str]
    warnings: List[str]


class OrchestratorAgent:
    """
    总指挥 Agent - 协调多角色协作完成项目生成

    工作流程：
    1. 分析需求复杂度
    2. 分配模型角色
    3. 架构师设计架构
    4. 按优先级生成文件
    5. 每个文件生成后进行验证和审查
    6. 错误时自动修复
    7. 完成后进行整体验证
    """

    def __init__(
        self,
        output_dir: str = "./generated_project",
        enable_review: bool = True,
        enable_validation: bool = True,
        enable_error_recovery: bool = True,
        memory_enabled: bool = True,
        spec_first: bool = True,
        dependency_graph: bool = True,
        callback: Optional[Callable] = None,
        # 新增：增量生成
        session_manager: Optional[SessionManager] = None,
        session_id: Optional[str] = None,
        incremental: bool = False,
        # 新增：缓存
        spec_cache: Optional[SpecCache] = None,
        # 新增：人机协作
        require_approval: bool = False,
        approval_callback: Optional[Callable] = None,
        # 新增：反馈学习
        feedback_learner: Optional[FeedbackLearner] = None
    ):
        self.output_dir = Path(output_dir)
        self.enable_review = enable_review
        self.enable_validation = enable_validation
        self.enable_error_recovery = enable_error_recovery
        self.memory_enabled = memory_enabled
        self.spec_first = spec_first
        self.dependency_graph = dependency_graph
        self.callback = callback

        # 增量生成
        self.session_manager = session_manager
        self.session_id = session_id
        self.incremental = incremental
        self._session_state = None

        # 缓存
        self.spec_cache = spec_cache

        # 人机协作
        self.require_approval = require_approval
        self.approval_callback = approval_callback

        # 反馈学习
        self.feedback_learner = feedback_learner

        # 初始化记忆系统
        if memory_enabled:
            self.conversation_memory = ConversationMemory()
            self.knowledge_memory = KnowledgeMemory()

        # 组件延迟初始化（在 generate 时根据复杂度创建）
        self.analyzer: Optional[ComplexityAnalyzer] = None
        self.model_router: Optional[LayeredModelRouter] = None
        self.architect: Optional[Architect] = None
        self.frontend_engineer: Optional[FrontendEngineer] = None
        self.backend_engineer: Optional[BackendEngineer] = None
        self.reviewer: Optional[CodeReviewer] = None
        self.validator: Optional[CodeValidator] = None
        self.error_recovery: Optional[ErrorRecoveryLoop] = None
        self.api_contract_checker: Optional[APIContractChecker] = None
        self.code_patcher: Optional[CodePatcher] = None
        self.dependency_graph_obj: Optional[DependencyGraph] = None

        # 生成状态
        self.complexity: Optional[ComplexityAnalysis] = None
        self.model_assignment: Optional[ModelAssignment] = None
        self.generated_files: List[Dict] = []
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self._start_time: Optional[float] = None  # 生成开始时间
        self._current_phase: str = "initializing"  # 当前阶段
        self._generated_contents: Dict[str, str] = {}  # 已生成文件的实际内容（用于上下文注入）

    def _report_progress(self, step: str, current: int, total: int, callback: Optional[Callable] = None, **kwargs):
        """报告进度（增强版：百分比、预计时间、阶段信息）"""
        percentage = round((current / total * 100) if total > 0 else 0, 1)

        elapsed = 0
        eta_seconds = 0
        if self._start_time:
            elapsed = time.time() - self._start_time
            if current > 0 and current < total:
                rate = current / elapsed  # 项/秒
                remaining = total - current
                eta_seconds = remaining / rate if rate > 0 else 0

        progress = {
            "type": "progress",
            "step": step,
            "phase": self._current_phase,
            "current": current,
            "total": total,
            "percentage": percentage,
            "elapsed_seconds": round(elapsed, 1),
            "eta_seconds": round(eta_seconds, 1),
            **kwargs
        }
        cb = callback or self.callback
        if cb:
            try:
                result = cb(json.dumps(progress, ensure_ascii=False))
                if asyncio.iscoroutine(result):
                    asyncio.create_task(result)
            except Exception as e:
                logger.error(f"进度回调失败: {e}")

    def build_progress_event(self, step: str, current: int, total: int, **kwargs) -> Dict:
        """构建进度事件（用于 SSE 流式推送，无需回调）"""
        percentage = round((current / total * 100) if total > 0 else 0, 1)

        elapsed = 0
        eta_seconds = 0
        if self._start_time:
            elapsed = time.time() - self._start_time
            if current > 0 and current < total:
                rate = current / elapsed
                remaining = total - current
                eta_seconds = remaining / rate if rate > 0 else 0

        return {
            "type": "progress",
            "step": step,
            "phase": self._current_phase,
            "current": current,
            "total": total,
            "percentage": percentage,
            "elapsed_seconds": round(elapsed, 1),
            "eta_seconds": round(eta_seconds, 1),
            **kwargs
        }

    def _report_thinking(self, agent: str, message: str, **kwargs):
        """报告思考过程（用于前端展示 AI 的思考）"""
        event = {
            "type": "thinking",
            "agent": agent,
            "message": message,
            "timestamp": time.time(),
            **kwargs
        }
        if self.callback:
            try:
                self.callback(event)
            except Exception as e:
                logger.error(f"思考事件推送失败: {e}")

    def _update_phase(self, phase: str):
        """更新当前阶段"""
        self._current_phase = phase

    async def _initialize_components(self, requirement: str):
        """根据需求初始化所有组件"""
        self._start_time = time.time()
        self._update_phase("analyzing")

        # 分析复杂度（中大型项目使用 LLM 辅助校准）
        self.analyzer = ComplexityAnalyzer()
        self.complexity = await self.analyzer.analyze_with_llm(requirement)

        self._report_progress(
            PROGRESS_LABELS["analyzing_complexity"],
            1, 5,
            complexity=self.complexity.level.value,
            estimated_files=self.complexity.estimated_files,
            tech_stack=self.complexity.key_technologies
        )

        # 分配模型（静态路由）
        self.model_router = LayeredModelRouter()
        self.model_assignment = self.model_router.get_assignment(self.complexity.level)

        self._report_progress(
            PROGRESS_LABELS["assigning_models"],
            2, 5,
            architect=self.model_assignment.architect_model,
            frontend=self.model_assignment.frontend_model,
            backend=self.model_assignment.backend_model,
            reviewer=self.model_assignment.reviewer_model
        )

        # 设置并发限制
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)
        Specialist.set_semaphore(semaphore)

        # 创建角色实例
        self.architect = Architect("架构师", self.model_assignment.architect_model, task_type="generate")
        self.frontend_engineer = FrontendEngineer("前端工程师", self.model_assignment.frontend_model, task_type="generate")
        self.backend_engineer = BackendEngineer("后端工程师", self.model_assignment.backend_model, task_type="generate")
        self.reviewer = CodeReviewer("审查员", self.model_assignment.reviewer_model, task_type="review")
        self.validator = CodeValidator(self.output_dir)
        self.error_recovery = ErrorRecoveryLoop(self.validator, self.reviewer)
        self.api_contract_checker = APIContractChecker()
        self.code_patcher = CodePatcher(llm_call_fn=self._call_llm_for_patch)

        self._report_progress(
            PROGRESS_LABELS["initializing_roles"],
            3, 5,
            roles=["架构师", "前端工程师", "后端工程师", "审查员"]
        )

    async def _select_dynamic_model(self, candidate_models: List[str], task_type: str) -> str:
        """从候选模型中动态选择最佳模型"""
        from app.agent.dynamic_model_router import get_dynamic_router

        router = await get_dynamic_router()
        return await router.get_best_model(candidate_models, task_type)

    def _validate_file_plan(self, file_plan: List[Dict]) -> List[Dict]:
        """验证并过滤文件计划，移除非法路径"""
        valid_files = []
        for file_info in file_plan:
            path = file_info.get("path", "")
            if not path:
                continue

            # 检查路径是否包含非法字符（非 ASCII 字母、数字、常见符号）
            # 允许：字母、数字、下划线、连字符、点、斜杠
            if re.search(r'[^a-zA-Z0-9_\-./]', path):
                self.warnings.append(f"跳过非法路径: {path}")
                continue

            # 检查路径深度（避免过深嵌套）
            depth = path.count('/') + path.count('\\')
            if depth > 5:
                self.warnings.append(f"跳过过深路径: {path}")
                continue

            # 检查路径是否以斜杠开头（绝对路径）
            if path.startswith('/') or path.startswith('\\'):
                path = path.lstrip('/\\')
                file_info["path"] = path

            # 检查文件扩展名是否有效
            ext = Path(path).suffix.lower()
            valid_extensions = {
                '.py', '.js', '.ts', '.jsx', '.tsx', '.vue', '.html', '.css', '.scss', '.sass',
                '.less', '.md', '.txt', '.json', '.yaml', '.yml', '.toml', '.env', '.sql',
                '.sh', '.bat', '.ps1', '.dockerfile', '.gitignore', '.editorconfig',
                '.graphql', '.proto', '.xml', '.svg', '.png', '.jpg', '.jpeg', '.gif', '.ico',
                '',  # 允许无扩展名
            }
            if ext not in valid_extensions:
                self.warnings.append(f"跳过不支持的文件类型: {path}")
                continue

            # 检查重复路径
            if any(f.get("path") == path for f in valid_files):
                self.warnings.append(f"跳过重复路径: {path}")
                continue

            valid_files.append(file_info)

        if not valid_files:
            # 如果所有文件都被过滤，返回默认文件
            self.warnings.append("所有文件路径被过滤，使用默认文件计划")
            valid_files = [
                {"path": "main.py", "description": "主程序入口", "priority": 1},
                {"path": "requirements.txt", "description": "依赖列表", "priority": 2},
                {"path": "README.md", "description": "项目文档", "priority": 3}
            ]

        return valid_files

    async def generate(self, requirement: str) -> Dict[str, Any]:
        """
        生成项目主入口（并发优化 + 增量生成 + 缓存 + 反馈学习）
        
        根据 spec_first 选项选择生成策略：
        - spec_first=True: 使用 Spec-First 策略（推荐）
        - spec_first=False: 使用传统生成策略

        Args:
            requirement: 项目需求描述

        Returns:
            生成结果
        """
        if self.spec_first:
            return await self.generate_with_spec_first(requirement, self.callback)
        else:
            return await self._generate_traditional(requirement)
        start_time = time.time()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 重置状态（支持多次调用）
        self.generated_files = []
        self.errors = []
        self.warnings = []

        # 尝试从缓存加载
        cached = None
        requirement_vector = None
        if self.spec_cache and not self.incremental:
            try:
                requirement_vector = await get_embedding(requirement)
            except Exception as e:
                logger.warning(f"BCE Embedding 失败，降级到关键词匹配: {e}")
            cached = self.spec_cache.lookup(requirement, requirement_vector=requirement_vector)
            if cached:
                logger.info(f"命中缓存: {cached.requirement_hash}")
                self._report_progress(
                    "cache_hit", 0, 1,
                    cache_hash=cached.requirement_hash,
                    cached_specs=list(cached.specs.keys())
                )

        # 1. 初始化组件
        await self._initialize_components(requirement)

        # 2. 架构设计（如果缓存命中则跳过）
        architecture = None
        file_plan = []
        if cached and cached.architecture:
            architecture = cached.architecture
            file_plan = cached.file_plan
            self._report_progress(
                "cache_loaded", 4, 5,
                file_count=len(file_plan)
            )
        else:
            self._report_thinking(
                "architect",
                "正在分析需求，设计系统架构... 我将确定技术栈、项目结构和关键组件。"
            )
            architecture = await self.architect.design_architecture(requirement, self.complexity)
            file_plan = architecture.get("file_plan", [])

            # 推送架构设计思路
            project_type = architecture.get("project_type", "")
            tech_stack = architecture.get("tech_stack", [])
            self._report_thinking(
                "architect",
                f"架构设计完成。项目类型：{project_type}，技术栈：{', '.join(tech_stack[:3])}，共规划 {len(file_plan)} 个文件。"
            )

        # 验证文件路径
        file_plan = self._validate_file_plan(file_plan)

        # 2.5 成本估算和熔断检查
        cost_analysis = self._estimate_generation_cost(architecture, file_plan)
        self._report_progress(
            PROGRESS_LABELS["cost_estimation"],
            3, 5,
            estimated_tokens=cost_analysis["estimated_tokens"],
            estimated_cost_usd=cost_analysis["estimated_cost_usd"],
            cost_level=cost_analysis["cost_level"],
            suggestion=cost_analysis["suggestion"]
        )

        # 如果成本过高且需要人工介入，暂停等待确认
        if self.require_approval and cost_analysis["cost_level"] == "high":
            self._report_progress(
                "pause_for_cost_approval",
                3, 5,
                estimated_cost_usd=cost_analysis["estimated_cost_usd"],
                suggestion=cost_analysis["suggestion"]
            )
            # 等待用户确认（5 分钟超时）
            approved = await self._wait_for_approval("cost_estimation", timeout=300.0)
            if not approved:
                self.warnings.append("用户拒绝高成本生成，已取消")
                return {
                    "success": False,
                    "cancelled_by_user": True,
                    "reason": "cost_too_high",
                    "cost_analysis": cost_analysis
                }

        # 3. 注册会话（在 architecture/file_plan 就绪后创建）
        if self.session_manager and self.session_id:
            if self.incremental:
                # 增量模式：恢复已有会话
                self._session_state = await self.session_manager.resume_session(self.session_id)
                if not self._session_state:
                    # 会话不存在，创建新会话
                    self._session_state = await self.session_manager.create_session(
                        requirement=requirement,
                        output_dir=str(self.output_dir),
                        architecture=architecture,
                        file_plan=file_plan,
                        session_id=self.session_id
                    )
            else:
                # 新生成模式：创建会话并存储状态
                self._session_state = await self.session_manager.create_session(
                    requirement=requirement,
                    output_dir=str(self.output_dir),
                    architecture=architecture,
                    file_plan=file_plan,
                    session_id=self.session_id
                )

        # 4. 并行生成文件

        # 生成 API 契约（用于前端生成时参考后端接口定义）
        api_contract_prompt = ""
        if self.api_contract_checker:
            # 收集已生成的后端文件
            backend_files = {}
            for py_file in self.output_dir.rglob('*.py'):
                if '__pycache__' not in str(py_file):
                    try:
                        backend_files[str(py_file.relative_to(self.output_dir))] = py_file.read_text()
                    except Exception:
                        pass

            if backend_files:
                api_contract_prompt = generate_frontend_prompt_contract(backend_files)

        # 发送依赖图数据（用于前端可视化）
        dep_graph = DependencyGraph()
        dep_graph.build_from_architecture(architecture)
        dep_layers = dep_graph.get_generation_layers()

        self._report_progress(
            PROGRESS_LABELS["dependency_graph"],
            4, 5,
            project_type=architecture.get("project_type", "unknown"),
            tech_stack=architecture.get("tech_stack", []),
            file_count=len(file_plan),
            file_plan=file_plan,
            layers=[list(layer) for layer in dep_layers],
            api_contract=api_contract_prompt
        )

        # 确保所有文件计划中的文件都在依赖图中
        for file_info in file_plan:
            path = file_info.get("path", "")
            if path and path not in dep_graph.nodes:
                dep_graph.add_file(path, priority=file_info.get("priority", 3))

        # 3. 生成文件（依赖分层并发优化）
        project_context = {
            "requirement": requirement,
            "architecture": architecture,
            "complexity": self.complexity.level.value,
            "output_dir": str(self.output_dir),
            "api_contract": api_contract_prompt
        }

        total_files = len(file_plan)

        # 增量生成处理
        if self.incremental and self.session_id:
            await self._handle_incremental_generation(
                requirement, file_plan, project_context, total_files
            )
        # 小项目直接并发生成（文件数 <= 5）
        elif total_files <= 5:
            await self._generate_files_small_project(file_plan, project_context, total_files)
        else:
            # 中大项目：按依赖分层并发（同一层内无依赖，可并行）
            await self._generate_files_by_dep_layers(file_plan, project_context, total_files, dep_graph)

        # 4. 最终验证（与保存记忆并行）
        final_validation = {}
        test_results = {"success": True, "message": "未运行动态测试"}
        save_memory_task = None
        if self.memory_enabled:
            save_memory_task = asyncio.create_task(self._save_to_memory(requirement, architecture))

        if self.enable_validation:
            final_validation = await self.validator.run_full_validation()

        # 4.1 动态测试执行（如果存在测试文件且静态验证通过）
        if final_validation.get("is_valid", False):
            test_runner = TestRunner(self.output_dir)
            test_results = await self._run_dynamic_tests(test_runner)
            if not test_results.get("success"):
                self.warnings.append(f"动态测试失败: {test_results.get('summary')}")
                # TODO: 未来可在此处调用 ReActAgent 进行自动修复

        if save_memory_task:
            await save_memory_task

        # 缓存规范（用于后续相似需求）
        if self.spec_cache and not cached:
            await self._cache_specs(requirement, architecture, file_plan, requirement_vector)

        # 记录学习数据
        if self.feedback_learner:
            await self._record_learning_data(requirement, architecture, file_plan)

        elapsed = time.time() - start_time

        return {
            "success": len(self.errors) == 0 and test_results.get("success", True),
            "output_dir": self.output_dir.name,
            "total_files_created": len(self.generated_files),
            "files": self.generated_files,
            "complexity": self.complexity.level.value if self.complexity else "unknown",
            "models_used": {
                "architect": self.model_assignment.architect_model if self.model_assignment else "N/A",
                "frontend": self.model_assignment.frontend_model if self.model_assignment else "N/A",
                "backend": self.model_assignment.backend_model if self.model_assignment else "N/A",
                "reviewer": self.model_assignment.reviewer_model if self.model_assignment else "N/A",
            },
            "validation": final_validation,
            "test_results": test_results,
            "errors": self.errors,
            "warnings": self.warnings,
            "elapsed_time": elapsed,
            "fix_attempts": [
                {
                    "file": h.file_path,
                    "attempts": h.attempts,
                    "success": h.fix_applied,
                    "model_used": h.model_used if hasattr(h, 'model_used') else None
                }
                for h in self.error_recovery.fix_history if self.error_recovery
            ],
            "session_id": self.session_id
        }

    async def _handle_incremental_generation(
        self,
        requirement: str,
        file_plan: List[Dict],
        project_context: Dict,
        total_files: int
    ):
        """处理增量生成"""
        if not self.session_manager or not self.session_id:
            await self._generate_files_small_project(file_plan, project_context, total_files)
            return

        # 检测变化
        result = await self.session_manager.detect_incremental_changes(
            self.session_id, requirement, self.output_dir
        )
        state = result["state"]

        incremental_plan = self.session_manager.get_file_plan_for_incremental(state)
        unchanged = state.unchanged_files

        self._report_progress(
            PROGRESS_LABELS["incremental_analysis"] if "incremental_analysis" in PROGRESS_LABELS else "分析变更内容",
            0, 1,
            total_files=total_files,
            files_to_regenerate=len(incremental_plan),
            files_reusable=len(unchanged),
            changed_files=state.changed_files,
            unchanged_files=unchanged
        )

        if unchanged:
            for path in unchanged:
                self.generated_files.append({
                    "path": path,
                    "description": "复用已有文件",
                    "success": True,
                    "reused": True
                })

        if not incremental_plan:
            self._report_progress(PROGRESS_LABELS["incremental_no_changes"], 1, 1)
            return

        # 判断是否使用 patch 模式（小变更）或全量生成（大变更）
        use_patch_mode = self._should_use_patch_mode(incremental_plan, requirement)

        if use_patch_mode and self.code_patcher:
            # Patch 模式：仅修改需要变更的部分
            await self._apply_patches_incremental(
                requirement, incremental_plan, project_context, total_files
            )
        else:
            # 全量模式：重新生成变化的文件
            semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)

            async def generate_with_semaphore(file_info: Dict) -> Dict:
                async with semaphore:
                    return await self._generate_single_file(file_info, project_context, total_files)

            tasks = [generate_with_semaphore(fi) for fi in incremental_plan]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    self.errors.append(f"文件生成异常: {str(result)}")
                elif result:
                    self.generated_files.append(result)

    def _compute_layers(self, file_plan: List[Dict]) -> List[List[str]]:
        """按优先级计算分层"""
        groups: Dict[int, List[str]] = {}
        for fi in file_plan:
            p = fi.get("priority", 3)
            if p not in groups:
                groups[p] = []
            groups[p].append(fi.get("path", ""))

        return [groups[p] for p in sorted(groups.keys())]

    async def _cache_specs(
        self,
        requirement: str,
        architecture: Dict,
        file_plan: List[Dict],
        requirement_vector: Optional[List[float]] = None
    ):
        """缓存规范"""
        if not self.spec_cache:
            return

        specs = {}
        if self.complexity:
            specs["complexity"] = {
                "level": self.complexity.level.value,
                "estimated_files": self.complexity.estimated_files,
                "has_frontend": self.complexity.has_frontend,
                "has_backend": self.complexity.has_backend,
                "has_database": self.complexity.has_database,
            }

        self.spec_cache.save(
            requirement=requirement,
            specs=specs,
            architecture=architecture,
            file_plan=file_plan,
            complexity=specs.get("complexity", {}),
            tech_stack=architecture.get("tech_stack", []),
            requirement_vector=requirement_vector
        )

    async def _record_learning_data(
        self,
        requirement: str,
        architecture: Dict,
        file_plan: List[Dict]
    ):
        """记录学习数据"""
        if not self.feedback_learner:
            return

        # 收集所有错误信息
        all_errors = []
        if self.error_recovery:
            for fix_attempt in self.error_recovery.fix_history:
                all_errors.append(fix_attempt.error_message)

        # 计算错误 embedding
        error_embeddings = {}
        if all_errors:
            error_embeddings = await self.feedback_learner.compute_error_embeddings(all_errors)

        # 记录修复历史
        if self.error_recovery:
            for fix_attempt in self.error_recovery.fix_history:
                self.feedback_learner.record_fix(
                    file_path=fix_attempt.file_path,
                    file_type="python",
                    original_content="",
                    fixed_content="",
                    errors={"validation_error": [fix_attempt.error_message]},
                    model_name=self.model_assignment.backend_model if self.model_assignment else "",
                    success=fix_attempt.fix_applied,
                    error_embeddings=error_embeddings
                )

    async def _run_dynamic_tests(self, runner: TestRunner) -> Dict[str, Any]:
        """运行测试用例（轻量级沙箱）"""
        self._report_progress(PROGRESS_LABELS["running_tests"], 0, 1, phase="testing")
        self._update_phase("running_tests")

        try:
            result = await runner.run_tests()
            
            summary = {
                "success": result.success,
                "total": result.total_tests,
                "passed": result.passed,
                "failed": result.failed,
                "errors": result.errors,
                "failed_tests": result.failed_tests,
                "logs_preview": result.logs[:1000]  # 仅返回日志前 1000 字符给前端
            }

            self._report_progress(
                PROGRESS_LABELS.get("tests_finished", "测试完成"),
                1, 1,
                phase="testing",
                **summary
            )

            # 如果测试失败，记录结果但不进行自动修复（根据用户需求）
            if not result.success:
                self.warnings.append(f"测试失败，按用户要求不进行自动修复: {result.logs[:200]}")
                self._report_progress(PROGRESS_LABELS["tests_failed_recovering"], 1, 1, phase="testing")

            return summary
        except Exception as e:
            logger.error(f"测试执行异常: {e}")
            return {"success": False, "message": str(e)}

    async def _generate_files_small_project(
        self,
        file_plan: List[Dict],
        project_context: Dict,
        total_files: int
    ):
        """小项目：所有文件并发+生成（无依赖关系）"""
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)

        async def generate_with_semaphore(file_info: Dict) -> Dict:
            async with semaphore:
                return await self._generate_single_file(file_info, project_context, total_files)

        tasks = [generate_with_semaphore(fi) for fi in file_plan]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                self.errors.append(f"文件生成异常: {str(result)}")
            elif result:
                self.generated_files.append(result)

    async def _generate_files_by_dep_layers(
        self,
        file_plan: List[Dict],
        project_context: Dict,
        total_files: int,
        dep_graph: DependencyGraph
    ):
        """中大项目：按依赖分层并发，同一层内文件无依赖关系可并行"""
        layers = dep_graph.get_generation_layers()
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)

        # file_plan 路径到信息的映射
        file_info_map: Dict[str, Dict] = {fi.get("path", ""): fi for fi in file_plan}

        for layer_idx, layer in enumerate(layers):
            layer_files = [f for f in layer if f in file_info_map]
            if not layer_files:
                continue

            self._report_progress(
                PROGRESS_LABELS.get("starting_layer", "开始生成分层文件"),
                len(self.generated_files) + 1,
                total_files + 4,
                layer=layer_idx + 1,
                total_layers=len(layers),
                files_in_layer=len(layer_files)
            )

            async def generate_with_semaphore(file_path: str) -> Dict:
                async with semaphore:
                    fi = file_info_map.get(file_path, {"path": file_path, "description": f"生成 {file_path}"})
                    return await self._generate_single_file(fi, project_context, total_files, self._generated_contents)

            tasks = [generate_with_semaphore(fp) for fp in layer_files]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    self.errors.append(f"文件生成异常: {str(result)}")
                elif result:
                    self.generated_files.append(result)
                    # 记录实际内容供后续层注入上下文
                    try:
                        full_path = self.output_dir / result["path"]
                        if full_path.exists():
                            self._generated_contents[result["path"]] = full_path.read_text(encoding="utf-8")
                    except Exception:
                        pass

    async def _generate_files_large_project(
        self,
        file_plan: List[Dict],
        project_context: Dict,
        total_files: int
    ):
        """中大项目：按优先级分层并发，低优先级依赖高优先级"""
        # 按优先级分组
        priority_groups: Dict[int, List[Dict]] = {}
        for fi in file_plan:
            p = fi.get("priority", 3)
            if p not in priority_groups:
                priority_groups[p] = []
            priority_groups[p].append(fi)

        sorted_priorities = sorted(priority_groups.keys())
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)
        generated_contents: Dict[str, str] = {}  # 记录已生成文件内容

        for priority in sorted_priorities:
            group = priority_groups[priority]
            group_size = len(group)

            self._report_progress(
                "starting_layer",
                len(self.generated_files) + 1,
                total_files + 4,
                priority=priority,
                files_in_layer=group_size
            )

            async def generate_with_semaphore(file_info: Dict) -> Dict:
                async with semaphore:
                    return await self._generate_single_file(file_info, project_context, total_files, generated_contents)

            tasks = [generate_with_semaphore(fi) for fi in group]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    self.errors.append(f"文件生成异常: {str(result)}")
                elif result:
                    self.generated_files.append(result)
                    # 记录内容供后续层参考
                    generated_contents[result["path"]] = result.get("size", 0)

    async def _generate_single_file(
        self,
        file_info: Dict,
        project_context: Dict,
        total_files: int,
        generated_contents: Optional[Dict] = None
    ) -> Optional[Dict]:
        """生成单个文件（带验证、审查、人机协作）"""
        file_path = file_info.get("path", "")
        description = file_info.get("description", "")
        priority = file_info.get("priority", 3)

        self._report_progress(
            PROGRESS_LABELS["generating_file"],
            len(self.generated_files) + 1,
            total_files + 4,
            file_path=file_path,
            description=description,
            model=self._select_model_for_file(file_path)
        )

        # 选择工程师
        engineer = self._select_engineer(file_path)
        role_name = engineer.name if hasattr(engineer, 'name') else '工程师'
        
        self._report_thinking(
            "engineer",
            f"{role_name} 正在分析 {file_path} 的需求：{description[:80]}{'...' if len(description) > 80 else ''}"
        )
        
        # 获取预防性提示（基于历史修复经验，向量化匹配）
        prevention_prompt = ""
        if self.feedback_learner:
            file_type = "frontend" if self._is_frontend_file(file_path) else "backend"
            prevention_prompt = await self.feedback_learner.get_prevention_prompt(
                file_path=file_path,
                file_type=file_type,
                project_context=project_context
            )

        content = await engineer.generate_file(file_path, description, project_context)

        if not content:
            # Fallback: 使用 ReAct Agent 尝试生成
            self._report_progress(
                PROGRESS_LABELS["react_fallback"],
                len(self.generated_files) + 1,
                total_files + 4,
                file_path=file_path
            )
            content = await self._react_generate_file(file_path, description, project_context)
            if not content:
                self.errors.append(f"文件生成失败（含 ReAct Fallback）: {file_path}")
                return None

        # 清理代码块标记
        content = self._clean_code_block(content)

        # 人机协作：关键文件暂停等待确认
        if self.require_approval and self._is_critical_file(file_path):
            self._report_progress(
                PROGRESS_LABELS["pause_for_approval"],
                len(self.generated_files) + 1,
                total_files + 4,
                file_path=file_path,
                description=description,
                content_preview=content[:200]
            )
            # 等待用户确认
            approved = await self._wait_for_approval(file_path)
            if not approved:
                self._report_progress(
                    PROGRESS_LABELS["file_rejected"],
                    len(self.generated_files) + 1,
                    total_files + 4,
                    file_path=file_path
                )
                self.warnings.append(f"文件被用户拒绝: {file_path}")
                return {
                    "path": file_path,
                    "description": description,
                    "success": False,
                    "size": 0,
                    "rejected_by_user": True
                }

        # 验证和审查（并发执行）
        if self.enable_validation or self.enable_review:
            success, content = await self._validate_and_review_file(
                file_path=file_path,
                content=content,
                description=description
            )
            if not success:
                self.warnings.append(f"文件验证未完全通过: {file_path}")

        # 写入文件
        full_path = self.output_dir / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)

        # 文件级流式推送：生成完成立即推送
        self._report_progress(
            PROGRESS_LABELS["file_generated"],
            len(self.generated_files) + 1,
            total_files + 4,
            file_path=file_path,
            description=description,
            size=len(content),
            content_preview=content[:300]
        )

        # API 一致性检查（前后端文件都生成后执行）
        if self.api_contract_checker and self._should_check_api_consistency(file_path):
            await self._check_and_report_api_issues(file_path, content)

        # 记录修复数据
        if self.feedback_learner and self.error_recovery:
            for fix_attempt in self.error_recovery.fix_history:
                if fix_attempt.file_path == str(full_path):
                    self.feedback_learner.record_fix(
                        file_path=file_path,
                        file_type="frontend" if self._is_frontend_file(file_path) else "backend",
                        original_content="",
                        fixed_content=content,
                        errors={"validation_error": [fix_attempt.error_message]},
                        model_name=self._select_model_for_file(file_path),
                        success=fix_attempt.fix_applied
                    )

        return {
            "path": file_path,
            "description": description,
            "success": True,
            "size": len(content)
        }

    def _is_frontend_file(self, file_path: str) -> bool:
        """判断是否为前端文件"""
        ext = Path(file_path).suffix.lower()
        return ext in {'.vue', '.js', '.jsx', '.ts', '.tsx', '.html', '.css', '.scss', '.sass', '.less'}

    def _is_critical_file(self, file_path: str) -> bool:
        """判断是否为关键文件（需要人工审批）"""
        critical_patterns = [
            'main.py', 'app.py', 'server.py',
            'config.py', 'settings.py',
            'database.py', 'models.py',
            'auth.py', 'security.py',
            'middleware.py',
        ]
        basename = Path(file_path).name
        return basename in critical_patterns

    async def _wait_for_approval(self, key: str, timeout: float = 300.0) -> bool:
        """
        等待用户审批（带超时机制）

        Args:
            key: 审批标识（文件路径或其他标识，如 "cost_estimation"）
            timeout: 超时时间（秒），默认 5 分钟

        Returns:
            True: 批准，False: 拒绝或超时
        """
        if not self.approval_callback:
            return True  # 没有回调，默认批准

        try:
            # 使用 asyncio.wait_for 设置超时
            approved = await asyncio.wait_for(
                self.approval_callback(key),
                timeout=timeout
            )
            return approved
        except asyncio.TimeoutError:
            logger.warning(f"审批超时（{timeout}s）: {key}，自动跳过")
            self.warnings.append(f"审批超时，自动跳过: {key}")
            return False  # 超时视为拒绝

    def _select_model_for_file(self, file_path: str) -> str:
        """根据文件类型选择模型"""
        ext = Path(file_path).suffix.lower()
        if ext in {'.vue', '.js', '.jsx', '.ts', '.tsx', '.html', '.css', '.scss', '.sass', '.less'}:
            return self.model_assignment.frontend_model if self.model_assignment else "Qwen/Qwen2.5-7B-Instruct"
        elif ext in {'.py', '.go', '.java', '.rs', '.rb', '.php'}:
            return self.model_assignment.backend_model if self.model_assignment else "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B"
        else:
            return self.model_assignment.frontend_model if self.model_assignment else "Qwen/Qwen3-8B"

    def _select_engineer(self, file_path: str) -> Specialist:
        """根据文件类型选择工程师"""
        ext = Path(file_path).suffix.lower()
        frontend_ext = {'.vue', '.js', '.jsx', '.ts', '.tsx', '.html', '.css', '.scss', '.sass', '.less'}
        if ext in frontend_ext or file_path.endswith(('.vue', '.html')):
            return self.frontend_engineer
        return self.backend_engineer

    async def _react_generate_file(
        self,
        file_path: str,
        description: str,
        project_context: Dict
    ) -> Optional[str]:
        """
        使用 ReAct Agent 模式生成文件（作为常规生成的 fallback）

        当工程师生成失败或返回空内容时，使用更结构化的 ReAct 模式重新生成。
        """
        try:
            requirement = project_context.get("requirement", "")
            architecture = project_context.get("architecture", {})
            tech_stack = architecture.get("tech_stack", [])

            system_prompt = (
                f"你是一个专业的软件工程师。你需要生成一个文件: {file_path}\n"
                f"项目技术栈: {', '.join(tech_stack)}\n"
                f"文件描述: {description}\n\n"
                "请按照以下步骤思考和生成：\n"
                "1. 分析需求：理解文件的目的和职责\n"
                "2. 设计结构：确定类/函数的结构和关系\n"
                "3. 编写代码：生成完整的、可运行的代码\n"
                "4. 自我审查：检查代码是否有错误\n\n"
                "直接输出代码，不要解释。"
            )

            user_prompt = (
                f"项目需求: {requirement[:500]}\n\n"
                f"请生成文件 {file_path}。"
            )

            response = await call_siliconflow(
                prompt=user_prompt,
                model="Qwen/Qwen3.5-4B",
                max_tokens=4096,
                temperature=0.4,
                system_prompt=system_prompt
            )
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            return self._clean_code_block(content) if content else None

        except Exception as e:
            logger.error(f"ReAct fallback 生成失败 ({file_path}): {e}")
            return None

    async def _validate_and_review_file(
        self,
        file_path: str,
        content: str,
        description: str
    ) -> Tuple[bool, str]:
        """验证并审查文件（带内容级缓存）"""
        full_path = self.output_dir / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # 检查验证缓存（相同内容跳过重复验证）
        content_hash = CodeValidator._compute_content_hash(content)
        cache_key = f"{file_path}:{content_hash}"
        cached_result = self.validator._validation_cache.get(cache_key) if self.validator else None
        if cached_result:
            self._report_progress(
                "validation_cache_hit",
                0, 0,
                file_path=file_path
            )
            return True, content

        # 先写入文件供验证
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)

        # 错误恢复循环
        if self.enable_error_recovery:
            success, content = await self.error_recovery.validate_and_fix(
                file_path=full_path,
                content=content,
                file_description=description,
                backend_model=self.model_assignment.backend_model if self.model_assignment else "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
                callback=self.callback
            )
            if success:
                # 重新写入修复后的内容
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                # 更新缓存 key（内容已变）
                content_hash = CodeValidator._compute_content_hash(content)
                cache_key = f"{file_path}:{content_hash}"

        # 代码审查（小项目跳过审查以提升速度）
        if self.enable_review and self.complexity.level not in (ProjectComplexity.SIMPLE,):
            review_result = await self.reviewer.review_code(
                code=content,
                file_path=file_path,
                context=description
            )
            if review_result.get("needs_fix") and review_result.get("risk_level") in ["high", "medium"]:
                self.warnings.append(
                    f"审查建议 {file_path}: {'; '.join(review_result.get('issues', []))}"
                )

        # 缓存验证结果（轻量级：只缓存语法检查结果）
        if self.validator and file_path.endswith('.py'):
            try:
                import ast
                ast.parse(content)
                self.validator._validation_cache[cache_key] = {
                    "is_valid": True,
                    "syntax_errors": [],
                    "import_errors": []
                }
                CodeValidator._clear_old_cache()
            except Exception:
                pass

        return True, content

    def _clean_code_block(self, content: str) -> str:
        """清理代码块标记"""
        # 移除 markdown 代码块标记
        pattern = r'```(?:\w+)?\s*(.*?)\s*```'
        match = re.search(pattern, content, re.DOTALL)
        if match:
            return match.group(1).strip()
        return content.strip()

    def _select_alternative_model(self, primary_model: str) -> str:
        """为交叉验证选择备选模型"""
        alt_map = {
            "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B": "Qwen/Qwen2.5-7B-Instruct",
            "Qwen/Qwen2.5-7B-Instruct": "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
            "Qwen/Qwen3-8B": "Qwen/Qwen2.5-7B-Instruct",
            "Qwen/Qwen3.5-4B": "Qwen/Qwen3-8B",
            "THUDM/GLM-Z1-9B-0414": "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
        }
        return alt_map.get(primary_model, "Qwen/Qwen2.5-7B-Instruct")

    def _select_engineer_for_model(self, model_name: str) -> Specialist:
        """为指定模型创建工程师实例"""
        ext = ".py"  # 默认后端工程师
        frontend_models = {"Qwen/Qwen3.5-4B", "Qwen/Qwen2.5-7B-Instruct", "Qwen/Qwen3-8B"}
        if model_name in frontend_models:
            return self.frontend_engineer
        return self.backend_engineer

    async def _save_to_memory(self, requirement: str, architecture: Dict):
        """保存生成记录到记忆系统"""
        if not self.memory_enabled:
            return

        try:
            from app.agent.memory import MemoryEntry

            # 保存到对话记忆
            entry = MemoryEntry(
                type="project_generation",
                content=f"需求: {requirement[:500]}\n架构: {json.dumps(architecture, ensure_ascii=False)[:1000]}",
                importance=0.8
            )
            self.conversation_memory.add(entry)

            # 保存到知识记忆
            tech_stack = architecture.get("tech_stack", [])
            for tech in tech_stack[:5]:
                tech_entry = MemoryEntry(
                    type="tech_stack",
                    content=f"项目使用了 {tech} 技术栈",
                    importance=0.7,
                    metadata={"source": "orchestrator_generation", "category": "tech_stack"}
                )
                self.knowledge_memory.add(tech_entry)
        except Exception as e:
            logger.error(f"保存记忆失败: {e}")

    # ==================== Spec-First 工作流 ====================

    async def generate_with_spec_first(
        self,
        requirement: str,
        callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        使用 Spec-First 策略生成项目

        工作流程：
        1. 分析需求复杂度
        2. 生成规范（OpenAPI、类型定义、数据库 Schema）
        3. 构建依赖图
        4. 按依赖顺序生成文件
        5. 每个文件经过迭代修复循环
        6. 最终验证

        这是推荐的新方法，比传统的 generate 方法有更好的代码质量。
        """
        start_time = time.time()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 重置状态（支持多次调用）
        self.generated_files = []
        self.errors = []
        self.warnings = []

        # Step 1: 初始化组件和分析复杂度
        await self._initialize_components(requirement)

        # 创建共享上下文
        ctx = SharedContext(requirement, self.output_dir)
        ctx.complexity = {
            "level": self.complexity.level.value,
            "estimated_files": self.complexity.estimated_files,
            "has_frontend": self.complexity.has_frontend,
            "has_backend": self.complexity.has_backend,
            "has_database": self.complexity.has_database,
            "key_technologies": self.complexity.key_technologies
        }
        ctx.model_assignment = {
            "architect_model": self.model_assignment.architect_model,
            "frontend_model": self.model_assignment.frontend_model,
            "backend_model": self.model_assignment.backend_model,
            "reviewer_model": self.model_assignment.reviewer_model,
            "fallback_model": self.model_assignment.fallback_model
        }

        self._report_progress("context_initialized", 1, 6, callback=callback)

        # Step 2: Spec-First 生成规范
        spec_generator = SpecFirstGenerator(ctx)
        specs_success = await spec_generator.generate_all_specs(
            requirement, ctx.complexity, callback
        )

        if not specs_success:
            self._report_progress("specs_failed", 2, 6, callback=callback)
            # 即使规范生成失败，也继续尝试生成项目
        else:
            self._report_progress("specs_completed", 2, 6, callback=callback)

        # Step 3: 架构设计（获取文件计划）
        architecture = await self.architect.design_architecture(requirement, self.complexity)
        file_plan = architecture.get("file_plan", [])

        self._report_progress(
            "architecture_design", 3, 6,
            file_count=len(file_plan),
            callback=callback
        )

        # Step 4: 构建依赖图
        dep_graph = DependencyGraph()
        dep_graph.build_from_architecture(architecture)

        # 如果规范生成成功，也根据规范补充依赖图
        if specs_success:
            dep_graph.build_from_specs(ctx.specs)

        generation_order = dep_graph.get_generation_order()
        ctx.set_metric("generation_order", generation_order)

        self._report_progress(
            "dependency_graph_built", 4, 6,
            files_in_order=len(generation_order),
            callback=callback
        )

        # Step 5: 按依赖分层并行生成文件
        refinement_loop_instance = RefinementLoop(ctx)
        generated_contents: Dict[str, str] = {}
        files_generated = 0
        files_failed = 0

        # 准备项目上下文
        project_context = {
            "requirement": requirement,
            "architecture": architecture,
            "complexity": ctx.complexity,
            "output_dir": str(self.output_dir)
        }

        # 确保所有文件计划中的文件都在依赖图中
        for file_info in file_plan:
            path = file_info.get("path", "")
            if path and path not in dep_graph.nodes:
                dep_graph.add_file(path, priority=file_info.get("priority", 3))

        # 获取分层生成顺序（同一层内无依赖关系，可并行）
        layers = dep_graph.get_generation_layers()
        total_files = sum(len(layer) for layer in layers)
        ctx.set_metric("generation_layers", len(layers))
        ctx.set_metric("generation_order", [f for layer in layers for f in layer])

        self._report_progress(
            "dependency_graph_built", 4, 6,
            files_in_order=total_files,
            parallel_layers=len(layers),
            callback=callback
        )

        # 使用 asyncio.Lock 保护共享状态
        state_lock = asyncio.Lock()

        # 创建交叉验证器
        cross_validator = CrossValidator(ctx)

        async def generate_single_file(
            file_path: str,
            file_index: int
        ) -> Dict[str, Any]:
            """生成单个文件（可并行调用）"""
            file_node = dep_graph.nodes.get(file_path)
            description = file_node.description if file_node else f"生成 {file_path}"
            file_type = file_node.file_type if file_node else "unknown"

            engineer = self._select_engineer(file_path)
            model_name = self._select_model_for_file(file_path)

            self._report_progress(
                "generating_file",
                4 + file_index,
                total_files + 5,
                file_path=file_path,
                file_type=file_type,
                model=model_name,
                callback=callback
            )

            # 构建增强的 prompt（包含规范和依赖文件上下文）
            spec_context = spec_generator.get_spec_context_for_file(file_path, file_type)
            dep_context = dep_graph.get_context_for_file(file_path, generated_contents)

            initial_content = await engineer.generate_file(file_path, description, project_context)
            if not initial_content:
                return {"path": file_path, "success": False, "error": "生成返回空内容"}

            initial_content = self._clean_code_block(initial_content)

            # 关键文件使用交叉验证
            if cross_validator.is_critical_file(file_path, file_type):
                self._report_progress(
                    "cross_validation",
                    4 + file_index,
                    total_files + 5,
                    file_path=file_path,
                    callback=callback
                )

                # 使用另一个模型独立生成
                alt_model = self._select_alternative_model(model_name)
                alt_engineer = self._select_engineer_for_model(alt_model)
                alt_content = await alt_engineer.generate_file(file_path, description, project_context)
                if alt_content:
                    alt_content = self._clean_code_block(alt_content)

                    judge_model = self.model_assignment.reviewer_model if self.model_assignment else "THUDM/GLM-Z1-9B-0414"

                    result = await cross_validator.cross_validate_with_refinement(
                        file_path=file_path,
                        file_type=file_type,
                        description=description,
                        content_a=initial_content,
                        model_a=model_name,
                        content_b=alt_content,
                        model_b=alt_model,
                        judge_model=judge_model,
                        refinement_loop=refinement_loop_instance,
                        project_context=project_context,
                        callback=callback
                    )
                else:
                    # 备选生成失败，降级到普通流程
                    result = await refinement_loop_instance.refine(
                        file_path=file_path,
                        file_type=file_type,
                        description=description,
                        initial_content=initial_content,
                        model_name=model_name,
                        project_context=project_context,
                        callback=callback
                    )
            else:
                # 普通文件：直接迭代修复
                result = await refinement_loop_instance.refine(
                    file_path=file_path,
                    file_type=file_type,
                    description=description,
                    initial_content=initial_content,
                    model_name=model_name,
                    project_context=project_context,
                    callback=callback
                )

            final_content = result.final_content

            # 写入文件
            full_path = self.output_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(final_content)

            return {
                "path": file_path,
                "description": description,
                "success": result.success,
                "size": len(final_content),
                "refinement_attempts": result.attempts,
                "issues_fixed": result.issues_fixed,
                "content": final_content,
                "model_name": model_name,
                "validation_passed": result.success,
                "validation_issues": [f"{i.type}: {i.message}" for i in result.remaining_issues]
            }

        # 逐层并行生成
        current_index = 0
        for layer_idx, layer in enumerate(layers):
            layer_size = len(layer)

            self._report_progress(
                "starting_layer",
                4 + current_index,
                total_files + 5,
                layer=layer_idx + 1,
                total_layers=len(layers),
                files_in_layer=layer_size,
                callback=callback
            )

            # 并行生成当前层的所有文件
            tasks = [
                generate_single_file(file_path, current_index + i)
                for i, file_path in enumerate(layer)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 处理结果
            for i, result in enumerate(results):
                file_path = layer[i]
                if isinstance(result, Exception):
                    self.errors.append(f"文件生成异常: {file_path} - {str(result)}")
                    ctx.add_error(f"文件生成异常: {file_path}")
                    files_failed += 1
                    continue

                if not result.get("success"):
                    self.errors.append(f"文件生成失败: {file_path}")
                    ctx.add_error(f"文件生成失败: {file_path}")
                    files_failed += 1
                    continue

                # 更新共享状态（加锁保护）
                async with state_lock:
                    content = result.pop("content")
                    model_name = result.pop("model_name")
                    validation_issues = result.pop("validation_issues", [])

                    ctx.save_file_content(file_path, content, model_name)
                    ctx.update_file_validation(file_path, result["success"], validation_issues)
                    generated_contents[file_path] = content[:MAX_CONTENT_FOR_CONTEXT]

                    self.generated_files.append(result)
                    files_generated += 1

                    if not result["success"]:
                        ctx.add_warning(f"文件 {file_path} 验证未完全通过")
                        self.warnings.append(f"文件验证未完全通过: {file_path}")

            current_index += layer_size

        self._report_progress("files_generated", total_files + 4, total_files + 5, callback=callback)

        # Step 6: 最终验证
        final_validation = {}
        if self.enable_validation:
            final_validation = await self.validator.run_full_validation()

        # Step 7: 保存记忆
        if self.memory_enabled:
            await self._save_to_memory(requirement, architecture)

        elapsed = time.time() - start_time

        return {
            "success": files_failed == 0,
            "output_dir": self.output_dir.name,
            "total_files_created": files_generated,
            "total_files_failed": files_failed,
            "files": self.generated_files,
            "complexity": self.complexity.level.value if self.complexity else "unknown",
            "models_used": {
                "architect": self.model_assignment.architect_model if self.model_assignment else "N/A",
                "frontend": self.model_assignment.frontend_model if self.model_assignment else "N/A",
                "backend": self.model_assignment.backend_model if self.model_assignment else "N/A",
                "reviewer": self.model_assignment.reviewer_model if self.model_assignment else "N/A",
            },
            "specs_generated": list(ctx.specs.keys()),
            "validation": final_validation,
            "errors": self.errors,
            "warnings": self.warnings,
            "elapsed_time": elapsed,
            "context_summary": ctx.get_summary(),
            "context_full": ctx.to_export_dict()
        }

    def _build_enhanced_prompt(
        self,
        file_path: str,
        description: str,
        project_context: Dict,
        spec_context: str,
        dep_context: str,
        file_type: str
    ) -> str:
        """构建增强的代码生成 prompt，包含规范和依赖上下文"""
        parts = [
            f"请创建以下文件：",
            f"",
            f"## 文件信息",
            f"- 路径: {file_path}",
            f"- 类型: {file_type}",
            f"- 描述: {description}",
            f"",
        ]

        if spec_context:
            parts.append(f"## 相关规范\n{spec_context}\n")

        if dep_context:
            parts.append(f"## 依赖文件内容\n{dep_context}\n")

        parts.append(f"## 项目上下文\n{json.dumps(project_context, ensure_ascii=False, indent=2)}\n")

        parts.append(f"请返回完整的文件内容，不要省略任何部分。")

        return "\n".join(parts)

    def _should_check_api_consistency(self, file_path: str) -> bool:
        """判断是否应该执行 API 一致性检查"""
        ext = Path(file_path).suffix.lower()
        # 仅对前端 API 调用文件或后端路由文件执行检查
        if ext in {'.vue', '.js', '.jsx', '.ts', '.tsx'}:
            return True
        if ext == '.py' and ('api' in file_path.lower() or 'route' in file_path.lower()):
            return True
        return False

    async def _check_and_report_api_issues(self, file_path: str, content: str):
        """执行 API 一致性检查并报告问题"""
        if not self.api_contract_checker:
            return

        is_frontend = self._is_frontend_file(file_path)

        # 收集对应端的文件
        if is_frontend:
            # 前端文件生成后，检查与后端的一致性
            backend_files = {}
            for py_file in self.output_dir.rglob('*.py'):
                if '__pycache__' not in str(py_file):
                    try:
                        backend_files[str(py_file.relative_to(self.output_dir))] = py_file.read_text()
                    except Exception:
                        pass

            issues = self.api_contract_checker.check_single_file_consistency(
                file_path=file_path,
                code=content,
                is_frontend=True,
                counterpart_files=backend_files
            )
        else:
            # 后端文件生成后，检查与前端的一致性
            frontend_files = {}
            for ext in ['*.vue', '*.js', '*.jsx', '*.ts', '*.tsx']:
                for f in self.output_dir.rglob(ext):
                    try:
                        frontend_files[str(f.relative_to(self.output_dir))] = f.read_text()
                    except Exception:
                        pass

            issues = self.api_contract_checker.check_single_file_consistency(
                file_path=file_path,
                code=content,
                is_frontend=False,
                counterpart_files=frontend_files
            )

        # 推送一致性问题
        for issue in issues:
            self._report_progress(
                "api_consistency_issue",
                len(self.generated_files) + 1,
                len(self.generated_files) + 5,
                issue_type=issue.issue_type,
                severity=issue.severity,
                message=issue.message,
                suggestion=issue.suggestion,
                file_path=file_path
            )
            if issue.severity == 'error':
                self.errors.append(f"API 不一致: {issue.message}")
            else:
                self.warnings.append(f"API 警告: {issue.message}")

    def _should_use_patch_mode(self, incremental_plan: List[Dict], requirement: str) -> bool:
        """
        判断是否应该使用 patch 模式

        Patch 模式适用于：
        1. 变更文件数量少（<=3 个）
        2. 需求描述是局部变更（如"添加 xx 功能"、"修改 xx"）
        3. 文件已存在
        """
        if len(incremental_plan) > 3:
            return False

        patch_keywords = ['添加', '增加', '修改', '更新', '删除', '移除', '调整', '优化', '修复']
        is_patch_request = any(kw in requirement for kw in patch_keywords)

        if not is_patch_request:
            return False

        # 检查文件是否已存在
        existing_count = 0
        for file_info in incremental_plan:
            file_path = self.output_dir / file_info.get("path", "")
            if file_path.exists():
                existing_count += 1

        return existing_count == len(incremental_plan)

    async def _apply_patches_incremental(
        self,
        requirement: str,
        incremental_plan: List[Dict],
        project_context: Dict,
        total_files: int
    ):
        """使用 patch 模式应用增量变更"""
        for file_info in incremental_plan:
            file_path = file_info.get("path", "")
            description = file_info.get("description", "")
            full_path = self.output_dir / file_path

            if not full_path.exists():
                # 新文件，使用全量生成
                result = await self._generate_single_file(file_info, project_context, total_files)
                if result:
                    self.generated_files.append(result)
                continue

            # 读取原始内容
            original_content = full_path.read_text(encoding='utf-8')

            self._report_progress(
                "applying_patch",
                len(self.generated_files) + 1,
                total_files + 4,
                file_path=file_path,
                description=description,
                mode="patch"
            )

            # 生成并应用 patch
            result = await apply_incremental_change(
                file_path=full_path,
                change_request=description,
                llm_call_fn=self._call_llm_for_patch,
                project_context=project_context
            )

            if result.success:
                self.generated_files.append({
                    "path": file_path,
                    "description": description,
                    "success": True,
                    "size": len(result.patched_content),
                    "mode": "patch",
                    "diff_preview": result.diff[:200]
                })

                self._report_progress(
                    "patch_applied",
                    len(self.generated_files),
                    total_files + 4,
                    file_path=file_path,
                    lines_changed=result.diff.count('\n+') + result.diff.count('\n-')
                )
            else:
                self.errors.append(f"Patch 应用失败: {file_path} - {', '.join(result.errors)}")
                # 降级到全量生成
                self.warnings.append(f"降级到全量生成: {file_path}")
                result = await self._generate_single_file(file_info, project_context, total_files)
                if result:
                    self.generated_files.append(result)

    async def _call_llm_for_patch(self, prompt: str, system_prompt: str) -> str:
        """调用 LLM 生成 patch（供 CodePatcher 使用）"""
        try:
            # 使用后端工程师生成 patch
            engineer = self.backend_engineer or self.architect
            if engineer:
                return await engineer.call_llm(prompt, system_prompt)
            return ""
        except Exception as e:
            logger.error(f"LLM patch 调用失败: {e}")
            return ""

    def _estimate_generation_cost(self, architecture: Dict, file_plan: List[Dict]) -> Dict:
        """
        估算生成成本和提供降级建议

        成本等级：
        - low: < $0.01 (SIMPLE/SMALL 项目)
        - medium: $0.01 - $0.10 (MEDIUM 项目)
        - high: > $0.10 (LARGE/ENTERPRISE 项目)
        """
        estimated_files = len(file_plan)
        level = self.complexity.level.value if self.complexity else "unknown"

        # 基于复杂度等级的成本估算
        cost_estimates = {
            "simple": {"tokens": 5000, "cost_usd": 0.005},
            "small": {"tokens": 15000, "cost_usd": 0.015},
            "medium": {"tokens": 45000, "cost_usd": 0.045},
            "large": {"tokens": 100000, "cost_usd": 0.10},
            "enterprise": {"tokens": 250000, "cost_usd": 0.25}
        }

        estimate = cost_estimates.get(level, cost_estimates["medium"])

        # 确定成本等级和建议
        if estimate["cost_usd"] < 0.01:
            cost_level = "low"
            suggestion = "成本较低，可直接生成"
        elif estimate["cost_usd"] < 0.10:
            cost_level = "medium"
            suggestion = "成本适中，建议开启 review 提高质量"
        else:
            cost_level = "high"
            suggestion = f"成本较高（约 ${estimate['cost_usd']:.2f}），建议：1) 简化需求 2) 使用更便宜的模型 3) 分阶段生成"

        return {
            "estimated_tokens": estimate["tokens"],
            "estimated_cost_usd": estimate["cost_usd"],
            "cost_level": cost_level,
            "suggestion": suggestion,
            "level": level,
            "estimated_files": estimated_files
        }
