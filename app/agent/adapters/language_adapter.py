"""
LanguageAdapter - 语言适配层

抽象各编程语言的差异，提供统一接口：
- 导入语句解析
- 文件类型推断
- 包/模块结构规则
- 符号定义提取
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from pathlib import Path


@dataclass
class ImportInfo:
    """导入信息"""
    module: str                  # 模块路径 (e.g., "app.models", "github.com/org/repo")
    symbols: List[str] = field(default_factory=list)  # 导入的符号 (e.g., ["User", "Base"])
    is_relative: bool = False    # 是否是相对导入
    alias: Optional[str] = None  # 别名 (e.g., "import numpy as np")
    raw_line: str = ""           # 原始行内容


@dataclass
class SymbolDefinition:
    """符号定义"""
    name: str                    # 符号名
    symbol_type: str             # 类型: function, class, variable, constant, interface, type, struct
    line_number: int = 0
    signature: Optional[str] = None  # 函数签名
    is_exported: bool = True     # 是否导出


class LanguageAdapter(ABC):
    """语言适配器基类"""

    # 语言标识
    language: str = "unknown"

    # 支持的文件扩展名
    extensions: List[str] = []

    # 包入口文件名 (Python: __init__.py, JS: index.js)
    package_init_filename: str = "__init__.py"

    @abstractmethod
    def parse_imports(self, content: str, file_path: str = "") -> List[ImportInfo]:
        """
        解析文件内容中的导入语句

        Args:
            content: 文件内容
            file_path: 文件路径（用于解析相对导入）

        Returns:
            导入信息列表
        """
        pass

    @abstractmethod
    def resolve_import_to_file(self, import_info: ImportInfo, current_file: str) -> List[str]:
        """
        将导入路径解析为可能的文件路径

        Args:
            import_info: 导入信息
            current_file: 当前文件路径

        Returns:
            可能的文件路径列表（因为某些语言有多种解析方式）
        """
        pass

    @abstractmethod
    def infer_file_type(self, file_path: str) -> str:
        """
        根据文件路径推断文件类型

        Args:
            file_path: 文件路径

        Returns:
            文件类型字符串 (e.g., "model", "api", "config", "test", "database")
        """
        pass

    @abstractmethod
    def extract_definitions(self, content: str) -> Dict[str, SymbolDefinition]:
        """
        提取文件中的符号定义

        Args:
            content: 文件内容

        Returns:
            符号名 -> 定义信息的映射
        """
        pass

    @abstractmethod
    def get_package_init_file(self, package_path: str) -> str:
        """
        获取包的入口文件路径

        Args:
            package_path: 包路径 (e.g., "app/models")

        Returns:
            入口文件路径 (e.g., "app/models/__init__.py")
        """
        pass

    @abstractmethod
    def is_project_module(self, module_name: str) -> bool:
        """
        判断是否是项目内模块（非标准库、非第三方）

        Args:
            module_name: 模块名

        Returns:
            是否是项目内模块
        """
        pass

    @abstractmethod
    def validate_package_structure(self, package_path: str, files: Dict[str, str]) -> List[str]:
        """
        验证包结构完整性，返回缺失的文件列表

        Args:
            package_path: 包路径
            files: 已生成的文件字典

        Returns:
            缺失的文件路径列表
        """
        pass

    def get_required_package_files(self, package_path: str) -> List[str]:
        """
        获取包所需的全部文件

        Args:
            package_path: 包路径

        Returns:
            所需文件列表
        """
        return [self.get_package_init_file(package_path)]

    def normalize_module_path(self, module_path: str) -> str:
        """
        标准化模块路径（用于比较）

        Args:
            module_path: 原始模块路径

        Returns:
            标准化后的路径
        """
        return module_path.replace(".", "/")


class LanguageAdapterRegistry:
    """
    语言适配器注册表

    支持：
    1. 按语言名获取适配器
    2. 按文件扩展名获取适配器
    3. 自动检测项目语言
    4. Fallback 到 GenericLanguageAdapter
    """

    _adapters: Dict[str, LanguageAdapter] = {}
    _extension_map: Dict[str, str] = {}  # extension -> language

    @classmethod
    def register(cls, adapter: LanguageAdapter):
        """注册语言适配器"""
        cls._adapters[adapter.language] = adapter
        for ext in adapter.extensions:
            cls._extension_map[ext] = adapter.language

    @classmethod
    def get_adapter(cls, language: str) -> Optional[LanguageAdapter]:
        """
        根据语言名获取适配器

        如果找不到对应语言，返回 GenericLanguageAdapter
        """
        adapter = cls._adapters.get(language)
        if adapter:
            return adapter

        # Fallback 到通用适配器
        return cls._adapters.get("generic")

    @classmethod
    def get_adapter_for_file(cls, file_path: str) -> Optional[LanguageAdapter]:
        """
        根据文件路径获取适配器

        如果扩展名无法识别，返回 GenericLanguageAdapter
        """
        ext = Path(file_path).suffix
        language = cls._extension_map.get(ext)
        if language:
            return cls._adapters.get(language)

        # Fallback 到通用适配器
        return cls._adapters.get("generic")

    @classmethod
    def detect_language(cls, files: Dict[str, str]) -> str:
        """
        根据文件集合自动检测项目语言

        Args:
            files: 文件字典 {path: content}

        Returns:
            检测到的语言名（如果没有明确匹配，返回 "generic"）
        """
        ext_count: Dict[str, int] = {}

        for file_path in files.keys():
            ext = Path(file_path).suffix
            if ext in cls._extension_map:
                language = cls._extension_map[ext]
                ext_count[language] = ext_count.get(language, 0) + 1

        if not ext_count:
            return "generic"  # 无法识别时用通用适配器

        # 返回文件数最多的语言
        dominant_language = max(ext_count, key=ext_count.get)

        # 如果多数文件是已知语言，使用该语言
        total_known = sum(ext_count.values())
        dominant_count = ext_count[dominant_language]

        # 超过 50% 的文件是同一语言，使用该语言适配器
        if dominant_count / total_known > 0.5:
            return dominant_language

        # 混合语言项目，使用通用适配器
        return "generic"

    @classmethod
    def get_adapter_for_project(cls, files: Dict[str, str]) -> LanguageAdapter:
        """
        根据项目文件自动选择最佳适配器

        Args:
            files: 文件字典 {path: content}

        Returns:
            最适合的语言适配器
        """
        language = cls.detect_language(files)
        return cls.get_adapter(language)

    @classmethod
    def get_all_adapters(cls) -> Dict[str, LanguageAdapter]:
        """获取所有已注册的适配器"""
        return cls._adapters.copy()

    @classmethod
    def get_supported_extensions(cls) -> List[str]:
        """获取所有支持的文件扩展名"""
        return list(cls._extension_map.keys())

    @classmethod
    def is_extension_supported(cls, ext: str) -> bool:
        """检查扩展名是否有专门的适配器"""
        return ext in cls._extension_map
