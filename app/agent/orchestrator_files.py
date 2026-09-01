import ast
import builtins
import importlib.util
import re
import symtable
import json
import asyncio
import hashlib
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
from app.agent.models import DEFAULT_CODE_MODEL, DEFAULT_REASONING_MODEL, DEFAULT_ARCHITECT_MODEL, DEFAULT_FAST_MODEL
from app.agent.utils import extract_engineer_content, write_file_atomic
from app.agent.dependency_graph import summarize_dependency_context


logger = logging.getLogger(__name__)

# 写入类工具名称（用于编辑标记检测）
_WRITE_TOOLS = {"partial_update", "insert_content", "regex_replace"}


def _python_module_name(file_path: str) -> str:
    normalized = file_path.replace('\\', '/').removesuffix('.py')
    if normalized.endswith('/__init__'):
        normalized = normalized[:-len('/__init__')]
    return normalized.replace('/', '.')


def _python_exports(content: str) -> set[str]:
    tree = ast.parse(content)
    exports = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            exports.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    exports.add(target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                exports.add(alias.asname or alias.name.split('.', 1)[0])
    return exports


def _structured_import_diagnostics(errors: List[str]) -> List[Dict[str, str]]:
    """将静态门禁文本转换为模型可直接执行的诊断项。"""
    diagnostics = []
    for error in errors:
        diagnostic = {"message": error}
        match = re.match(r"(.+?\.py) 未导出符号 (.+)，", error)
        if match:
            diagnostic.update({
                "type": "missing_export",
                "dependency_file": match.group(1),
                "symbol": match.group(2),
            })
        elif "名称 " in error and "未定义或导入" in error:
            symbol = error.split("名称 ", 1)[1].split(" 在", 1)[0]
            diagnostic.update({"type": "undefined_global", "symbol": symbol})
        elif error.startswith("调用 "):
            diagnostic["type"] = "signature_mismatch"
        elif "禁止混用" in error:
            diagnostic["type"] = "database_abstraction_mismatch"
        else:
            diagnostic["type"] = "static_validation_error"
        diagnostics.append(diagnostic)
    return diagnostics


def _validate_python_implementation(content: str, file_path: str) -> List[str]:
    """Reject syntactically valid Python placeholders that contain no implementation."""
    if not file_path.endswith('.py') or file_path.endswith('__init__.py'):
        return []
    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError:
        return []

    substantive_nodes = [
        node for node in tree.body
        if not isinstance(node, (ast.Import, ast.ImportFrom))
        and not (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        )
    ]
    if substantive_nodes:
        return []
    return ["Python 文件仅包含导入或说明文本，缺少可执行实现"]


def _validate_python_project_imports(
    content: str,
    file_path: str,
    generated_contents: Dict[str, str],
    all_project_files: List[str],
) -> List[str]:
    """校验 Python 项目内导入只引用已生成依赖及其真实导出。"""
    if not file_path.endswith('.py'):
        return []
    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError as exc:
        return [f"Python 语法错误: {exc.msg} (line {exc.lineno})"]

    project_modules = {
        _python_module_name(path): path
        for path in all_project_files
        if path.endswith('.py') and path != file_path
    }
    generated_modules = {
        _python_module_name(path): source
        for path, source in generated_contents.items()
        if path.endswith('.py')
    }
    errors = []
    imported_project_functions: Dict[str, Tuple[str, str]] = {}
    symbol_table = symtable.symtable(content, file_path, "exec")
    defined_globals = {
        symbol.get_name()
        for symbol in symbol_table.get_symbols()
        if symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace()
    }
    referenced_globals = {
        symbol.get_name()
        for symbol in symbol_table.get_symbols()
        if symbol.is_referenced()
    }
    pending_tables = list(symbol_table.get_children())
    while pending_tables:
        child_table = pending_tables.pop()
        pending_tables.extend(child_table.get_children())
        for symbol in child_table.get_symbols():
            if symbol.is_global() and symbol.is_assigned():
                defined_globals.add(symbol.get_name())
            if symbol.is_global() and symbol.is_referenced():
                referenced_globals.add(symbol.get_name())

    runtime_globals = set(dir(builtins)) | {
        "__file__",
        "__name__",
        "__package__",
        "__spec__",
    }
    for name in sorted(referenced_globals - defined_globals - runtime_globals):
        errors.append(f"名称 {name} 在模块全局作用域中未定义或导入")

    creates_sqlalchemy_base = any(
        isinstance(node, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(target, ast.Name) and target.id == "Base"
            for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        )
        and isinstance(node.value, ast.Call)
        and (
            isinstance(node.value.func, ast.Name)
            and node.value.func.id == "declarative_base"
            or isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "declarative_base"
        )
        for node in tree.body
    )
    if creates_sqlalchemy_base:
        for module, source in generated_modules.items():
            try:
                dependency_exports = _python_exports(source)
            except SyntaxError:
                continue
            if "Base" in dependency_exports and module in project_modules:
                errors.append(
                    f"{project_modules[module]} 已导出 SQLAlchemy Base，{file_path} 必须导入复用，"
                    "禁止再次调用 declarative_base()"
                )
                break

    if file_path.endswith("models.py"):
        database_source = generated_modules.get("database")
        if database_source:
            database_uses_sqlite = bool(re.search(r"\b(?:import\s+sqlite3|from\s+sqlite3\s+import)\b", database_source))
            database_uses_sqlalchemy = "sqlalchemy" in database_source
            model_uses_sqlite = bool(re.search(r"\b(?:import\s+sqlite3|from\s+sqlite3\s+import)\b", content))
            model_uses_sqlalchemy = "sqlalchemy" in content
            if database_uses_sqlite and model_uses_sqlalchemy:
                errors.append("database.py 使用原生 sqlite3 时，models.py 禁止混用 SQLAlchemy ORM")
            elif database_uses_sqlalchemy and model_uses_sqlite:
                errors.append("database.py 使用 SQLAlchemy 时，models.py 禁止混用原生 sqlite3")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name
                if module in project_modules and module not in generated_modules:
                    errors.append(f"项目模块 {project_modules[module]} 尚未生成，当前拓扑层禁止导入")
                elif module not in project_modules:
                    root_module = module.split('.', 1)[0]
                    try:
                        available = importlib.util.find_spec(root_module) is not None
                    except (ImportError, ValueError, AttributeError):
                        available = False
                    if not available:
                        errors.append(f"模块 {root_module} 不在项目文件集合中且当前运行时不可用")
        elif isinstance(node, ast.ImportFrom) and node.module:
            module = node.module.lstrip('.')
            if module not in project_modules:
                root_module = module.split('.', 1)[0]
                try:
                    available = importlib.util.find_spec(root_module) is not None
                except (ImportError, ValueError, AttributeError):
                    available = False
                if not available:
                    errors.append(f"模块 {root_module} 不在项目文件集合中且当前运行时不可用")
                continue
            if module not in generated_modules:
                errors.append(f"项目模块 {project_modules[module]} 尚未生成，当前拓扑层禁止导入")
                continue
            try:
                exports = _python_exports(generated_modules[module])
            except SyntaxError:
                continue
            for alias in node.names:
                if alias.name != '*' and alias.name not in exports:
                    errors.append(
                        f"{project_modules[module]} 未导出符号 {alias.name}，请使用其真实接口"
                    )
                elif alias.name != '*':
                    imported_project_functions[alias.asname or alias.name] = (module, alias.name)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        imported_function = imported_project_functions.get(node.func.id)
        if not imported_function:
            continue
        module, exported_name = imported_function
        try:
            dependency_tree = ast.parse(generated_modules[module])
        except (SyntaxError, KeyError):
            continue
        definition = next(
            (
                candidate
                for candidate in dependency_tree.body
                if isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef))
                and candidate.name == exported_name
            ),
            None,
        )
        if definition is None:
            continue

        positional_params = [*definition.args.posonlyargs, *definition.args.args]
        required_count = len(positional_params) - len(definition.args.defaults)
        positional_count = len(node.args)
        keyword_names = {keyword.arg for keyword in node.keywords if keyword.arg is not None}
        supplied_names = {
            parameter.arg for parameter in positional_params[:positional_count]
        } | keyword_names
        required_names = {parameter.arg for parameter in positional_params[:required_count]}
        missing_names = sorted(required_names - supplied_names)

        if definition.args.vararg is None and positional_count > len(positional_params):
            errors.append(
                f"调用 {node.func.id} 传入 {positional_count} 个位置参数，"
                f"但 {project_modules[module]} 中定义最多接受 {len(positional_params)} 个"
            )
        if missing_names:
            errors.append(
                f"调用 {node.func.id} 缺少必需参数 {', '.join(missing_names)}，"
                f"请匹配 {project_modules[module]} 中的真实签名"
            )
        accepted_keywords = {
            parameter.arg for parameter in [*positional_params, *definition.args.kwonlyargs]
        }
        unexpected_keywords = sorted(keyword_names - accepted_keywords)
        if definition.args.kwarg is None and unexpected_keywords:
            errors.append(
                f"调用 {node.func.id} 使用了未声明参数 {', '.join(unexpected_keywords)}，"
                f"请匹配 {project_modules[module]} 中的真实签名"
            )
    return list(dict.fromkeys(errors))


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
    except Exception as e:
        logger.debug(f"文件操作失败：{e}")
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
        root_modules = {
            Path(project_file).stem
            for project_file in all_project_files
            if '/' not in project_file.replace('\\', '/') and project_file.endswith('.py')
        }
        def normalize_root_from_dot_import(match: re.Match) -> str:
            imported_names = match.group(2)
            module_names = [
                name.strip().split(" as ", 1)[0]
                for name in imported_names.split(",")
            ]
            if module_names and all(name in root_modules for name in module_names):
                return f"{match.group(1)}import {imported_names}"
            return match.group(0)

        content = re.sub(
            r'^(\s*)from\s+\.\s+import\s+([A-Za-z_]\w*(?:\s+as\s+[A-Za-z_]\w*)?(?:\s*,\s*[A-Za-z_]\w*(?:\s+as\s+[A-Za-z_]\w*)?)*)$',
            normalize_root_from_dot_import,
            content,
            flags=re.MULTILINE,
        )
        content = re.sub(
            r'^(\s*from\s+)\.([A-Za-z_]\w*)(\s+import\s+)',
            lambda match: (
                f"{match.group(1)}{match.group(2)}{match.group(3)}"
                if match.group(2) in root_modules
                else match.group(0)
            ),
            content,
            flags=re.MULTILINE,
        )
        return re.sub(
            r'^(\s*from\s+)([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+)(\s+import\s+)',
            lambda match: (
                f"{match.group(1)}{match.group(2).rsplit('.', 1)[-1]}{match.group(3)}"
                if match.group(2).rsplit('.', 1)[-1] in root_modules
                else match.group(0)
            ),
            content,
            flags=re.MULTILINE,
        )
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

        # 直接并发生成，由 LLMClient 内部信号量控制并发度
        if self.cancel_event and self.cancel_event.is_set():
            logger.info("[生成] 检测到取消信号，跳过小项目生成")
            return
        tasks = [self._generate_single_file(fi, project_context, total_files) for fi in file_plan]
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

        file_info_map: Dict[str, Dict] = {fi.get("path", ""): fi for fi in file_plan}

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
            stashed = _git_stash_push(str(self.output_dir), existing_files, f"agent-backup-layer-{layer_idx}")

            # 直接并发生成，由 LLMClient 内部信号量控制并发度
            async def generate_file(file_path: str) -> Dict:
                fi = file_info_map.get(file_path, {"path": file_path, "description": f"生成 {file_path}"})
                return await self._generate_single_file(fi, project_context, total_files, self._generated_contents)

            tasks = [generate_file(fp) for fp in layer_files]
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

        content = await engineer.generate_file(
            file_path, description, project_context, spec_context, dep_context,
            project_path=str(self.output_dir), callback=self.callback,
            is_existing_file=is_existing,
        )
        if asyncio.iscoroutine(content):
            logger.warning(f"generate_file 返回协程，自动 await: {file_path}")
            content = await content

        # 统一提取工程师生成的内容
        all_files = list(self.dependency_graph_obj.nodes.keys()) if self.dependency_graph_obj else []
        raw_content = content  # 保存原始内容用于恢复

        # 获取期望的语言，用于 LLM 语言检测
        project_language = project_context.get("architecture", {}).get("language", "")
        from app.agent.utils import get_expected_language_for_file
        expected_language = get_expected_language_for_file(file_path, project_language)
        async def llm_caller(prompt: str) -> str:
            return await call_llm(
                model=DEFAULT_CODE_MODEL,
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

        if not content:
            # 内容无效（可能是 JSON 元数据），尝试恢复
            from app.agent.utils import is_valid_code_content
            _, invalid_reason = is_valid_code_content(file_path, raw_content or "")
            if invalid_reason:
                logger.warning(f"内容无效: {file_path} - {invalid_reason}，尝试恢复")
                content = await self._recover_invalid_content_orchestator(
                    file_path, description, project_context, invalid_reason, engineer
                )

            if not content:
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

        import_errors = _validate_python_implementation(content, file_path)
        import_errors.extend(_validate_python_project_imports(
            content, file_path, generated_contents or {}, all_files
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
                content = corrected_content
            import_errors = _validate_python_implementation(content, file_path)
            import_errors.extend(_validate_python_project_imports(
                content, file_path, generated_contents or {}, all_files
            ))

        from app.agent.validation_report import ValidationReport
        validation_report = ValidationReport.create(source="cloud")
        for validation_error in import_errors:
            validation_report = validation_report.with_finding(
                validation_error,
                file_path=file_path,
                scope="cloud_syntax",
            )
        self.validation_report = validation_report
                "validation_report": validation_report.model_dump(mode="json"),
        if import_errors:
            error_message = f"文件生成失败: {file_path}（跨文件导入不一致: {'；'.join(import_errors)}）"
            self.errors.append(error_message)
            logger.error(error_message)
            return {
                "path": file_path,
                "description": description,
                "validation_report": validation_report.model_dump(mode="json"),
                "success": False,
                "size": 0,
            }

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
            self.errors.append(error_message)
            logger.error(error_message)
            return {
                "path": file_path,
                "description": description,
                "success": False,
                "size": 0,
            }

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
            "validation_report": validation_report.model_dump(mode="json"),
                        success=fix_attempt.fix_applied
                    )

        return {
            "path": file_path,
            "description": description,
            "success": True,
            "validation_report": validation_report.model_dump(mode="json"),
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

    async def _recover_invalid_content_orchestator(
        self,
        file_path: str,
        description: str,
        project_context: Dict,
        reason: str,
        engineer,
    ) -> Optional[str]:
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
                project_path=str(self.output_dir), callback=self.callback,
                is_existing_file=False,
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

        validation_success = True

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
            else:
                validation_success = False

        if self.enable_review:
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
                if review_result.get("risk_level") == "high":
                    validation_success = False

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
            except SyntaxError as e:
                validation_success = False
                logger.warning(f"文件语法错误: {file_path}: {e}")
            except Exception as e:
                logger.debug(f"文件操作失败：{e}")

        return validation_success, content

    def _clean_code_block(self, content: str) -> str:
        from app.agent.utils import clean_code_block
        return clean_code_block(content)

    def _select_alternative_model(self, primary_model: str) -> str:
        alt_map = {
            DEFAULT_REASONING_MODEL: DEFAULT_CODE_MODEL,
            DEFAULT_CODE_MODEL: DEFAULT_REASONING_MODEL,
            DEFAULT_FAST_MODEL: DEFAULT_CODE_MODEL,
            DEFAULT_ARCHITECT_MODEL: DEFAULT_REASONING_MODEL,
        }
        return alt_map.get(primary_model, DEFAULT_CODE_MODEL)

    def _select_engineer_for_model(self, model_name: str) -> Specialist:
        frontend_models = {DEFAULT_FAST_MODEL, DEFAULT_CODE_MODEL}
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
