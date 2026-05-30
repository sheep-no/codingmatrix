import re
import asyncio
import logging
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path

from app.utils import call_llm
from app.agent.specialists import Specialist
from app.agent.code_patcher import apply_incremental_change
from app.agent.complexity import ProjectComplexity
from app.agent.code_validator import CodeValidator
from app.agent.orchestrator_progress import PROGRESS_LABELS, MAX_CONCURRENT_LLM_CALLS

logger = logging.getLogger(__name__)


class FilesMixin:

    async def _generate_files_small_project(
        self,
        file_plan: List[Dict],
        project_context: Dict,
        total_files: int
    ):
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)

        async def generate_with_semaphore(file_info: Dict) -> Dict:
            async with semaphore:
                return await self._generate_single_file(file_info, project_context, total_files)

        tasks = [generate_with_semaphore(fi) for fi in file_plan]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                self.errors.append(f"文件生成失败: 内部异常 - {self._friendly_error(str(result))}")
            elif result:
                self.generated_files.append(result)

    async def _generate_files_by_dep_layers(
        self,
        file_plan: List[Dict],
        project_context: Dict,
        total_files: int,
        dep_graph
    ):
        layers = dep_graph.get_generation_layers()
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)

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
                    self.errors.append(f"文件生成失败: 内部异常 - {self._friendly_error(str(result))}")
                elif result:
                    self.generated_files.append(result)
                    try:
                        full_path = self.output_dir / result["path"]
                        if full_path.exists():
                            self._generated_contents[result["path"]] = full_path.read_text(encoding="utf-8")
                    except Exception as read_err:
                        logger.debug(f"读取生成文件内容失败: {read_err}")

    async def _generate_single_file(
        self,
        file_info: Dict,
        project_context: Dict,
        total_files: int,
        generated_contents: Optional[Dict] = None
    ) -> Optional[Dict]:
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

        content = await engineer.generate_file(file_path, description, project_context)

        if not content:
            self._report_progress(
                PROGRESS_LABELS["react_fallback"],
                len(self.generated_files) + 1,
                total_files + 4,
                file_path=file_path
            )
            content = await self._react_generate_file(file_path, description, project_context)
            if not content:
                self.errors.append(f"文件生成失败: {file_path}（模型未能生成有效内容，请尝试更换模型或稍后重试）")
                return None

        content = self._clean_code_block(content)

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
                self.warnings.append(f"文件验证未完全通过: {file_path}")

        # 验证并修复路径格式
        file_path = self._normalize_file_path(file_path)

        full_path = self.output_dir / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)

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
            "size": len(content)
        }

    def _friendly_error(self, error_msg: str) -> str:
        """将技术错误信息转换为用户友好的描述"""
        error_lower = error_msg.lower()
        
        if "timeout" in error_lower or "timed out" in error_lower:
            return "请求超时，请稍后重试"
        if "rate limit" in error_lower or "429" in error_lower:
            return "请求频率过高，请稍后重试"
        if "401" in error_lower or "unauthorized" in error_lower:
            return "API 认证失败，请检查 API Key 配置"
        if "403" in error_lower or "forbidden" in error_lower:
            return "API 访问被拒绝，请检查权限"
        if "404" in error_lower or "not found" in error_lower:
            return "API 端点不存在"
        if "500" in error_lower or "internal server" in error_lower:
            return "API 服务异常，请稍后重试"
        if "connection" in error_lower or "network" in error_lower:
            return "网络连接失败，请检查网络"
        if "out of memory" in error_lower or "oom" in error_lower:
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
        
        # 检查是否是 "目录/扩展名" 的错误格式
        parts = file_path.split('/')
        if len(parts) >= 2:
            last_part = parts[-1]
            # 如果最后一部分是纯扩展名（如 rpy, py, js 等），则合并到上一级
            if last_part and not '.' in last_part and len(last_part) <= 10:
                # 这可能是错误的路径格式
                # 检查上一级目录名是否像文件名
                parent = parts[-2]
                if '.' not in parent:
                    # 合并为 文件名.扩展名
                    fixed_path = '/'.join(parts[:-2]) + f"{parent}.{last_part}" if len(parts) > 2 else f"{parent}.{last_part}"
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
        ext = Path(file_path).suffix.lower()
        if ext in {'.vue', '.js', '.jsx', '.ts', '.tsx', '.html', '.css', '.scss', '.sass', '.less'}:
            return self.model_assignment.frontend_model if self.model_assignment else "Qwen/Qwen3-8B"
        elif ext in {'.py', '.go', '.java', '.rs', '.rb', '.php'}:
            return self.model_assignment.backend_model if self.model_assignment else "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B"
        else:
            return self.model_assignment.frontend_model if self.model_assignment else "Qwen/Qwen3-8B"

    def _select_engineer(self, file_path: str) -> Specialist:
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

            response = await call_llm(
                model="Qwen/Qwen3.5-4B",
                prompt=user_prompt,
                max_tokens=4096,
                temperature=0.4,
                system_prompt=system_prompt,
                api_key_token=self.api_key_token
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
        full_path = self.output_dir / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

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

        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)

        if self.enable_error_recovery:
            success, content = await self.error_recovery.validate_and_fix(
                file_path=full_path,
                content=content,
                file_description=description,
                backend_model=self.model_assignment.backend_model if self.model_assignment else "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
                callback=self.callback
            )
            if success:
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                content_hash = CodeValidator._compute_content_hash(content)
                cache_key = f"{file_path}:{content_hash}"

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
        pattern = r'```(?:\w+)?\s*(.*?)\s*```'
        match = re.search(pattern, content, re.DOTALL)
        if match:
            return match.group(1).strip()
        return content.strip()

    def _select_alternative_model(self, primary_model: str) -> str:
        alt_map = {
            "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B": "Qwen/Qwen3-8B",
            "Qwen/Qwen3-8B": "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
            "Qwen/Qwen3.5-4B": "Qwen/Qwen3-8B",
            "THUDM/GLM-Z1-9B-0414": "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
        }
        return alt_map.get(primary_model, "Qwen/Qwen3-8B")

    def _select_engineer_for_model(self, model_name: str) -> Specialist:
        frontend_models = {"Qwen/Qwen3.5-4B", "Qwen/Qwen3-8B"}
        if model_name in frontend_models:
            return self.frontend_engineer
        return self.backend_engineer

    async def _apply_patches_incremental(
        self,
        requirement: str,
        incremental_plan: List[Dict],
        project_context: Dict,
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
                self.errors.append(f"跨文件修改失败: 影响了 {len(patch_result.failed_patches)} 个文件的关联修改")

        for file_info in incremental_plan:
            file_path = file_info.get("path", "")
            description = file_info.get("description", "")
            full_path = self.output_dir / file_path

            if file_path in [f for deps in affected_files.values() for f in deps]:
                continue

            if not full_path.exists():
                result = await self._generate_single_file(file_info, project_context, total_files)
                if result:
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
                self.errors.append(f"文件修改失败: {file_path}（正在降级为全量生成）")
                self.warnings.append(f"降级到全量生成：{file_path}")
                result = await self._generate_single_file(file_info, project_context, total_files)
                if result:
                    self.generated_files.append(result)
                continue

            original_content = full_path.read_text(encoding='utf-8')

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
                self.errors.append(f"文件修改失败: {file_path}（正在降级为全量生成）")
                self.warnings.append(f"降级到全量生成: {file_path}")
                result = await self._generate_single_file(file_info, project_context, total_files)
                if result:
                    self.generated_files.append(result)