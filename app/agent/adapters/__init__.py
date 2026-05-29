"""
Language Adapters - 语言适配层

提供统一接口处理不同编程语言的差异：
- 导入语法解析
- 文件类型推断
- 包/模块结构规则
- 符号定义提取
"""

from .language_adapter import (
    LanguageAdapter,
    LanguageAdapterRegistry,
    ImportInfo,
    SymbolDefinition,
    PackageStructure,
)

from .python import PythonLanguageAdapter
from .javascript import JavaScriptLanguageAdapter
from .generic import GenericLanguageAdapter

__all__ = [
    "LanguageAdapter",
    "LanguageAdapterRegistry",
    "ImportInfo",
    "SymbolDefinition",
    "PackageStructure",
    "PythonLanguageAdapter",
    "JavaScriptLanguageAdapter",
    "GenericLanguageAdapter",
]
