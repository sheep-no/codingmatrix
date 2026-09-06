"""
DependencyGraph - 依赖图驱动生成

核心理念：通过分析文件间的依赖关系，确定最优的文件生成顺序。
这确保在生成某个文件时，它所依赖的文件已经存在并被纳入上下文。

典型依赖关系：
- models -> 数据库 Schema (Spec)
- services -> models, types (Spec)
- apis/views -> services, types (Spec)
- 前端组件 -> API 定义
- 配置文件 -> 无依赖（最早生成）
"""

import logging
import re
from typing import Optional, Dict, Any, List, Set
from pathlib import Path
from dataclasses import dataclass, field
from collections import defaultdict

from app.agent.signature_extractor import extract_signatures, get_context_budget
from app.agent.shadow_scanner import scan_shadow_dependencies, SKIP_DIRS
from app.agent.dependency_rules import DEPENDENCY_RULES, PATH_TYPE_RULES, EXTENSION_TYPE_MAP
from app.agent.generation_plan import GenerationPlan

logger = logging.getLogger(__name__)


def summarize_dependency_context(context: str) -> Dict[str, Any]:
    """返回依赖上下文的可审计摘要，避免日志记录完整源码。"""
    context = context or ""
    dependency_files = re.findall(r"^## 依赖文件: ([^\n]+)", context, re.MULTILINE)
    signature_lines = re.findall(r"(?:^|\n)(?:def |async def |class |function )", context)
    return {
        "present": bool(context.strip()),
        "chars": len(context),
        "dependency_files": dependency_files,
        "dependency_file_count": len(dependency_files),
        "signature_marker_count": len(signature_lines),
        "preview": "; ".join(dependency_files)[:240],
    }


@dataclass
class FileNode:
    """依赖图中的一个文件节点"""
    path: str
    file_type: str
    priority: int  # 1-5，越小越优先
    dependencies: List[str] = field(default_factory=list)
    description: str = ""


