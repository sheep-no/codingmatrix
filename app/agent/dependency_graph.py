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
from typing import Optional, Dict, Any, List, Set, Tuple
from pathlib import Path
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)

# 扫描已有项目时跳过的目录
SKIP_DIRS = {
    '__pycache__', 'node_modules', '.git', 'venv', '.venv',
    'dist', 'build', '.next', 'coverage', '.pytest_cache',
    'playwright-report', 'test-results', '.turbo'
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

    # ==================== 预定义的依赖规则 ====================

    # 文件类型到依赖类型的映射
    DEPENDENCY_RULES: Dict[str, List[str]] = {
        # 基础设施层 - 最先生成
        "config": [],
        "env": [],
        "dockerfile": [],
        "service_config": ["env"],  # v4.8.0: 服务连接配置依赖 env
        "docker_compose": ["env", "config"],  # v4.8.0: docker-compose 依赖 env 和 config

        # 数据库相关
        "database": ["config"],
        "model": ["database", "config"],
        "repository": ["model"],
        "migration": ["model", "database"],

        # 类型和工具
        "types": ["config"],
        "utils": ["config", "env"],  # v4.8.0: utils 可能读取 env 配置
        "constants": ["config"],

        # 业务层 - v4.8.0: service 依赖 service_config 和 env
        "service": ["model", "repository", "types", "utils", "service_config", "env"],
        "schema": ["model", "types"],

        # API 层
        "api": ["service", "schema", "types"],
        "view": ["service", "schema", "types"],
        "controller": ["service", "schema", "types"],
        "router": ["service", "schema", "types"],

        # 前端
        "frontend_types": ["api"],
        "frontend_api": ["frontend_types"],
        "frontend_component": ["frontend_api", "frontend_types"],
        "frontend_page": ["frontend_component"],
        "frontend_style": [],

        # 测试
        "test": ["model", "service", "api"],

        # 文档
        "readme": [],
        "docs": [],
    }

    # 文件路径到类型的映射规则
    PATH_TYPE_RULES: List[Tuple[str, str]] = [
        # 配置
        ("requirements.txt", "config"),
        ("package.json", "config"),
        (".env", "env"),
        (".env.example", "env"),
        (".env.local", "env"),
        ("Dockerfile", "dockerfile"),
        ("docker-compose.yml", "docker_compose"),  # v4.8.0: 独立类型
        ("docker-compose.yaml", "docker_compose"),
        ("pyproject.toml", "config"),
        ("setup.py", "config"),
        ("Makefile", "config"),

        # v4.8.0: 服务连接配置
        ("redis_config.py", "service_config"),
        ("redis_connection.py", "service_config"),
        ("database_config.py", "service_config"),
        ("db_connection.py", "service_config"),
        ("mongodb_config.py", "service_config"),
        ("rabbitmq_config.py", "service_config"),
        ("elasticsearch_config.py", "service_config"),
        ("connections.py", "service_config"),
        ("connections/", "service_config"),
        ("connectors/", "service_config"),

        # Python 配置
        ("config.py", "config"),
        ("settings.py", "config"),
        ("config/", "config"),
        ("settings/", "config"),

        # 数据库
        ("database.py", "database"),
        ("database/", "database"),
        ("db.py", "database"),

        # 模型
        ("models.py", "model"),
        ("models/", "model"),
        ("model/", "model"),
        ("entities/", "model"),
        ("entity/", "model"),

        # Repository
        ("repositories/", "repository"),
        ("repository/", "repository"),
        ("repos/", "repository"),
        ("dao/", "repository"),

        # 类型
        ("types.py", "types"),
        ("types/", "types"),
        ("schemas.py", "types"),
        ("schemas/", "schema"),
        ("dto/", "schema"),

        # 工具
        ("utils/", "utils"),
        ("utils.py", "utils"),
        ("helpers/", "utils"),
        ("helpers.py", "utils"),
        ("constants.py", "constants"),
        ("constants/", "constants"),

        # 服务
        ("services/", "service"),
        ("service/", "service"),
        ("business/", "service"),

        # API/View/Controller
        ("api/", "api"),
        ("apis/", "api"),
        ("views/", "view"),
        ("view/", "view"),
        ("controllers/", "controller"),
        ("controller/", "controller"),
        ("routers/", "router"),
        ("router/", "router"),
        ("routes/", "router"),

        # 前端
        ("src/types/", "frontend_types"),
        ("src/api/", "frontend_api"),
        ("src/apis/", "frontend_api"),
        ("src/components/", "frontend_component"),
        ("src/component/", "frontend_component"),
        ("src/pages/", "frontend_page"),
        ("src/page/", "frontend_page"),
        ("src/views/", "frontend_page"),
        ("src/styles/", "frontend_style"),
        ("src/assets/", "frontend_style"),

        # 迁移
        ("migrations/", "migration"),
        ("alembic/", "migration"),

        # 测试
        ("tests/", "test"),
        ("test/", "test"),
        ("__tests__/", "test"),

        # 文档
        ("README.md", "readme"),
        ("docs/", "docs"),
    ]

    def __init__(self):
        self.nodes: Dict[str, FileNode] = {}
        self.adjacency: Dict[str, Set[str]] = defaultdict(set)  # file -> set of files it depends on
        self.reverse_adjacency: Dict[str, Set[str]] = defaultdict(set)  # file -> set of files that depend on it

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
            logger.warning(f"添加依赖时节点不存在: {file_path}")
            return

        if depends_on not in self.nodes:
            logger.warning(f"依赖目标节点不存在: {depends_on} (被 {file_path} 依赖)")

        self.nodes[file_path].dependencies.append(depends_on)
        self.adjacency[file_path].add(depends_on)
        self.reverse_adjacency[depends_on].add(file_path)

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
        """从架构设计结果构建依赖图"""
        file_plan = architecture.get("file_plan", [])

        for file_info in file_plan:
            path = file_info.get("path", "")
            description = file_info.get("description", "")
            priority = file_info.get("priority", 3)

            if not path:
                continue

            self.add_file(path, priority=priority, description=description)

        # 根据类型规则自动添加依赖
        self._auto_add_dependencies()

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

        for path, node in self.nodes.items():
            dep_types = self.DEPENDENCY_RULES.get(node.file_type, [])
            for dep_type in dep_types:
                for other_path in type_to_files.get(dep_type, []):
                    if other_path != path:
                        self.add_dependency(path, other_path)

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
            # 找到优先级最低的边并移除
            min_priority = float('inf')
            edge_to_remove = None

            for i in range(len(cycle) - 1):
                from_node = cycle[i]
                to_node = cycle[i + 1]
                priority = self.nodes[from_node].priority if from_node in self.nodes else 99

                if priority < min_priority:
                    min_priority = priority
                    edge_to_remove = (from_node, to_node)

            if edge_to_remove:
                from_node, to_node = edge_to_remove
                self.adjacency[from_node].discard(to_node)
                self.reverse_adjacency[to_node].discard(from_node)
                if from_node in self.nodes:
                    if to_node in self.nodes[from_node].dependencies:
                        self.nodes[from_node].dependencies.remove(to_node)
                logger.info(f"打破循环依赖: {from_node} -> {to_node}")

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

    def get_context_for_file(self, file_path: str, generated_files: Dict[str, str], max_context_bytes: int = 3000) -> str:
        """
        获取某个文件生成时应该注入的上下文

        动态分配上下文预算：
        - 核心依赖（models, config）分配更多字节
        - 次要依赖分配较少字节
        - 总上下文不超过 max_context_bytes
        """
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

            preview = content[:budget]
            truncated = len(content) > budget
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
        for pattern, file_type in self.PATH_TYPE_RULES:
            if path == pattern or path.startswith(pattern) or path.endswith(pattern):
                return file_type

        # 根据扩展名推断
        ext = Path(path).suffix.lower()
        ext_map = {
            '.py': 'model',  # 默认 Python 文件为 model 类型
            '.js': 'frontend_component',
            '.ts': 'frontend_types',
            '.vue': 'frontend_component',
            '.jsx': 'frontend_component',
            '.tsx': 'frontend_component',
            '.html': 'frontend_page',
            '.css': 'frontend_style',
            '.scss': 'frontend_style',
            '.md': 'docs',
            '.json': 'config',
            '.yaml': 'config',
            '.yml': 'config',
            '.toml': 'config',
            '.sql': 'migration',
            '.env': 'env',
            '.sh': 'config',
            '.dockerfile': 'dockerfile',
            '.txt': 'config',
        }
        return ext_map.get(ext, 'utils')

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
        import re
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
        return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

    def build_from_existing_project(self, project_path: Path) -> Dict[str, Any]:
        """
        从已有项目目录构建依赖图（解析源代码 import/require 语句）

        用于增量修改场景：用户上传项目后，构建真实依赖关系

        v4.7.0 增强：附带阴影依赖扫描结果（只记录不阻断）
        """
        result = self._build_graph_from_project(project_path)

        shadow_deps = self.scan_shadow_dependencies(project_path)
        result["shadow_dependencies"] = shadow_deps

        return result

    def _build_graph_from_project(self, project_path: Path) -> Dict[str, Any]:
        """核心构建逻辑（原有 build_from_existing_project 内容）"""
        self.nodes.clear()
        self.adjacency.clear()
        self.reverse_adjacency.clear()

        py_imports: Dict[str, List[str]] = {}
        js_requires: Dict[str, List[str]] = {}

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

        self._auto_add_dependencies()

        for file_path, dep_paths in py_imports.items():
            for dep in dep_paths:
                if dep in self.nodes and dep != file_path:
                    self.add_dependency(file_path, dep)

        for file_path, dep_paths in js_requires.items():
            for dep in dep_paths:
                if dep in self.nodes and dep != file_path:
                    self.add_dependency(file_path, dep)

        order = self.get_generation_order()

        logger.info(
            f"已有项目依赖图构建完成: "
            f"{len(self.nodes)} 节点, "
            f"{sum(len(d) for d in self.adjacency.values())} 边"
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
        except Exception:
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
                candidate = str(base_path / "__init__.py")
                candidate_py = str(base_path) + ".py"

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
        except Exception:
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

    def scan_shadow_dependencies(self, project_path: Path) -> Dict[str, List[str]]:
        """
        阴影依赖扫描：发现隐式依赖（只记录不阻断）

        扫描以下模式：
        - eval/exec 动态代码执行
        - 动态 import (importlib.import_module)
        - 环境变量依赖 (os.environ/os.getenv)
        - 动态加载 (require.context, webpack dynamic import)
        - 反射调用 (__import__, getattr 动态模块)

        Returns:
            {file_path: [发现的隐式依赖模式描述]}
        """
        shadow_deps: Dict[str, List[str]] = {}

        patterns = {
            'eval_exec': r'\beval\s*\(|\bexec\s*\(',
            'dynamic_import': r'importlib\.import_module|__import__\s*\(',
            'env_dependency': r'os\.environ\b|os\.getenv\s*\(',
            'dynamic_require': r'require\.context|import\s*\(',
            'getattr_dynamic': r'getattr\s*\([^,]+,\s*["\']',
        }

        for file_path in project_path.rglob("*"):
            if any(part in SKIP_DIRS for part in file_path.parts):
                continue
            if not file_path.is_file():
                continue

            suffix = file_path.suffix.lower()
            if suffix not in ('.py', '.js', '.ts', '.jsx', '.tsx', '.vue'):
                continue

            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
            except Exception:
                continue

            rel_path = str(file_path.relative_to(project_path))
            found = []

            for pattern_name, regex in patterns.items():
                if re.search(regex, content):
                    found.append(pattern_name)

            if found:
                shadow_deps[rel_path] = found

        if shadow_deps:
            logger.info(f"阴影依赖扫描发现 {len(shadow_deps)} 个文件含有隐式依赖（仅记录）")
            for path, patterns_found in shadow_deps.items():
                logger.info(f"  {path}: {', '.join(patterns_found)}")

        return shadow_deps
