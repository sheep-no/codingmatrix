import ast  # noqa: F401 - tests patch this module attribute
import asyncio
import hashlib
import importlib.util  # noqa: F401 - tests patch this module attribute
import json
import logging
import re
import subprocess  # noqa: F401 - tests patch this module attribute
from pathlib import Path

from app.agent.code_patcher import apply_incremental_change
from app.agent.code_validator import CodeValidator
from app.agent.dependency_graph import summarize_dependency_context
from app.agent.dynamic_model_router import get_context_length
from app.agent.models import DEFAULT_CODE_MODEL, DEFAULT_FAST_MODEL
from app.agent.orchestrator_progress import PROGRESS_LABELS
from app.agent.specialists import Specialist
from app.agent.topology_scheduler import HeartbeatTracker
from app.agent.utils import (
    extract_engineer_content,
    is_documentation_file,
    write_file_atomic,
)
from app.utils import call_llm

logger = logging.getLogger(__name__)


from app.agent.file_generation_repairs import (  # noqa: F401
    _ROLE_ALIASES,
    _WRITE_TOOLS,
    _architecture_path_for_role,
    _declared_python_framework_roots,
    _file_contract,
    _file_matches_role,
    _file_plan_item,
    _file_role,
    _fix_absolute_imports,
    _format_review_issues,
    _git_stash_drop,
    _git_stash_pop,
    _git_stash_push,
    _invalid_sqlalchemy_metadata_owners,
    _is_edit_marker,
    _python_class_fields,
    _python_defined_exports,
    _python_exports,
    _python_module_name,
    _python_project_module_aliases,
    _repair_python_fastapi_class_route_registration,
    _repair_python_invalid_code_marker,
    _repair_python_known_imports,
    _repair_python_project_call_keywords,
    _repair_python_project_symbol_imports,
    _repair_python_pydantic_base_alias,
    _repair_python_schema_field_access,
    _repair_python_sessionmaker_class_none,
    _repair_python_shared_base,
    _repair_python_sqlalchemy_datetime_defaults,
    _repair_python_sqlalchemy_get_db,
    _repair_python_sqlalchemy_metadata_owner,
    _repair_python_sqlalchemy_table_initialization,
    _repair_python_sqlalchemy_text_execute,
    _repair_python_sqlite_connection_url,
    _repair_python_sync_async_calls,
    _repair_python_test_database_fixtures,
    _repair_python_unmounted_fastapi_router,
    _structured_import_diagnostics,
    _validate_python_contract,
    _validate_python_database_abstraction,
    _validate_python_implementation,
    _validate_python_project_imports,
    _validate_python_schema_field_access,
    _validate_python_sqlalchemy_metadata_owner,
    _validate_python_test_structure,
)


