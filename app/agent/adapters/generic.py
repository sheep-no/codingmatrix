"""
GenericLanguageAdapter - 通用语言适配器

适用于冷门语言或未知语言。不解析代码语法，而是：
1. 依赖 Architect 输出的 file_plan 中的 file_type 和 imports 字段
2. 使用简单的文件扩展名映射
3. 作为所有语言的 fallback

核心原则：让 LLM（Architect）在设计阶段就声明依赖关系，而不是事后解析代码
"""

import re
from typing import Dict, List, Optional, Set
from pathlib import Path

from .language_adapter import (
    LanguageAdapter, LanguageAdapterRegistry,
    ImportInfo, SymbolDefinition
)


class GenericLanguageAdapter(LanguageAdapter):
    """
    通用语言适配器

    设计哲学：
    - 不假设任何语言的语法
    - 依赖 file_plan 的结构化数据
    - 对于 file_plan 中没有的信息，使用 LLM 推断
    """

    language = "generic"
    extensions = []  # 通用适配器没有固定扩展名
    package_init_filename = ""  # 通用适配器不假设包入口文件

    # 常见文件类型映射（跨语言通用）
    COMMON_FILE_PATTERNS = {
        # 配置文件
        "Makefile": "config",
        "CMakeLists.txt": "config",
        "Cargo.toml": "config",
        "go.mod": "config",
        "go.sum": "config",
        "pom.xml": "config",
        "build.gradle": "config",
        "build.sbt": "config",
        "Gemfile": "config",
        "composer.json": "config",
        "pubspec.yaml": "config",
        "mix.exs": "config",
        "Package.swift": "config",
        ".env": "env",
        ".env.example": "env",
        "docker-compose.yml": "docker_compose",
        "Dockerfile": "dockerfile",

        # 文档
        "README.md": "readme",
        "README": "readme",
        "LICENSE": "docs",
        "CHANGELOG": "docs",
    }

    # 目录名 → 文件类型（跨语言通用）
    COMMON_DIR_PATTERNS = {
        "src": "source",
        "lib": "library",
        "test": "test",
        "tests": "test",
        "spec": "test",
        "docs": "docs",
        "doc": "docs",
        "examples": "example",
        "example": "example",
        "cmd": "entrypoint",
        "internal": "internal",
        "pkg": "package",
        "public": "static",
        "static": "static",
        "assets": "assets",
        "config": "config",
        "configs": "config",
        "settings": "config",
    }

    # file_plan 数据缓存（由 build_from_file_plan 设置）
    _file_plan_data: Dict[str, Dict] = {}

    def set_file_plan_data(self, file_plan: List[Dict]):
        """
        设置 file_plan 数据

        Args:
            file_plan: Architect 输出的文件计划列表，每个元素包含：
                - path: 文件路径
                - description: 文件描述
                - file_type: 文件类型（可选）
                - imports: 导入列表（可选）
        """
        self._file_plan_data = {}
        for item in file_plan:
            path = item.get("path", "")
            if path:
                self._file_plan_data[path] = item

    def parse_imports(self, content: str, file_path: str = "") -> List[ImportInfo]:
        """
        解析导入语句

        对于通用适配器，不尝试解析代码语法。
        返回 file_plan 中声明的 imports。
        """
        # 优先使用 file_plan 中的数据
        if file_path and file_path in self._file_plan_data:
            plan = self._file_plan_data[file_path]
            return self._parse_plan_imports(plan.get("imports", []))

        # 作为 fallback，尝试简单的通用模式匹配
        return self._guess_imports(content)

    def _parse_plan_imports(self, imports: List) -> List[ImportInfo]:
        """解析 file_plan 中的 imports 字段"""
        result = []

        for imp in imports:
            if isinstance(imp, str):
                # 简单字符串形式: "app.models"
                result.append(ImportInfo(
                    module=imp,
                    symbols=[],
                    is_relative=imp.startswith('.'),
                ))
            elif isinstance(imp, dict):
                # 结构化形式: {"module": "app.models", "symbols": ["User"]}
                result.append(ImportInfo(
                    module=imp.get("module", ""),
                    symbols=imp.get("symbols", []),
                    is_relative=imp.get("is_relative", False),
                ))

        return result

    def _guess_imports(self, content: str) -> List[ImportInfo]:
        """
        尝试猜测导入（通用模式）

        这是一个非常宽松的匹配，适用于大多数语言的常见导入模式：
        - #include <xxx> / #include "xxx" (C/C++)
        - import xxx (Java, Kotlin, Swift, Go)
        - require('xxx') (Node.js)
        - using xxx (C#)
        - open xxx (OCaml)
        - use xxx (Rust)
        """
        imports = []

        if not content:
            return imports

        patterns = [
            # C/C++ #include
            (r'#include\s+[<"]([^>"]+)[>"]', False),
            # import xxx (大多数语言)
            (r'\bimport\s+["\']?([\w./@-]+)["\']?', False),
            # require('xxx')
            (r'\brequire\s*\(\s*["\']([^"\']+)["\']\s*\)', False),
            # using xxx (C#)
            (r'\busing\s+([\w.]+)\s*;', False),
            # use xxx (Rust)
            (r'\buse\s+([\w:]+)', False),
            # from xxx import (Python 风格)
            (r'\bfrom\s+([\w.]+)\s+import', False),
            # Go import
            (r'\bimport\s+["\']([^"\']+)["\']', False),
        ]

        for line in content.split('\n'):
            stripped = line.strip()

            # 跳过注释
            if stripped.startswith('//') or stripped.startswith('#') or stripped.startswith('/*'):
                continue

            for pattern, is_relative in patterns:
                match = re.search(pattern, stripped)
                if match:
                    module = match.group(1)
                    # 过滤掉明显不是项目模块的
                    if not self._looks_like_stdlib(module):
                        imports.append(ImportInfo(
                            module=module,
                            symbols=[],
                            is_relative=is_relative,
                            raw_line=stripped
                        ))
                    break  # 每行只匹配一个模式

        return imports

    def _looks_like_stdlib(self, module: str) -> bool:
        """粗略判断是否像标准库"""
        # 绝对路径或系统路径
        if module.startswith('/') or module.startswith('C:\\'):
            return True
        # 常见标准库前缀
        stdlib_prefixes = ['std', 'system', 'core', 'posix', 'win32']
        top = module.split('/')[0].split('.')[0].lower()
        return top in stdlib_prefixes

    def resolve_import_to_file(self, import_info: ImportInfo, current_file: str) -> List[str]:
        """
        将导入路径解析为文件路径

        通用适配器使用 file_plan 中的数据来解析。
        """
        candidates = []
        module = import_info.module

        if not module:
            return candidates

        # 相对导入
        if import_info.is_relative:
            current_dir = str(Path(current_file).parent)
            base_path = current_dir if current_dir != '.' else ''
            if base_path:
                candidates.append(f"{base_path}/{module}")
                # 常见扩展名
                for ext in ['', '.c', '.cpp', '.h', '.rs', '.go', '.java', '.kt']:
                    candidates.append(f"{base_path}/{module}{ext}")
            return candidates

        # 从 file_plan 中推断扩展名
        file_extensions = set()
        for plan_path in self._file_plan_data.keys():
            if '.' in plan_path:
                ext = '.' + plan_path.rsplit('.', 1)[1]
                file_extensions.add(ext)

        # 检查 file_plan 中是否有匹配的文件
        for plan_path in self._file_plan_data.keys():
            # 精确匹配
            if plan_path == module:
                candidates.append(plan_path)
            # 模块路径转文件路径（带扩展名）
            elif plan_path == f"{module}" or plan_path.endswith(f"/{module}"):
                candidates.append(plan_path)
            # 模块名匹配（不带路径前缀）
            elif Path(plan_path).stem == module:
                candidates.append(plan_path)

        # 通用路径转换（使用从 file_plan 推断的扩展名）
        path_form = module.replace('.', '/')
        if file_extensions:
            # 使用 file_plan 中的扩展名
            for ext in file_extensions:
                candidates.append(f"{path_form}{ext}")
        else:
            # 使用常见扩展名
            for ext in ['', '.c', '.cpp', '.h', '.rs', '.go', '.java', '.kt', '.swift']:
                candidates.append(f"{path_form}{ext}")

        # 去重
        seen = set()
        unique_candidates = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                unique_candidates.append(c)

        return unique_candidates

    def infer_file_type(self, file_path: str) -> str:
        """
        根据文件路径推断文件类型

        优先使用 file_plan 中的 file_type 字段。
        """
        # 优先使用 file_plan 中的数据
        if file_path in self._file_plan_data:
            plan_type = self._file_plan_data[file_path].get("file_type")
            if plan_type:
                return plan_type

        # 文件名匹配
        basename = Path(file_path).name
        if basename in self.COMMON_FILE_PATTERNS:
            return self.COMMON_FILE_PATTERNS[basename]

        # 目录名匹配
        parts = Path(file_path).parts
        for part in parts:
            part_lower = part.lower()
            if part_lower in self.COMMON_DIR_PATTERNS:
                return self.COMMON_DIR_PATTERNS[part_lower]

        # 扩展名推断
        ext = Path(file_path).suffix.lower()
        ext_type_map = {
            '.c': 'source', '.cpp': 'source', '.cc': 'source', '.cxx': 'source',
            '.h': 'header', '.hpp': 'header', '.hxx': 'header',
            '.rs': 'source', '.go': 'source', '.java': 'source', '.kt': 'source',
            '.swift': 'source', '.m': 'source', '.mm': 'source',
            '.rb': 'source', '.php': 'source', '.lua': 'source', '.pl': 'source',
            '.r': 'source', '.R': 'source', '.jl': 'source',
            '.zig': 'source', '.nim': 'source', '.v': 'source', '.vhd': 'source',
            '.asm': 'source', '.s': 'source',
            '.e': 'source',  # 易语言
        }

        if ext in ext_type_map:
            return ext_type_map[ext]

        return "unknown"

    def extract_definitions(self, content: str) -> Dict[str, SymbolDefinition]:
        """
        提取符号定义

        通用适配器只做最基本的提取：
        - 函数/方法定义（大多数语言用 function/func/def/void 等关键字）
        - 类/结构体定义
        """
        definitions = {}

        if not content:
            return definitions

        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # 跳过注释
            if stripped.startswith('//') or stripped.startswith('#') or stripped.startswith('/*'):
                continue

            # 函数定义（通用模式）
            func_match = re.match(
                r'^(?:(?:public|private|protected|static|async|virtual|override|fn|func|def|function|sub|void|int|string|bool)\s+)*(\w+)\s*\([^)]*\)\s*(?:{|\b(?:begin|do)\b)',
                stripped
            )
            if func_match:
                func_name = func_match.group(1)
                # 排除关键字
                keywords = {'if', 'else', 'for', 'while', 'switch', 'case', 'return', 'class', 'struct', 'enum'}
                if func_name.lower() not in keywords and func_name[0].isupper() or func_name[0].islower():
                    definitions[func_name] = SymbolDefinition(
                        name=func_name,
                        symbol_type="function",
                        line_number=i,
                        is_exported=not func_name.startswith('_')
                    )
                continue

            # 类/结构体定义（通用模式）
            class_match = re.match(
                r'^(?:(?:public|private|protected|abstract|static|final)\s+)*(?:class|struct|interface|enum|type)\s+(\w+)',
                stripped
            )
            if class_match:
                class_name = class_match.group(1)
                definitions[class_name] = SymbolDefinition(
                    name=class_name,
                    symbol_type="class",
                    line_number=i,
                    is_exported=not class_name.startswith('_')
                )
                continue

        return definitions

    def get_package_init_file(self, package_path: str) -> str:
        """
        获取包的入口文件

        通用适配器不假设包结构，返回空字符串。
        应该由 file_plan 指定。
        """
        return ""

    def is_project_module(self, module_name: str) -> bool:
        """
        判断是否是项目内模块

        通用适配器使用 file_plan 数据来判断。
        """
        if not module_name:
            return False

        # 检查 file_plan 中是否有匹配的文件
        for plan_path in self._file_plan_data.keys():
            if plan_path == module_name:
                return True
            # 模块路径转文件路径匹配
            path_form = module_name.replace('.', '/')
            if plan_path.startswith(path_form):
                return True

        return False

    def validate_package_structure(self, package_path: str, files: Dict[str, str]) -> List[str]:
        """验证包结构（通用适配器不做严格检查）"""
        # 通用适配器不假设包结构
        return []

    def get_imports_from_file_plan(self, file_path: str) -> List[ImportInfo]:
        """从 file_plan 获取文件的导入信息"""
        if file_path in self._file_plan_data:
            plan = self._file_plan_data[file_path]
            return self._parse_plan_imports(plan.get("imports", []))
        return []


# 注册适配器（不注册到扩展名映射，因为它是 fallback）
LanguageAdapterRegistry._adapters["generic"] = GenericLanguageAdapter()
