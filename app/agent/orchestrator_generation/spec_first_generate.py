import time
import asyncio
import logging
from typing import Optional, Dict, Any, Callable

from app.agent.spec_first_generator import SpecFirstGenerator
from app.agent.refinement_loop import RefinementLoop
from app.agent.dependency_graph import DependencyGraph
from app.agent.cross_validator import CrossValidator
from app.agent.shared_context import SharedContext
from app.agent.topology_scheduler import TopologyScheduler
from app.agent.critical_decision import CriticalDecisionExtractor
from app.agent.global_constraint import GlobalConstraintParser
from app.agent.architecture_inspector import ArchitectureInspector
from app.agent.orchestrator_progress import MAX_CONTENT_FOR_CONTEXT
from app.agent.adapters import LanguageAdapterRegistry
from app.agent.dynamic_model_router import get_context_length
from app.agent.utils import extract_engineer_content, write_file_atomic, cleanup_temp_files

logger = logging.getLogger(__name__)


class SpecFirstGenerateMixin:

    async def generate_with_spec_first(
        self,
        requirement: str,
        callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        start_time = time.time()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.generated_files = []
        self.errors = []
        self.warnings = []

        await self._initialize_components(requirement)

        self._association_result = await self._generate_requirement_associations(
            requirement, self.complexity.level.value
        )
        if not self._association_result.skipped and self._association_result.enhanced_requirement:
            self._report_progress(
                "requirement_association",
                1, 6,
                callback=callback,
                domain=self._association_result.domain_matched,
                items_count=len(self._association_result.items),
                history_matched=self._association_result.history_matched_count
            )
            requirement = self._association_result.enhanced_requirement

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
        self._report_step_detail("项目上下文已加载（复杂度、模型分配、技术栈）", category="初始化")

        # 提前检测语言，用于规范生成
        from app.agent.language_detector import LanguageDetector
        lang_result = LanguageDetector.detect(requirement)
        detected_language = lang_result.language
        logger.info(f"语言检测: {detected_language} (置信度: {lang_result.confidence:.2f})")

        spec_generator = SpecFirstGenerator(ctx, language=detected_language, api_key_token=self.api_key_token)
        specs_success = await spec_generator.generate_all_specs(
            requirement, ctx.complexity, callback
        )

        if not specs_success:
            self._report_progress("specs_failed", 2, 6, callback=callback)
            self._report_step_detail("规格书生成失败，将回退到默认架构", category="规格书")
        else:
            self._report_progress("specs_completed", 2, 6, callback=callback)
            self._report_step_detail("规格书已生成（API 契约 + 数据模型）", category="规格书")

        architecture = await self.architect.design_architecture(requirement, self.complexity)
        file_plan = architecture.get("file_plan", [])

        # 如果 file_plan 为空，使用默认架构
        if not file_plan:
            logger.warning("架构师未返回 file_plan，使用默认架构")
            architecture = self.architect._get_default_architecture(self.complexity)
            file_plan = architecture.get("file_plan", [])

        # 分批规划：如果 file_plan 文件数不足复杂度预期，自动扩展
        estimated_files = ctx.complexity.get("estimated_files", len(file_plan)) if isinstance(ctx.complexity, dict) else (ctx.complexity.estimated_files if ctx.complexity else len(file_plan))
        if len(file_plan) < estimated_files and estimated_files > 10:
            logger.info(f"分批规划触发：当前 {len(file_plan)} 个文件，预期 {estimated_files} 个")
            architecture = await self.architect.expand_file_plan(
                architecture, self.complexity, target_file_count=estimated_files,
                target_language=detected_language
            )
            file_plan = architecture.get("file_plan", [])
            logger.info(f"分批规划完成：最终 {len(file_plan)} 个文件")

        self._report_progress(
            "architecture_design", 3, 6,
            file_count=len(file_plan),
            callback=callback
        )

        constraint_parser = GlobalConstraintParser()
        global_constraints = constraint_parser.parse_requirement(requirement)
        ctx.set_metric("global_constraints", constraint_parser.get_constraints_summary())

        decision_extractor = CriticalDecisionExtractor()
        _ = decision_extractor.extract_from_architecture(
            architecture, ctx.complexity
        )
        decision_questions = decision_extractor.format_as_questions()
        ctx.set_metric("critical_decisions", decision_questions)

        if decision_questions:
            self._report_progress(
                "awaiting_user_decision", 4, 6,
                critical_decisions=decision_questions,
                callback=callback
            )
            # 等待用户决策并应用
            if self.decision_callback:
                try:
                    user_decisions = await asyncio.wait_for(
                        self.decision_callback(decision_questions),
                        timeout=120
                    )
                    if user_decisions and isinstance(user_decisions, dict):
                        decision_extractor.apply_user_choice(user_decisions)
                        logger.info(f"用户决策已应用: {user_decisions}")
                    else:
                        logger.warning("用户决策为空或格式错误，使用默认值")
                except asyncio.TimeoutError:
                    logger.warning("决策等待超时（120s），使用默认值继续")
                except Exception as e:
                    logger.error(f"获取用户决策失败: {e}，使用默认值")

        refinement_loop_instance = RefinementLoop(ctx, complexity=self.complexity.level.value if self.complexity else "medium", api_key_token=self.api_key_token)
        generated_contents: Dict[str, str] = {}
        files_generated = 0
        files_failed = 0

        project_context = {
            "requirement": requirement,
            "architecture": architecture,
            "complexity": ctx.complexity,
            "output_dir": str(self.output_dir)
        }

        constraint_prompt = constraint_parser.generate_prompt_fragment("all", "all")
        if constraint_prompt:
            project_context["global_constraints"] = constraint_prompt

        # 获取语言适配器
        detected_language = architecture.get("language", "python")
        language_adapter = LanguageAdapterRegistry.get_adapter(detected_language)
        logger.info(f"使用语言适配器: {language_adapter.language} (检测语言: {detected_language})")

        dep_graph = DependencyGraph(language_adapter=language_adapter)
        dep_graph.build_from_architecture(architecture)

        logger.info(f"依赖图构建完成: {len(dep_graph.nodes)} 个文件节点, file_plan={len(file_plan)} 个文件")

        layers = dep_graph.get_generation_layers()
        ctx.set_metric("generation_layers", len(layers))
        ctx.set_metric("generation_order", [f for layer in layers for f in layer])

        if hasattr(self, 'use_dynamic_topology') and self.use_dynamic_topology:
            result = await self._generate_with_dynamic_topology(
                ctx, dep_graph, spec_generator, architecture, requirement,
                project_context, generated_contents, callback, language_adapter
            )
            files_generated = result.get("files_generated", 0)
            files_failed = result.get("files_failed", 0)
            files_skipped = result.get("files_skipped", 0)
            self.generated_files = result.get("generated_files", [])
            self.errors.extend(result.get("errors", []))
            self.warnings.extend(result.get("warnings", []))
            total_files = result.get("total_files", 0)
        else:
            total_files = sum(len(layer) for layer in layers)
            files_skipped = 0

            self._report_progress(
                "dependency_graph_built", 4, 6,
                files_in_order=total_files,
                parallel_layers=len(layers),
                callback=callback
            )

            state_lock = asyncio.Lock()

            cross_validator = CrossValidator(ctx, language_adapter=language_adapter, api_key_token=self.api_key_token)

            async def generate_single_file(
                file_path: str,
                file_index: int
            ) -> Dict[str, Any]:
                file_node = dep_graph.nodes.get(file_path)
                description = file_node.description if file_node else f"生成 {file_path}"
                file_type = file_node.file_type if file_node else "unknown"
                file_priority = file_node.priority if file_node else 5

                # 断点续传：检查文件是否已存在且完整
                full_path = self.output_dir / file_path
                cleanup_temp_files(self.output_dir, file_path)

                if full_path.exists():
                    try:
                        existing_content = full_path.read_text(encoding='utf-8')
                        if existing_content.strip():
                            # 检查文件修改时间和大小
                            stat = full_path.stat()
                            file_size = stat.st_size
                            file_mtime = stat.st_mtime
                            
                            # 文件大小检查：至少 10 字节
                            if file_size < 10:
                                logger.warning(f"文件太小，重新生成: {file_path} ({file_size} bytes)")
                            else:
                                logger.info(f"文件已存在，跳过生成: {file_path} (size={file_size}, mtime={file_mtime})")
                                self._report_progress(
                                    "skipping_existing_file",
                                    4 + file_index,
                                    total_files + 5,
                                    file_path=file_path,
                                    callback=callback
                                )
                                return {
                                    "path": file_path,
                                    "description": description,
                                    "file_type": file_type,
                                    "success": True,
                                    "size": len(existing_content),
                                    "refinement_attempts": 0,
                                    "issues_fixed": 0,
                                    "content": existing_content,
                                    "model_name": "cached",
                                    "validation_passed": True,
                                    "validation_issues": [],
                                    "skipped": True
                                }
                    except Exception as e:
                        logger.warning(f"读取已存在文件失败: {file_path}, {e}")

                engineer = self._select_engineer(file_path)
                model_name = self._select_model_for_file(file_path)

                self._report_model_info(engineer.name if hasattr(engineer, 'name') else str(engineer), model_name)
                self._report_progress(
                    "generating_file",
                    4 + file_index,
                    total_files + 5,
                    file_path=file_path,
                    file_type=file_type,
                    model=model_name,
                    callback=callback
                )

                spec_context = spec_generator.get_spec_context_for_file(
                    file_path, file_type,
                    max_chars_per_spec=SpecFirstGenerator.get_spec_budget(get_context_length(model_name))
                )
                dep_context = dep_graph.get_context_for_file(
                    file_path, generated_contents, model_context_length=get_context_length(model_name)
                )

                initial_content = await engineer.generate_file(
                    file_path, description, project_context, spec_context, dep_context,
                    project_path=str(self.output_dir), callback=callback,
                    is_existing_file=(self.output_dir / file_path).exists()
                )
                if asyncio.iscoroutine(initial_content):
                    logger.warning(f"generate_file 返回协程，自动 await: {file_path}")
                    initial_content = await initial_content
                if not initial_content:
                    return {"path": file_path, "success": False, "error": "生成返回空内容"}

                # 统一提取工程师生成的内容
                initial_content = extract_engineer_content(
                    initial_content, engineer, self.output_dir, file_path
                )
                if initial_content is None or not initial_content.strip():
                    return {"path": file_path, "success": False, "error": "内容提取失败或仅含空白字符"}

                if cross_validator.is_critical_file(file_path, file_type, file_priority):
                    self._report_progress(
                        "cross_validation",
                        4 + file_index,
                        total_files + 5,
                        file_path=file_path,
                        callback=callback
                    )

                    alt_model = self._select_alternative_model(model_name)
                    alt_engineer = self._select_engineer_for_model(alt_model)
                    alt_content = await alt_engineer.generate_file(
                        file_path, description, project_context, spec_context, dep_context,
                        project_path=str(self.output_dir), callback=callback,
                        is_existing_file=(self.output_dir / file_path).exists()
                    )
                    if asyncio.iscoroutine(alt_content):
                        logger.warning(f"alt generate_file 返回协程，自动 await: {file_path}")
                        alt_content = await alt_content
                    if alt_content:
                        alt_content = extract_engineer_content(
                            alt_content, alt_engineer, self.output_dir, file_path
                        )

                        from app.agent.models import DEFAULT_ARCHITECT_MODEL
                        judge_model = self.model_assignment.reviewer_model if self.model_assignment else DEFAULT_ARCHITECT_MODEL

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

                # 原子写入
                write_file_atomic(self.output_dir, file_path, final_content)

                return {
                    "path": file_path,
                    "description": description,
                    "file_type": file_type,
                    "success": result.success,
                    "size": len(final_content),
                    "refinement_attempts": result.attempts,
                    "issues_fixed": result.issues_fixed,
                    "content": final_content,
                    "model_name": model_name,
                    "validation_passed": result.success,
                    "validation_issues": [f"{i.type}: {i.message}" for i in result.remaining_issues]
                }

            current_index = 0
            for layer_idx, layer in enumerate(layers):
                if self.cancel_event and self.cancel_event.is_set():
                    logger.info(f"[生成] 检测到取消信号，终止层循环 | layer={layer_idx + 1}/{len(layers)}")
                    break
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

                tasks = [
                    generate_single_file(file_path, current_index + i)
                    for i, file_path in enumerate(layer)
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for i, result in enumerate(results):
                    file_path = layer[i]
                    if isinstance(result, Exception):
                        self.errors.append(f"文件生成失败: {file_path}（内部异常）")
                        ctx.add_error(f"文件生成失败: {file_path}")
                        files_failed += 1
                        continue

                    if not result.get("success"):
                        self.errors.append(f"文件生成失败: {file_path}（模型未能生成有效内容，请尝试更换模型）")
                        ctx.add_error(f"文件生成失败: {file_path}")
                        files_failed += 1
                        continue

                    async with state_lock:
                        content = result.pop("content")
                        model_name = result.pop("model_name")
                        file_type = result.pop("file_type", "unknown")
                        validation_issues = result.pop("validation_issues", [])
                        skipped = result.pop("skipped", False)

                        ctx.save_file_content(file_path, content, model_name)
                        ctx.update_file_validation(file_path, result["success"], validation_issues)
                        generated_contents[file_path] = content[:MAX_CONTENT_FOR_CONTEXT]

                        self.generated_files.append(result)
                        if skipped:
                            files_skipped += 1
                        else:
                            files_generated += 1

                        if not result["success"]:
                            ctx.add_warning(f"文件 {file_path} 验证未完全通过")
                            self.warnings.append(f"文件验证未完全通过: {file_path}")

                    description = result.get("description", f"生成 {file_path}")
                    self._report_file_event(file_path, content, description, file_type)

                current_index += layer_size

        self._report_progress("files_generated", total_files + 4, total_files + 5, callback=callback)

        # ============ 完整性验证（新增） ============
        generated_files_dict = {f: ctx.get_file_content(f) for f in ctx.files.keys()}

        # 1. IntegrityValidator - 完整性验证
        from app.agent.integrity_validator import IntegrityValidator
        integrity_validator = IntegrityValidator(language_adapter=language_adapter)
        integrity_result = integrity_validator.validate(generated_files_dict)

        if not integrity_result.passed:
            logger.warning(f"完整性验证发现 {integrity_result.error_count} 个错误")
            self.warnings.extend([issue.message for issue in integrity_result.issues if issue.severity == "error"])

            # 自动生成修复文件（如 __init__.py）
            fixes = integrity_validator.generate_fixes(integrity_result, generated_files_dict)
            if fixes:
                for fix_path, fix_content in fixes.items():
                    full_path = self.output_dir / fix_path
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(full_path, 'w', encoding='utf-8') as f:
                        f.write(fix_content)
                    ctx.save_file_content(fix_path, fix_content, "integrity_fix")
                    logger.info(f"自动修复文件: {fix_path}")
                    self._report_file_event(fix_path, fix_content, "自动补充的包初始化文件", "python")

        # 2. DependencyGraph 完整性验证
        dep_graph_issues = dep_graph.validate_completeness()
        if dep_graph_issues:
            logger.warning(f"依赖图完整性验证发现 {len(dep_graph_issues)} 个问题")
            missing_files = dep_graph.get_missing_files()
            if missing_files:
                architecture = dep_graph.add_missing_files(architecture)
                # 为新发现的文件生成内容
                for missing_file in missing_files:
                    if missing_file not in generated_files_dict:
                        # 使用默认内容
                        init_filename = language_adapter.package_init_filename if language_adapter else '__init__.py'
                        if init_filename and missing_file.endswith(init_filename):
                            default_content = '"""Package initialization"""\n'
                        else:
                            default_content = f'"""Module: {missing_file}"""\n'

                        full_path = self.output_dir / missing_file
                        full_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(full_path, 'w', encoding='utf-8') as f:
                            f.write(default_content)

                        ctx.save_file_content(missing_file, default_content, "integrity_fix")
                        logger.info(f"自动补充完整性文件: {missing_file}")
                        self._report_file_event(missing_file, default_content, "自动补充的模块文件", "python")
                        files_generated += 1

        # 3. CrossValidator 跨文件一致性验证
        if hasattr(self, 'model_assignment') and self.model_assignment:
            cross_validator = CrossValidator(ctx, language_adapter=language_adapter, api_key_token=self.api_key_token)
            fix_model = self.model_assignment.reviewer_model

            # 更新生成文件字典
            generated_files_dict = {f: ctx.get_file_content(f) for f in ctx.files.keys()}

            fixed_files, cross_issues = await cross_validator.validate_and_fix(
                generated_files_dict, architecture, fix_model
            )

            if cross_issues:
                logger.warning(f"跨文件一致性验证发现 {len(cross_issues)} 个问题")
                self.warnings.extend([issue.get("message", "") for issue in cross_issues])

                # 应用修复
                for fix_path, fix_content in fixed_files.items():
                    if fix_content != generated_files_dict.get(fix_path):
                        full_path = self.output_dir / fix_path
                        full_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(full_path, 'w', encoding='utf-8') as f:
                            f.write(fix_content)
                        ctx.save_file_content(fix_path, fix_content, "cross_validator_fix")
                        logger.info(f"跨文件一致性修复: {fix_path}")

        self._report_progress("integrity_validated", total_files + 4, total_files + 5, callback=callback)
        # ============ 完整性验证结束 ============

        final_validation = {}
        if self.enable_validation:
            final_validation = await self.validator.run_full_validation()

            # 推送验证结果事件
            self._report_validation_results({
                "passed": final_validation.get("is_valid", False),
                "checks": final_validation.get("checks", []),
                "issues": final_validation.get("issues", []),
                "score": final_validation.get("score", 0)
            })

        if self.memory_enabled:
            await self._save_to_memory(requirement, architecture)

        elapsed = time.time() - start_time

        architecture_inspector = ArchitectureInspector()
        architecture_inspector.set_context(
            architecture=architecture,
            generated_files={f: ctx.get_file_content(f) for f in ctx.files.keys()},
            constraints=global_constraints if global_constraints else [],
            decisions=decision_extractor.get_all_choices() if decision_extractor else {}
        )
        architecture_check = architecture_inspector.inspect()

        ctx.set_metric("architecture_check", {
            "passed": architecture_check.passed,
            "alignment_score": architecture_check.architecture_alignment_score,
            "violations_count": len(architecture_check.violations),
            "suggestions": architecture_check.suggestions[:5]
        })

        if not architecture_check.passed:
            self.warnings.append(f"架构检查发现问题: {len(architecture_check.violations)} 个违规")

        # 记录跳过的文件数
        if files_skipped > 0:
            logger.info(f"断点续传: 跳过 {files_skipped} 个已存在文件")

        # 报告最终成本和性能指标
        self._report_current_cost()
        self._report_final_metrics()

        return {
            "success": files_failed == 0,
            "output_dir": self.output_dir.name,
            "total_files_created": files_generated,
            "total_files_failed": files_failed,
            "total_files_skipped": files_skipped,
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
            "context_full": ctx.to_export_dict(),
            "requirement_coverage": self._check_requirement_coverage(
                requirement, architecture, file_plan
            ),
            "global_constraints": ctx.get_metric("global_constraints"),
            "critical_decisions": ctx.get_metric("critical_decisions"),
            "architecture_check": ctx.get_metric("architecture_check"),
            "cost": self.cost_tracker.get_summary() if hasattr(self, 'cost_tracker') else {},
            "performance": {
                "total_duration": round(elapsed, 1),
                "files_generated": files_generated,
                "files_per_minute": round(files_generated / (elapsed / 60), 1) if elapsed > 0 else 0,
                "avg_file_time": round(elapsed / files_generated, 1) if files_generated > 0 else 0,
            }
        }

    async def _generate_with_dynamic_topology(
        self,
        ctx: SharedContext,
        dep_graph: DependencyGraph,
        spec_generator: SpecFirstGenerator,
        architecture: Dict,
        requirement: str,
        project_context: Dict,
        generated_contents: Dict[str, str],
        callback: Optional[Callable] = None,
        language_adapter=None
    ) -> Dict[str, Any]:
        """使用动态拓扑调度生成文件"""
        scheduler = TopologyScheduler(max_concurrent=8, max_retries=2, cancel_event=self.cancel_event)
        scheduler.build_from_dependency_graph(dep_graph)

        cross_validator = CrossValidator(ctx, language_adapter=language_adapter)
        refinement_loop = RefinementLoop(ctx, complexity=self.complexity.level.value if self.complexity else "medium", api_key_token=self.api_key_token)

        files_generated = 0
        files_failed = 0
        generated_files_list = []
        errors_list = []
        warnings_list = []
        state_lock = asyncio.Lock()
        total_files = len(scheduler.nodes)

        def progress_report(event: str, file_path: str, completed: int, total: int):
            self._report_progress(
                event, completed, total + 5,
                file_path=file_path,
                callback=callback
            )

        async def file_generator(file_path: str, upstream_context: Dict[str, str]) -> str:
            """单文件生成器（供 TopologyScheduler 调用）"""
            nonlocal files_generated, files_failed
            file_node = dep_graph.nodes.get(file_path)
            description = file_node.description if file_node else f"生成 {file_path}"
            file_type = file_node.file_type if file_node else "unknown"
            file_priority = file_node.priority if file_node else 5

            # 断点续传：检查文件是否已存在且完整
            full_path = self.output_dir / file_path
            tmp_path = full_path.with_suffix(full_path.suffix + '.tmp')

            # 如果存在 .tmp 文件，说明上次写入中断，删除它
            if tmp_path.exists():
                logger.warning(f"发现未完成的文件，删除: {tmp_path}")
                tmp_path.unlink()

            if full_path.exists():
                try:
                    existing_content = full_path.read_text(encoding='utf-8')
                    if existing_content.strip():
                        # 检查文件修改时间和大小
                        stat = full_path.stat()
                        file_size = stat.st_size
                        file_mtime = stat.st_mtime
                        
                        # 文件大小检查：至少 10 字节
                        if file_size < 10:
                            logger.warning(f"文件太小，重新生成: {file_path} ({file_size} bytes)")
                        else:
                            logger.info(f"文件已存在，跳过生成: {file_path} (size={file_size}, mtime={file_mtime})")
                            progress_report("skipping_existing_file", file_path, files_generated, total_files)

                            async with state_lock:
                                ctx.save_file_content(file_path, existing_content, "cached")
                                ctx.update_file_validation(file_path, True, [])
                                generated_contents[file_path] = existing_content[:MAX_CONTENT_FOR_CONTEXT]

                                generated_files_list.append({
                                    "path": file_path,
                                    "description": description,
                                    "success": True,
                                    "size": len(existing_content),
                                    "model_name": "cached",
                                    "skipped": True
                                })
                                files_generated += 1

                            return existing_content
                except Exception as e:
                    logger.warning(f"读取已存在文件失败: {file_path}, {e}")

            engineer = self._select_engineer(file_path)
            model_name = self._select_model_for_file(file_path)

            self._report_model_info(engineer.name if hasattr(engineer, 'name') else str(engineer), model_name)
            combined_context = {**project_context}
            if upstream_context:
                combined_context["upstream_files"] = {
                    path: content[:MAX_CONTENT_FOR_CONTEXT]
                    for path, content in upstream_context.items()
                }

            spec_context = spec_generator.get_spec_context_for_file(
                file_path, file_type,
                max_chars_per_spec=SpecFirstGenerator.get_spec_budget(get_context_length(model_name))
            )
            dep_context = dep_graph.get_context_for_file(
                file_path,
                {k: v for k, v in upstream_context.items()} if upstream_context else generated_contents,
                model_context_length=get_context_length(model_name),
            )

            initial_content = await engineer.generate_file(
                file_path, description, combined_context, spec_context, dep_context,
                project_path=str(self.output_dir), callback=callback,
                is_existing_file=(self.output_dir / file_path).exists()
            )
            if asyncio.iscoroutine(initial_content):
                logger.warning(f"generate_file 返回协程，自动 await: {file_path}")
                initial_content = await initial_content
            if not initial_content:
                raise ValueError(f"文件生成失败: {file_path}（模型未能生成有效内容，请尝试更换模型或稍后重试）")

            # 检查工程师是否已通过工具直接编辑了文件
            if engineer.get_edited_files():
                full = self.output_dir / file_path
                if full.exists():
                    initial_content = full.read_text(encoding='utf-8')
            else:
                initial_content = self._clean_code_block(initial_content)

            if cross_validator.is_critical_file(file_path, file_type, file_priority):
                alt_model = self._select_alternative_model(model_name)
                alt_engineer = self._select_engineer_for_model(alt_model)
                alt_content = await alt_engineer.generate_file(
                    file_path, description, combined_context, spec_context, dep_context,
                    project_path=str(self.output_dir), callback=callback,
                    is_existing_file=(self.output_dir / file_path).exists()
                )
                if asyncio.iscoroutine(alt_content):
                    logger.warning(f"alt generate_file 返回协程，自动 await: {file_path}")
                    alt_content = await alt_content
                if alt_content:
                    # 检查替代工程师是否已通过工具直接编辑了文件
                    if alt_engineer.get_edited_files():
                        full = self.output_dir / file_path
                        if full.exists():
                            alt_content = full.read_text(encoding='utf-8')
                    else:
                        alt_content = self._clean_code_block(alt_content)
                    from app.agent.models import DEFAULT_ARCHITECT_MODEL
                    judge_model = self.model_assignment.reviewer_model if self.model_assignment else DEFAULT_ARCHITECT_MODEL

                    result = await cross_validator.cross_validate_with_refinement(
                        file_path=file_path,
                        file_type=file_type,
                        description=description,
                        content_a=initial_content,
                        model_a=model_name,
                        content_b=alt_content,
                        model_b=alt_model,
                        judge_model=judge_model,
                        refinement_loop=refinement_loop,
                        project_context=combined_context,
                        callback=callback
                    )
                else:
                    result = await refinement_loop.refine(
                        file_path=file_path,
                        file_type=file_type,
                        description=description,
                        initial_content=initial_content,
                        model_name=model_name,
                        project_context=combined_context,
                        callback=callback
                    )
            else:
                result = await refinement_loop.refine(
                    file_path=file_path,
                    file_type=file_type,
                    description=description,
                    initial_content=initial_content,
                    model_name=model_name,
                    project_context=combined_context,
                    callback=callback
                )

            final_content = result.final_content

            # 原子写入：先写临时文件，完成后重命名
            full_path = self.output_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = full_path.with_suffix(full_path.suffix + '.tmp')
            with open(tmp_path, 'w', encoding='utf-8') as f:
                f.write(final_content)
            tmp_path.rename(full_path)

            self._report_file_event(file_path, final_content, description, file_type)

            async with state_lock:
                ctx.save_file_content(file_path, final_content, model_name)
                ctx.update_file_validation(file_path, result.success, [])
                generated_contents[file_path] = final_content[:MAX_CONTENT_FOR_CONTEXT]

                generated_files_list.append({
                    "path": file_path,
                    "description": description,
                    "success": result.success,
                    "size": len(final_content),
                    "model_name": model_name
                })
                files_generated += 1

                if not result.success:
                    warnings_list.append(f"文件验证未完全通过: {file_path}")

            return final_content

        self._report_progress(
            "dynamic_topology_start", 4, 6,
            total_files=total_files,
            callback=callback
        )

        result = await scheduler.run(file_generator, progress_report)

        files_failed = len(result.get("failed_files", []))
        for failed_file in result.get("failed_files", []):
            errors_list.append(f"文件生成失败: {failed_file}")
            ctx.add_error(f"文件生成失败: {failed_file}")

        self._report_progress(
            "dynamic_topology_complete", total_files + 4, total_files + 5,
            files_generated=files_generated,
            files_failed=files_failed,
            stats=scheduler.get_stats(),
            callback=callback
        )

        # ============ 完整性验证（新增） ============
        generated_files_dict = {f: ctx.get_file_content(f) for f in ctx.files.keys()}

        # 1. IntegrityValidator - 完整性验证
        from app.agent.integrity_validator import IntegrityValidator
        integrity_validator = IntegrityValidator(language_adapter=language_adapter)
        integrity_result = integrity_validator.validate(generated_files_dict)

        if not integrity_result.passed:
            logger.warning(f"完整性验证发现 {integrity_result.error_count} 个错误")
            warnings_list.extend([issue.message for issue in integrity_result.issues if issue.severity == "error"])

            # 自动生成修复文件（如 __init__.py）
            fixes = integrity_validator.generate_fixes(integrity_result, generated_files_dict)
            if fixes:
                for fix_path, fix_content in fixes.items():
                    full_path = self.output_dir / fix_path
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(full_path, 'w', encoding='utf-8') as f:
                        f.write(fix_content)
                    ctx.save_file_content(fix_path, fix_content, "integrity_fix")
                    logger.info(f"自动修复文件: {fix_path}")
                    self._report_file_event(fix_path, fix_content, "自动补充的包初始化文件", "python")
                    files_generated += 1

        # 2. DependencyGraph 完整性验证
        dep_graph_issues = dep_graph.validate_completeness()
        if dep_graph_issues:
            logger.warning(f"依赖图完整性验证发现 {len(dep_graph_issues)} 个问题")
            missing_files = dep_graph.get_missing_files()
            if missing_files:
                architecture = dep_graph.add_missing_files(architecture)
                for missing_file in missing_files:
                    if missing_file not in generated_files_dict:
                        if missing_file.endswith('__init__.py'):
                            default_content = '"""Package initialization"""\n'
                        else:
                            default_content = f'"""Module: {missing_file}"""\n'

                        full_path = self.output_dir / missing_file
                        full_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(full_path, 'w', encoding='utf-8') as f:
                            f.write(default_content)
                        ctx.save_file_content(missing_file, default_content, "auto_generated")
                        logger.info(f"自动生成缺失文件: {missing_file}")
                        self._report_file_event(missing_file, default_content, "自动补充的模块文件", "python")
                        files_generated += 1

        # 3. CrossValidator 跨文件一致性验证
        if hasattr(self, 'model_assignment') and self.model_assignment:
            cross_validator = CrossValidator(ctx, language_adapter=language_adapter, api_key_token=self.api_key_token)
            fix_model = self.model_assignment.reviewer_model

            generated_files_dict = {f: ctx.get_file_content(f) for f in ctx.files.keys()}

            fixed_files, cross_issues = await cross_validator.validate_and_fix(
                generated_files_dict, architecture, fix_model
            )

            if cross_issues:
                logger.warning(f"跨文件一致性验证发现 {len(cross_issues)} 个问题")
                warnings_list.extend([issue.get("message", "") for issue in cross_issues])

                for fix_path, fix_content in fixed_files.items():
                    if fix_content != generated_files_dict.get(fix_path):
                        full_path = self.output_dir / fix_path
                        full_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(full_path, 'w', encoding='utf-8') as f:
                            f.write(fix_content)
                        ctx.save_file_content(fix_path, fix_content, "cross_validator_fix")
                        logger.info(f"跨文件一致性修复: {fix_path}")

        self._report_progress("integrity_validated", total_files + 4, total_files + 5, callback=callback)
        # ============ 完整性验证结束 ============

        # 统计跳过的文件数
        files_skipped = sum(1 for f in generated_files_list if f.get("skipped"))

        return {
            "files_generated": files_generated,
            "files_failed": files_failed,
            "files_skipped": files_skipped,
            "total_files": total_files,
            "generated_files": generated_files_list,
            "errors": errors_list,
            "warnings": warnings_list,
            "scheduler_stats": scheduler.get_stats()
        }