class FilesMixin:

    async def _generate_files_small_project(
        self,
        file_plan: list[dict],
        project_context: dict,
        total_files: int
    ):
        # 分离已有文件和新文件
        existing_files = []
        new_files = []
        for fi in file_plan:
            fp = fi.get("path", "")
            full_path = self.output_dir / fp
            if full_path.exists():
                existing_files.append(fp)
            else:
                new_files.append(fp)

        # git stash 备份已有文件
        errors_baseline = len(self.errors)
        stashed = _git_stash_push(str(self.output_dir), existing_files, "agent-backup-batch")
        if not stashed:
            self.warnings.append(
                "增量备份不可用（git stash 失败），生成失败时无法回滚已修改文件"
            )

        # 分批并发生成，避免大量协程同时存在
        if self.cancel_event and self.cancel_event.is_set():
            logger.info("[生成] 检测到取消信号，跳过小项目生成")
            return
        BATCH_SIZE = 20
        results = []
        for i in range(0, len(file_plan), BATCH_SIZE):
            if self.cancel_event and self.cancel_event.is_set():
                logger.info("[生成] 检测到取消信号，中断批次生成")
                return
            batch = file_plan[i:i + BATCH_SIZE]
            batch_results = await asyncio.gather(
                *[self._generate_single_file(fi, project_context, total_files) for fi in batch],
                return_exceptions=True
            )
            results.extend(batch_results)

        # 检查是否全部成功
        all_success = True
        for i, result in enumerate(results):
            if isinstance(result, asyncio.CancelledError):
                # 取消从 LLM 流内以 BaseException 冒出，须显式分诊，
                # 否则 truthy 分支对其调 .get() 会 AttributeError 绕过回滚
                file_path = file_plan[i].get("path", "unknown") if i < len(file_plan) else "unknown"
                self.errors.append(f"文件生成被取消: {file_path}")
                all_success = False
            elif isinstance(result, Exception):
                self.errors.append(f"文件生成失败: 内部异常 - {self._friendly_error(str(result))}")
                all_success = False
            elif result is None:
                file_path = file_plan[i].get("path", "unknown") if i < len(file_plan) else "unknown"
                self.errors.append(f"文件生成失败: {file_path}（返回空内容）")
                all_success = False
            elif result and not result.get("success", True):
                all_success = False

        if not all_success:
            # 回滚：恢复 git stash + 删除新文件
            if stashed:
                _git_stash_pop(str(self.output_dir))
                logger.info(f"git stash pop: 回滚 {len(existing_files)} 个文件")
            for fp in new_files:
                full_path = self.output_dir / fp
                if full_path.exists():
                    full_path.unlink()
                    logger.info(f"删除失败的新文件: {fp}")
            self.warnings.append("小项目生成失败，已回滚")
            raise RuntimeError(
                "small project file generation failed: "
                + "; ".join(self.errors[errors_baseline:])
            )
        else:
            # 成功：丢弃 stash
            if stashed:
                _git_stash_drop(str(self.output_dir))
            for result in results:
                if result and not isinstance(result, BaseException):
                    self.generated_files.append(result)

    async def _generate_files_by_dep_layers(
        self,
        file_plan: list[dict],
        project_context: dict,
        total_files: int,
        dep_graph
    ):
        layers = dep_graph.get_generation_layers()

        file_info_map: dict[str, dict] = {fi.get("path", ""): fi for fi in file_plan}

        for layer_idx, layer in enumerate(layers):
            if self.cancel_event and self.cancel_event.is_set():
                logger.info(f"[生成] 检测到取消信号，终止层循环 | layer={layer_idx + 1}/{len(layers)}")
                break
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

            # 分离已有文件和新文件
            existing_files = []
            new_files = []
            for fp in layer_files:
                full_path = self.output_dir / fp
                if full_path.exists():
                    existing_files.append(fp)
                else:
                    new_files.append(fp)

            # git stash 备份已有文件
            errors_baseline = len(self.errors)
            stashed = _git_stash_push(str(self.output_dir), existing_files, f"agent-backup-layer-{layer_idx}")
            if not stashed:
                self.warnings.append(
                    f"第 {layer_idx + 1} 层增量备份不可用（git stash 失败），失败时无法回滚该层已修改文件"
                )

            # 直接并发生成，由 LLMClient 内部信号量控制并发度
            async def generate_file(file_path: str) -> dict:
                fi = file_info_map.get(file_path, {"path": file_path, "description": f"生成 {file_path}"})
                return await self._generate_single_file(fi, project_context, total_files, self._generated_contents)

            tasks = [generate_file(fp) for fp in layer_files]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 检查本层是否全部成功
            layer_success = True
            for i, result in enumerate(results):
                if isinstance(result, asyncio.CancelledError):
                    # 取消从 LLM 流内以 BaseException 冒出，须显式分诊，
                    # 否则 truthy 分支对其调 .get() 会 AttributeError 绕过回滚
                    file_path = layer_files[i] if i < len(layer_files) else "unknown"
                    self.errors.append(f"文件生成被取消: {file_path}")
                    layer_success = False
                elif isinstance(result, Exception):
                    self.errors.append(f"文件生成失败: 内部异常 - {self._friendly_error(str(result))}")
                    layer_success = False
                elif result is None:
                    file_path = layer_files[i] if i < len(layer_files) else "unknown"
                    self.errors.append(f"文件生成失败: {file_path}（返回空内容）")
                    layer_success = False
                elif result and not result.get("success", True):
                    layer_success = False

            if not layer_success:
                # 回滚：恢复 git stash + 删除新文件
                if stashed:
                    _git_stash_pop(str(self.output_dir))
                    logger.info(f"git stash pop: 回滚第 {layer_idx+1} 层 {len(existing_files)} 个文件")
                for fp in new_files:
                    full_path = self.output_dir / fp
                    if full_path.exists():
                        full_path.unlink()
                        logger.info(f"删除失败的新文件: {fp}")
                self.warnings.append(f"第 {layer_idx+1} 层生成失败，已回滚")
                raise RuntimeError(
                    f"dependency layer {layer_idx + 1} file generation failed: "
                    + "; ".join(self.errors[errors_baseline:])
                )
            else:
                # 成功：丢弃 stash
                if stashed:
                    _git_stash_drop(str(self.output_dir))
                for result in results:
                    if result and not isinstance(result, BaseException):
                        self.generated_files.append(result)
                        try:
                            full_path = self.output_dir / result["path"]
                            if full_path.exists():
                                self._generated_contents[result["path"]] = full_path.read_text(encoding="utf-8")
                        except Exception as read_err:
                            logger.debug(f"读取生成文件内容失败: {read_err}")

    async def _generate_single_file(
        self,
        file_info: dict,
        project_context: dict,
        total_files: int,
        generated_contents: dict | None = None
    ) -> dict | None:
        file_path = file_info.get("path", "")
        description = file_info.get("description", "")

        self._report_progress(
            PROGRESS_LABELS["generating_file"],
            len(self.generated_files) + 1,
            total_files + 4,
            file_path=file_path,
            description=description,
            model=self._select_model_for_file(file_path)
        )

        engineer = self._select_engineer(file_path)
        role_name = engineer.name if hasattr(engineer, 'name') else '工程师'

        self._report_thinking(
            "engineer",
            f"{role_name} 正在分析 {file_path} 的需求：{description[:80]}{'...' if len(description) > 80 else ''}"
        )

        prevention_prompt = ""
        if self.feedback_learner:
            file_type = "frontend" if self._is_frontend_file(file_path) else "backend"
            prevention_prompt = await self.feedback_learner.get_prevention_prompt(
                file_path=file_path,
                file_type=file_type,
                project_context=project_context
            )
            if prevention_prompt:
                project_context = {**project_context, "prevention_hints": prevention_prompt}

        spec_context = ""
        dep_context = ""
        if self.dependency_graph_obj:
            file_model = self._select_model_for_file(file_path)
            dep_context = self.dependency_graph_obj.get_context_for_file(
                file_path,
                generated_contents or {},
                model_context_length=get_context_length(file_model),
            )
        dep_audit = summarize_dependency_context(dep_context)
        logger.info(
            "依赖上下文审计: target=%s model=%s generated_count=%d dep=%s",
            file_path,
            self._select_model_for_file(file_path),
            len(generated_contents or {}),
            dep_audit,
        )

        # 判断文件是否已存在
        full_path = self.output_dir / self._normalize_file_path(file_path)
        is_existing = full_path.exists()

        # 清空编辑记录
        engineer.clear_edits()

        heartbeat_tracker = HeartbeatTracker(
            timeout=float(getattr(self, "heartbeat_timeout", 120.0))
        )

        content = await engineer.generate_file(
            file_path, description, project_context, spec_context, dep_context,
            project_path=str(self.output_dir), callback=self.callback,
            is_existing_file=is_existing,
            heartbeat_tracker=heartbeat_tracker,
        )
        if asyncio.iscoroutine(content):
            logger.warning(f"generate_file 返回协程，自动 await: {file_path}")
            content = await content

        # 防御性检查：确保返回值是字符串而非协程
        if asyncio.iscoroutine(content):
            logger.warning(f"generate_file 返回协程而非字符串，自动 await: {file_path}")
            content = await content

        # 统一提取工程师生成的内容
        all_files = list(self.dependency_graph_obj.nodes.keys()) if self.dependency_graph_obj else []
        raw_content = content  # 保存原始内容用于恢复

        # 获取期望的语言，用于 LLM 语言检测
        project_language = project_context.get("architecture", {}).get("language", "")
        from app.agent.utils import get_expected_language_for_file
        expected_language = get_expected_language_for_file(file_path, project_language)
        assignment = getattr(self, "model_assignment", None)
        detection_model = getattr(assignment, "backend_model", None) if assignment else None

        async def llm_caller(prompt: str) -> str:
            if not detection_model:
                raise RuntimeError("model assignment is required for language detection")
            return await call_llm(
                model=detection_model,
                prompt=prompt,
                system_prompt="你是一个代码语言检测器。只回答 YES 或 NO。",
                api_key_token=getattr(self, 'api_key_token', None)
            )

        content = await extract_engineer_content(
            content, engineer, self.output_dir, file_path,
            fix_imports_fn=_fix_absolute_imports,
            all_files=all_files,
            expected_language=expected_language,
            llm_caller=llm_caller,
        )
        architecture = project_context.get("architecture", {})
        if content:
            content = _repair_python_shared_base(
                content, file_path, generated_contents or {}, architecture
            )
            content = _repair_python_sqlalchemy_metadata_owner(
                content, file_path, generated_contents or {}, architecture
            )
            content = _repair_python_sqlalchemy_text_execute(content, file_path)
            content = _repair_python_fastapi_class_route_registration(content, file_path)
            content = _repair_python_sqlite_connection_url(content, file_path)
            content = _repair_python_invalid_code_marker(content, file_path)
            content = _repair_python_unmounted_fastapi_router(content, file_path)
            content = _repair_python_sqlalchemy_datetime_defaults(content, file_path)
            content = _repair_python_sessionmaker_class_none(content, file_path)
            content = _repair_python_pydantic_base_alias(content, file_path)
            content = _repair_python_sqlalchemy_get_db(content, file_path, architecture)
            content = _repair_python_sqlalchemy_table_initialization(
                content,
                file_path,
                generated_contents or {},
                architecture,
            )
            content = _repair_python_test_database_fixtures(
                content, file_path, architecture
            )
            content = _repair_python_sync_async_calls(content, generated_contents or {})

        if not content:
            # 内容无效（可能是 JSON 元数据），尝试恢复
            from app.agent.utils import is_valid_code_content
            _, invalid_reason = is_valid_code_content(file_path, raw_content or "")
            if invalid_reason:
                logger.warning(f"内容无效: {file_path} - {invalid_reason}，尝试恢复")
                content = await self._recover_invalid_content_orchestator(
                    file_path,
                    description,
                    project_context,
                    invalid_reason,
                    engineer,
                    spec_context=spec_context,
                    dep_context=dep_context,
                    heartbeat_tracker=heartbeat_tracker,
                )

            if not content:
                raise RuntimeError(
                    f"file generation failed for {file_path}: empty content after recovery"
                )

        import_errors = _validate_python_implementation(content, file_path)
        import_errors.extend(_validate_python_database_abstraction(content, file_path, architecture))
        import_errors.extend(_validate_python_sqlalchemy_metadata_owner(content, file_path))
        import_errors.extend(_validate_python_schema_field_access(
            content, file_path, generated_contents or {}
        ))
        import_errors.extend(_validate_python_contract(
            content, file_path, project_context.get("architecture", {})
        ))
        import_errors.extend(_validate_python_project_imports(
            content, file_path, generated_contents or {}, all_files,
            project_context.get("architecture", {}),
        ))
        repaired_content = _repair_python_known_imports(content, import_errors)
        repaired_content = _repair_python_project_symbol_imports(
            repaired_content, import_errors, generated_contents or {}
        )
        repaired_content = _repair_python_project_call_keywords(repaired_content, import_errors)
        repaired_content = _repair_python_schema_field_access(repaired_content, import_errors)
        if repaired_content != content:
            content = repaired_content
            import_errors = _validate_python_implementation(content, file_path)
            import_errors.extend(_validate_python_database_abstraction(content, file_path, architecture))
            import_errors.extend(_validate_python_sqlalchemy_metadata_owner(content, file_path))
            import_errors.extend(_validate_python_schema_field_access(
                content, file_path, generated_contents or {}
            ))
            import_errors.extend(_validate_python_contract(
                content, file_path, project_context.get("architecture", {})
            ))
            import_errors.extend(_validate_python_project_imports(
                content, file_path, generated_contents or {}, all_files,
                project_context.get("architecture", {}),
            ))
        seen_error_fingerprints = set()
        for correction_round in range(1, 4):
            if not import_errors:
                break
            current_fingerprints = {
                hashlib.sha256(error.strip().encode("utf-8")).hexdigest()
                for error in import_errors
            }
            repeated_fingerprints = current_fingerprints & seen_error_fingerprints
            if repeated_fingerprints:
                logger.error(
                    "重复静态错误，停止继续修复: file=%s fingerprints=%d errors=%s",
                    file_path,
                    len(repeated_fingerprints),
                    import_errors,
                )
                break
            seen_error_fingerprints.update(current_fingerprints)
            logger.warning(
                "跨文件导入门禁失败: file=%s round=%d errors=%s",
                file_path,
                correction_round,
                import_errors,
            )
            engineer.clear_edits()
            correction = "；".join(import_errors)
            diagnostics = json.dumps(
                _structured_import_diagnostics(import_errors),
                ensure_ascii=False,
                indent=2,
            )
            correction_instructions = (
                "这些错误来自候选代码的静态检查。对于‘名称 X 在模块全局作用域中未定义或导入’，"
                "必须在模块顶层添加定义 X 的真实 import，或彻底移除对 X 的引用；"
                "对于项目模块或符号错误，只能使用已生成依赖上下文中真实存在的模块和导出。"
                "候选文件必须包含该文件职责所需的完整可执行实现，不能只返回 import、注释或问题说明。"
                "输出前逐个检查函数体、默认参数、ORM 字段参数和装饰器引用的名称，"
                "确认每个名称均已在模块顶层定义或导入。"
            )
            dependency_exports = []
            for dependency_path, dependency_source in (generated_contents or {}).items():
                if not dependency_path.endswith(".py"):
                    continue
                try:
                    exports = sorted(_python_exports(dependency_source))
                except SyntaxError:
                    continue
                dependency_exports.append(f"{dependency_path}: {', '.join(exports)}")
            if dependency_exports:
                correction_instructions += (
                    "已生成依赖真实公共符号清单如下，只能从清单中选择项目符号："
                    + "；".join(dependency_exports)
                    + "。"
                )
            if any("禁止混用" in error for error in import_errors):
                correction_instructions += (
                    "当前文件违反数据库抽象统一约束：必须根据架构契约和已生成依赖选择唯一持久化栈，"
                    "从候选源码中完整移除另一套驱动及其 API，不能只删除一条 import。"
                )
            corrected_raw = await engineer.generate_file(
                file_path,
                f"{description}\n此前候选文件校验失败：{correction}。"
                f"\n结构化诊断（逐项修复）：\n{diagnostics}\n{correction_instructions}"
                "请基于下面的上一版候选源码重新生成完整文件并修复全部问题：\n"
                f"```{expected_language}\n{content}\n```",
                project_context,
                spec_context,
                dep_context,
                project_path=str(self.output_dir),
                callback=self.callback,
                is_existing_file=is_existing,
                heartbeat_tracker=heartbeat_tracker,
            )
            if asyncio.iscoroutine(corrected_raw):
                corrected_raw = await corrected_raw
            corrected_content = await extract_engineer_content(
                corrected_raw,
                engineer,
                self.output_dir,
                file_path,
                fix_imports_fn=_fix_absolute_imports,
                all_files=all_files,
                expected_language=expected_language,
                llm_caller=llm_caller,
            )
            if corrected_content:
                content = _repair_python_shared_base(
                    corrected_content, file_path, generated_contents or {}, architecture
                )
                content = _repair_python_sqlalchemy_metadata_owner(
                    content, file_path, generated_contents or {}, architecture
                )
                content = _repair_python_sqlalchemy_text_execute(content, file_path)
                content = _repair_python_sqlalchemy_datetime_defaults(content, file_path)
                content = _repair_python_sessionmaker_class_none(content, file_path)
                content = _repair_python_pydantic_base_alias(content, file_path)
                content = _repair_python_sqlalchemy_get_db(content, file_path, architecture)
                content = _repair_python_sqlalchemy_table_initialization(
                    content,
                    file_path,
                    generated_contents or {},
                    architecture,
                )
                content = _repair_python_test_database_fixtures(
                    content, file_path, project_context.get("architecture", {})
                )
                content = _repair_python_sync_async_calls(
                    content, generated_contents or {}
                )
                import_errors = _validate_python_implementation(content, file_path)
                import_errors.extend(
                    _validate_python_database_abstraction(content, file_path, architecture)
                )
                import_errors.extend(_validate_python_sqlalchemy_metadata_owner(content, file_path))
                import_errors.extend(_validate_python_schema_field_access(
                    content, file_path, generated_contents or {}
                ))
                import_errors.extend(_validate_python_contract(
                    content, file_path, project_context.get("architecture", {})
                ))
                import_errors.extend(_validate_python_project_imports(
                    content, file_path, generated_contents or {}, all_files,
                    project_context.get("architecture", {}),
                ))
                repaired_content = _repair_python_known_imports(content, import_errors)
                repaired_content = _repair_python_project_symbol_imports(
                    repaired_content, import_errors, generated_contents or {}
                )
                repaired_content = _repair_python_project_call_keywords(
                    repaired_content, import_errors
                )
                repaired_content = _repair_python_schema_field_access(
                    repaired_content, import_errors
                )
                if repaired_content != content:
                    content = repaired_content
                    import_errors = _validate_python_implementation(content, file_path)
                    import_errors.extend(
                        _validate_python_database_abstraction(content, file_path, architecture)
                    )
                    import_errors.extend(_validate_python_sqlalchemy_metadata_owner(content, file_path))
                    import_errors.extend(_validate_python_schema_field_access(
                        content, file_path, generated_contents or {}
                    ))
                    import_errors.extend(_validate_python_contract(
                        content, file_path, project_context.get("architecture", {})
                    ))
                    import_errors.extend(_validate_python_project_imports(
                        content, file_path, generated_contents or {}, all_files,
                        project_context.get("architecture", {}),
                    ))
            else:
                from app.agent.utils import is_valid_code_content
                _, invalid_reason = is_valid_code_content(file_path, corrected_raw or "")
                invalid_reason = invalid_reason or "无法提取有效完整文件内容"
                import_errors = [f"修复响应无效: {invalid_reason}"]
                logger.warning(
                    "静态修复响应无效，保留上一版候选继续重试: file=%s round=%d reason=%s",
                    file_path,
                    correction_round,
                    invalid_reason,
                )

        from app.agent.validation_report import ValidationReport
        validation_report = ValidationReport.create(source="cloud")
        for validation_error in import_errors:
            validation_report = validation_report.with_finding(
                validation_error,
                file_path=file_path,
                scope="cloud_syntax",
            )
        self.validation_report = validation_report

        if import_errors:
            error_message = f"文件生成失败: {file_path}（跨文件导入不一致: {'；'.join(import_errors)}）"
            self.errors.append(error_message)
            logger.error(error_message)
            raise RuntimeError(error_message)

        if self.require_approval and self._is_critical_file(file_path):
            self._report_progress(
                PROGRESS_LABELS["pause_for_approval"],
                len(self.generated_files) + 1,
                total_files + 4,
                file_path=file_path,
                description=description,
                content_preview=content[:200]
            )
            approved = await self._wait_for_approval(file_path)
            if not approved:
                self._report_progress(
                    PROGRESS_LABELS["file_rejected"],
                    len(self.generated_files) + 1,
                    total_files + 4,
                    file_path=file_path
                )
                self._report_file_rejected(
                    file_path=file_path,
                    reason="用户在 HITL 审批中拒绝"
                )
                self.warnings.append(f"文件被用户拒绝: {file_path}")
                return {
                    "path": file_path,
                    "description": description,
                    "success": False,
                    "size": 0,
                    "rejected_by_user": True
                }

        if self.enable_validation or self.enable_review:
            success, content = await self._validate_and_review_file(
                file_path=file_path,
                content=content,
                description=description
            )
            if not success:
                self.errors.append(f"文件验证失败，禁止落盘: {file_path}")
                raise RuntimeError(f"file validation failed: {file_path}")

        # 验证并修复路径格式
        file_path = self._normalize_file_path(file_path)

        # 所有生成路径统一在内容处理完成后落盘，事件只代表已持久化产物。
        commit_result = None
        artifact_committer = getattr(self, "artifact_committer", None)
        if artifact_committer is not None:
            commit_result = artifact_committer.commit(
                file_path,
                content,
                model_name=self._select_model_for_file(file_path),
            )
            persisted = commit_result.success
            if persisted and commit_result.completion_event is not None:
                completion_events = getattr(self, "artifact_completion_events", None)
                if completion_events is not None:
                    completion_events.append(commit_result.completion_event)
        else:
            persisted = write_file_atomic(self.output_dir, file_path, content)
        if not persisted:
            error_message = f"文件落盘失败: {file_path}"
            if commit_result is not None and commit_result.diagnostic:
                error_message = f"{error_message}（{commit_result.diagnostic.message}）"
            self.errors.append(error_message)
            logger.error(error_message)
            raise RuntimeError(error_message)

        self._report_progress(
            PROGRESS_LABELS["file_generated"],
            len(self.generated_files) + 1,
            total_files + 4,
            file_path=file_path,
            description=description,
            size=len(content),
            content_preview=content[:300]
        )

        file_type = "frontend" if self._is_frontend_file(file_path) else "backend"
        self._report_file_event(file_path, content, description, file_type)

        if self.api_contract_checker and self._should_check_api_consistency(file_path):
            await self._check_and_report_api_issues(file_path, content)

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
            "size": len(content),
            "validation_report": validation_report.model_dump(mode="json"),
        }

    def _friendly_error(self, error_msg: str) -> str:
        """将技术错误信息转换为用户友好的描述"""
        error_lower = error_msg.lower()

        if "timeout" in error_lower or "timed out" in error_lower:
            return "请求超时，请稍后重试"
        # HTTP 状态码按独立词匹配，避免把 "500 chars"、"4293 tokens" 等文本误判
        if "rate limit" in error_lower or re.search(r'\b429\b', error_lower):
            return "请求频率过高，请稍后重试"
        if "unauthorized" in error_lower or re.search(r'\b401\b', error_lower):
            return "API 认证失败，请检查 API Key 配置"
        if "forbidden" in error_lower or re.search(r'\b403\b', error_lower):
            return "API 访问被拒绝，请检查权限"
        if "not found" in error_lower or re.search(r'\b404\b', error_lower):
            return "API 端点不存在"
        if "internal server" in error_lower or re.search(r'\b500\b', error_lower):
            return "API 服务异常，请稍后重试"
        if "connection" in error_lower or "network" in error_lower:
            return "网络连接失败，请检查网络"
        if "out of memory" in error_lower or re.search(r'\boom\b', error_lower):
            return "内存不足，请减少项目复杂度"
        if "json" in error_lower or "parse" in error_lower:
            return "模型返回格式异常，请重试"

        # 截断过长的错误信息
        if len(error_msg) > 100:
            return error_msg[:100] + "..."
        return error_msg

    def _normalize_file_path(self, file_path: str) -> str:
        """
        规范化文件路径，修复常见的路径格式错误

        例如：
        - events/rpy -> events.rpy
        - init/rpy -> init.rpy
        - screen/rpy -> screen.rpy
        """
        if not file_path:
            return file_path

        # Windows 风格分隔符（LLM 偶尔生成）统一为 POSIX，否则在 Linux 上
        # 会落盘成名为 `src\utils\api.py` 的单一文件。
        file_path = file_path.replace('\\', '/')

        # 已知文件扩展名（不含点）
        KNOWN_EXTENSIONS = {'py', 'js', 'ts', 'jsx', 'tsx', 'vue', 'html', 'css', 'scss', 'sass',
                           'less', 'json', 'yaml', 'yml', 'toml', 'ini', 'cfg', 'conf',
                           'md', 'txt', 'rst', 'sql', 'sh', 'bash', 'zsh', 'fish',
                           'rpy', 'rpyc', 'renpy'}

        # 检查是否是 "目录/扩展名" 的错误格式
        parts = file_path.split('/')
        if len(parts) >= 2:
            last_part = parts[-1]
            # 如果最后一部分是已知的纯扩展名，则合并到上一级
            if last_part and last_part.lower() in KNOWN_EXTENSIONS:
                parent = parts[-2]
                if '.' not in parent:
                    # 合并为 文件名.扩展名
                    prefix = '/'.join(parts[:-2])
                    fixed_path = f"{prefix}/{parent}.{last_part}" if prefix else f"{parent}.{last_part}"
                    logger.warning(f"路径格式修正: {file_path} -> {fixed_path}")
                    return fixed_path

        return file_path

    def _is_frontend_file(self, file_path: str) -> bool:
        ext = Path(file_path).suffix.lower()
        return ext in {'.vue', '.js', '.jsx', '.ts', '.tsx', '.html', '.css', '.scss', '.sass', '.less'}

    def _is_critical_file(self, file_path: str) -> bool:
        critical_patterns = [
            'main.py', 'app.py', 'server.py',
            'config.py', 'settings.py',
            'database.py', 'models.py',
            'auth.py', 'security.py',
            'middleware.py',
        ]
        basename = Path(file_path).name
        return basename in critical_patterns

    def _select_model_for_file(self, file_path: str) -> str:
        if not getattr(self, "model_assignment", None):
            raise RuntimeError("model assignment is required to select a file model")
        ext = Path(file_path).suffix.lower()
        file_name = Path(file_path).name.lower()
        if file_name in {"pom.xml", "build.gradle", "build.gradle.kts", "dockerfile"}:
            return self.model_assignment.reviewer_model
        if "/test/" in file_path.lower() or file_name.startswith("test_") or file_name.endswith("_test.py"):
            return self.model_assignment.reviewer_model
        if ext in {'.vue', '.js', '.jsx', '.ts', '.tsx', '.html', '.css', '.scss', '.sass', '.less'}:
            return self.model_assignment.frontend_model
        elif ext in {'.py', '.go', '.java', '.rs', '.rb', '.php'}:
            return self.model_assignment.backend_model
        else:
            return self.model_assignment.frontend_model

    def _select_engineer(self, file_path: str) -> Specialist:
        ext = Path(file_path).suffix.lower()
        frontend_ext = {'.vue', '.js', '.jsx', '.ts', '.tsx', '.html', '.css', '.scss', '.sass', '.less'}
        if ext in frontend_ext or file_path.endswith(('.vue', '.html')):
            return self.frontend_engineer
        return self.backend_engineer

    async def _recover_invalid_content_orchestator(
        self,
        file_path: str,
        description: str,
        project_context: dict,
        reason: str,
        engineer,
        spec_context: str = "",
        dep_context: str = "",
        heartbeat_tracker=None,
    ) -> str | None:
        """恢复无效内容（orchestrator_files 版本）"""
        if "JSON 元数据" in reason:
            recovery_prompt = f"""【紧急修复】上次你返回了 JSON 元数据，不是代码。

错误示例（不要这样返回）：
{{"status": "completed", "file_path": "{file_path}", ...}}

正确示例（直接返回代码）：
from fastapi import APIRouter
router = APIRouter()

请直接返回 {file_path} 的完整代码，不要包裹在 JSON 中。
文件描述：{description}
"""
        elif "Markdown" in reason:
            recovery_prompt = f"""【紧急修复】上次你返回了 Markdown 文档，不是代码。

请直接返回 {file_path} 的完整代码，不要用 Markdown 格式包裹。
文件描述：{description}
"""
        else:
            recovery_prompt = f"""【紧急修复】上次生成的内容无效：{reason}

请直接返回 {file_path} 的完整代码。
文件描述：{description}
"""

        for attempt in range(2):
            logger.info(f"内容恢复尝试 {attempt + 1}/2: {file_path}")

            content = await engineer.generate_file(
                file_path, recovery_prompt, project_context,
                spec_context=spec_context,
                dep_context=dep_context,
                project_path=str(self.output_dir), callback=self.callback,
                is_existing_file=False,
                heartbeat_tracker=heartbeat_tracker,
            )
            if asyncio.iscoroutine(content):
                content = await content

            all_files = list(self.dependency_graph_obj.nodes.keys()) if self.dependency_graph_obj else []
            content = await extract_engineer_content(
                content, engineer, self.output_dir, file_path,
                fix_imports_fn=_fix_absolute_imports,
                all_files=all_files
            )

            if content:
                from app.agent.utils import is_valid_code_content
                is_valid, new_reason = is_valid_code_content(file_path, content)
                if is_valid:
                    logger.info(f"内容恢复成功: {file_path} (第 {attempt + 1} 次)")
                    return content
                logger.warning(f"内容恢复失败: {file_path} - {new_reason} (第 {attempt + 1} 次)")

        logger.error(f"内容恢复彻底失败: {file_path}")
        return None

    async def _direct_llm_generate_file(
        self,
        file_path: str,
        description: str,
        project_context: dict
    ) -> str | None:
        raise RuntimeError(
            f"direct LLM file generation is disabled: {file_path}"
        )

    async def _validate_and_review_file(
        self,
        file_path: str,
        content: str,
        description: str
    ) -> tuple[bool, str]:
        if self.enable_error_recovery and not getattr(self, "model_assignment", None):
            raise RuntimeError("model assignment is required for file validation")
        content_hash = CodeValidator._compute_content_hash(content)
        cache_key = f"{file_path}:{content_hash}"
        cached_result = (
            self.validator.get_cached_validation_by_key(cache_key)
            if self.validator else None
        )
        if cached_result:
            self._report_progress(
                "validation_cache_hit",
                0, 0,
                file_path=file_path
            )
            return True, content

        validation_success = True

        if self.enable_error_recovery:
            full_path = self.output_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            success, content = await self.error_recovery.validate_and_fix(
                file_path=full_path,
                content=content,
                file_description=description,
                backend_model=self.model_assignment.backend_model,
                callback=self.callback
            )
            if success:
                try:
                    await asyncio.to_thread(full_path.write_text, content, encoding='utf-8')
                except OSError as e:
                    logger.error(f"文件写入失败（错误恢复后）: {file_path} - {e}")
                    validation_success = False
                content_hash = CodeValidator._compute_content_hash(content)
                cache_key = f"{file_path}:{content_hash}"
            else:
                validation_success = False

        if self.enable_review:
            review_result = await self.reviewer.review_code(
                code=content,
                file_path=file_path,
                context=description
            )
            if review_result.get("needs_fix") and review_result.get("risk_level") in ["high", "medium"]:
                review_warning = f"审查建议 {file_path}: {_format_review_issues(review_result.get('issues'))}"
                self.warnings.append(review_warning)
                self._report_warning(
                    message=review_warning,
                    code="review_suggestion",
                    file_path=file_path,
                    risk_level=review_result.get("risk_level"),
                )
                # 高风险审查只对源代码文件禁止落盘。文档/文本类产物的正确内容
                # 不是代码，审查器按代码口径给出的结构性结论（例如 README 描述
                # 的源码布局被判为缺少 __init__.py）不能回滚整个依赖层。
                if review_result.get("risk_level") == "high" and not is_documentation_file(file_path):
                    validation_success = False

        if self.validator and self.enable_validation and file_path.endswith('.py'):
            # 走 CodeValidator 的正式单文件接口（语法 + 运行时导入 + API 兼容），
            # 不再只做 ast.parse：此前的简化检查会把含缺失项目内导入的文件也当
            # 成功并写入 `is_valid: True` 的缓存，后续相同内容重试会被该假成功
            # 缓存放行。验证内容与 error_recovery.validate_and_fix 一致，均以临
            # 时文件方式校验。
            full_path = self.output_dir / file_path
            temp_file = full_path.parent / f".temp_validate_{full_path.name}"
            try:
                full_path.parent.mkdir(parents=True, exist_ok=True)
                temp_file.write_text(content, encoding='utf-8')
                validation_result = await self.validator.validate_single_file(temp_file)
            except Exception as e:
                validation_success = False
                logger.warning(f"文件语法校验异常: {file_path}: {e}")
            else:
                if not validation_result.get("is_valid", True):
                    validation_success = False
                    logger.warning(
                        "文件验证失败: %s (syntax=%s runtime=%s api=%s)",
                        file_path,
                        validation_result.get("syntax_errors"),
                        validation_result.get("runtime_errors"),
                        validation_result.get("api_errors"),
                    )
                # 仅在整体验证通过时入缓存：失败结果若被缓存，相同内容重试会在
                # 缓存命中处提前返回成功，绕过 error_recovery 与审查。
                if validation_success:
                    self.validator.store_validation(cache_key, validation_result)
            finally:
                try:
                    temp_file.unlink()
                except OSError:
                    pass

        return validation_success, content

    def _clean_code_block(self, content: str) -> str:
        from app.agent.utils import clean_code_block
        return clean_code_block(content)

    def _select_alternative_model(self, primary_model: str) -> str | None:
        """Pick a distinct assigned model for the cross-validation A/B pass.

        Returns None when no distinct model exists and the user enabled the
        degradation switch, letting callers fall back to single-model review.
        """
        assignment = getattr(self, "model_assignment", None)
        if not assignment:
            raise RuntimeError(
                "model assignment is required to select an alternative model"
            )
        # Prefer models other than the reviewer, which judges the A/B result.
        for attribute in (
            "architect_model",
            "backend_model",
            "frontend_model",
            "fallback_model",
            "reviewer_model",
        ):
            candidate = getattr(assignment, attribute, None)
            if candidate and candidate != primary_model:
                return str(candidate)
        if getattr(self, "cross_validation_fallback", False):
            return None
        raise RuntimeError(
            "a distinct alternative model is required for cross-validation"
        )

    def _select_engineer_for_model(self, model_name: str) -> Specialist:
        frontend_models = {DEFAULT_FAST_MODEL, DEFAULT_CODE_MODEL}
        if model_name in frontend_models:
            return self.frontend_engineer
        return self.backend_engineer

    async def _apply_patches_incremental(
        self,
        requirement: str,
        incremental_plan: list[dict],
        project_context: dict,
        total_files: int
    ):
        changed_files = [fi.get("path", "") for fi in incremental_plan]
        affected_files = {}

        if self.dependency_graph_obj and self.cross_file_patcher:
            for changed_file in changed_files:
                affected = self.dependency_graph_obj.get_affected_files(changed_file)
                if affected:
                    affected_files[changed_file] = affected

        if affected_files:
            logger.info(f"检测到跨文件依赖：{len(affected_files)} 个变更文件影响 {sum(len(v) for v in affected_files.values())} 个下游文件")

            file_contents = {}
            all_files = set(changed_files)
            for deps in affected_files.values():
                all_files.update(deps)

            for file_path in all_files:
                full_path = self.output_dir / file_path
                if full_path.exists():
                    file_contents[file_path] = full_path.read_text(encoding='utf-8', errors='ignore')

            patch_result = await self.cross_file_patcher.generate_cross_file_patches(
                requirement=requirement,
                changed_files=changed_files,
                affected_files=affected_files,
                project_path=self.output_dir,
                file_contents=file_contents,
            )

            if patch_result.primary_result and patch_result.primary_result.success:
                self.generated_files.append({
                    "path": patch_result.primary_file,
                    "description": f"跨文件变更 (影响 {len(patch_result.dependency_chain)} 个文件)",
                    "success": True,
                    "cross_file_changes": True,
                    "affected_files": patch_result.dependency_chain,
                })
            else:
                raise RuntimeError(
                    "cross-file patch failed: "
                    f"{len(patch_result.failed_patches)} file(s)"
                )

        for file_info in incremental_plan:
            file_path = file_info.get("path", "")
            description = file_info.get("description", "")
            full_path = self.output_dir / file_path

            if file_path in [f for deps in affected_files.values() for f in deps]:
                continue

            if not full_path.exists():
                result = await self._generate_single_file(file_info, project_context, total_files)
                if not result or not result.get("success"):
                    raise RuntimeError(
                        f"incremental patch failed for {file_path}: "
                        "missing file was not generated"
                    )
                self.generated_files.append(result)
                continue

            self._report_progress(
                "applying_patch",
                len(self.generated_files) + 1,
                total_files + 4,
                file_path=file_path,
                description=description,
                mode="patch"
            )

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
                raise RuntimeError(
                    f"incremental patch failed for {file_path}: "
                    + "; ".join(getattr(result, "errors", []) or ["apply failed"])
                )
