import time
import asyncio
import logging
from typing import Optional, Dict, Any, Callable, List

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

        spec_generator = SpecFirstGenerator(ctx)
        specs_success = await spec_generator.generate_all_specs(
            requirement, ctx.complexity, callback
        )

        if not specs_success:
            self._report_progress("specs_failed", 2, 6, callback=callback)
        else:
            self._report_progress("specs_completed", 2, 6, callback=callback)

        architecture = await self.architect.design_architecture(requirement, self.complexity)
        file_plan = architecture.get("file_plan", [])

        self._report_progress(
            "architecture_design", 3, 6,
            file_count=len(file_plan),
            callback=callback
        )

        constraint_parser = GlobalConstraintParser()
        global_constraints = constraint_parser.parse_requirement(requirement)
        ctx.set_metric("global_constraints", constraint_parser.get_constraints_summary())

        decision_extractor = CriticalDecisionExtractor()
        critical_decisions = decision_extractor.extract_from_architecture(
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

        constraint_prompt = constraint_parser.generate_prompt_fragment("all", "all")
        if constraint_prompt:
            project_context["global_constraints"] = constraint_prompt

        dep_graph = DependencyGraph()
        dep_graph.build_from_architecture(architecture)

        if specs_success:
            dep_graph.build_from_specs(ctx.specs)

        generation_order = dep_graph.get_generation_order()
        ctx.set_metric("generation_order", generation_order)

        self._report_progress(
            "dependency_graph_built", 4, 6,
            files_in_order=len(generation_order),
            callback=callback
        )

        refinement_loop_instance = RefinementLoop(ctx)
        generated_contents: Dict[str, str] = {}
        files_generated = 0
        files_failed = 0

        project_context = {
            "requirement": requirement,
            "architecture": architecture,
            "complexity": ctx.complexity,
            "output_dir": str(self.output_dir)
        }

        for file_info in file_plan:
            path = file_info.get("path", "")
            if path and path not in dep_graph.nodes:
                dep_graph.add_file(path, priority=file_info.get("priority", 3))

        layers = dep_graph.get_generation_layers()
        ctx.set_metric("generation_layers", len(layers))
        ctx.set_metric("generation_order", [f for layer in layers for f in layer])

        if hasattr(self, 'use_dynamic_topology') and self.use_dynamic_topology:
            result = await self._generate_with_dynamic_topology(
                ctx, dep_graph, spec_generator, architecture, requirement,
                project_context, generated_contents, callback
            )
            files_generated = result.get("files_generated", 0)
            files_failed = result.get("files_failed", 0)
            self.generated_files = result.get("generated_files", [])
            self.errors.extend(result.get("errors", []))
            self.warnings.extend(result.get("warnings", []))
            total_files = result.get("total_files", 0)
        else:
            total_files = sum(len(layer) for layer in layers)

            self._report_progress(
                "dependency_graph_built", 4, 6,
                files_in_order=total_files,
                parallel_layers=len(layers),
                callback=callback
            )

            state_lock = asyncio.Lock()

            cross_validator = CrossValidator(ctx)

            async def generate_single_file(
                file_path: str,
                file_index: int
            ) -> Dict[str, Any]:
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

                spec_context = spec_generator.get_spec_context_for_file(file_path, file_type)
                dep_context = dep_graph.get_context_for_file(file_path, generated_contents)

                initial_content = await engineer.generate_file(file_path, description, project_context)
                if not initial_content:
                    return {"path": file_path, "success": False, "error": "生成返回空内容"}

                initial_content = self._clean_code_block(initial_content)

                if cross_validator.is_critical_file(file_path, file_type):
                    self._report_progress(
                        "cross_validation",
                        4 + file_index,
                        total_files + 5,
                        file_path=file_path,
                        callback=callback
                    )

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

                tasks = [
                    generate_single_file(file_path, current_index + i)
                    for i, file_path in enumerate(layer)
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

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

        final_validation = {}
        if self.enable_validation:
            final_validation = await self.validator.run_full_validation()

        if self.memory_enabled:
            await self._save_to_memory(requirement, architecture)

        elapsed = time.time() - start_time

        architecture_inspector = ArchitectureInspector()
        architecture_inspector.set_context(
            architecture=architecture,
            generated_files={f: ctx.get_file_content(f) for f in ctx.generated_files.keys()},
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
            "context_full": ctx.to_export_dict(),
            "requirement_coverage": self._check_requirement_coverage(
                requirement, architecture, file_plan
            ),
            "global_constraints": ctx.get_metric("global_constraints"),
            "critical_decisions": ctx.get_metric("critical_decisions"),
            "architecture_check": ctx.get_metric("architecture_check")
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
        callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """使用动态拓扑调度生成文件"""
        scheduler = TopologyScheduler(max_concurrent=5, max_retries=2)
        scheduler.build_from_dependency_graph(dep_graph)

        cross_validator = CrossValidator(ctx)
        refinement_loop = RefinementLoop(ctx)

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
            file_node = dep_graph.nodes.get(file_path)
            description = file_node.description if file_node else f"生成 {file_path}"
            file_type = file_node.file_type if file_node else "unknown"

            engineer = self._select_engineer(file_path)
            model_name = self._select_model_for_file(file_path)

            combined_context = {**project_context}
            if upstream_context:
                combined_context["upstream_files"] = {
                    path: content[:MAX_CONTENT_FOR_CONTEXT]
                    for path, content in upstream_context.items()
                }

            initial_content = await engineer.generate_file(file_path, description, combined_context)
            if not initial_content:
                raise ValueError("生成返回空内容")

            initial_content = self._clean_code_block(initial_content)

            if cross_validator.is_critical_file(file_path, file_type):
                alt_model = self._select_alternative_model(model_name)
                alt_engineer = self._select_engineer_for_model(alt_model)
                alt_content = await alt_engineer.generate_file(file_path, description, combined_context)
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

            full_path = self.output_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(final_content)

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

        return {
            "files_generated": files_generated,
            "files_failed": files_failed,
            "total_files": total_files,
            "generated_files": generated_files_list,
            "errors": errors_list,
            "warnings": warnings_list,
            "scheduler_stats": scheduler.get_stats()
        }