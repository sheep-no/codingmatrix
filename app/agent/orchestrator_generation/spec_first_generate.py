import time
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from collections import defaultdict

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
from app.agent.dependency_graph_validator import DependencyGraphValidator, format_validation_feedback, MAX_VALIDATION_RETRIES

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

        # 检查缓存
        cached = None
        if self.spec_cache and not self.incremental:
            try:
                cached = self.spec_cache.lookup(requirement)
                if cached:
                    logger.info(f"命中规范缓存: {cached.requirement_hash}")
                    self._report_progress(
                        "cache_hit", 0, 1,
                        cache_hash=cached.requirement_hash,
                        cached_specs=list(cached.specs.keys())
                    )
            except Exception as e:
                logger.warning(f"缓存查询失败: {e}")

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

        # 初始化 file_plan 变量
        file_plan = []

        # 提前检测语言，用于规范生成
        from app.agent.language_detector import LanguageDetector
        lang_result = LanguageDetector.detect(requirement)
        detected_language = lang_result.language
        logger.info(f"语言检测: {detected_language} (置信度: {lang_result.confidence:.2f})")

        # 初始化变量
        spec_generator = None

        # 如果有缓存，使用缓存的规范
        if cached and cached.specs:
            for spec_name, spec_data in cached.specs.items():
                ctx.save_spec(spec_name, spec_data, "cache")
            logger.info(f"从缓存加载规范: {list(cached.specs.keys())}")
            specs_success = True
        else:
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

        # 如果有缓存，使用缓存的架构和文件计划
        if cached and cached.architecture:
            architecture = cached.architecture
            file_plan = cached.file_plan
            logger.info(f"从缓存加载架构: {len(file_plan)} 个文件")
            
            # 从缓存加载依赖图
            if cached.dependency_graph:
                detected_lang = architecture.get("language", "python")
                lang_adapter = LanguageAdapterRegistry.get_adapter(detected_lang)
                dep_graph = DependencyGraph.from_dict(cached.dependency_graph, language_adapter=lang_adapter)
                logger.info(f"从缓存加载依赖图: {len(dep_graph.nodes)} 个节点")
        else:
            architecture = await self.architect.design_architecture(requirement, self.complexity, callback=callback)
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
                        for decision_id, choice in user_decisions.items():
                            decision_extractor.apply_user_choice(decision_id, choice)
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
            "output_dir": getattr(self, '_relative_output_dir', None) or str(self.output_dir)
        }

        constraint_prompt = constraint_parser.generate_prompt_fragment("all", "all")
        if constraint_prompt:
            project_context["global_constraints"] = constraint_prompt

        # 获取语言适配器
        detected_language = architecture.get("language", "python")
        language_adapter = LanguageAdapterRegistry.get_adapter(detected_language)
        logger.info(f"使用语言适配器: {language_adapter.language} (检测语言: {detected_language})")

        # 尝试从磁盘加载依赖图（支持增量构建）
        dep_graph_path = self.output_dir / ".dep_graph.json"
        dep_graph = DependencyGraph.load(str(dep_graph_path), language_adapter=language_adapter)

        if dep_graph is None:
            dep_graph = DependencyGraph(language_adapter=language_adapter)
            dep_graph.build_from_architecture(architecture)

            # 依赖图验证：首次生成时全图验证
            validation_feedback = ""
            for retry in range(MAX_VALIDATION_RETRIES + 1):
                validator = DependencyGraphValidator(
                    llm_caller=self._create_validator_llm_caller(),
                    language_adapter=language_adapter,
                )
                validation_result = await validator.validate(dep_graph, scope="full", architecture=architecture)

                if validation_result.passed:
                    logger.info(f"依赖图验证通过 (第 {retry + 1} 次)")
                    break

                validation_feedback = format_validation_feedback(validation_result)
                logger.warning(f"依赖图验证未通过 (第 {retry + 1}/{MAX_VALIDATION_RETRIES + 1} 次): {len(validation_result.issues)} 个问题")

                if retry < MAX_VALIDATION_RETRIES:
                    # 反馈给架构师重新生成
                    architecture = await self.architect.design_architecture(
                        requirement, self.complexity, feedback=validation_feedback, callback=callback
                    )
                    file_plan = architecture.get("file_plan", [])

                    # 重新构建依赖图
                    dep_graph = DependencyGraph(language_adapter=language_adapter)
                    dep_graph.build_from_architecture(architecture)
                else:
                    logger.warning(f"依赖图验证达到最大重试次数，继续生成")

            logger.info(f"依赖图构建完成: {len(dep_graph.nodes)} 个文件节点, file_plan={len(file_plan)} 个文件")
            # 保存依赖图到磁盘
            dep_graph.save(str(dep_graph_path))
        else:
            logger.info(f"从磁盘加载依赖图: {len(dep_graph.nodes)} 个文件节点")
            # 确保 file_plan 已定义
            if 'file_plan' not in locals():
                file_plan = architecture.get("file_plan", [])
            # 增量更新：添加新文件到依赖图
            new_files = []
            for file_info in file_plan:
                file_path = file_info.get("path", "")
                if file_path and file_path not in dep_graph.nodes:
                    dep_graph.add_file(
                        file_path,
                        file_type=file_info.get("file_type"),
                        priority=file_info.get("priority", 3),
                        description=file_info.get("description", "")
                    )
                    new_files.append(file_path)

            # 增量验证：只验证新增文件
            if new_files:
                validator = DependencyGraphValidator(
                    llm_caller=self._create_validator_llm_caller(),
                    language_adapter=language_adapter,
                )
                validation_result = await validator.validate(
                    dep_graph, scope="incremental", new_files=new_files, architecture=architecture
                )
                if not validation_result.passed:
                    logger.warning(f"增量依赖图验证未通过: {len(validation_result.issues)} 个问题")
                    for issue in validation_result.issues:
                        logger.warning(f"  [{issue.issue_type}] {issue.message}")

            # 保存更新后的依赖图
            dep_graph.save(str(dep_graph_path))

        # LLM 批量推断未知 file_type（通用，不依赖语言）
        unknown_files = dep_graph.get_unknown_type_files()
        if unknown_files:
            logger.info(f"发现 {len(unknown_files)} 个未知 file_type 文件，启动 LLM 批量推断")
            await self._infer_unknown_file_types(dep_graph, unknown_files, architecture, detected_language)
            dep_graph.save(str(dep_graph_path))

        layers = dep_graph.get_generation_layers()
        ctx.set_metric("generation_layers", len(layers))
        ctx.set_metric("generation_order", [f for layer in layers for f in layer])

        if hasattr(self, 'use_dynamic_topology') and self.use_dynamic_topology:
            try:
                result = await self._generate_with_dynamic_topology(
                    ctx, dep_graph, spec_generator, architecture, requirement,
                    project_context, generated_contents, callback, language_adapter
                )
            finally:
                # 清除依赖图白名单（延迟到此处，确保被取消的 ReAct 协程也被阻止写入）
                from app.agent.tools import set_allowed_file_paths
                set_allowed_file_paths(None)
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
                normalized = self._strip_output_dir_prefix(file_path)
                full_path = self.output_dir / normalized
                cleanup_temp_files(self.output_dir, normalized)

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

                spec_context = {}
                if spec_generator:
                    spec_context = spec_generator.get_spec_context_for_file(
                        file_path, file_type,
                        max_chars_per_spec=SpecFirstGenerator.get_spec_budget(get_context_length(model_name))
                    )
                dep_context = dep_graph.get_context_for_file(
                    file_path, generated_contents, model_context_length=get_context_length(model_name),
                    project_spec=architecture.get("project_spec")
                )

                initial_content = await engineer.generate_file(
                    file_path, description, project_context, spec_context, dep_context,
                    project_path=str(self.output_dir), callback=callback,
                    is_existing_file=(self.output_dir / normalized).exists()
                )
                if asyncio.iscoroutine(initial_content):
                    logger.warning(f"generate_file 返回协程，自动 await: {file_path}")
                    initial_content = await initial_content

                # 统一提取工程师生成的内容（内置有效性检测 + LLM 语言检测）
                # 注意：extract_engineer_content 会检查工程师是否通过工具直接写入了文件
                # 即使 generate_file 返回空内容（LLM 用工具写文件后返回摘要），也能从磁盘读取
                raw_content = initial_content  # 保存原始内容用于恢复
                target_language = project_context.get("architecture", {}).get("language", "")
                from app.agent.utils import get_expected_language_for_file
                file_expected_language = get_expected_language_for_file(file_path, target_language)
                initial_content = await extract_engineer_content(
                    initial_content, engineer, self.output_dir, file_path,
                    expected_language=file_expected_language,
                    llm_caller=self._quick_llm_check,
                )
                if initial_content is None or not initial_content.strip():
                    # 内容无效（可能是 JSON 元数据或语言不匹配），尝试恢复
                    from app.agent.utils import is_valid_code_content
                    _, invalid_reason = is_valid_code_content(file_path, raw_content or "")
                    if invalid_reason:
                        logger.warning(f"内容无效: {file_path} - {invalid_reason}，尝试恢复")
                    else:
                        invalid_reason = "内容提取失败或语言不匹配"
                    recovered = await self._recover_invalid_content(
                        file_path, description, project_context, invalid_reason,
                        engineer, spec_context, dep_context, callback
                    )
                    if recovered:
                        initial_content = recovered
                    else:
                        # 恢复失败，重试+升级模型
                        initial_content = await self._retry_generate_file(
                            file_path, description, project_context, spec_context, dep_context,
                            engineer, callback, reason=invalid_reason
                        )
                        if not initial_content:
                            logger.error(f"所有重试均失败，跳过文件: {file_path}")
                            return {"path": file_path, "success": False, "error": f"文件生成失败: {invalid_reason}"}

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
                        is_existing_file=(self.output_dir / normalized).exists()
                     )
                    if asyncio.iscoroutine(alt_content):
                        logger.warning(f"alt generate_file 返回协程，自动 await: {file_path}")
                        alt_content = await alt_content
                    if alt_content:
                        target_language = project_context.get("architecture", {}).get("language", "")
                        from app.agent.utils import get_expected_language_for_file
                        file_expected_language = get_expected_language_for_file(file_path, target_language)
                        alt_content = await extract_engineer_content(
                            alt_content, alt_engineer, self.output_dir, file_path,
                            expected_language=file_expected_language,
                            llm_caller=self._quick_llm_check,
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

                # 写入前内容质量校验
                from app.agent.utils import validate_content_quality
                quality_warning = validate_content_quality(file_path, final_content)
                if quality_warning:
                    logger.warning(f"内容质量校验失败: {file_path} - {quality_warning}")
                    retry_content = await engineer.generate_file(
                        file_path, f"【重要】请只返回代码，不要返回任何解释或思考过程。\n\n{description}",
                        project_context, spec_context, dep_context,
                        project_path=str(self.output_dir), callback=callback,
                        is_existing_file=False
                    )
                    if asyncio.iscoroutine(retry_content):
                        retry_content = await retry_content
                    if retry_content:
                        target_language = project_context.get("architecture", {}).get("language", "")
                        from app.agent.utils import get_expected_language_for_file
                        file_expected_language = get_expected_language_for_file(file_path, target_language)
                        retry_content = await extract_engineer_content(
                            retry_content, engineer, self.output_dir, file_path,
                            expected_language=file_expected_language,
                            llm_caller=self._quick_llm_check,
                        )
                        retry_warning = validate_content_quality(file_path, retry_content or "")
                        if not retry_warning and retry_content:
                            final_content = retry_content
                            logger.info(f"内容质量重试成功: {file_path}")

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
                from app.agent.utils import write_file_atomic as _wf_atomic
                for fix_path, fix_content in fixes.items():
                    _wf_atomic(self.output_dir, fix_path, fix_content, skip_placeholder_check=True)
                    ctx.save_file_content(fix_path, fix_content, "integrity_fix")
                    logger.info(f"自动修复文件: {fix_path}")
                    self._report_file_event(fix_path, fix_content, "自动补充的包初始化文件", detected_language)

        # 2. DependencyGraph 完整性验证
        dep_graph_issues = dep_graph.validate_completeness()
        if dep_graph_issues:
            logger.warning(f"依赖图完整性验证发现 {len(dep_graph_issues)} 个问题")
            missing_files = dep_graph.get_missing_files()
            if missing_files:
                architecture = dep_graph.add_missing_files(architecture)
                # 为新发现的文件生成内容
                from app.agent.utils import write_file_atomic as _wf_atomic
                for missing_file in missing_files:
                    if missing_file not in generated_files_dict:
                        # 使用 IntegrityValidator 生成真实内容
                        init_filename = language_adapter.package_init_filename if language_adapter else '__init__.py'
                        if init_filename and (missing_file.endswith(init_filename) or missing_file.endswith('__init__.py')):
                            default_content = integrity_validator._generate_init_content(missing_file, generated_files_dict)
                        elif missing_file.endswith('index.js') or missing_file.endswith('index.ts'):
                            default_content = integrity_validator._generate_index_content(missing_file, generated_files_dict)
                        else:
                            # 根据文件扩展名生成正确的内容
                            ext = Path(missing_file).suffix
                            if ext == '.py':
                                default_content = f'"""Module: {missing_file}"""\n'
                            elif ext in ('.js', '.ts'):
                                default_content = f'// Module: {missing_file}\n'
                            else:
                                default_content = ''

                        _wf_atomic(self.output_dir, missing_file, default_content, skip_placeholder_check=True)
                        ctx.save_file_content(missing_file, default_content, "integrity_fix")
                        logger.info(f"自动补充完整性文件: {missing_file}")
                        self._report_file_event(missing_file, default_content, "自动补充的模块文件", detected_language)
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
                from app.agent.utils import write_file_atomic as _wf_atomic
                for fix_path, fix_content in fixed_files.items():
                    if fix_content != generated_files_dict.get(fix_path):
                        _wf_atomic(self.output_dir, fix_path, fix_content)
                        ctx.save_file_content(fix_path, fix_content, "cross_validator_fix")
                        logger.info(f"跨文件一致性修复: {fix_path}")

        self._report_progress("integrity_validated", total_files + 4, total_files + 5, callback=callback)

        # 4. 项目级沙箱验证（新增）
        from app.agent.utils import validate_in_sandbox
        # 使用最新的文件字典（包含所有修复）
        final_files_dict = {f: ctx.get_file_content(f) for f in ctx.files.keys()}
        sandbox_ok, sandbox_errors = validate_in_sandbox(
            project_dir=str(self.output_dir),
            files=final_files_dict,
            level="run",
            context={"trigger": "project_complete"}
        )
        if not sandbox_ok:
            logger.warning(f"项目级沙箱验证发现 {len(sandbox_errors)} 个错误")
            self.warnings.extend(sandbox_errors)

            # 自动修复：将错误反馈给 LLM 修复
            fixed_files = await self._fix_sandbox_errors(sandbox_errors, final_files_dict, ctx)
            if fixed_files:
                logger.info(f"沙箱验证自动修复: {len(fixed_files)} 个文件")
                # 重新验证
                final_files_dict = {f: ctx.get_file_content(f) for f in ctx.files.keys()}
                sandbox_ok, sandbox_errors = validate_in_sandbox(
                    project_dir=str(self.output_dir),
                    files=final_files_dict,
                    level="run",
                    context={"trigger": "project_complete"}
                )
                if sandbox_ok:
                    logger.info("沙箱验证修复后通过")
                else:
                    logger.warning(f"沙箱验证修复后仍有 {len(sandbox_errors)} 个错误")
        else:
            logger.info("项目级沙箱验证通过")

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

        # 保存到 spec_cache（规范缓存）
        if self.spec_cache:
            try:
                specs_to_cache = {}
                for spec_name in ("openapi", "types", "db_schema", "config"):
                    spec_data = ctx.get_spec(spec_name)
                    if spec_data:
                        specs_to_cache[spec_name] = spec_data
                
                tech_stack = ctx.complexity.get("key_technologies", []) if isinstance(ctx.complexity, dict) else []
                self.spec_cache.save(
                    requirement=requirement,
                    specs=specs_to_cache,
                    architecture=architecture,
                    file_plan=file_plan,
                    complexity=ctx.complexity,
                    tech_stack=tech_stack,
                    dependency_graph=dep_graph.to_dict() if dep_graph else None
                )
                logger.info(f"规范已缓存: {len(specs_to_cache)} 个规范, {len(file_plan)} 个文件")
            except Exception as e:
                logger.warning(f"缓存保存失败: {e}")

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
        # 免费模型速率限制：并行度降为 2，避免 429 错误
        scheduler = TopologyScheduler(
            max_concurrent=5, max_retries=2, timeout_per_file=300.0,
            heartbeat_timeout=300.0,  # 300 秒无 LLM 调用活动视为僵尸
            cancel_event=self.cancel_event,
            output_dir=str(self.output_dir)
        )
        scheduler.build_from_dependency_graph(dep_graph)

        # 设置依赖图白名单：LLM 工具只允许写入依赖图中的文件
        from app.agent.tools import set_allowed_file_paths
        set_allowed_file_paths(set(dep_graph.nodes.keys()))

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

        async def file_generator(file_path: str, upstream_context: Dict[str, str], tracker=None) -> str:
            """单文件生成器（供 TopologyScheduler 调用）"""
            nonlocal files_generated, files_failed
            file_node = dep_graph.nodes.get(file_path)
            description = file_node.description if file_node else f"生成 {file_path}"
            file_type = file_node.file_type if file_node else "unknown"
            file_priority = file_node.priority if file_node else 5

            # 断点续传：检查文件是否已存在且完整
            normalized = self._strip_output_dir_prefix(file_path)
            full_path = self.output_dir / normalized
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

            spec_context = {}
            if spec_generator:
                spec_context = spec_generator.get_spec_context_for_file(
                    file_path, file_type,
                    max_chars_per_spec=SpecFirstGenerator.get_spec_budget(get_context_length(model_name))
                )
            dep_context = dep_graph.get_context_for_file(
                file_path,
                {k: v for k, v in upstream_context.items()} if upstream_context else generated_contents,
                model_context_length=get_context_length(model_name),
                project_spec=project_context.get("architecture", {}).get("project_spec"),
            )

            initial_content = await engineer.generate_file(
                file_path, description, combined_context, spec_context, dep_context,
                project_path=str(self.output_dir), callback=callback,
                is_existing_file=(self.output_dir / normalized).exists(),
                heartbeat_tracker=tracker
            )
            if asyncio.iscoroutine(initial_content):
                logger.warning(f"generate_file 返回协程，自动 await: {file_path}")
                initial_content = await initial_content

            # 统一提取工程师生成的内容（内置有效性检测 + LLM 语言检测）
            # 注意：extract_engineer_content 会检查工程师是否通过工具直接写入了文件
            # 即使 generate_file 返回空内容（LLM 用工具写文件后返回摘要），也能从磁盘读取
            raw_content = initial_content  # 保存原始内容用于恢复
            architecture = project_context.get("architecture", {})
            target_language = architecture.get("language", "")
            from app.agent.utils import get_expected_language_for_file
            file_expected_language = get_expected_language_for_file(file_path, target_language)
            logger.info(f"extract_engineer_content 调用: file_path={file_path}, target_language={target_language}, file_expected_language={file_expected_language}")
            initial_content = await extract_engineer_content(
                initial_content, engineer, self.output_dir, file_path,
                expected_language=file_expected_language,
                llm_caller=self._quick_llm_check,
            )
            if initial_content is None or not initial_content.strip():
                # 内容无效（可能是 JSON 元数据或语言不匹配），尝试恢复
                from app.agent.utils import is_valid_code_content
                _, invalid_reason = is_valid_code_content(file_path, raw_content or "")
                if invalid_reason:
                    logger.warning(f"内容无效: {file_path} - {invalid_reason}，尝试恢复")
                else:
                    invalid_reason = "内容提取失败或语言不匹配"
                recovered = await self._recover_invalid_content(
                    file_path, description, combined_context, invalid_reason,
                    engineer, spec_context, dep_context, callback,
                    heartbeat_tracker=tracker
                )
                if recovered:
                    initial_content = recovered
                else:
                    # 恢复失败，重试+升级模型
                    initial_content = await self._retry_generate_file(
                        file_path, description, combined_context, spec_context, dep_context,
                        engineer, callback, heartbeat_tracker=tracker, reason=invalid_reason
                    )
                    if not initial_content:
                        logger.error(f"所有重试均失败，跳过文件: {file_path}")
                        raise ValueError(f"文件生成失败: {file_path}（模型未能生成有效内容，请尝试更换模型或稍后重试）")

            if cross_validator.is_critical_file(file_path, file_type, file_priority):
                alt_model = self._select_alternative_model(model_name)
                alt_engineer = self._select_engineer_for_model(alt_model)
                if tracker:
                    tracker.touch()
                alt_content = await alt_engineer.generate_file(
                    file_path, description, combined_context, spec_context, dep_context,
                    project_path=str(self.output_dir), callback=callback,
                    is_existing_file=(self.output_dir / normalized).exists(),
                    heartbeat_tracker=tracker
                )
                if tracker:
                    tracker.touch()
                if asyncio.iscoroutine(alt_content):
                    logger.warning(f"alt generate_file 返回协程，自动 await: {file_path}")
                    alt_content = await alt_content
                if alt_content:
                    # 检查替代工程师是否已通过工具直接编辑了文件
                    if alt_engineer.get_edited_files():
                        full = self.output_dir / normalized
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

            # 写入前内容质量校验：检测 LLM 思考过程泄漏等非代码内容
            from app.agent.utils import validate_content_quality
            quality_warning = validate_content_quality(file_path, final_content)
            if quality_warning:
                logger.warning(f"内容质量校验失败: {file_path} - {quality_warning}")
                # 尝试重新生成一次
                retry_content = await engineer.generate_file(
                    file_path, f"【重要】请只返回代码，不要返回任何解释或思考过程。\n\n{description}",
                    project_context, spec_context, dep_context,
                    project_path=str(self.output_dir), callback=callback,
                    is_existing_file=False
                )
                if asyncio.iscoroutine(retry_content):
                    retry_content = await retry_content
                if retry_content:
                    target_language = project_context.get("architecture", {}).get("language", "")
                    from app.agent.utils import get_expected_language_for_file
                    file_expected_language = get_expected_language_for_file(file_path, target_language)
                    retry_content = await extract_engineer_content(
                        retry_content, engineer, self.output_dir, file_path,
                        expected_language=file_expected_language,
                        llm_caller=self._quick_llm_check,
                    )
                    retry_warning = validate_content_quality(file_path, retry_content or "")
                    if not retry_warning and retry_content:
                        final_content = retry_content
                        logger.info(f"内容质量重试成功: {file_path}")
                    else:
                        logger.warning(f"内容质量重试仍失败: {file_path}，尝试重试+升级模型")
                        final_content = await self._retry_generate_file(
                            file_path, description, combined_context, spec_context, dep_context,
                            engineer, callback, heartbeat_tracker=tracker, reason="内容质量校验失败"
                        )
                        if not final_content:
                            logger.error(f"所有重试均失败，跳过文件: {file_path}")
                            result.success = False

            # 写入前语法验证：精炼循环可能未能修复语法错误
            syntax_ok = await self._validate_content_syntax(file_path, final_content)
            if not syntax_ok and final_content:
                logger.warning(f"文件语法验证失败: {file_path}，尝试 error_recovery 修复")
                # 尝试用 error_recovery 修复
                if hasattr(self, 'error_recovery') and self.error_recovery:
                    full_path = self.output_dir / normalized
                    full_path.parent.mkdir(parents=True, exist_ok=True)
                    from app.agent.utils import write_file_atomic as _wf_atomic
                    _wf_atomic(self.output_dir, normalized, final_content, skip_placeholder_check=True)
                    try:
                        backend_model = getattr(self, 'model_assignment', None)
                        backend_model = backend_model.backend_model if backend_model else "Qwen/Qwen3-8B"
                        er_success, er_content = await self.error_recovery.validate_and_fix(
                            file_path=full_path,
                            content=final_content,
                            file_description=description,
                            backend_model=backend_model,
                            callback=callback
                        )
                        if er_success and er_content:
                            final_content = er_content
                            syntax_ok = True
                    except Exception as e:
                        logger.warning(f"error_recovery 修复失败: {e}")
                if not syntax_ok:
                    logger.warning(f"语法验证未通过，尝试重试+升级模型: {file_path}")
                    final_content = await self._retry_generate_file(
                        file_path, description, combined_context, spec_context, dep_context,
                        engineer, callback, heartbeat_tracker=tracker, reason="语法验证失败"
                    )
                    if not final_content:
                        logger.error(f"所有重试均失败，跳过文件: {file_path}")
                        result.success = False

            # 原子写入（统一使用 write_file_atomic）
            if final_content:
                from app.agent.utils import write_file_atomic as _wf_atomic
                write_ok = _wf_atomic(self.output_dir, normalized, final_content)
                if not write_ok:
                    logger.error(f"文件写入失败: {file_path}")
                    result.success = False

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

        generated_files_dict = {f: ctx.get_file_content(f) for f in ctx.files.keys()}

        # ============ 清理不符合项目语言的文件 ============
        if language_adapter:
            # 根据 file_plan 重新确定项目实际使用的文件扩展名
            # （架构师可能规划了多语言文件，如前端 JS + 后端 Python）
            planned_extensions = set()
            if architecture:
                for fp in architecture.get("file_plan", []):
                    if isinstance(fp, dict) and "path" in fp:
                        ext = Path(fp["path"]).suffix.lower()
                        if ext:
                            planned_extensions.add(ext)
            
            # 语言适配器的扩展名 + file_plan 中的扩展名 = 项目实际允许的扩展名
            expected_extensions = set(language_adapter.extensions) | planned_extensions
            
            files_to_remove = []
            for file_path in list(ctx.files.keys()):
                ext = Path(file_path).suffix.lower()

                # 检查是否是不符合项目语言的文件
                if ext in ('.py', '.pyw', '.pyi') and not any(e in expected_extensions for e in ('.py', '.pyw', '.pyi')):
                    files_to_remove.append(file_path)
                    logger.warning(f"移除不符合项目语言的文件: {file_path} (项目语言: {language_adapter.language})")
                elif ext in ('.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs') and not any(e in expected_extensions for e in ('.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs')):
                    files_to_remove.append(file_path)
                    logger.warning(f"移除不符合项目语言的文件: {file_path} (项目语言: {language_adapter.language})")
            
            for file_path in files_to_remove:
                # 删除文件
                full_path = self.output_dir / file_path
                if full_path.exists():
                    full_path.unlink()
                    logger.info(f"已删除文件: {full_path}")
                # 从上下文中移除
                if file_path in ctx.files:
                    del ctx.files[file_path]
                if file_path in generated_files_dict:
                    del generated_files_dict[file_path]
                files_generated -= 1

        # ============ 清理文件名有问题的文件 ============
        files_to_fix = []
        for file_path in list(ctx.files.keys()):
            # 检查文件名是否有空格
            filename = Path(file_path).name
            if ' ' in filename:
                files_to_fix.append(file_path)
                logger.warning(f"文件名包含空格: {file_path}")
            # 检查文件名是否有中文字符且缺少分隔符
            elif any('\u4e00' <= c <= '\u9fff' for c in filename):
                # 中文文件名可能是合理的（如 图表.js），但需要确保路径正确
                pass

        for file_path in files_to_fix:
            # 尝试修复文件名（移除空格）
            fixed_path = file_path.replace(' ', '')
            if fixed_path != file_path:
                full_path = self.output_dir / file_path
                fixed_full_path = self.output_dir / fixed_path
                if full_path.exists():
                    fixed_full_path.parent.mkdir(parents=True, exist_ok=True)
                    full_path.rename(fixed_full_path)
                    logger.info(f"修复文件名: {file_path} -> {fixed_path}")
                    # 更新上下文
                    if file_path in ctx.files:
                        ctx.files[fixed_path] = ctx.files.pop(file_path)
                    if file_path in generated_files_dict:
                        generated_files_dict[fixed_path] = generated_files_dict.pop(file_path)

        self._report_progress(
            "dynamic_topology_complete", total_files + 4, total_files + 5,
            files_generated=files_generated,
            files_failed=files_failed,
            stats=scheduler.get_stats(),
            callback=callback
        )

        # ============ 清理根目录重复文件 ============
        # 检查根目录是否有与 src/ 目录重复的文件
        root_files = [f for f in ctx.files.keys() if '/' not in f and '\\' not in f]
        src_files = [f for f in ctx.files.keys() if f.startswith('src/')]
        
        for root_file in root_files:
            root_name = Path(root_file).name
            # 检查是否有同名的 src/ 文件
            for src_file in src_files:
                src_name = Path(src_file).name
                if root_name == src_name:
                    # 根目录文件是重复的，删除它
                    full_path = self.output_dir / root_file
                    if full_path.exists():
                        full_path.unlink()
                        logger.info(f"删除根目录重复文件: {root_file} (与 {src_file} 重复)")
                    if root_file in ctx.files:
                        del ctx.files[root_file]
                    if root_file in generated_files_dict:
                        del generated_files_dict[root_file]
                    files_generated -= 1
                    break

        # ============ 清理功能重复文件 ============
        # 检查所有目录中同名的功能重复文件（如 main.py 出现在多个目录）
        all_files = list(ctx.files.keys())
        name_to_paths = defaultdict(list)
        for f in all_files:
            name = Path(f).name
            name_to_paths[name].append(f)
        
        for name, paths in name_to_paths.items():
            if len(paths) <= 1:
                continue
            
            # 优先保留的目录顺序：src/ > app/ > 根目录
            priority_dirs = ['src/', 'app/', 'src/app/']
            best_path = None
            for prefix in priority_dirs:
                for p in paths:
                    if p.startswith(prefix):
                        best_path = p
                        break
                if best_path:
                    break
            
            if not best_path:
                best_path = paths[0]
            
            for p in paths:
                if p == best_path:
                    continue
                # 删除重复文件
                full_path = self.output_dir / p
                if full_path.exists():
                    full_path.unlink()
                    logger.info(f"删除功能重复文件: {p} (保留 {best_path})")
                if p in ctx.files:
                    del ctx.files[p]
                if p in generated_files_dict:
                    del generated_files_dict[p]
                files_generated -= 1

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
                from app.agent.utils import write_file_atomic as _wf_atomic
                for fix_path, fix_content in fixes.items():
                    _wf_atomic(self.output_dir, fix_path, fix_content, skip_placeholder_check=True)
                    ctx.save_file_content(fix_path, fix_content, "integrity_fix")
                    logger.info(f"自动修复文件: {fix_path}")
                    lang_for_report = language_adapter.language if language_adapter else "python"
                    self._report_file_event(fix_path, fix_content, "自动补充的包初始化文件", lang_for_report)
                    files_generated += 1

        # 2. DependencyGraph 完整性验证
        dep_graph_issues = dep_graph.validate_completeness()
        if dep_graph_issues:
            logger.warning(f"依赖图完整性验证发现 {len(dep_graph_issues)} 个问题")
            missing_files = dep_graph.get_missing_files()
            if missing_files:
                architecture = dep_graph.add_missing_files(architecture)
                from app.agent.utils import write_file_atomic as _wf_atomic
                for missing_file in missing_files:
                    if missing_file not in generated_files_dict:
                        # 使用 IntegrityValidator 生成真实内容
                        init_filename = language_adapter.package_init_filename if language_adapter else '__init__.py'
                        if missing_file.endswith(init_filename) or missing_file.endswith('__init__.py'):
                            default_content = integrity_validator._generate_init_content(missing_file, generated_files_dict)
                        elif missing_file.endswith('index.js') or missing_file.endswith('index.ts'):
                            default_content = integrity_validator._generate_index_content(missing_file, generated_files_dict)
                        else:
                            # 根据文件扩展名生成正确的内容
                            ext = Path(missing_file).suffix
                            if ext == '.py':
                                default_content = f'"""Module: {missing_file}"""\n'
                            elif ext in ('.js', '.ts'):
                                default_content = f'// Module: {missing_file}\n'
                            else:
                                default_content = ''

                        _wf_atomic(self.output_dir, missing_file, default_content, skip_placeholder_check=True)
                        ctx.save_file_content(missing_file, default_content, "auto_generated")
                        logger.info(f"自动生成缺失文件: {missing_file}")
                        lang_for_report = language_adapter.language if language_adapter else "python"
                        self._report_file_event(missing_file, default_content, "自动补充的模块文件", lang_for_report)
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

                from app.agent.utils import write_file_atomic as _wf_atomic
                for fix_path, fix_content in fixed_files.items():
                    if fix_content != generated_files_dict.get(fix_path):
                        _wf_atomic(self.output_dir, fix_path, fix_content)
                        ctx.save_file_content(fix_path, fix_content, "cross_validator_fix")
                        logger.info(f"跨文件一致性修复: {fix_path}")

        self._report_progress("integrity_validated", total_files + 4, total_files + 5, callback=callback)

        # 4. 项目级沙箱验证
        from app.agent.utils import validate_in_sandbox
        final_files_dict = {f: ctx.get_file_content(f) for f in ctx.files.keys()}
        sandbox_ok, sandbox_errors = validate_in_sandbox(
            project_dir=str(self.output_dir),
            files=final_files_dict,
            level="run",
            context={"trigger": "project_complete"}
        )
        if not sandbox_ok:
            logger.warning(f"项目级沙箱验证发现 {len(sandbox_errors)} 个错误")
            warnings_list.extend(sandbox_errors)

            # 自动修复：将错误反馈给 LLM 修复
            fixed_files = await self._fix_sandbox_errors(sandbox_errors, final_files_dict, ctx)
            if fixed_files:
                logger.info(f"沙箱验证自动修复: {len(fixed_files)} 个文件")
                # 重新验证
                final_files_dict = {f: ctx.get_file_content(f) for f in ctx.files.keys()}
                sandbox_ok, sandbox_errors = validate_in_sandbox(
                    project_dir=str(self.output_dir),
                    files=final_files_dict,
                    level="run",
                    context={"trigger": "project_complete"}
                )
                if sandbox_ok:
                    logger.info("沙箱验证修复后通过")
                else:
                    logger.warning(f"沙箱验证修复后仍有 {len(sandbox_errors)} 个错误")
        else:
            logger.info("项目级沙箱验证通过")

        # ============ 完整性验证结束 ============

        # ============ 项目完整性验证（补充缺失文件） ============
        if 'file_plan' not in locals():
            file_plan = architecture.get("file_plan", [])
        final_generated_dict = {f: ctx.get_file_content(f) for f in ctx.files.keys()}
        completeness = await self._validate_project_completeness(file_plan, final_generated_dict)

        if not completeness["is_complete"]:
            logger.warning(
                f"项目完整性检查未通过: "
                f"缺失 {len(completeness['missing_files'])} 个文件, "
                f"无效 {len(completeness['invalid_files'])} 个文件"
            )

            # 尝试补充缺失文件
            for missing_file in completeness["missing_files"]:
                logger.info(f"尝试补充缺失文件: {missing_file}")
                desc = next((f["description"] for f in file_plan if f["path"] == missing_file), "")
                content = await self._direct_llm_generate_file(missing_file, desc, project_context)
                if content:
                    from app.agent.utils import is_valid_code_content, write_file_atomic as _wf_atomic
                    is_valid, _ = is_valid_code_content(missing_file, content)
                    if is_valid:
                        _wf_atomic(self.output_dir, missing_file, content)
                        ctx.save_file_content(missing_file, content, "completeness_fix")
                        logger.info(f"缺失文件已补充: {missing_file}")
                        files_generated += 1

        logger.info(f"项目生成完成: {completeness['total_generated']}/{completeness['total_planned']} 文件")

        # 统计跳过的文件数
        files_skipped = sum(1 for f in generated_files_list if f.get("skipped"))

        # 注意：白名单清除已移到 generate_with_spec_first 的 finally 块中

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

    async def _validate_content_syntax(self, file_path: str, content: str) -> bool:
        """验证文件内容语法，返回 True 表示通过"""
        import ast
        import re
        from pathlib import Path

        ext = Path(file_path).suffix.lower()

        if ext == '.py':
            try:
                ast.parse(content)
                return True
            except SyntaxError:
                return False

        elif ext in ('.js', '.ts', '.vue'):
            # 检测 Python 代码混入 JS 文件
            python_indicators = ['def ', 'import ', 'from ', 'class ', 'self.', 'print(']
            python_count = sum(1 for ind in python_indicators if ind in content)
            if python_count >= 3:
                return False
            import tempfile
            import subprocess
            try:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
                    f.write(content)
                    tmp_path = f.name
                result = subprocess.run(
                    ['node', '-c', tmp_path],
                    capture_output=True, text=True, timeout=5
                )
                Path(tmp_path).unlink(missing_ok=True)
                return result.returncode == 0
            except (subprocess.TimeoutExpired, FileNotFoundError):
                return content.count('{') == content.count('}') and content.count('(') == content.count(')')

        elif ext == '.html':
            for tag in ['html', 'head', 'body']:
                open_count = len(re.findall(rf'<{tag}[\s>]', content, re.IGNORECASE))
                close_count = len(re.findall(rf'</{tag}>', content, re.IGNORECASE))
                if open_count > close_count:
                    return False
            script_opens = len(re.findall(r'<script[\s>]', content, re.IGNORECASE))
            script_closes = len(re.findall(r'</script>', content, re.IGNORECASE))
            return script_opens == script_closes

        elif ext == '.css':
            if content.count('{') != content.count('}'):
                return False
            # 检测非 CSS 内容（大段中文描述文本）
            lines = [l.strip() for l in content.split('\n') if l.strip() and not l.strip().startswith('/*')]
            chinese_lines = sum(1 for l in lines if len(re.findall(r'[\u4e00-\u9fff]', l)) > 10)
            if chinese_lines > len(lines) * 0.3 and chinese_lines > 3:
                return False
            return True

        return True

    def _strip_output_dir_prefix(self, file_path: str) -> str:
        """去除 file_path 中可能的 output_dir 前缀，避免路径重复"""
        from pathlib import Path
        rel = getattr(self, '_relative_output_dir', None)
        if rel and file_path.startswith(rel + "/"):
            return file_path[len(rel) + 1:]
        if rel:
            rel_path = Path(rel)
            try:
                rel_str = str(rel_path)
                if file_path.startswith(rel_str + "/"):
                    return file_path[len(rel_str) + 1:]
            except Exception:
                pass
        return file_path

    def _create_validator_llm_caller(self):
        """创建验证器用的 LLM 调用函数"""
        from app.agent.llm_client import LLMClient

        # 使用 reviewer 模型进行验证（轻量任务，不需要生成模型）
        model_name = self.model_assignment.reviewer_model if self.model_assignment else None
        if not model_name:
            # fallback 到 architect 模型
            model_name = self.model_assignment.architect_model if self.model_assignment else "glm-z1-9b"

        client = LLMClient(
            model_name=model_name,
            task_type="review",
            api_key_token=self.api_key_token,
            cancel_event=self.cancel_event,
        )

        async def llm_caller(prompt: str, system_prompt: str) -> str:
            return await client.call(prompt, system_prompt)

        return llm_caller

    async def _infer_unknown_file_types(self, dep_graph, unknown_files: list, architecture: dict, language: str):
        """LLM 批量推断未知 file_type（语言无关通用方法）

        将所有 unknown 文件一次性发给 LLM，让它根据文件路径、描述和项目上下文
        推断每个文件的类型。语言无关：不依赖任何语言特定的硬编码规则。

        Args:
            dep_graph: 依赖图实例
            unknown_files: 未知类型的文件路径列表
            architecture: 架构设计字典
            language: 项目语言
        """
        file_plan = architecture.get("file_plan", [])
        file_descriptions = {f["path"]: f.get("description", "") for f in file_plan}

        # 构建文件信息列表
        file_info_lines = []
        for path in unknown_files:
            node = dep_graph.nodes.get(path)
            desc = file_descriptions.get(path, node.description if node else "")
            # 获取入度/出度信息辅助推断
            in_deg = len(dep_graph.reverse_adjacency.get(path, set()))
            out_deg = len(dep_graph.adjacency.get(path, set()))
            # 获取直接依赖的文件类型
            dep_types = []
            for dep in dep_graph.adjacency.get(path, set()):
                dep_node = dep_graph.nodes.get(dep)
                if dep_node:
                    dep_types.append(dep_node.file_type)
            dep_info = f", 依赖的文件类型: {dep_types}" if dep_types else ""
            file_info_lines.append(
                f"- {path} (描述: {desc}, 被{in_deg}个文件依赖, 依赖{out_deg}个文件{dep_info})"
            )

        valid_types = "entry, model, api, service, repository, types, database, config, middleware, frontend_component, frontend_page, frontend_style, template, test, utils, docs"

        prompt = f"""你是一个代码架构分析器。请根据以下信息，推断每个文件的 file_type。

项目语言: {language}
项目描述: {architecture.get('project_type', '')}

待推断的文件列表:
{chr(10).join(file_info_lines)}

有效的 file_type 值: {valid_types}

请返回一个 JSON 数组，每个元素包含 path 和 file_type 两个字段。
只输出 JSON，不要任何解释。
示例: [{{"path": "src/config.py", "file_type": "config"}}, ...]"""

        try:
            from app.utils import call_llm
            # 获取 backend_model，如果 model_assignment 不存在则使用默认值
            backend_model = getattr(self.model_assignment, 'backend_model', None) if self.model_assignment else None
            if not backend_model:
                from app.agent.models import DEFAULT_CODE_MODEL
                backend_model = DEFAULT_CODE_MODEL
            
            response = await call_llm(
                model=backend_model,
                prompt=prompt,
                system_prompt="你是一个代码文件类型推断器。只输出 JSON 数组。",
                api_key_token=getattr(self, 'api_key_token', None)
            )

            if response:
                # 处理可能的 dict 响应
                if isinstance(response, dict):
                    response = response.get("content", "") or response.get("text", "") or str(response)
                if not response.strip():
                    return
                import json as _json
                # 清理可能的 markdown 包裹
                text = response.strip()
                if text.startswith('```'):
                    text = text.split('\n', 1)[-1]
                if text.endswith('```'):
                    text = text.rsplit('```', 1)[0]
                text = text.strip()

                # 尝试解析 JSON
                inferred = _json.loads(text)
                if isinstance(inferred, list):
                    valid_type_set = set(valid_types.split(', '))
                    updated = 0
                    for item in inferred:
                        if isinstance(item, dict):
                            path = item.get("path", "")
                            ftype = item.get("file_type", "")
                            if path and ftype and ftype in valid_type_set:
                                dep_graph.update_file_type(path, ftype)
                                updated += 1
                    logger.info(f"LLM 批量推断完成: {updated}/{len(inferred)} 个文件类型已更新")
                else:
                    logger.warning(f"LLM 推断返回非数组格式: {type(inferred).__name__}")
            else:
                logger.warning("LLM 推断返回空响应")
        except Exception as e:
            logger.warning(f"LLM 批量推断失败: {e}，保留原有 file_type")

    async def _retry_generate_file(
        self,
        file_path: str,
        description: str,
        project_context: Dict,
        spec_context: str,
        dep_context: str,
        engineer,
        callback,
        heartbeat_tracker=None,
        reason: str = "",
    ) -> Optional[str]:
        """重试生成文件：先用当前模型重试，失败后升级到更强模型

        替代原来的 _generate_placeholder，不再生成占位符文件。

        Args:
            file_path: 文件路径
            description: 文件描述
            project_context: 项目上下文
            spec_context: 规格上下文
            dep_context: 依赖上下文
            engineer: 当前工程师实例
            callback: 进度回调
            heartbeat_tracker: 心跳追踪器
            reason: 失败原因

        Returns:
            生成的内容，失败返回 None
        """
        from app.agent.utils import is_valid_code_content, clean_code_block, validate_language_with_llm, get_expected_language_for_file

        target_language = project_context.get("architecture", {}).get("language", "")
        file_expected_language = get_expected_language_for_file(file_path, target_language)

        # 第一轮：用当前模型重试（直接 LLM，不走 ReAct）
        error_hint = f"上次生成失败：{reason}" if reason else "上次生成失败"
        retry_prompt = f"""请直接返回文件 {file_path} 的完整代码。

{error_hint}

文件描述：{description}
{spec_context}
{dep_context}

【严格要求】
- 直接输出代码，不要输出任何解释或思考过程
- 第一行必须是 import 语句或函数/类定义或 HTML 标签
- 代码必须完整，不要用 ... 省略
- **禁止占位符**：严禁生成 TODO、FIXME、pass、NotImplementedError 等占位符"""

        for attempt in range(2):
            logger.info(f"重试生成文件 (当前模型) {attempt + 1}/2: {file_path}")
            if heartbeat_tracker:
                heartbeat_tracker.touch()

            content = await engineer.call_llm(retry_prompt, engineer.SYSTEM_PROMPT, thinking_budget=50)
            if heartbeat_tracker:
                heartbeat_tracker.touch()

            if not content or not content.strip():
                continue

            content = clean_code_block(content)
            is_valid, new_reason = is_valid_code_content(file_path, content)
            if is_valid:
                if file_expected_language and self._quick_llm_check:
                    lang_ok, _ = await validate_language_with_llm(
                        file_path, content, file_expected_language, self._quick_llm_check
                    )
                    if lang_ok:
                        logger.info(f"重试成功 (当前模型): {file_path}")
                        return content
                else:
                    logger.info(f"重试成功 (当前模型): {file_path}")
                    return content

        # 第二轮：升级到更强模型
        if hasattr(self, 'model_assignment') and self.model_assignment:
            alt_model = self._select_alternative_model(
                getattr(engineer, 'model_name', None) or self.model_assignment.backend_model
            )
            alt_engineer = self._select_engineer_for_model(alt_model)
            if alt_engineer and alt_engineer is not engineer:
                logger.info(f"升级模型重试: {file_path} -> {alt_model}")
                for attempt in range(2):
                    if heartbeat_tracker:
                        heartbeat_tracker.touch()

                    content = await alt_engineer.call_llm(retry_prompt, alt_engineer.SYSTEM_PROMPT, thinking_budget=50)
                    if heartbeat_tracker:
                        heartbeat_tracker.touch()

                    if not content or not content.strip():
                        continue

                    content = clean_code_block(content)
                    is_valid, new_reason = is_valid_code_content(file_path, content)
                    if is_valid:
                        if file_expected_language and self._quick_llm_check:
                            lang_ok, _ = await validate_language_with_llm(
                                file_path, content, file_expected_language, self._quick_llm_check
                            )
                            if lang_ok:
                                logger.info(f"重试成功 (升级模型 {alt_model}): {file_path}")
                                return content
                        else:
                            logger.info(f"重试成功 (升级模型 {alt_model}): {file_path}")
                            return content

        logger.error(f"所有重试均失败: {file_path}，文件将不会被生成")
        return None

    async def _fix_sandbox_errors(
        self,
        sandbox_errors: list,
        files_dict: dict,
        ctx,
        max_rounds: int = 2,
    ) -> list:
        """自动修复沙箱验证错误

        Args:
            sandbox_errors: 沙箱验证错误列表
            files_dict: 文件字典 {file_path: content}
            ctx: 共享上下文
            max_rounds: 最大修复轮次（默认 2）

        Returns:
            修复的文件路径列表
        """
        import re
        from app.utils.aicloud.llm_caller import call_llm

        fixed_files = []

        # 解析错误，按文件分组
        # 支持三种格式:
        #   1. "file_path: ImportError: message"
        #   2. "file_path: Import Error: NameError: message"
        #   3. "file_path.Class.method(): NameError: message"
        #   4. "File \"file_path\", line N: ErrorType: message" (带行号)
        file_errors = {}
        for error in sandbox_errors:
            file_path = None
            error_type = None
            error_msg = None
            line_number = None

            # 尝试提取行号：File "xxx", line N
            line_match = re.search(r'File "([^"]+)", line (\d+)', error)
            if line_match:
                file_path = line_match.group(1)
                line_number = int(line_match.group(2))
            else:
                # 尝试提取文件路径：找第一个 .py 结尾的部分
                py_match = re.search(r'(\S+\.py)\b', error)
                if not py_match:
                    continue
                file_path = py_match.group(1)

            # 判断是哪种格式
            if '():' in error or '().' in error:
                # 格式 3: 运行时错误 - "src/models.py.Class.method(): NameError: ..."
                type_match = re.search(r'(\w+Error):\s*(.+)$', error)
                if type_match:
                    error_type = type_match.group(1)
                    error_msg = type_match.group(2)
            else:
                # 格式 1/2: 导入错误
                type_match = re.search(r'(?:Import\s+Error|ImportError|Exception):\s*(.+)$', error)
                if type_match:
                    error_msg = type_match.group(1)
                    nested_match = re.match(r'^(\w+Error):\s*(.+)$', error_msg)
                    if nested_match:
                        error_type = nested_match.group(1)
                        error_msg = nested_match.group(2)
                    else:
                        error_type = "ImportError"

            if file_path and file_path in files_dict and error_type:
                if file_path not in file_errors:
                    file_errors[file_path] = []
                file_errors[file_path].append({
                    "type": error_type,
                    "message": error_msg,
                    "line": line_number,
                    "full_error": error
                })

        if not file_errors:
            return fixed_files

        # 对每个文件进行修复（最多 max_rounds 轮）
        for file_path, errors in file_errors.items():
            for round_num in range(max_rounds):
                try:
                    content = files_dict[file_path]

                    # 构建详细的错误信息（包含行号和上下文）
                    error_details = []
                    for err in errors:
                        detail = f"- 错误类型: {err['type']}\n  消息: {err['message']}"
                        if err['line']:
                            detail += f"\n  行号: {err['line']}"
                            # 提取错误行周围的上下文（前后各 3 行）
                            lines = content.split('\n')
                            start = max(0, err['line'] - 4)
                            end = min(len(lines), err['line'] + 3)
                            context_lines = []
                            for i in range(start, end):
                                prefix = ">>>" if i == err['line'] - 1 else "   "
                                context_lines.append(f"{prefix} {i+1}: {lines[i]}")
                            detail += f"\n  上下文:\n" + "\n".join(context_lines)
                        error_details.append(detail)

                    error_text = "\n\n".join(error_details)

                    system_prompt = (
                        "你是一个专业的软件工程师。你需要修复代码中的导入错误和运行时错误。\n"
                        "常见修复方式:\n"
                        "1. ImportError: 添加缺失的 import 语句\n"
                        "2. NameError: 确保变量/函数已定义或已导入\n"
                        "3. ModuleNotFoundError: 检查模块路径是否正确\n\n"
                        "重要规则:\n"
                        "- 只修复报告的错误，不要删除或修改其他代码\n"
                        "- 保持代码结构和功能不变\n"
                        "- 禁止生成占位符代码（console.log、TODO、FIXME、pass 等）\n"
                        "- 直接输出修复后的完整代码，不要解释"
                    )

                    user_prompt = (
                        f"文件路径: {file_path}\n\n"
                        f"当前代码:\n```python\n{content}\n```\n\n"
                        f"检测到的错误（第 {round_num + 1}/{max_rounds} 轮修复）:\n{error_text}\n\n"
                        "请修复上述错误，输出完整的修复后代码。只修改有错误的部分，保持其他代码不变。"
                    )

                    response = await call_llm(
                        model=self.model_assignment.reviewer_model if hasattr(self, 'model_assignment') and self.model_assignment else None,
                        prompt=user_prompt,
                        max_tokens=4096,
                        temperature=0.3,
                        system_prompt=system_prompt,
                        api_key_token=self.api_key_token
                    )

                    fixed_content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if not fixed_content:
                        break

                    # 清理代码块标记
                    fixed_content = self._clean_code_block(fixed_content)

                    # 验证修复后的代码是否有效
                    from app.agent.utils import is_valid_code_content
                    is_valid, reason = is_valid_code_content(file_path, fixed_content)

                    if not is_valid or fixed_content == content:
                        logger.warning(f"沙箱验证修复无效: {file_path} - {reason}")
                        break

                    # 写入文件（使用原子写入）
                    from app.agent.utils import write_file_atomic as _wf_atomic
                    _wf_atomic(self.output_dir, file_path, fixed_content)

                    # 更新上下文
                    ctx.save_file_content(file_path, fixed_content, "sandbox_fix")
                    files_dict[file_path] = fixed_content  # 更新字典供下一轮使用

                    # 重新验证这个文件
                    from app.agent.utils import validate_in_sandbox
                    ok, new_errors = validate_in_sandbox(
                        project_dir=str(self.output_dir),
                        files={file_path: fixed_content},
                        level="run",
                        context={"trigger": "sandbox_fix"}
                    )

                    if ok:
                        fixed_files.append(file_path)
                        logger.info(f"沙箱验证修复成功: {file_path} (第 {round_num + 1} 轮)")
                        break
                    else:
                        # 解析新错误，准备下一轮修复
                        errors = []
                        for err in new_errors:
                            err_match = re.search(r'(\w+Error):\s*(.+)$', err)
                            if err_match:
                                errors.append({
                                    "type": err_match.group(1),
                                    "message": err_match.group(2),
                                    "line": None,
                                    "full_error": err
                                })
                        if not errors or round_num == max_rounds - 1:
                            logger.warning(f"沙箱验证修复失败: {file_path} (第 {round_num + 1} 轮)")
                            break

                except Exception as e:
                    logger.warning(f"沙箱验证修复异常: {file_path} - {e}")
                    break

        return fixed_files

    async def _recover_invalid_content(
        self,
        file_path: str,
        description: str,
        project_context: Dict,
        reason: str,
        engineer,
        spec_context: str = "",
        dep_context: str = "",
        callback=None,
        heartbeat_tracker=None,
    ) -> Optional[str]:
        """恢复无效内容：直接调用 LLM 生成代码（不走 ReAct，节省 token）

        Args:
            file_path: 文件路径
            description: 文件描述
            project_context: 项目上下文
            reason: 无效原因（来自 is_valid_code_content）
            engineer: 工程师实例
            spec_context: 规格上下文
            dep_context: 依赖上下文
            callback: 进度回调

        Returns:
            恢复后的内容，失败返回 None
        """
        if "JSON 元数据" in reason:
            error_hint = "上次返回了 JSON 元数据，不是代码。请直接返回代码，不要包裹在 JSON 中。"
        elif "Markdown" in reason:
            error_hint = "上次返回了 Markdown 文档，不是代码。请直接返回代码，不要用 Markdown 格式包裹。"
        else:
            error_hint = f"上次生成的内容无效：{reason}"

        # 构建精简 prompt：只包含生成单个文件所需的最小上下文
        file_name = file_path.rsplit('/', 1)[-1] if '/' in file_path else file_path
        recovery_prompt = f"""请直接返回文件 {file_path} 的完整代码。

{error_hint}

文件描述：{description}
{spec_context}
{dep_context}

【严格要求】
- 直接输出代码，不要输出任何解释或思考过程
- 不要调用任何工具，不要搜索文件
- 第一行必须是 import 语句或函数/类定义或 HTML 标签
- 代码必须完整，不要用 ... 省略
- 不要用 ```markdown 代码块标记包裹整个文件
- **禁止占位符**：严禁生成 console.log("placeholder")、TODO、FIXME、pass、NotImplementedError 等占位符，必须是完整实现"""

        for attempt in range(3):
            logger.info(f"内容恢复尝试 {attempt + 1}/3: {file_path}（直接 LLM）")
            if heartbeat_tracker:
                heartbeat_tracker.touch()

            # 直接调用 LLM，不走 ReAct（上下文已齐全，只需生成代码）
            content = await engineer.call_llm(recovery_prompt, engineer.SYSTEM_PROMPT, thinking_budget=50)
            if heartbeat_tracker:
                heartbeat_tracker.touch()

            if not content or not content.strip():
                logger.warning(f"内容恢复 LLM 返回空: {file_path} (第 {attempt + 1} 次)")
                continue

            # 清理代码块标记
            from app.agent.utils import clean_code_block
            content = clean_code_block(content)

            # 验证
            from app.agent.utils import get_expected_language_for_file, is_valid_code_content, validate_language_with_llm
            target_language = project_context.get("architecture", {}).get("language", "")
            file_expected_language = get_expected_language_for_file(file_path, target_language)

            is_valid, new_reason = is_valid_code_content(file_path, content)
            if is_valid:
                # 语言检测
                if file_expected_language and self._quick_llm_check:
                    lang_ok, lang_reason = await validate_language_with_llm(
                        file_path, content, file_expected_language, self._quick_llm_check
                    )
                    if not lang_ok:
                        logger.warning(f"内容恢复语言检测失败: {file_path} - {lang_reason} (第 {attempt + 1} 次)")
                        continue
                logger.info(f"内容恢复成功: {file_path} (第 {attempt + 1} 次)")
                # 写入文件（使用原子写入）
                from app.agent.utils import write_file_atomic as _wf_atomic
                _wf_atomic(self.output_dir, file_path, content)
                return content
            logger.warning(f"内容恢复失败: {file_path} - {new_reason} (第 {attempt + 1} 次)")

        logger.error(f"内容恢复彻底失败: {file_path}")
        return None

    async def _validate_project_completeness(
        self,
        file_plan: list,
        generated_files: Dict[str, str],
    ) -> Dict[str, Any]:
        """验证项目完整性

        检查所有计划文件是否都已生成，内容是否有效。

        Returns:
            {
                "total_planned": int,
                "total_generated": int,
                "missing_files": [str],
                "empty_files": [str],
                "invalid_files": [(str, str)],
                "is_complete": bool
            }
        """
        from app.agent.utils import is_valid_code_content

        planned_files = {f["path"] for f in file_plan}
        generated_set = set(generated_files.keys())

        missing_files = sorted(planned_files - generated_set)

        empty_files = [
            f for f, c in generated_files.items()
            if not c or len(c.strip()) < 10
        ]

        invalid_files = []
        placeholder_files = []
        for f, c in generated_files.items():
            if f in empty_files:
                continue
            is_valid, reason = is_valid_code_content(f, c)
            if not is_valid:
                invalid_files.append((f, reason))
            # 占位符检测
            from app.agent.utils import is_placeholder_content
            is_ph, ph_reason = is_placeholder_content(c, f)
            if is_ph:
                placeholder_files.append((f, ph_reason))
                logger.warning(f"检测到占位符文件: {f} - {ph_reason}")

        return {
            "total_planned": len(planned_files),
            "total_generated": len(generated_set),
            "missing_files": missing_files,
            "empty_files": empty_files,
            "invalid_files": invalid_files,
            "placeholder_files": placeholder_files,
            "is_complete": len(missing_files) == 0 and len(invalid_files) == 0 and len(placeholder_files) == 0,
        }

    async def _quick_llm_check(self, prompt: str) -> str:
        """快速 LLM 检查（用于语言校验等轻量任务）"""
        from app.utils import call_llm
        try:
            # 获取 backend_model，如果 model_assignment 不存在则使用默认值
            backend_model = getattr(self.model_assignment, 'backend_model', None) if self.model_assignment else None
            if not backend_model:
                from app.agent.models import DEFAULT_CODE_MODEL
                backend_model = DEFAULT_CODE_MODEL
            
            response = await call_llm(
                model=backend_model,
                prompt=prompt,
                system_prompt="你是一个代码语言检测器。只回答 YES 或 NO。",
                api_key_token=getattr(self, 'api_key_token', None)
            )
            return response.strip() if response else ""
        except Exception as e:
            logger.debug(f"_quick_llm_check 失败: {e}")
            return ""

    async def refactor_file(
        self,
        file_to_split: str,
        requirement: str,
        callback: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """重构：拆分过大文件

        Args:
            file_to_split: 要拆分的文件路径
            requirement: 拆分需求描述
            callback: 进度回调

        Returns:
            {"success": bool, "new_files": [...], "errors": [...]}
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 1. 加载已有依赖图
        dep_graph_path = self.output_dir / ".dep_graph.json"
        detected_language = "python"
        language_adapter = LanguageAdapterRegistry.get_adapter(detected_language)
        dep_graph = DependencyGraph.load(str(dep_graph_path), language_adapter=language_adapter)

        if dep_graph is None:
            return {"success": False, "errors": ["依赖图不存在，无法执行重构"]}

        if file_to_split not in dep_graph.nodes:
            return {"success": False, "errors": [f"文件 {file_to_split} 不在依赖图中"]}

        # 2. 读取原文件内容
        full_path = self.output_dir / file_to_split
        if not full_path.exists():
            return {"success": False, "errors": [f"文件 {file_to_split} 不存在"]}
        original_content = full_path.read_text(encoding='utf-8')

        # 3. 让架构师生成拆分方案
        split_prompt = f"""请为以下文件生成拆分方案：

文件路径：{file_to_split}
拆分需求：{requirement}

文件内容：
```
{original_content[:8000]}
```

请输出 JSON 格式的拆分方案：
```json
{{
  "new_files": [
    {{"path": "新文件路径", "file_type": "文件类型", "priority": 3, "description": "文件描述"}}
  ],
  "import_mapping": {{
    "旧 import 路径": "新 import 路径"
  }},
  "old_file_action": "delete|keep"
}}
```

new_files: 拆分后的新文件列表
import_mapping: 旧文件的 import 应该重定向到哪个新文件
old_file_action: delete 表示删除原文件，keep 表示保留（如只读包装器）

要求：
- 新文件路径必须合法，不得包含空格
- file_type 必须从以下值中选择：entry, model, api, service, repository, types, database, config, middleware, frontend_component, frontend_page, frontend_style, template, test, utils, docs
- import_mapping 必须覆盖原文件的所有导出"""

        from app.utils import call_llm
        backend_model = getattr(self.model_assignment, 'backend_model', None) if self.model_assignment else None
        if not backend_model:
            from app.agent.models import DEFAULT_CODE_MODEL
            backend_model = DEFAULT_CODE_MODEL

        response = await call_llm(
            model=backend_model,
            prompt=split_prompt,
            system_prompt="你是一个代码重构专家。只输出 JSON 格式，不要包含任何解释文字。",
            api_key_token=self.api_key_token,
        )

        # 4. 解析拆分方案
        import json
        try:
            # 提取 JSON
            response_text = response.strip()
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()
            elif "```" in response_text:
                start = response_text.find("```") + 3
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()

            split_plan = json.loads(response_text)
        except (json.JSONDecodeError, ValueError) as e:
            return {"success": False, "errors": [f"拆分方案解析失败: {e}"]}

        new_files = split_plan.get("new_files", [])
        import_mapping = split_plan.get("import_mapping", {})
        old_file_action = split_plan.get("old_file_action", "delete")

        if not new_files:
            return {"success": False, "errors": ["拆分方案中没有新文件"]}

        # 5. 更新依赖图
        added_paths = dep_graph.refactor_file(file_to_split, new_files, import_mapping)

        # 6. 验证重构后的依赖图
        validator = DependencyGraphValidator(
            llm_caller=self._create_validator_llm_caller(),
            language_adapter=language_adapter,
        )
        validation_result = await validator.validate(
            dep_graph, scope="refactor", new_files=added_paths
        )

        if not validation_result.passed:
            logger.warning(f"重构验证未通过: {len(validation_result.issues)} 个问题")
            for issue in validation_result.issues:
                logger.warning(f"  [{issue.issue_type}] {issue.message}")

        # 7. 保存依赖图
        dep_graph.save(str(dep_graph_path))

        # 8. 生成新文件（使用现有的文件生成流程）
        self._report_progress(
            "refactor_start", 0, len(added_paths),
            callback=callback,
            old_file=file_to_split,
            new_files=added_paths,
        )

        generated = []
        errors = []
        for i, new_path in enumerate(added_paths):
            node = dep_graph.nodes.get(new_path)
            description = node.description if node else f"拆分自 {file_to_split}"

            # 构建上下文
            upstream_context = dep_graph.get_context_for_file(
                new_path, generated, str(self.output_dir)
            )
            context = f"这是从 {file_to_split} 拆分出来的文件。\n\n需求：{requirement}\n\n"
            context += f"原始文件内容（参考）：\n```\n{original_content[:4000]}\n```\n\n"
            if upstream_context:
                context += f"依赖文件内容：\n{upstream_context}\n"

            # 调用工程师生成
            try:
                from app.agent.backend_engineer import BackendEngineer
                engineer = BackendEngineer(
                    model_name=self.model_assignment.backend_model if self.model_assignment else None,
                    api_key_token=self.api_key_token,
                )
                content = await engineer.generate_file(
                    new_path, description, context, "",
                    project_path=str(self.output_dir),
                    callback=callback,
                    is_existing_file=False,
                )

                # 提取内容
                from app.agent.utils import extract_engineer_content
                content = await extract_engineer_content(
                    content, engineer, self.output_dir, new_path,
                    expected_language="Python",
                    llm_caller=self._quick_llm_check,
                )

                if content:
                    # 写入文件
                    write_file_atomic(self.output_dir, new_path, content)
                    generated.append(new_path)
                    self._report_progress(
                        "refactor_file_generated", i + 1, len(added_paths),
                        callback=callback,
                        file_path=new_path,
                    )
                else:
                    errors.append(f"文件生成失败: {new_path} (内容为空)")
            except Exception as e:
                errors.append(f"文件生成异常: {new_path} ({e})")

        # 9. 处理原文件
        if old_file_action == "delete" and generated:
            # 只有所有新文件都生成成功才删除原文件
            if len(generated) == len(added_paths):
                full_path.unlink()
                logger.info(f"已删除原文件: {file_to_split}")
            else:
                logger.warning(f"部分新文件生成失败，保留原文件: {file_to_split}")

        self._report_progress(
            "refactor_complete", len(added_paths), len(added_paths),
            callback=callback,
            old_file=file_to_split,
            new_files=generated,
            errors=errors,
        )

        return {
            "success": len(errors) == 0,
            "old_file": file_to_split,
            "new_files": generated,
            "errors": errors,
        }