class DependencyGraph:
    """
    依赖图驱动的文件生成排序器

    工作流程：
    1. 构建依赖图（基于文件类型和路径规则）
    2. 执行拓扑排序
    3. 输出有序的生成列表
    4. 在生成每个文件时，注入其依赖文件的内容到上下文
    """

    # 从 dependency_rules.py 导入，保持向后兼容访问
    DEPENDENCY_RULES = DEPENDENCY_RULES
    PATH_TYPE_RULES = PATH_TYPE_RULES

    def __init__(self, language_adapter=None):
        self.nodes: Dict[str, FileNode] = {}
        self.adjacency: Dict[str, Set[str]] = defaultdict(set)  # file -> set of files it depends on
        self.reverse_adjacency: Dict[str, Set[str]] = defaultdict(set)  # file -> set of files that depend on it
        self.language_adapter = language_adapter  # 语言适配器（可选）
        self.generation_plan = None

    def add_file(self, path: str, file_type: Optional[str] = None, priority: int = 3, description: str = ""):
        """添加文件节点"""
        if not path:
            return
        
        # 空格路径检查：拒绝带空格的路径
        if ' ' in path:
            logger.warning(f"拒绝带空格的文件路径: {path}")
            return
        
        # 特殊字符检查
        if ',' in path or ';' in path:
            logger.warning(f"拒绝含特殊字符的文件路径: {path}")
            return
        
        # 包名检查：拒绝无扩展名且无目录分隔符的路径（如 "moment", "axios", "models"）
        if '/' not in path and '.' not in path:
            logger.warning(f"拒绝包名/目录名作为文件路径: {path}")
            return
        
        # 规范化路径：去除多余斜杠、统一使用正斜杠
        path = path.replace('\\', '/').replace('//', '/')
        
        if file_type is None:
            file_type = self._infer_file_type(path)

        node = FileNode(
            path=path,
            file_type=file_type,
            priority=priority,
            description=description
        )
        self.nodes[path] = node

    def add_dependency(self, file_path: str, depends_on: str):
        """添加显式依赖"""
        if file_path not in self.nodes:
            self.add_file(file_path)

        # 只有当依赖目标也在图中时，才添加边（避免引入外部库作为节点）
        if depends_on in self.nodes and depends_on != file_path:
            # 预防性环检测：检查 depends_on 是否已依赖 file_path
            if self._would_create_cycle(file_path, depends_on):
                logger.warning(f"忽略循环依赖: {file_path} -> {depends_on}")
                return
            if depends_on not in self.adjacency[file_path]:
                self.nodes[file_path].dependencies.append(depends_on)
                self.adjacency[file_path].add(depends_on)
                self.reverse_adjacency[depends_on].add(file_path)

    def _would_create_cycle(self, file_path: str, depends_on: str) -> bool:
        """检查添加 file_path -> depends_on 是否会创建环

        从 depends_on 出发做 BFS，如果能到达 file_path 则会形成环。
        """
        visited = set()
        queue = [depends_on]
        while queue:
            current = queue.pop(0)
            if current == file_path:
                return True
            if current in visited:
                continue
            visited.add(current)
            for neighbor in self.adjacency.get(current, set()):
                if neighbor in self.nodes and neighbor not in visited:
                    queue.append(neighbor)
        return False

    def get_affected_files(self, changed_files: List[str]) -> Dict[str, List[str]]:
        """
        给定变更文件列表，返回所有受影响的下游文件。

        使用 reverse_adjacency 进行 BFS 遍历，计算传递依赖的受影响文件。

        Args:
            changed_files: 变更文件路径列表

        Returns:
            {变更文件: [受影响的下游文件列表]}
        """
        affected = {}
        for changed in changed_files:
            dependents = self._get_transitive_dependents(changed)
            affected[changed] = dependents
        return affected

    def _get_transitive_dependents(self, file_path: str, max_depth: int = 10) -> List[str]:
        """
        BFS 遍历 reverse_adjacency，查找所有传递依赖的下游文件。

        Args:
            file_path: 源文件路径
            max_depth: 最大遍历深度（防止循环依赖无限遍历）

        Returns:
            受影响的下游文件列表（不含源文件自身）
        """
        result = []
        visited = set()
        queue = [(file_path, 0)]

        while queue:
            current, depth = queue.pop(0)
            if current in visited or depth > max_depth:
                continue
            visited.add(current)

            for dep in self.reverse_adjacency.get(current, set()):
                if dep not in visited and dep != file_path:
                    result.append(dep)
                    queue.append((dep, depth + 1))

        return result

    def build_from_architecture(self, architecture: Dict[str, Any]):
        """从架构设计结果构建依赖图（优先使用 LLM 声明的依赖）"""
        file_plan = architecture.get("file_plan", [])
        if file_plan:
            try:
                self.generation_plan = GenerationPlan.from_architecture(architecture)
                file_plan = list(self.generation_plan.file_entries())
            except ValueError as exc:
                # Legacy graph rules still resolve inferred and external imports.
                # Preserve that migration behavior while exposing the failed plan.
                self.generation_plan = None
                logger.warning("项目级生成计划暂未冻结，沿用依赖图兼容规则: %s", exc)

        # 0. 自动设置 GenericLanguageAdapter 的 file_plan_data
        # 这样 _import_to_file_path 就可以正确解析任何语言的 import
        if self.language_adapter and hasattr(self.language_adapter, 'set_file_plan_data'):
            self.language_adapter.set_file_plan_data(file_plan)

        # 0.5 过滤和规范化 file_plan
        cleaned_file_plan = []
        seen_paths = set()
        # 先处理基础文件的声明，使互相冲突的 LLM imports 按架构优先级
        # 确定稳定方向，后续反向边会被环检测拒绝。
        dependency_plan = sorted(
            file_plan,
            key=lambda item: (item.get("priority", 3), item.get("path", "")),
        )
        for file_info in dependency_plan:
            path = file_info.get("path", "")
            if not path:
                continue
            
            # 空格路径检查：跳过带空格的路径
            if ' ' in path:
                logger.warning(f"跳过带空格的文件路径: {path}")
                continue
            
            # 特殊字符检查
            if ',' in path or ';' in path:
                logger.warning(f"跳过含特殊字符的文件路径: {path}")
                continue
            
            # 包名检查：跳过无扩展名且无目录分隔符的路径（如 "moment", "axios", "models"）
            if '/' not in path and '.' not in path:
                logger.warning(f"跳过包名/目录名作为文件路径: {path}")
                continue
            
            # 点号路径转换：无斜杠但有多段点号（如 src.app.utils.py）
            if '/' not in path and '.' in path:
                dot_segments = path.split('.')
                if len(dot_segments) >= 3:
                    known_exts = {'py','js','ts','jsx','tsx','css','html','json','md','yaml','yml','toml','cfg','ini','sh','sql','go','rs','java','rb','php'}
                    last = dot_segments[-1].lower()
                    if last in known_exts:
                        original = path
                        path = '/'.join(dot_segments[:-1]) + '.' + last
                        logger.info(f"点号路径自动转换: {original} -> {path}")
                    else:
                        logger.warning(f"可疑路径格式（无斜杠但有点号分隔）: {path}，将由验证 LLM 判断")
            
            # 规范化路径
            path = path.replace('\\', '/').replace('//', '/')
            if path.startswith('./'):
                path = path[2:]
            
            # 去重
            if path in seen_paths:
                logger.warning(f"跳过重复的文件路径: {path}")
                continue
            seen_paths.add(path)
            
            # 更新 file_info 中的路径
            file_info["path"] = path
            cleaned_file_plan.append(file_info)
        
        if len(cleaned_file_plan) != len(file_plan):
            logger.warning(f"file_plan 清理: {len(file_plan)} -> {len(cleaned_file_plan)} 个文件")
        
        # 使用清理后的 file_plan 更新架构
        architecture["file_plan"] = cleaned_file_plan
        file_plan = cleaned_file_plan

        # 1. 先添加所有文件节点（确保所有文件都在图中）
        for file_info in file_plan:
            path = file_info.get("path", "")
            description = file_info.get("description", "")
            priority = file_info.get("priority", 3)
            file_type = file_info.get("file_type")
            if not file_type or file_type in {"unknown", "other", "utils"}:
                file_type = self._infer_file_type(path)

            if not path:
                continue

            self.add_file(path, priority=priority, description=description, file_type=file_type)

        database_paths = {
            path for path, node in self.nodes.items()
            if node.file_type == "database"
        }
        model_paths = {
            path for path, node in self.nodes.items()
            if node.file_type == "model"
        }
        for file_info in file_plan:
            if file_info.get("path") not in database_paths:
                continue

            def references_model(value: Any) -> bool:
                return (
                    isinstance(value, str)
                    and (
                        value in model_paths
                        or self._import_to_file_path(value) in model_paths
                    )
                )

            for field in ("imports", "dependencies"):
                values = file_info.get(field)
                if isinstance(values, list):
                    file_info[field] = [
                        value for value in values
                        if not references_model(value)
                    ]
            contract = file_info.get("contract")
            if isinstance(contract, dict) and isinstance(contract.get("required_imports"), list):
                contract["required_imports"] = [
                    value for value in contract["required_imports"]
                    if not references_model(value)
                ]

        # 2. 再处理依赖关系（此时所有文件都在图中）
        files_with_resolved_imports = set()
        for file_info in file_plan:
            path = file_info.get("path", "")
            if not path:
                continue

            # 使用 LLM 显式声明的依赖（dependencies 字段）
            explicit_deps = file_info.get("dependencies", [])
            if isinstance(explicit_deps, list):
                for dep in explicit_deps:
                    if dep and dep != path:  # 避免自依赖
                        self.add_dependency(path, dep)

            # 使用 imports 字段构建依赖关系
            imports = file_info.get("imports", [])
            if isinstance(imports, list) and imports:
                for imp in imports:
                    if imp and imp != path:
                        # 转换 import 路径为文件路径
                        dep_path = self._import_to_file_path(imp)
                        if dep_path:
                            self.add_dependency(path, dep_path)
                            files_with_resolved_imports.add(path)

        # 3. 类型规则补齐已解析 imports 尚未覆盖的依赖类型
        contract_driven = any(
            isinstance(item, dict) and isinstance(item.get("contract"), dict) and item.get("contract")
            for item in file_plan
        )
        self._auto_add_dependencies(files_with_resolved_imports, use_legacy_rules=not contract_driven)
        if contract_driven:
            # Contracts define exact edges; preserve the invariant that an entry
            # module can consume the repository layer when the plan omits it.
            entry_paths = [
                path for path, node in self.nodes.items()
                if node.file_type == "entry"
            ]
            repository_paths = [
                path for path, node in self.nodes.items()
                if node.file_type == "repository"
            ]
            for entry_path in entry_paths:
                for repository_path in repository_paths:
                    if repository_path not in self.adjacency.get(entry_path, set()):
                        self.add_dependency(entry_path, repository_path)

            # Keep persistence infrastructure below application models. LLM
            # plans occasionally emit both directions; the database module
            # must remain generatable before model declarations.
            for database_path in database_paths:
                for model_path in model_paths & self.adjacency.get(database_path, set()):
                    self.adjacency[database_path].discard(model_path)
                    self.reverse_adjacency[model_path].discard(database_path)
                    if model_path in self.nodes[database_path].dependencies:
                        self.nodes[database_path].dependencies.remove(model_path)
                for model_path in model_paths:
                    if database_path not in self.adjacency.get(model_path, set()):
                        self.add_dependency(model_path, database_path)

            # Python validation schemas describe the public shape of ORM
            # entities, so generate them with the real model declarations in
            # context instead of asking two independent layers to guess types.
            python_schema_paths = {
                path for path, node in self.nodes.items()
                if path.endswith(".py") and node.file_type in {"schema", "types"}
            }
            python_model_paths = {path for path in model_paths if path.endswith(".py")}
            for schema_path in python_schema_paths:
                for model_path in python_model_paths:
                    if model_path not in self.adjacency.get(schema_path, set()):
                        self.add_dependency(schema_path, model_path)

            # Python repositories consume validated request/response schemas.
            # Normalize an accidental reverse edge before enforcing that layer.
            python_repository_paths = {
                path for path in repository_paths if path.endswith(".py")
            }
            for repository_path in python_repository_paths:
                for schema_path in python_schema_paths:
                    self.adjacency[schema_path].discard(repository_path)
                    self.reverse_adjacency[repository_path].discard(schema_path)
                    if repository_path in self.nodes[schema_path].dependencies:
                        self.nodes[schema_path].dependencies.remove(repository_path)
                    if schema_path not in self.adjacency.get(repository_path, set()):
                        self.add_dependency(repository_path, schema_path)

            # Tests execute against the completed runtime graph. Keep them in a
            # final generation layer even when a contract omits explicit imports.
            test_paths = {
                path for path, node in self.nodes.items()
                if node.file_type == "test"
            }
            runtime_paths = set(self.nodes) - test_paths
            for test_path in test_paths:
                for runtime_path in runtime_paths:
                    self.add_dependency(test_path, runtime_path)

        # 3.5 去重：基于图结构消除功能重复文件
        self.deduplicate()

        # 4. 输出依赖图详情（调试用）
        logger.info(f"=== 依赖图构建详情 ===")
        logger.info(f"文件节点 ({len(self.nodes)}):")
        for path, node in sorted(self.nodes.items()):
            logger.info(f"  {path} (type={node.file_type}, priority={node.priority})")
        logger.info(f"依赖关系 ({sum(len(d) for d in self.adjacency.values())} 条):")
        for path, deps in sorted(self.adjacency.items()):
            if deps:
                logger.info(f"  {path} -> {sorted(deps)}")
        logger.info(f"被依赖关系:")
        for path, dependents in sorted(self.reverse_adjacency.items()):
            if dependents:
                logger.info(f"  {path} <- {sorted(dependents)}")
        logger.info(f"========================")

    def deduplicate(self):
        """基于图结构消除功能重复文件

        当多个文件同名（如 models.py 和 src/models/models.py）且 file_type 相同时，
        根据图结构评分选择保留哪个：
        - 被依赖数（入度）越高越重要
        - 路径越深越具体
        - 依赖数越多越完整

        同名但 file_type 不同的文件（如 models/user.py 和 routers/user.py）不视为重复。

        语言无关：不依赖任何语言特定的命名规则。
        """
        from collections import defaultdict

        # 按 (文件名, file_type) 分组
        name_type_to_paths: Dict[tuple, List[str]] = defaultdict(list)
        for path in list(self.nodes.keys()):
            filename = Path(path).name
            node = self.nodes.get(path)
            file_type = node.file_type if node else 'unknown'
            name_type_to_paths[(filename, file_type)].append(path)

        removed = []

        for (filename, file_type), paths in name_type_to_paths.items():
            if len(paths) <= 1:
                continue

            # 对每个候选文件评分
            scores = {}
            for path in paths:
                # 入度：被多少文件依赖（越多越重要）
                in_degree = len(self.reverse_adjacency.get(path, set()))
                # 出度：依赖多少文件（越多越完整）
                out_degree = len(self.adjacency.get(path, set()))
                # 路径深度（越深越具体）
                depth = path.count('/')
                # 是否有明确的 file_type（非 unknown/unknown）
                node = self.nodes.get(path)
                has_type = node and node.file_type not in ('unknown', 'utils', '')

                score = in_degree * 10 + out_degree * 2 + depth * 5 + (20 if has_type else 0)
                scores[path] = score

            # 保留得分最高的
            best_path = max(scores, key=scores.get)

            for path in paths:
                if path == best_path:
                    continue

                # 将被删除文件的入边重定向到 best_path
                dependents = list(self.reverse_adjacency.get(path, set()))
                for dep in dependents:
                    if dep in self.nodes:
                        self.adjacency[dep].discard(path)
                        if best_path not in self.adjacency[dep]:
                            self.add_dependency(dep, best_path)

                # 将被删除文件的出边转移到 best_path（如果 best_path 还没有该依赖）
                deps = list(self.adjacency.get(path, set()))
                for dep in deps:
                    if dep != best_path and dep in self.nodes:
                        self.add_dependency(best_path, dep)

                # 从图中移除
                self._remove_node(path)
                removed.append((path, best_path, scores[path]))

        if removed:
            logger.info(f"去重: 移除 {len(removed)} 个重复文件")
            for old_path, best_path, score in removed:
                logger.info(f"  移除 {old_path} (score={score}), 保留 {best_path}")

    def get_unknown_type_files(self) -> List[str]:
        """返回所有 file_type 为 unknown 或 utils 或空字符串的文件路径列表"""
        return [
            path for path, node in self.nodes.items()
            if node.file_type in ('unknown', 'utils', '')
        ]

    def update_file_type(self, path: str, new_type: str):
        """更新指定文件的 file_type"""
        if path in self.nodes and new_type and new_type not in ('unknown', ''):
            old_type = self.nodes[path].file_type
            self.nodes[path].file_type = new_type
            if old_type != new_type:
                logger.info(f"file_type 更新: {path} ({old_type} -> {new_type})")

    def refactor_file(self, old_path: str, new_files: List[Dict[str, Any]], import_mapping: Dict[str, str]) -> List[str]:
        """重构文件：将旧节点替换为新节点，更新依赖关系

        Args:
            old_path: 旧文件路径
            new_files: 新文件列表，每个包含 path, file_type, priority, description
            import_mapping: import 映射 {旧 import 路径: 新 import 路径}

        Returns:
            新添加的文件路径列表
        """
        if old_path not in self.nodes:
            logger.warning(f"重构失败: {old_path} 不在依赖图中")
            return []

        old_node = self.nodes[old_path]
        old_type = old_node.file_type

        # 获取旧文件的所有依赖和被依赖关系
        old_deps = list(self.adjacency.get(old_path, set()))
        old_dependents = list(self.reverse_adjacency.get(old_path, set()))

        # 添加新文件节点
        new_paths = []
        for nf in new_files:
            nf_path = nf.get("path", "")
            if not nf_path:
                continue
            self.add_file(
                nf_path,
                file_type=nf.get("file_type", old_type),
                priority=nf.get("priority", old_node.priority),
                description=nf.get("description", "")
            )
            new_paths.append(nf_path)

        # 将旧文件的出边（依赖）转移到新文件
        # 根据 import_mapping 决定每个新文件依赖哪些旧依赖
        for new_path in new_paths:
            new_node = self.nodes.get(new_path)
            if not new_node:
                continue
            # 新文件默认继承旧文件的依赖（可通过 import_mapping 精确控制）
            for old_dep in old_deps:
                # 检查 import_mapping 是否有重定向
                mapped_dep = import_mapping.get(old_dep, old_dep)
                if mapped_dep in self.nodes:
                    self.add_dependency(new_path, mapped_dep)

        # 将旧文件的入边（被依赖）转移到新文件
        # 根据 import_mapping 决定哪些已有文件依赖哪个新文件
        for dependent in old_dependents:
            if dependent not in self.nodes:
                continue
            # 检查 dependent 的依赖应该指向哪个新文件
            # 默认指向第一个新文件（通常是主入口文件）
            target = new_paths[0] if new_paths else None
            # 检查 import_mapping 中是否有更精确的映射
            for old_import, new_import in import_mapping.items():
                if old_import == old_path and new_import in self.nodes:
                    target = new_import
                    break
            if target:
                # 移除旧边，添加新边
                self.adjacency[dependent].discard(old_path)
                self.nodes[dependent].dependencies = [d for d in self.nodes[dependent].dependencies if d != old_path]
                self.add_dependency(dependent, target)

        # 移除旧节点
        self._remove_node(old_path)
        logger.info(f"重构完成: {old_path} -> {new_paths}")

        return new_paths

    def _remove_node(self, path: str):
        """从图中完全移除一个节点及其所有边"""
        if path in self.nodes:
            del self.nodes[path]
        if path in self.adjacency:
            del self.adjacency[path]
        if path in self.reverse_adjacency:
            # 清理其他节点对它的引用
            for dependent in self.reverse_adjacency[path]:
                if dependent in self.adjacency:
                    self.adjacency[dependent].discard(path)
                if dependent in self.nodes and path in self.nodes[dependent].dependencies:
                    self.nodes[dependent].dependencies.remove(path)
            del self.reverse_adjacency[path]

    def _import_to_file_path(self, import_path: str) -> Optional[str]:
        """将 import 路径转换为文件路径"""
        # 使用语言适配器
        if self.language_adapter:
            from .adapters import ImportInfo
            import_info = ImportInfo(module=import_path, symbols=[], is_relative=False)
            candidates = self.language_adapter.resolve_import_to_file(import_info, "")

            # 在已知节点中查找匹配
            for candidate in candidates:
                if candidate in self.nodes:
                    return candidate

            # 严格文件集合可能将 app/models.py 等路径扁平化为 models.py。
            # 当文件名在图中唯一时，允许按模块末段匹配扁平化后的节点。
            module_name = import_path.lstrip('.').replace('\\', '/').split('/')[-1].split('.')[-1]
            basename_matches = [
                path
                for path in self.nodes
                if Path(path).stem == module_name
            ]
            if len(basename_matches) == 1:
                return basename_matches[0]

            # 不返回不存在的候选路径（避免创建垃圾文件）
            return None

        # Fallback: 通用规则
        pkg_path = import_path.replace('.', '/')

        # 检查是否是包（在 nodes 中存在入口文件）
        if self.language_adapter:
            init_path = self.language_adapter.get_package_init_file(pkg_path)
            if init_path and init_path in self.nodes:
                return init_path
        else:
            # 通用默认值
            init_path = pkg_path + '/__init__.py'
            if init_path in self.nodes:
                return init_path

        # 检查是否是模块文件
        extensions = self.language_adapter.extensions if self.language_adapter else {'.py'}
        for ext in extensions:
            file_path = pkg_path + ext
            if file_path in self.nodes:
                return file_path

        # 不返回不存在的路径（避免创建垃圾文件）
        return None

    def build_from_specs(self, specs: Dict[str, Any]):
        """根据规范构建基础依赖"""
        # 如果存在 OpenAPI 规范，添加相关的 API 和模型文件
        if "openapi" in specs:
            openapi = specs["openapi"].content if hasattr(specs["openapi"], 'content') else specs["openapi"]
            paths = openapi.get("paths", {})
            schemas = openapi.get("components", {}).get("schemas", {})

            # 为每个 API 路径添加 API 文件
            for path_str, methods in paths.items():
                api_path = self._path_to_api_file(path_str)
                if api_path:
                    self.add_file(api_path, file_type="api", priority=4)
                    # API 依赖 Service
                    service_path = self._path_to_service_file(path_str)
                    if service_path:
                        self.add_file(service_path, file_type="service", priority=3)
                        self.add_dependency(api_path, service_path)

            # 为每个 Schema 添加 Model 文件
            for schema_name in schemas:
                model_path = f"app/models/{self._camel_to_snake(schema_name)}.py"
                self.add_file(model_path, file_type="model", priority=2)

    def _auto_add_dependencies(self, files_with_imports: set, use_legacy_rules: bool = True):
        """按文件类型补齐 imports 尚未覆盖的依赖类型。"""
        if not use_legacy_rules:
            logger.info("架构契约已提供依赖边界，跳过基于文件类型的兼容规则")
            return
        type_to_files: Dict[str, List[str]] = defaultdict(list)
        for path, node in self.nodes.items():
            type_to_files[node.file_type].append(path)

        logger.info(f"_auto_add_dependencies: 文件类型分布 = {dict(type_to_files)}")
        logger.info(
            "_auto_add_dependencies: 已解析 imports 的文件 (%d): %s",
            len(files_with_imports),
            sorted(files_with_imports),
        )

        added_by_rules = 0
        replaced_reverse_edges = 0
        for path, node in self.nodes.items():
            dep_types = self.DEPENDENCY_RULES.get(node.file_type, [])
            for dep_type in dep_types:
                existing_dep_types = {
                    self.nodes[dependency].file_type
                    for dependency in self.adjacency.get(path, set())
                    if dependency in self.nodes
                }
                if dep_type in existing_dep_types:
                    continue

                for other_path in type_to_files.get(dep_type, []):
                    if other_path == path:
                        continue

                    # 类型规则是架构层级的最终裁决，覆盖 LLM 同时声明的直接反向边。
                    if path in self.adjacency.get(other_path, set()):
                        self.adjacency[other_path].discard(path)
                        self.reverse_adjacency[path].discard(other_path)
                        self.nodes[other_path].dependencies = [
                            dependency
                            for dependency in self.nodes[other_path].dependencies
                            if dependency != path
                        ]
                        replaced_reverse_edges += 1

                    before = other_path in self.adjacency.get(path, set())
                    self.add_dependency(path, other_path)
                    if not before and other_path in self.adjacency.get(path, set()):
                        added_by_rules += 1

        logger.info(
            "_auto_add_dependencies: 类型规则添加了 %d 条依赖, 覆盖 %d 条直接反向边",
            added_by_rules,
            replaced_reverse_edges,
        )

    def ensure_package_files(self) -> List[str]:
        """
        确保所有包都有入口文件（如 __init__.py）

        使用 language_adapter 检查包结构，添加缺失的文件。

        Returns:
            添加的文件路径列表
        """
        added_files = []

        # 收集所有包路径
        packages = set()
        init_file_name = self.language_adapter.package_init_filename if self.language_adapter else '__init__.py'
        for path in self.nodes:
            if '/' in path:
                parts = path.rsplit('/', 1)
                if len(parts) == 2:
                    pkg = parts[0]
                    # 检查是否是包（有文件但没有入口文件）
                    if not path.endswith(init_file_name):
                        packages.add(pkg)

         # 检查每个包
        for pkg in packages:
            if self.language_adapter:
                missing = self.language_adapter.validate_package_structure(
                    pkg, {p: "" for p in self.nodes}
                )
                for init_path in missing:
                    if init_path not in self.nodes:
                        self.add_file(init_path, file_type="config", priority=5,
                                     description=f"Package init file for {pkg}")
                        added_files.append(init_path)
                        # Make __init__.py depend on all other files in the same package
                        for other_path in self.nodes:
                            if other_path != init_path and other_path.startswith(pkg + '/') and not other_path.endswith(init_file_name):
                                self.add_dependency(init_path, other_path)
            else:
                # Fallback: 通用规则
                init_path = f"{pkg}/{init_file_name}"
                if init_path not in self.nodes:
                    self.add_file(init_path, file_type="config", priority=5,
                                 description=f"Package init file for {pkg}")
                    added_files.append(init_path)
                    # Make __init__.py depend on all other files in the same package
                    for other_path in self.nodes:
                        if other_path != init_path and other_path.startswith(pkg + '/') and not other_path.endswith(init_file_name):
                            self.add_dependency(init_path, other_path)

        return added_files

    def get_generation_order(self) -> List[str]:
        """
        获取文件生成顺序（拓扑排序）

        Returns:
            按依赖顺序排列的文件路径列表
        """
        # 先尝试打破循环依赖
        self._break_cycles()

        # Kahn's 算法实现拓扑排序
        in_degree: Dict[str, int] = defaultdict(int)

        # 计算入度
        for node_path in self.nodes:
            if node_path not in in_degree:
                in_degree[node_path] = 0
            for dep in self.adjacency.get(node_path, set()):
                if dep in self.nodes:  # 只计算存在的节点
                    in_degree[node_path] += 1

        # 初始化队列（入度为 0 的节点）
        queue = []
        for node_path in self.nodes:
            if in_degree[node_path] == 0:
                queue.append(node_path)

        # 按优先级排序
        queue.sort(key=lambda x: self.nodes[x].priority if x in self.nodes else 99)

        result = []
        while queue:
            # 选择优先级最高的节点
            queue.sort(key=lambda x: self.nodes[x].priority if x in self.nodes else 99)
            node = queue.pop(0)
            result.append(node)

            # 更新依赖该节点的节点的入度
            for dependent in self.reverse_adjacency.get(node, set()):
                if dependent in self.nodes:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)

        # 检查是否有循环依赖
        if len(result) != len(self.nodes):
            missing = set(self.nodes.keys()) - set(result)
            logger.warning(f"检测到循环依赖，以下文件无法确定顺序: {missing}")
            # 将剩余文件按优先级追加到结果末尾
            sorted_missing = sorted(missing, key=lambda x: self.nodes[x].priority if x in self.nodes else 99)
            result.extend(sorted_missing)

        return result

    def _break_cycles(self):
        """检测并打破循环依赖"""
        visited = set()
        rec_stack = set()
        cycles = []

        def dfs(node: str, path: List[str]):
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in self.adjacency.get(node, set()):
                if neighbor not in self.nodes:
                    continue
                if neighbor not in visited:
                    dfs(neighbor, path)
                elif neighbor in rec_stack:
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)

            path.pop()
            rec_stack.discard(node)

        for node in self.nodes:
            if node not in visited:
                dfs(node, [])

        # 打破检测到的循环
        for cycle in cycles:
            # 策略：移除指向入度最大的节点的边
            # 入度大的节点更可能从其他路径获得依赖，移除该边影响最小
            max_in_degree = -1
            edge_to_remove = None

            for i in range(len(cycle) - 1):
                from_node = cycle[i]
                to_node = cycle[i + 1]
                in_degree = len(self.reverse_adjacency.get(to_node, set()))

                if in_degree > max_in_degree:
                    max_in_degree = in_degree
                    edge_to_remove = (from_node, to_node)

            if edge_to_remove:
                from_node, to_node = edge_to_remove
                self.adjacency[from_node].discard(to_node)
                self.reverse_adjacency[to_node].discard(from_node)
                if from_node in self.nodes:
                    if to_node in self.nodes[from_node].dependencies:
                        self.nodes[from_node].dependencies.remove(to_node)
                logger.info(f"打破循环依赖: {from_node} -> {to_node} (目标入度={max_in_degree})")

    def get_generation_layers(self) -> List[List[str]]:
        """
        获取按依赖关系分层的生成顺序

        返回一个列表的列表，每个子列表中的文件可以并行生成，
        因为它们之间没有相互依赖关系。

        示例: [[config.py, .env], [models.py], [services.py], [api.py]]
        """
        # 先打破循环依赖
        self._break_cycles()

        in_degree: Dict[str, int] = defaultdict(int)
        for node_path in self.nodes:
            if node_path not in in_degree:
                in_degree[node_path] = 0
            for dep in self.adjacency.get(node_path, set()):
                if dep in self.nodes:
                    in_degree[node_path] += 1

        layers = []
        remaining = set(self.nodes.keys())

        while remaining:
            # 找出所有入度为 0 的节点（当前层可以并行生成的文件）
            current_layer = [n for n in remaining if in_degree[n] == 0]
            if not current_layer:
                # 理论上不会到这里（已打破循环）
                current_layer = list(remaining)

            # 按优先级排序
            current_layer.sort(key=lambda x: self.nodes[x].priority if x in self.nodes else 99)
            layers.append(current_layer)

            # 更新入度
            for node in current_layer:
                remaining.discard(node)
                for dependent in self.reverse_adjacency.get(node, set()):
                    if dependent in remaining:
                        in_degree[dependent] -= 1

        return layers

    # 向后兼容：保留类方法引用
    get_context_budget = staticmethod(get_context_budget)

    def get_context_package_for_file(
        self,
        file_path: str,
        generated_files: Dict[str, str],
        max_context_bytes: int = 0,
        model_context_length: int = 0,
        project_spec: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """构建目标文件的可序列化依赖上下文包。"""
        if max_context_bytes <= 0:
            ctx_len = model_context_length if model_context_length > 0 else 32768
            max_context_bytes = get_context_budget(ctx_len)

        package: Dict[str, Any] = {
            "target_file": file_path,
            "dependencies": [],
            "budget_chars": max_context_bytes,
        }

        if project_spec:
            node = self.nodes.get(file_path)
            file_type = node.file_type if node else "unknown"
            file_spec = project_spec.get(file_type, project_spec.get("default", {}))
            if file_spec:
                spec_lines = []
                storage = file_spec.get("storage", {})
                terminology = file_spec.get("terminology", {})
                if storage:
                    spec_lines.append(f"- 存储方式: {storage.get('type', 'unknown')}")
                    if storage.get("filename"):
                        spec_lines.append(f"- 存储文件: {storage['filename']}")
                if terminology:
                    terms = ", ".join(f"{k}={v}" for k, v in terminology.items())
                    spec_lines.append(f"- 术语表: {terms}")
                if spec_lines:
                    package["project_spec"] = "\n".join(spec_lines)

        dependencies = self.adjacency.get(file_path, set())
        sorted_deps = sorted(
            [d for d in dependencies if d in generated_files],
            key=lambda d: self.nodes[d].priority if d in self.nodes else 99
        )

        remaining_budget = max_context_bytes
        for index, dep_path in enumerate(sorted_deps):
            content = generated_files[dep_path]
            node = self.nodes.get(dep_path)
            is_core = node and node.priority <= 2 if node else False

            remaining_deps = len(sorted_deps) - index
            if is_core and remaining_deps > 1:
                budget = int(remaining_budget * 0.6)
            else:
                budget = max(200, remaining_budget // max(1, remaining_deps))

            if self.language_adapter and hasattr(self.language_adapter, "extract_signatures"):
                signatures = self.language_adapter.extract_signatures(content, dep_path)
            else:
                signatures = extract_signatures(dep_path, content)
            signature_budget = max(0, int(budget * 0.4))
            code_budget = max(0, budget - signature_budget)
            signature_text = (signatures or "")[:signature_budget]
            code_text = content[:code_budget]
            package["dependencies"].append({
                "path": dep_path,
                "relation": "imports",
                "symbols": re.findall(r"(?:class|def|async def|function)\s+([A-Za-z_]\w*)", signature_text),
                "signatures": signature_text,
                "relevant_code": code_text,
                "content_chars": len(content),
                "signature_chars": len(signature_text),
                "relevant_code_chars": len(code_text),
                "truncated": len(content) > code_budget,
            })
            remaining_budget -= len(signature_text) + len(code_text) + 80
            if remaining_budget <= 0:
                break

        return package

    def get_context_for_file(
        self,
        file_path: str,
        generated_files: Dict[str, str],
        max_context_bytes: int = 0,
        model_context_length: int = 0,
        project_spec: Optional[Dict] = None,
    ) -> str:
        """渲染上下文包，保持现有工程师 prompt 接口兼容。"""
        package = self.get_context_package_for_file(
            file_path,
            generated_files,
            max_context_bytes=max_context_bytes,
            model_context_length=model_context_length,
            project_spec=project_spec,
        )
        parts = []
        if package.get("project_spec"):
            node = self.nodes.get(file_path)
            file_type = node.file_type if node else "unknown"
            parts.append(f"## 项目规范 (file_type={file_type})\n{package['project_spec']}\n")
        for dependency in package["dependencies"]:
            sections = []
            if dependency["signatures"]:
                sections.append(dependency["signatures"])
            if dependency["relevant_code"]:
                sections.append(dependency["relevant_code"])
            preview = "\n".join(sections)
            suffix = "..." if dependency["truncated"] else ""
            parts.append(f"## 依赖文件: {dependency['path']}\n```\n{preview}{suffix}\n```\n")
        return "\n".join(parts)

    def get_dependency_summary(self) -> Dict[str, List[str]]:
        """获取依赖关系摘要"""
        summary = {}
        for path, deps in self.adjacency.items():
            if deps:
                summary[path] = list(deps)
        return summary

    def to_dict(self) -> Dict[str, Any]:
        """导出依赖图信息"""
        return {
            "nodes": {path: {"type": node.file_type, "priority": node.priority, "description": node.description} for path, node in self.nodes.items()},
            "dependencies": {k: list(v) for k, v in self.adjacency.items() if v},
            "generation_order": self.get_generation_order()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], language_adapter=None) -> 'DependencyGraph':
        """从字典恢复依赖图"""
        graph = cls(language_adapter=language_adapter)
        
        # 恢复节点
        for path, node_info in data.get("nodes", {}).items():
            graph.add_file(
                path=path,
                file_type=node_info.get("type"),
                priority=node_info.get("priority", 3),
                description=node_info.get("description", "")
            )
        
        # 恢复依赖关系
        for source, targets in data.get("dependencies", {}).items():
            for target in targets:
                graph.add_dependency(source, target)
        
        return graph

    def save(self, filepath: str):
        """持久化依赖图到磁盘"""
        import json
        data = self.to_dict()
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"依赖图已保存到: {filepath}")

    @classmethod
    def load(cls, filepath: str, language_adapter=None) -> Optional['DependencyGraph']:
        """从磁盘加载依赖图"""
        import json
        from pathlib import Path
        
        if not Path(filepath).exists():
            logger.info(f"依赖图文件不存在: {filepath}")
            return None
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            graph = cls.from_dict(data, language_adapter=language_adapter)
            logger.info(f"从磁盘加载依赖图: {len(graph.nodes)} 个节点, {len(graph.adjacency)} 条依赖")
            return graph
        except Exception as e:
            logger.warning(f"加载依赖图失败: {e}")
            return None

    # ==================== 辅助方法 ====================

    def _infer_file_type(self, path: str) -> str:
        """根据文件路径推断文件类型"""
        # 优先使用语言适配器
        if self.language_adapter:
            return self.language_adapter.infer_file_type(path)

        # 使用硬编码规则作为 fallback
        for pattern, file_type in self.PATH_TYPE_RULES:
            if path == pattern or path.startswith(pattern) or path.endswith(pattern):
                return file_type

        # 特殊处理包入口文件
        if self.language_adapter and self.language_adapter.package_init_filename:
            init_file_name = self.language_adapter.package_init_filename
            if path.endswith(init_file_name):
                return 'config'

        # 根据扩展名推断
        ext = Path(path).suffix.lower()
        return EXTENSION_TYPE_MAP.get(ext, 'utils')

    def _path_to_api_file(self, api_path: str) -> str:
        """将 API 路径转换为文件路径"""
        # /api/users -> app/api/users.py
        # /api/users/{id} -> app/api/users.py
        parts = api_path.strip('/').split('/')
        # 移除路径参数
        parts = [p for p in parts if not p.startswith('{')]
        if not parts:
            return ""
        return f"app/api/{'_'.join(parts)}.py"

    def _path_to_service_file(self, api_path: str) -> str:
        """将 API 路径转换为 Service 文件路径"""
        parts = api_path.strip('/').split('/')
        parts = [p for p in parts if not p.startswith('{')]
        if not parts:
            return ""
        return f"app/services/{'_'.join(parts)}_service.py"

    def _camel_to_snake(self, name: str) -> str:
        """驼峰转蛇形"""
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

    async def build_from_existing_project(self, project_path: Path) -> Dict[str, Any]:
        """
        从已有项目目录构建依赖图（解析源代码 import/require 语句）

        用于增量修改场景：用户上传项目后，构建真实依赖关系

        v4.7.0 增强：附带阴影依赖扫描结果（只记录不阻断）
        v5.12.x 增强：阴影依赖扫描改为异步，避免阻塞事件循环
        """
        result = self._build_graph_from_project(project_path)

        shadow_deps = await scan_shadow_dependencies(project_path)
        result["shadow_dependencies"] = shadow_deps

        return result

    def _build_graph_from_project(self, project_path: Path) -> Dict[str, Any]:
        """核心构建逻辑（原有 build_from_existing_project 内容）"""
        self.nodes.clear()
        self.adjacency.clear()
        self.reverse_adjacency.clear()

        py_imports: Dict[str, List[str]] = {}
        js_requires: Dict[str, List[str]] = {}
        generic_imports: Dict[str, List[str]] = {}  # 通用依赖

        for file_path in project_path.rglob("*"):
            if any(part in SKIP_DIRS for part in file_path.parts):
                continue
            if not file_path.is_file():
                continue

            rel_path = str(file_path.relative_to(project_path))
            suffix = file_path.suffix.lower()

            self.add_file(rel_path)

            if suffix == '.py':
                deps = self._parse_python_imports(file_path, project_path)
                py_imports[rel_path] = deps

            elif suffix in ('.js', '.ts', '.jsx', '.tsx', '.vue'):
                deps = self._parse_js_requires(file_path, project_path)
                js_requires[rel_path] = deps

            else:
                # 增量场景反推：对于非 Python/JS 文件，尝试从内容中反推依赖
                # 这是一个通用兜底，适用于增量上传的项目中包含其他语言
                try:
                    content = file_path.read_text(encoding='utf-8', errors='ignore')
                    if content:
                        deps = self.extract_dependencies_from_content(rel_path, content)
                        if deps:
                            generic_imports[rel_path] = deps
                except Exception as read_err:
                    logger.warning(f"读取文件内容失败用于依赖分析：{read_err}")

        self._auto_add_dependencies()

        for file_path, dep_paths in py_imports.items():
            for dep in dep_paths:
                self.add_dependency(file_path, dep)

        for file_path, dep_paths in js_requires.items():
            for dep in dep_paths:
                self.add_dependency(file_path, dep)

        for file_path, dep_paths in generic_imports.items():
            for dep in dep_paths:
                self.add_dependency(file_path, dep)

        order = self.get_generation_order()

        logger.info(
            f"已有项目依赖图构建完成: "
            f"{len(self.nodes)} 节点, "
            f"{sum(len(d) for d in self.adjacency.values())} 边 (含 {len(generic_imports)} 通用推导)"
        )

        return {
            "nodes": len(self.nodes),
            "edges": sum(len(d) for d in self.adjacency.values()),
            "order": order
        }

    def _parse_python_imports(self, file_path: Path, project_path: Path) -> List[str]:
        """解析 Python 文件的 import 语句，映射到项目内的文件路径"""
        deps = []
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
        except Exception as e:
            logger.debug(f"读取文件失败 {file_path}：{e}")
            return deps

        patterns = [
            r'from\s+([a-zA-Z_][a-zA-Z0-9_.]*)\s+import',
            r'import\s+([a-zA-Z_][a-zA-Z0-9_.]*)',
        ]

        seen = set()
        for pattern in patterns:
            for match in re.finditer(pattern, content):
                module = match.group(1)
                parts = module.split('.')
                base_path = Path(project_path) / "/".join(parts)
                # 检查包入口文件和模块文件
                init_file_name = self.language_adapter.package_init_filename if self.language_adapter else '__init__.py'
                candidate = str(base_path / init_file_name)
                extensions = self.language_adapter.extensions if self.language_adapter else {'.py'}
                default_ext = list(extensions)[0] if extensions else '.py'
                candidate_py = str(base_path) + default_ext

                for candidate_path in [candidate, candidate_py]:
                    rel = candidate_path.replace(str(project_path) + "/", "")
                    if (project_path / rel).exists() and rel not in seen:
                        deps.append(rel)
                        seen.add(rel)

        return deps

    def _parse_js_requires(self, file_path: Path, project_path: Path) -> List[str]:
        """解析 JS/TS/Vue 文件的 require/import 语句"""
        deps = []
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
        except Exception as e:
            logger.debug(f"读取文件失败 {file_path}：{e}")
            return deps

        patterns = [
            r'import\s+.*?\s+from\s+["\'](\./[^"\']+)["\']',
            r'import\s+.*?\s+from\s+["\'](\.\./[^"\']+)["\']',
            r'require\s*\(\s*["\'](\./[^"\']+)["\']\s*\)',
            r'require\s*\(\s*["\'](\.\./[^"\']+)["\']\s*\)',
        ]

        seen = set()
        for pattern in patterns:
            for match in re.finditer(pattern, content):
                import_path = match.group(1)
                resolved = str((file_path.parent / import_path).resolve())

                try:
                    rel = resolved.replace(str(project_path.resolve()) + "/", "")
                except ValueError:
                    continue

                for ext in ['', '.js', '.ts', '.jsx', '.tsx', '.vue', '/index.js', '/index.ts']:
                    candidate = rel + ext
                    if (project_path / candidate).exists() and candidate not in seen:
                        deps.append(candidate)
                        seen.add(candidate)
                        break

        return deps

    def extract_dependencies_from_content(self, file_path: str, content: str) -> List[str]:
        """
        从文件内容中提取项目内的依赖关系（增量场景反推）

        Args:
            file_path: 当前文件路径
            content: 文件内容

        Returns:
            提取到的项目内其他文件的路径列表
        """
        deps = []

        suffix = Path(file_path).suffix.lower()

        # 使用已有的解析逻辑进行提取
        patterns = []
        if suffix == '.py':
            patterns = [
                r'from\s+([a-zA-Z_][a-zA-Z0-9_.]*)\s+import',
                r'import\s+([a-zA-Z_][a-zA-Z0-9_.]*)',
            ]
        elif suffix in ('.js', '.ts', '.jsx', '.tsx', '.vue'):
            patterns = [
                r'import\s+.*?\s+from\s+["\'](\./[^"\']+)["\']',
                r'import\s+.*?\s+from\s+["\'](\.\./[^"\']+)["\']',
                r'require\s*\(\s*["\'](\./[^"\']+)["\']\s*\)',
                r'require\s*\(\s*["\'](\.\./[^"\']+)["\']\s*\)',
            ]

        # 通用匹配：易语言、C#、Go、Rust 等（通过关键字匹配文件路径）
        # 这里做一个泛化处理：查找所有存在于当前 nodes 中的路径关键字
        if not patterns and self.nodes:
            # 提取路径中的文件名或模块名进行反向匹配
            possible_names = set()
            for node_path in self.nodes.keys():
                possible_names.add(Path(node_path).stem)
                possible_names.add(Path(node_path).name)

            for name in possible_names:
                # 使用边界匹配避免子串误杀
                if re.search(r'\b' + re.escape(name) + r'\b', content):
                    deps.append(name)
            return list(set(deps))

        # 执行具体语言的解析
        if not patterns:
            return []

        def _path_segments_contain(path: str, part: str) -> bool:
            """检查 path 的某一段（按 . 或 / 分割）是否等于 part

            避免子串误杀：'api' 不会匹配 'api_config'，但会匹配 'api/users.py'。
            """
            segments = re.split(r'[./\\]', path)
            return part in segments

        for pattern in patterns:
            for match in re.finditer(pattern, content):
                module = match.group(1)
                # 尝试将模块名映射到现有文件路径
                parts = module.replace('/', '.').split('.')

                # 使用路径段匹配（避免子串误杀）
                for node_path in self.nodes.keys():
                    if any(_path_segments_contain(node_path, p) for p in parts):
                        if node_path != file_path:
                            deps.append(node_path)

        return list(set(deps))

    def update_node_dependencies(self, file_path: str, new_deps: List[str]):
        """
        更新某个文件的依赖关系（用于增量生成场景）

        Args:
            file_path: 目标文件路径
            new_deps: 新发现的依赖文件列表
        """
        # 清除该文件的旧依赖
        self.adjacency[file_path].clear()
        if file_path in self.nodes:
            self.nodes[file_path].dependencies = []

        # 清理反向依赖中指向该文件的边（adjacency）
        for src in self.adjacency:
            self.adjacency[src].discard(file_path)

        # 清理 reverse_adjacency 中所有指向 file_path 的边
        # 修复：之前 v5.12.0 之前只清理了 adjacency 没清理 reverse_adjacency
        # 导致反向图逐渐累积脏数据，get_affected_files() 返回错误结果
        for src in list(self.reverse_adjacency.keys()):
            self.reverse_adjacency[src].discard(file_path)
            if not self.reverse_adjacency[src]:
                del self.reverse_adjacency[src]

        # 添加新依赖
        for dep in new_deps:
            self.add_dependency(file_path, dep)

    def validate_completeness(self) -> List[Dict[str, str]]:
        """
        验证依赖图完整性：检查被引用的模块是否在图中

        Returns:
            问题列表，每个问题包含 type, file, message, suggestion
        """
        issues = []

        for path, node in self.nodes.items():
            # 检查所有依赖是否都在图中
            for dep in self.adjacency.get(path, set()):
                if dep not in self.nodes:
                    issues.append({
                        "type": "missing_dependency",
                        "file": path,
                        "message": f"依赖的文件不在依赖图中: {dep}",
                        "suggestion": f"将 {dep} 添加到 file_plan"
                    })

        return issues

    def get_missing_files(self) -> List[str]:
        """获取缺失的文件列表（被依赖但不在图中的文件）"""
        missing = set()

        for path in self.nodes:
            for dep in self.adjacency.get(path, set()):
                if dep not in self.nodes:
                    missing.add(dep)

        return list(missing)

    def add_missing_files(self, architecture: Dict[str, Any]) -> Dict[str, Any]:
        """
        补充缺失的文件到架构和依赖图

        Args:
            architecture: 原始架构设计

        Returns:
            更新后的架构设计
        """
        missing = self.get_missing_files()
        if not missing:
            return architecture

        file_plan = architecture.get("file_plan", [])
        planned_paths = {f["path"] for f in file_plan}

        added_count = 0
        for file_path in missing:
            if file_path not in planned_paths:
                # 推断文件描述和优先级
                description = self._infer_file_description(file_path)
                priority = self._infer_file_priority(file_path)

                file_plan.append({
                    "path": file_path,
                    "description": description,
                    "priority": priority,
                    "imports": []
                })

                # 添加到依赖图
                self.add_file(file_path, priority=priority, description=description)
                added_count += 1

                logger.info(f"自动补充缺失文件: {file_plan}")

        if added_count > 0:
            architecture["file_plan"] = file_plan
            logger.info(f"共补充 {added_count} 个缺失文件")

        return architecture

    def _infer_file_description(self, file_path: str) -> str:
        """推断文件描述"""
        # 检查是否是包入口文件
        if self.language_adapter and self.language_adapter.package_init_filename:
            init_file_name = self.language_adapter.package_init_filename
            if file_path.endswith(init_file_name):
                pkg = file_path.rsplit('/', 1)[0] if '/' in file_path else ''
                return f"{pkg} 包初始化文件"
        elif 'database' in file_path.lower():
            return "数据库连接配置"
        elif 'config' in file_path.lower():
            return "配置文件"
        elif 'schema' in file_path.lower():
            return "数据模式定义"
        elif 'core' in file_path.lower():
            return "核心模块"
        else:
            return "自动补充的模块文件"

    def _infer_file_priority(self, file_path: str) -> int:
        """推断文件优先级（1-5，越小越优先）

        重要：__init__.py 必须为 priority=5（最后生成），
        因为工程师生成 __init__.py 时需要先读取同包内其他文件。
        这与 ensure_package_files() 中 priority=5 一致。
        """
        # 检查是否是包入口文件
        if self.language_adapter and self.language_adapter.package_init_filename:
            init_file_name = self.language_adapter.package_init_filename
            if file_path.endswith(init_file_name):
                return 5  # 最后生成，让工程师读到实际导出
        elif '__init__' in Path(file_path).name:
            return 5

        if 'database' in file_path.lower() or 'config' in file_path.lower():
            return 1
        elif 'core' in file_path.lower():
            return 1
        elif 'model' in file_path.lower():
            return 2
        elif 'service' in file_path.lower():
            return 3
        else:
            return 3
