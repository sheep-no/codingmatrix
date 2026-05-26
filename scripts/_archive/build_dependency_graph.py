"""
静态依赖图谱生成器

扫描代码库，分析模块导入、函数调用链、Schema引用、模型关联，
生成 data/dependency_graph.json 供 Agent 在修改代码时查询受影响文件。

用法:
    python scripts/build_dependency_graph.py [--target app/] [--output data/dependency_graph.json]
"""

import ast
import json
import os
import sys
import logging
from pathlib import Path
from typing import Dict, List, Set, Optional
from dataclasses import dataclass, field, asdict
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class FunctionInfo:
    """函数信息"""
    name: str
    line: int
    args: List[str]
    is_async: bool
    decorators: List[str]


@dataclass
class ClassInfo:
    """类信息"""
    name: str
    line: int
    base_classes: List[str]
    methods: List[FunctionInfo] = field(default_factory=list)


@dataclass
class FileInfo:
    """文件信息"""
    path: str
    imports: List[str] = field(default_factory=list)
    from_imports: Dict[str, List[str]] = field(default_factory=dict)
    functions: List[FunctionInfo] = field(default_factory=list)
    classes: List[ClassInfo] = field(default_factory=list)
    called_functions: List[str] = field(default_factory=list)
    referenced_models: List[str] = field(default_factory=list)
    referenced_schemas: List[str] = field(default_factory=list)
    routes: List[Dict] = field(default_factory=list)


@dataclass
class DependencyEdge:
    """依赖边"""
    source: str
    target: str
    type: str  # import, call, reference, route
    detail: str = ""


