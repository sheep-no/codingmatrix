import re
import json
import asyncio
import logging
import subprocess
from typing import Optional, Dict, List, Tuple
from pathlib import Path

from app.utils import call_llm
from app.agent.specialists import Specialist
from app.agent.code_patcher import apply_incremental_change
from app.agent.complexity import ProjectComplexity
from app.agent.code_validator import CodeValidator
from app.agent.orchestrator_progress import PROGRESS_LABELS
from app.agent.specialist_base import get_global_llm_semaphore
from app.agent.models import DEFAULT_CODE_MODEL, DEFAULT_REASONING_MODEL, DEFAULT_ARCHITECT_MODEL
from app.agent.utils import extract_engineer_content, write_file_atomic


logger = logging.getLogger(__name__)

# 写入类工具名称（用于编辑标记检测）
_WRITE_TOOLS = {"partial_update", "insert_content", "regex_replace"}


def _is_edit_marker(content: str) -> bool:
    """检查工程师返回的内容是否是编辑标记（而非完整文件内容）"""
    if not content:
        return False
    try:
        data = json.loads(content.strip())
        return isinstance(data, dict) and data.get("action") == "edited"
    except (json.JSONDecodeError, ValueError):
        return False


def _git_stash_push(work_dir: str, files: List[str], message: str = "agent-backup") -> bool:
    """用 git stash 备份已 track 的文件"""
    if not files:
        return True
    try:
        result = subprocess.run(
            ['git', 'stash', 'push', '-m', message, '--'] + files,
            cwd=work_dir, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            logger.info(f"git stash push: {len(files)} 个文件")
            return True
        logger.warning(f"git stash push 失败: {result.stderr.strip()}")
        return False
    except Exception as e:
        logger.warning(f"git stash push 异常: {e}")
        return False


def _git_stash_pop(work_dir: str) -> bool:
    """恢复最近的 git stash"""
    try:
        result = subprocess.run(
            ['git', 'stash', 'pop'],
            cwd=work_dir, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            logger.info("git stash pop: 恢复成功")
            return True
        logger.warning(f"git stash pop 失败: {result.stderr.strip()}")
        return False
    except Exception as e:
        logger.warning(f"git stash pop 异常: {e}")
        return False


def _git_stash_drop(work_dir: str) -> bool:
    """丢弃最近的 git stash"""
    try:
        result = subprocess.run(
            ['git', 'stash', 'drop'],
            cwd=work_dir, capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False


def _fix_absolute_imports(
    content: str, file_path: str, all_project_files: List[str]
) -> str:
    """修复 Python 文件中的绝对导入，转为相对导入。

    当 LLM 生成 from src.utils import greet 时，自动转为 from .utils import greet。
    仅处理 Python 文件，且仅当目标模块在同包内存在时才转换。
    """
    if not file_path.endswith('.py'):
        return content

    # 当前文件的包路径
    parts = file_path.replace('\\', '/').split('/')
    if len(parts) < 2:
        return content  # 顶层文件，无需处理
    current_pkg = '/'.join(parts[:-1])  # e.g. "src/utils"

    # 构建同包文件集合（用于判断目标模块是否在同一包内）
    same_pkg_modules = set()
    for f in all_project_files:
        if not f.endswith('.py'):
            continue
        f_norm = f.replace('\\', '/')
        f_pkg = '/'.join(f_norm.split('/')[:-1])
        if f_pkg == current_pkg:
            stem = f_norm.split('/')[-1].replace('.py', '')
            same_pkg_modules.add(stem)

    # 匹配 from src.xxx import yyy 或 from src.xxx.yyy import zzz
    # 需要找到 common prefix（如 src/ 或 app/）来识别绝对导入
    lines = content.split('\n')
    fixed_lines = []
    changed = False

    for line in lines:
        stripped = line.strip()
        # 匹配 from <prefix>.<module> import <names>
        m = re.match(r'^(from\s+)([\w.]+)(\s+import\s+.+)$', stripped)
        if m:
            prefix = m.group(1)
            module_path = m.group(2)  # e.g. "src.utils" or "app.models.user"
            suffix = m.group(3)

            # 将模块路径转为文件路径
            module_parts = module_path.split('.')

            # 尝试找到与 current_pkg 匹配的前缀，然后检查剩余部分是否在同包内
            # 例如: current_pkg = "src/utils", module_path = "src.utils.helpers"
            #   → prefix_match at "src.utils", remainder = "helpers"
            for i in range(1, len(module_parts)):
                candidate_pkg = '/'.join(module_parts[:i])
                if candidate_pkg == current_pkg:
                    target_module = module_parts[i]
                    if target_module in same_pkg_modules:
                        # 转为相对导入
                        new_import = f"{prefix}.{target_module}{suffix}"
                        fixed_lines.append(line.replace(stripped, new_import))
                        changed = True
                        break
            else:
                fixed_lines.append(line)
        else:
            fixed_lines.append(line)

    if changed:
        logger.info(f"自动修复绝对导入: {file_path}")
    return '\n'.join(fixed_lines)


class FilesMixin:

    async def _generate_files_small_project(
        self,
        file_plan: List[Dict],
        project_context: Dict,
        total_files: int
    ):
        semaphore = get_global_llm_semaphore()

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
        stashed = _git_stash_push(str(self.output_dir), existing_files, "agent-backup-batch")

        async def generate_with_semaphore(file_info: Dict) -> Dict:
            async with semaphore:
                return await self._generate_single_file(file_info, project_context, total_files)

        tasks = [generate_with_semaphore(fi) for fi in file_plan]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 检查是否全部成功
        all_success = True
        for i, result in enumerate(results):
            if isinstance(result, Exception):
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
        else:
            # 成功：丢弃 stash
            if stashed:
                _git_stash_drop(str(self.output_dir))
            for result in results:
                if result and not isinstance(result, Exception):
                    self.generated_files.append(result)

    async def _generate_files_by_dep_layers(
        self,
        file_plan: List[Dict],
        project_context: Dict,
        total_files: int,
        dep_graph
    ):
        layers = dep_graph.get_generation_layers()
        semaphore = get_global_llm_semaphore()

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
            stashed = _git_stash_push(str(self.output_dir), existing_files, f"agent-backup-layer-{layer_idx}")

            async def generate_with_semaphore(file_path: str) -> Dict:
                async with semaphore:
                    fi = file_info_map.get(file_path, {"path": file_path, "description": f"生成 {file_path}"})
                    return await self._generate_single_file(fi, project_context, total_files, self._generated_contents)

            tasks = [generate_with_semaphore(fp) for fp in layer_files]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 检查本层是否全部成功
            layer_success = True
            for i, result in enumerate(results):
                if isinstance(result, Exception):
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
            else:
                # 成功：丢弃 stash
                if stashed:
                    _git_stash_drop(str(self.output_dir))
                for result in results:
                    if result and not isinstance(result, Exception):
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
            dep_context = self.dependency_graph_obj.get_context_for_file(
                file_path, generated_contents or {}
            )

        # 判断文件是否已存在
        full_path = self.output_dir / self._normalize_file_path(file_path)
        is_existing = full_path.exists()

        # 清空编辑记录
        engineer.clear_edits()

        content = await engineer.generate_file(
            file_path, description, project_context, spec_context, dep_context,
            project_path=str(self.output_dir), callback=self.callback,
            is_existing_file=is_existing,
        )

        # 统一提取工程师生成的内容
        all_files = list(self.dependency_graph_obj.nodes.keys()) if self.dependency_graph_obj else []
        content = extract_engineer_content(
            content, engineer, self.output_dir, file_path,
            fix_imports_fn=_fix_absolute_imports,
            all_files=all_files
        )

        if content is None:
            # 空内容：fallback
            self._report_progress(
                PROGRESS_LABELS["react_fallback"],
                len(self.generated_files) + 1,
                total_files + 4,
                file_path=file_path
            )
            content = await self._direct_llm_generate_file(file_path, description, project_context)
            if not content:
                self.errors.append(f"文件生成失败: {file_path}（模型未能生成有效内容，请尝试更换模型或稍后重试）")
                return None
            content = self._clean_code_block(content)
            content = _fix_absolute_imports(content, file_path, all_files)
            write_file_atomic(self.output_dir, file_path, content)

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
                self.warnings.append(f"文件验证未完全通过: {file_path}")

        # 验证并修复路径格式
        file_path = self._normalize_file_path(file_path)

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
            if last_part and '.' not in last_part and len(last_part) <= 10:
                # 这可能是错误的路径格式
                # 检查上一级目录名是否像文件名
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
        ext = Path(file_path).suffix.lower()
        if ext in {'.vue', '.js', '.jsx', '.ts', '.tsx', '.html', '.css', '.scss', '.sass', '.less'}:
            return self.model_assignment.frontend_model if self.model_assignment else DEFAULT_CODE_MODEL
        elif ext in {'.py', '.go', '.java', '.rs', '.rb', '.php'}:
            return self.model_assignment.backend_model if self.model_assignment else DEFAULT_REASONING_MODEL
        else:
            return self.model_assignment.frontend_model if self.model_assignment else DEFAULT_CODE_MODEL

    def _select_engineer(self, file_path: str) -> Specialist:
        ext = Path(file_path).suffix.lower()
        frontend_ext = {'.vue', '.js', '.jsx', '.ts', '.tsx', '.html', '.css', '.scss', '.sass', '.less'}
        if ext in frontend_ext or file_path.endswith(('.vue', '.html')):
            return self.frontend_engineer
        return self.backend_engineer

    async def _direct_llm_generate_file(
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
                model=DEFAULT_CODE_MODEL,
                prompt=user_prompt,
                max_tokens=4096,
                temperature=0.4,
                system_prompt=system_prompt,
                api_key_token=self.api_key_token
            )
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            return self._clean_code_block(content) if content else None

        except Exception as e:
            logger.error(f"直接 LLM 生成失败 ({file_path}): {e}")
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
                backend_model=self.model_assignment.backend_model if self.model_assignment else DEFAULT_REASONING_MODEL,
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
                review_warning = f"审查建议 {file_path}: {'; '.join(review_result.get('issues', []))}"
                self.warnings.append(review_warning)
                self._report_warning(
                    message=review_warning,
                    code="review_suggestion",
                    file_path=file_path,
                    risk_level=review_result.get("risk_level"),
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
                logger.debug("文件操作失败")

        return True, content

    def _clean_code_block(self, content: str) -> str:
        from app.agent.utils import clean_code_block
        return clean_code_block(content)

    def _select_alternative_model(self, primary_model: str) -> str:
        alt_map = {
            DEFAULT_REASONING_MODEL: DEFAULT_CODE_MODEL,
            DEFAULT_CODE_MODEL: DEFAULT_REASONING_MODEL,
            "Qwen/Qwen3.5-4B": DEFAULT_CODE_MODEL,
            DEFAULT_ARCHITECT_MODEL: DEFAULT_REASONING_MODEL,
        }
        return alt_map.get(primary_model, DEFAULT_CODE_MODEL)

    def _select_engineer_for_model(self, model_name: str) -> Specialist:
        frontend_models = {"Qwen/Qwen3.5-4B", DEFAULT_CODE_MODEL}
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
