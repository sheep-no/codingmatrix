import time
import asyncio
import logging
from typing import Dict, Any, List

from app.utils.AiCodeUtil import get_embedding
from app.agent.api_contract_checker import generate_frontend_prompt_contract
from app.agent.dependency_graph import DependencyGraph
from app.agent.orchestrator_progress import PROGRESS_LABELS, MAX_CONCURRENT_LLM_CALLS
from app.agent.tracing import traced

logger = logging.getLogger(__name__)


class TraditionalGenerateMixin:

    @traced("orchestrator.traditional", attributes={"component": "orchestrator"})
    async def _generate_traditional(self, requirement: str) -> Dict[str, Any]:
        start_time = time.time()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.generated_files = []
        self.errors = []
        self.warnings = []

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

                if cached and cached.architecture and self.reviewer:
                    review_passed = await self._cache_review_gate(cached)
                    if not review_passed:
                        logger.warning(f"缓存架构审查未通过，重新生成")
                        self.warnings.append("缓存命中但审查闸门拦截，重新生成")
                        cached = None

        await self._initialize_components(requirement)

        self._association_result = await self._generate_requirement_associations(
            requirement, self.complexity.level.value
        )
        if not self._association_result.skipped and self._association_result.enhanced_requirement:
            requirement = self._association_result.enhanced_requirement

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

            project_type = architecture.get("project_type", "")
            tech_stack = architecture.get("tech_stack", [])
            self._report_thinking(
                "architect",
                f"架构设计完成。项目类型：{project_type}，技术栈：{', '.join(tech_stack[:3])}，共规划 {len(file_plan)} 个文件。"
            )

        file_plan = self._validate_file_plan(file_plan)

        cost_analysis = self._estimate_generation_cost(architecture, file_plan)
        self._report_progress(
            PROGRESS_LABELS["cost_estimation"],
            3, 5,
            estimated_tokens=cost_analysis["estimated_tokens"],
            estimated_cost_usd=cost_analysis["estimated_cost_usd"],
            cost_level=cost_analysis["cost_level"],
            suggestion=cost_analysis["suggestion"]
        )

        if self.require_approval and cost_analysis["cost_level"] == "high":
            self._report_progress(
                "pause_for_cost_approval",
                3, 5,
                estimated_cost_usd=cost_analysis["estimated_cost_usd"],
                suggestion=cost_analysis["suggestion"]
            )
            approved = await self._wait_for_approval("cost_estimation", timeout=300.0)
            if not approved:
                self.warnings.append("用户拒绝高成本生成，已取消")
                return {
                    "success": False,
                    "cancelled_by_user": True,
                    "reason": "cost_too_high",
                    "cost_analysis": cost_analysis
                }

        if self.session_manager and self.session_id:
            if self.incremental:
                self._session_state = await self.session_manager.resume_session(self.session_id)
                if not self._session_state:
                    self._session_state = await self.session_manager.create_session(
                        requirement=requirement,
                        output_dir=str(self.output_dir),
                        architecture=architecture,
                        file_plan=file_plan,
                        session_id=self.session_id
                    )
            else:
                self._session_state = await self.session_manager.create_session(
                    requirement=requirement,
                    output_dir=str(self.output_dir),
                    architecture=architecture,
                    file_plan=file_plan,
                    session_id=self.session_id
                )

        api_contract_prompt = ""
        if self.api_contract_checker:
            backend_files = {}
            for py_file in self.output_dir.rglob('*.py'):
                if '__pycache__' not in str(py_file):
                    try:
                        backend_files[str(py_file.relative_to(self.output_dir))] = py_file.read_text()
                    except Exception:
                        pass

            if backend_files:
                api_contract_prompt = generate_frontend_prompt_contract(backend_files)

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

        for file_info in file_plan:
            path = file_info.get("path", "")
            if path and path not in dep_graph.nodes:
                dep_graph.add_file(path, priority=file_info.get("priority", 3))

        project_context = {
            "requirement": requirement,
            "architecture": architecture,
            "complexity": self.complexity.level.value,
            "output_dir": str(self.output_dir),
            "api_contract": api_contract_prompt
        }

        total_files = len(file_plan)

        if self.incremental and self.session_id:
            await self._handle_incremental_generation(
                requirement, file_plan, project_context, total_files
            )
        elif total_files <= 5:
            await self._generate_files_small_project(file_plan, project_context, total_files)
        else:
            await self._generate_files_by_dep_layers(file_plan, project_context, total_files, dep_graph)

        final_validation = {}
        test_results = {"success": True, "message": "未运行动态测试"}
        save_memory_task = None
        if self.memory_enabled:
            save_memory_task = asyncio.create_task(self._save_to_memory(requirement, architecture))

        if self.enable_validation:
            final_validation = await self.validator.run_full_validation()

        if final_validation.get("is_valid", False):
            from app.agent.test_runner import IsolatedTestRunner
            test_runner = IsolatedTestRunner(self.output_dir)
            test_results = await self._run_dynamic_tests(test_runner)
            if not test_results.get("success"):
                self.warnings.append(f"动态测试失败: {test_results.get('summary')}")
                react_result = await self._try_react_auto_fix(test_results)
                if react_result and react_result.get("fixed"):
                    test_results = react_result.get("test_results", test_results)
                    self.warnings.append("ReAct 自动修复已尝试应用")

        if save_memory_task:
            await save_memory_task

        if self.spec_cache and not cached:
            await self._cache_specs(requirement, architecture, file_plan, requirement_vector)

        if self.feedback_learner:
            await self._record_learning_data(requirement, architecture, file_plan)

        coverage_check = self._check_requirement_coverage(
            requirement, architecture, file_plan
        )

        elapsed = time.time() - start_time

        await self._git_save_snapshot(
            f"Agent 生成: {requirement[:80]}"
            if not self.incremental
            else f"Agent 增量修改: {requirement[:80]}"
        )

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
            "session_id": self.session_id,
            "requirement_coverage": coverage_check,
        }

        if coverage_check.get("checked") and coverage_check.get("uncovered"):
            uncovered_desc = ", ".join(
                u["item"] for u in coverage_check["uncovered"][:3]
            )
            self.warnings.append(
                f"需求覆盖率 {coverage_check['coverage_rate']:.0%}, "
                f"未覆盖项: {uncovered_desc}"
            )

        try:
            domain = self._association_result.domain_matched if hasattr(self, '_association_result') and self._association_result else ""
            await self._extract_and_save_feature_list(
                requirement, self.generated_files, domain
            )
        except Exception as e:
            logger.warning(f"功能清单提取失败(非阻塞): {e}")

        return result