class DependencyAnalyzer(ast.NodeVisitor):
    """AST 依赖分析器"""

    def __init__(self, file_path: str, source: str):
        self.file_path = file_path
        self.source = source
        self.tree = ast.parse(source, filename=file_path)
        self.info = FileInfo(path=file_path)

    def analyze(self) -> FileInfo:
        """执行分析"""
        self.visit(self.tree)
        return self.info

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.info.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            names = [alias.name for alias in node.names]
            self.info.from_imports[node.module] = names

            # 检测 Schema 引用
            if 'schema' in node.module.lower() or 'Schema' in node.module:
                self.info.referenced_schemas.extend(names)

            # 检测 Model 引用
            if 'model' in node.module.lower() or 'Model' in node.module:
                self.info.referenced_models.extend(names)

        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        func_info = FunctionInfo(
            name=node.name,
            line=node.lineno,
            args=[arg.arg for arg in node.args.args],
            is_async=False,
            decorators=[self._get_decorator_name(d) for d in node.decorator_list]
        )
        self.info.functions.append(func_info)

        # 检测路由装饰器
        for dec in node.decorator_list:
            dec_name = self._get_decorator_name(dec)
            if dec_name in ('get', 'post', 'put', 'delete', 'patch', 'router.get', 'router.post',
                           'router.put', 'router.delete', 'router.patch'):
                route_info = self._extract_route_info(dec_name, node)
                if route_info:
                    self.info.routes.append(route_info)

        # 收集函数调用
        self._collect_calls(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        func_info = FunctionInfo(
            name=node.name,
            line=node.lineno,
            args=[arg.arg for arg in node.args.args],
            is_async=True,
            decorators=[self._get_decorator_name(d) for d in node.decorator_list]
        )
        self.info.functions.append(func_info)

        # 检测路由装饰器
        for dec in node.decorator_list:
            dec_name = self._get_decorator_name(dec)
            if dec_name in ('get', 'post', 'put', 'delete', 'patch', 'router.get', 'router.post',
                           'router.put', 'router.delete', 'router.patch'):
                route_info = self._extract_route_info(dec_name, node)
                if route_info:
                    self.info.routes.append(route_info)

        self._collect_calls(node)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        class_info = ClassInfo(
            name=node.name,
            line=node.lineno,
            base_classes=[self._get_name(b) for b in node.bases]
        )
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_info = FunctionInfo(
                    name=item.name,
                    line=item.lineno,
                    args=[arg.arg for arg in item.args.args],
                    is_async=isinstance(item, ast.AsyncFunctionDef),
                    decorators=[self._get_decorator_name(d) for d in item.decorator_list]
                )
                class_info.methods.append(method_info)
                self._collect_calls(item)

        self.info.classes.append(class_info)
        self.generic_visit(node)

    def _collect_calls(self, node: ast.AST):
        """收集函数调用"""
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                call_name = self._get_call_name(child)
                if call_name:
                    self.info.called_functions.append(call_name)

    def _get_decorator_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_attribute_chain(node)
        elif isinstance(node, ast.Call):
            return self._get_decorator_name(node.func)
        return ""

    def _get_attribute_chain(self, node: ast.Attribute) -> str:
        parts = []
        current = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return '.'.join(reversed(parts))

    def _get_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_attribute_chain(node)
        return ""

    def _get_call_name(self, node: ast.Call) -> str:
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            return self._get_attribute_chain(node.func)
        return ""

    def _extract_route_info(self, decorator: str, node) -> Optional[Dict]:
        """提取路由信息"""
        # 查找路径参数
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                dec_name = self._get_decorator_name(child.func)
                if dec_name == decorator and child.args:
                    path = ""
                    if isinstance(child.args[0], ast.Constant):
                        path = child.args[0].value
                    return {
                        "method": decorator.split('.')[-1].upper() if '.' in decorator else decorator.upper(),
                        "path": path,
                        "function": node.name,
                        "line": node.lineno
                    }
        return None


class DependencyGraphBuilder:
    """依赖图谱构建器"""

    def __init__(self, target_dir: str):
        self.target_dir = Path(target_dir)
        self.file_infos: Dict[str, FileInfo] = {}
        self.edges: List[DependencyEdge] = []
        self.module_map: Dict[str, str] = {}  # module_name -> file_path

    def build(self) -> Dict:
        """构建完整依赖图谱"""
        logger.info(f"扫描目录: {self.target_dir}")

        # 第一步：收集所有 Python 文件
        py_files = list(self.target_dir.rglob('*.py'))
        logger.info(f"发现 {len(py_files)} 个 Python 文件")

        # 第二步：解析每个文件
        for py_file in py_files:
            self._analyze_file(py_file)

        # 第三步：构建模块映射
        self._build_module_map()

        # 第四步：构建依赖边
        self._build_edges()

        # 第五步：生成输出
        return self._generate_output()

    def _analyze_file(self, file_path: Path):
        """分析单个文件"""
        try:
            source = file_path.read_text(encoding='utf-8')
            analyzer = DependencyAnalyzer(str(file_path), source)
            info = analyzer.analyze()
            self.file_infos[str(file_path)] = info
        except SyntaxError as e:
            logger.warning(f"语法错误，跳过: {file_path} ({e})")
        except Exception as e:
            logger.warning(f"分析失败: {file_path} ({e})")

    def _build_module_map(self):
        """构建模块名到文件路径的映射"""
        for file_path in self.file_infos:
            rel_path = Path(file_path).relative_to(self.target_dir)
            module_name = str(rel_path.with_suffix('')).replace(os.sep, '.')
            self.module_map[module_name] = file_path

            # 也映射 __init__.py 的父目录
            if file_path.endswith('__init__.py'):
                parent_module = str(rel_path.parent).replace(os.sep, '.') if rel_path.parent != Path('.') else ''
                if parent_module:
                    self.module_map[parent_module] = file_path

    def _build_edges(self):
        """构建依赖边"""
        for file_path, info in self.file_infos.items():
            rel_path = str(Path(file_path).relative_to(self.target_dir))

            # 导入依赖
            for imp in info.imports:
                target = self._resolve_module(imp)
                if target:
                    self.edges.append(DependencyEdge(
                        source=rel_path, target=target, type="import", detail=f"import {imp}"
                    ))

            for module, names in info.from_imports.items():
                target = self._resolve_module(module)
                if target:
                    self.edges.append(DependencyEdge(
                        source=rel_path, target=target, type="import",
                        detail=f"from {module} import {', '.join(names)}"
                    ))

            # 模型引用
            for model in info.referenced_models:
                self.edges.append(DependencyEdge(
                    source=rel_path, target=f"models/{model}", type="reference",
                    detail=f"references model {model}"
                ))

            # Schema 引用
            for schema in info.referenced_schemas:
                self.edges.append(DependencyEdge(
                    source=rel_path, target=f"schema/{schema}", type="reference",
                    detail=f"references schema {schema}"
                ))

            # 路由
            for route in info.routes:
                self.edges.append(DependencyEdge(
                    source=rel_path, target=f"api:{route['method']} {route['path']}",
                    type="route", detail=f"route {route['method']} {route['path']}"
                ))

    def _resolve_module(self, module_name: str) -> Optional[str]:
        """解析模块名到相对路径"""
        if module_name in self.module_map:
            return str(Path(self.module_map[module_name]).relative_to(self.target_dir))

        # 尝试带 __init__ 的变体
        for key, value in self.module_map.items():
            if key.startswith(module_name):
                return str(Path(value).relative_to(self.target_dir))

        return None

    def _generate_output(self) -> Dict:
        """生成输出 JSON"""
        # 文件节点
        files = {}
        for file_path, info in self.file_infos.items():
            rel_path = str(Path(file_path).relative_to(self.target_dir))
            files[rel_path] = {
                "functions": [asdict(f) for f in info.functions],
                "classes": [self._class_to_dict(c) for c in info.classes],
                "routes": info.routes,
                "import_count": len(info.imports) + sum(len(v) for v in info.from_imports.values()),
                "model_refs": info.referenced_models,
                "schema_refs": info.referenced_schemas,
            }

        # 依赖边
        edges = []
        for edge in self.edges:
            edges.append({
                "source": edge.source,
                "target": edge.target,
                "type": edge.type,
                "detail": edge.detail,
            })

        # 反向索引：文件被哪些文件依赖
        reverse_index = defaultdict(list)
        for edge in self.edges:
            if edge.type == "import":
                reverse_index[edge.target].append(edge.source)

        # 路由索引
        route_index = {}
        for edge in self.edges:
            if edge.type == "route":
                route_index[edge.target] = edge.source

        return {
            "version": "1.0",
            "target": str(self.target_dir),
            "file_count": len(files),
            "edge_count": len(edges),
            "files": files,
            "edges": edges,
            "reverse_index": dict(reverse_index),
            "route_index": route_index,
        }

    def _class_to_dict(self, c: ClassInfo) -> Dict:
        return {
            "name": c.name,
            "line": c.line,
            "base_classes": c.base_classes,
            "method_count": len(c.methods),
        }


def main():
    import argparse
    parser = argparse.ArgumentParser(description='生成代码依赖图谱')
    parser.add_argument('--target', default='app', help='目标目录 (默认: app)')
    parser.add_argument('--output', default='data/dependency_graph.json', help='输出文件')
    args = parser.parse_args()

    target = Path(args.target)
    if not target.exists():
        logger.error(f"目标目录不存在: {target}")
        sys.exit(1)

    builder = DependencyGraphBuilder(str(target))
    graph = builder.build()

    output_path = Path(args.output)
    output_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding='utf-8')

    logger.info(f"依赖图谱已生成: {output_path}")
    logger.info(f"  文件数: {graph['file_count']}")
    logger.info(f"  依赖边: {graph['edge_count']}")
    logger.info(f"  路由数: {len(graph['route_index'])}")


if __name__ == '__main__':
    main()
