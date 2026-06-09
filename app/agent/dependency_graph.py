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

logger = logging.getLogger(__name__)


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

    def add_file(self, path: str, file_type: Optional[str] = None, priority: int = 3, description: str = ""):
        """添加文件节点"""
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

        # 0. 自动设置 GenericLanguageAdapter 的 file_plan_data
        # 这样 _import_to_file_path 就可以正确解析任何语言的 import
        if self.language_adapter and hasattr(self.language_adapter, 'set_file_plan_data'):
            self.language_adapter.set_file_plan_data(file_plan)

        # 1. 先添加所有文件节点（确保所有文件都在图中）
        for file_info in file_plan:
            path = file_info.get("path", "")
            description = file_info.get("description", "")
            priority = file_info.get("priority", 3)

            if not path:
                continue

            self.add_file(path, priority=priority, description=description)

        # 2. 再处理依赖关系（此时所有文件都在图中）
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
            if isinstance(imports, list):
                for imp in imports:
                    if imp and imp != path:
                        # 转换 import 路径为文件路径
                        dep_path = self._import_to_file_path(imp)
                        if dep_path:
                            self.add_dependency(path, dep_path)

        # 3. 硬编码规则作为兜底（补充 LLM 可能遗漏的依赖）
        self._auto_add_dependencies()

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

            # 返回第一个候选（后续会补充）
            if candidates:
                return candidates[0]

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

        # 尝试返回最可能的路径（后续会补充）
        default_ext = list(extensions)[0] if extensions else '.py'
        return pkg_path + default_ext

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

    def _auto_add_dependencies(self):
        """根据文件类型自动添加依赖（优化版：O(n*k) 而非 O(n²)）"""
        type_to_files: Dict[str, List[str]] = defaultdict(list)
        for path, node in self.nodes.items():
            type_to_files[node.file_type].append(path)

        logger.info(f"_auto_add_dependencies: 文件类型分布 = {dict(type_to_files)}")
        logger.info(f"_auto_add_dependencies: DEPENDENCY_RULES = {dict(self.DEPENDENCY_RULES)}")

        added_by_rules = 0
        for path, node in self.nodes.items():
            dep_types = self.DEPENDENCY_RULES.get(node.file_type, [])
            for dep_type in dep_types:
                # 只为实际存在的文件类型添加依赖
                if dep_type in type_to_files:
                    for other_path in type_to_files.get(dep_type, []):
                        if other_path != path:
                            self.add_dependency(path, other_path)
                            added_by_rules += 1

        logger.info(f"_auto_add_dependencies: 硬编码规则添加了 {added_by_rules} 条依赖")

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

    def get_context_for_file(self, file_path: str, generated_files: Dict[str, str], max_context_bytes: int = 0, model_context_length: int = 0) -> str:
        """
        获取某个文件生成时应该注入的上下文

        动态分配上下文预算：
        - 核心依赖（models, config）分配更多字节
        - 次要依赖分配较少字节
        - 总上下文不超过 max_context_bytes
        - max_context_bytes=0 时根据 model_context_length 自动计算
        """
        if max_context_bytes <= 0:
            ctx_len = model_context_length if model_context_length > 0 else 32768
            max_context_bytes = get_context_budget(ctx_len)

        dependencies = self.adjacency.get(file_path, set())
        if not dependencies:
            return ""

        # 按依赖重要性排序（优先级低的 = 更基础 = 更重要）
        sorted_deps = sorted(
            [d for d in dependencies if d in generated_files],
            key=lambda d: self.nodes[d].priority if d in self.nodes else 99
        )
        if not sorted_deps:
            return ""

        # 动态分配预算：核心依赖获得更多字节
        total_deps = len(sorted_deps)
        parts = []
        remaining_budget = max_context_bytes

        for i, dep_path in enumerate(sorted_deps):
            content = generated_files[dep_path]
            node = self.nodes.get(dep_path)
            is_core = node and node.priority <= 2 if node else False

            # 核心依赖分配 60% 剩余预算，非核心分配均分剩余
            if is_core and total_deps > 1:
                budget = int(remaining_budget * 0.6)
            else:
                budget = max(200, remaining_budget // max(1, total_deps - i))

            signatures = extract_signatures(dep_path, content)
            preview = signatures if signatures else content[:budget]
            truncated = not signatures and len(content) > budget
            parts.append(
                f"## 依赖文件: {dep_path}\n```{preview}{'...' if truncated else ''}```\n"
            )
            remaining_budget -= len(preview) + 50  # 50 for formatting overhead
            if remaining_budget <= 0:
                break

        return "\n".join(parts) if parts else ""

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
            "nodes": {path: {"type": node.file_type, "priority": node.priority} for path, node in self.nodes.items()},
            "dependencies": {k: list(v) for k, v in self.adjacency.items() if v},
            "generation_order": self.get_generation_order()
        }

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
