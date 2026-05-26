"""
多语言依赖解析器 - Multi-Language Dependency Parser

支持所有主流编程语言的 import/require 语句解析：
- Python: import, from ... import
- JavaScript/TypeScript: require(), import from, import()
- Java: import
- Go: import
- Rust: use, extern crate
- C/C++: #include
- Ruby: require, include
- PHP: require, include, use
- Swift: import
- Kotlin: import
- C#: using
- Scala: import
- R: library(), require()
"""

import re
import logging
from typing import List, Set, Dict, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class LanguageDependencyParser:
    """多语言依赖解析器"""
    
    # 各语言的 import 语法规则
    LANGUAGE_PATTERNS: Dict[str, Dict] = {
        # ==================== Python ====================
        "python": {
            "extensions": [".py", ".pyw", ".pyx"],
            "patterns": [
                # import module
                r'^import\s+([\w\.]+)',
                # from module import ...
                r'^from\s+([\w\.]+)\s+import',
                # import module as alias
                r'^import\s+([\w\.]+)\s+as\s+\w+',
            ],
            "comment_regex": r'#.*$',
            "string_regex": r'("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"[^"\\]*(?:\\.[^"\\]*")*|\'[^\'\\]*(?:\\.[^\'\\]*\')*\')',
        },
        
        # ==================== JavaScript/TypeScript ====================
        "javascript": {
            "extensions": [".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"],
            "patterns": [
                # import ... from 'module'
                r'import\s+[\w\s{},*]+\s+from\s+["\']([^"\']+)["\']',
                # import 'module' (side effect)
                r'import\s+["\']([^"\']+)["\']',
                # require('module')
                r'require\s*\(\s*["\']([^"\']+)["\']\s*\)',
                # import() dynamic
                r'import\s*\(\s*["\']([^"\']+)["\']\s*\)',
                # export ... from 'module'
                r'export\s+[\w\s{},*]+\s+from\s+["\']([^"\']+)["\']',
            ],
            "comment_regex": r'//.*$|/\*[\s\S]*?\*/',
            "string_regex": r'(`[^`]*`|"[^"\\]*(?:\\.[^"\\]*")*|\'[^\'\\]*(?:\\.[^\'\\]*\')*\')',
        },
        
        # ==================== Java ====================
        "java": {
            "extensions": [".java", ".groovy"],
            "patterns": [
                # import package.class
                r'^import\s+(static\s+)?([\w\.]+)(?:\.\*)?',
            ],
            "comment_regex": r'//.*$|/\*[\s\S]*?\*/',
            "string_regex": r'"[^"\\]*(?:\\.[^"\\]*")*"',
        },
        
        # ==================== Go ====================
        "go": {
            "extensions": [".go"],
            "patterns": [
                # import "package" (single or multi-line)
                r'import\s*\((?:[^)]*?)\)',
                # 单行 import "package"
                r'import\s+"([^"]+)"',
                # 多行 import 内的单个 package
                r'"\s*([^"]+)\s*"',
            ],
            "comment_regex": r'//.*$|/\*[\s\S]*?\*/',
            "string_regex": r'"[^"\\]*(?:\\.[^"\\]*")*|`[^`]*`',
        },
        
        # ==================== Rust ====================
        "rust": {
            "extensions": [".rs"],
            "patterns": [
                # use crate::module
                r'^use\s+([\w::]+)',
                # extern crate
                r'^extern\s+crate\s+(\w+)',
                # mod module
                r'^mod\s+(\w+)',
            ],
            "comment_regex": r'//.*$|/\*[\s\S]*?\*/',
            "string_regex": r'"[^"\\]*(?:\\.[^"\\]*")*|r#*"[^"]*"#*',
        },
        
        # ==================== C/C++ ====================
        "cpp": {
            "extensions": [".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx"],
            "patterns": [
                # #include <header>
                r'#include\s*<([^>]+)>',
                # #include "header"
                r'#include\s*"([^"]+)"',
            ],
            "comment_regex": r'//.*$|/\*[\s\S]*?\*/',
            "string_regex": r'"[^"\\]*(?:\\.[^"\\]*")*"',
        },
        
        # ==================== Ruby ====================
        "ruby": {
            "extensions": [".rb", ".rbw", ".gemspec"],
            "patterns": [
                # require 'module'
                r'require\s+[\'"]([^\'"]+)[\'"]',
                # require_relative 'module'
                r'require_relative\s+[\'"]([^\'"]+)[\'"]',
                # include Module
                r'include\s+(\w+)',
                # extend Module
                r'extend\s+(\w+)',
            ],
            "comment_regex": r'#.*$',
            "string_regex": r'("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"[^"\\]*(?:\\.[^"\\]*")*|\'[^\'\\]*(?:\\.[^\'\\]*\')*\')',
        },
        
        # ==================== PHP ====================
        "php": {
            "extensions": [".php"],
            "patterns": [
                # require 'file'
                r'require\s+[\'"]([^\'"]+)[\'"]',
                # require_once 'file'
                r'require_once\s+[\'"]([^\'"]+)[\'"]',
                # include 'file'
                r'include\s+[\'"]([^\'"]+)[\'"]',
                # include_once 'file'
                r'include_once\s+[\'"]([^\'"]+)[\'"]',
                # use Namespace\Class
                r'use\s+([\w\\]+)',
            ],
            "comment_regex": r'//.*$|#.*$|/\*[\s\S]*?\*/',
            "string_regex": r'("[^"\\]*(?:\\.[^"\\]*")*|\'[^\'\\]*(?:\\.[^\'\\]*\')*\')',
        },
        
        # ==================== Swift ====================
        "swift": {
            "extensions": [".swift"],
            "patterns": [
                # import Module
                r'import\s+(\w+)',
            ],
            "comment_regex": r'//.*$|/\*[\s\S]*?\*/',
            "string_regex": r'"[^"\\]*(?:\\.[^"\\]*")*"',
        },
        
        # ==================== Kotlin ====================
        "kotlin": {
            "extensions": [".kt", ".kts"],
            "patterns": [
                # import package.class
                r'import\s+(?:static\s+)?([\w\.]+)(?:\.\*)?',
            ],
            "comment_regex": r'//.*$|/\*[\s\S]*?\*/',
            "string_regex": r'"[^"\\]*(?:\\.[^"\\]*")*"',
        },
        
        # ==================== C# ====================
        "csharp": {
            "extensions": [".cs"],
            "patterns": [
                # using Namespace
                r'using\s+([\w\.]+)',
            ],
            "comment_regex": r'//.*$|/\*[\s\S]*?\*/',
            "string_regex": r'@"[^"]*"|"[^"\\]*(?:\\.[^"\\]*")*"',
        },
        
        # ==================== Scala ====================
        "scala": {
            "extensions": [".scala"],
            "patterns": [
                # import package._
                r'import\s+([\w\.]+(?:\._|\.\*)?)',
            ],
            "comment_regex": r'//.*$|/\*[\s\S]*?\*/',
            "string_regex": r'"""[\s\S]*?"""|"[^"\\]*(?:\\.[^"\\]*")*"',
        },
        
        # ==================== R ====================
        "r": {
            "extensions": [".R", ".r"],
            "patterns": [
                # library(package)
                r'library\s*\(\s*(\w+)\s*\)',
                # require(package)
                r'require\s*\(\s*(\w+)\s*\)',
            ],
            "comment_regex": r'#.*$',
            "string_regex": r'"[^"\\]*(?:\\.[^"\\]*")*|\'[^\'\\]*(?:\\.[^\'\\]*\')*\'',
        },
    }
    
    def __init__(self):
        self.compiled_patterns: Dict[str, List[Tuple[str, re.Pattern]]] = {}
        self._compile_patterns()
    
    def _compile_patterns(self):
        """预编译所有正则表达式"""
        for lang, config in self.LANGUAGE_PATTERNS.items():
            self.compiled_patterns[lang] = []
            for pattern in config["patterns"]:
                try:
                    compiled = re.compile(pattern, re.MULTILINE)
                    self.compiled_patterns[lang].append((pattern, compiled))
                except re.error as e:
                    logger.warning(f"语言 {lang} 的正则表达式编译失败：{pattern}, 错误：{e}")
    
    def detect_language(self, filepath: str) -> Optional[str]:
        """根据文件扩展名检测编程语言"""
        ext = Path(filepath).suffix.lower()
        
        for lang, config in self.LANGUAGE_PATTERNS.items():
            if ext in config["extensions"]:
                return lang
        
        return None
    
    def parse_imports(self, filepath: str, content: str) -> Set[str]:
        """
        解析文件中的 import 语句
        
        Args:
            filepath: 文件路径
            content: 文件内容
        
        Returns:
            导入的模块/文件集合
        """
        lang = self.detect_language(filepath)
        if not lang:
            logger.debug(f"不支持的语言：{filepath}")
            return set()
        
        # 移除注释和字符串
        content = self._remove_comments_and_strings(content, lang)
        
        # 提取所有 import
        imports = set()
        for pattern_name, compiled in self.compiled_patterns[lang]:
            matches = compiled.findall(content)
            for match in matches:
                if isinstance(match, tuple):
                    # 多个捕获组时取第一个非空
                    import_path = next((m for m in match if m), "")
                else:
                    import_path = match
                
                if import_path:
                    imports.add(self._normalize_import(import_path, lang, filepath))
        
        return imports
    
    def _remove_comments_and_strings(self, content: str, lang: str) -> str:
        """移除注释和字符串字面量"""
        config = self.LANGUAGE_PATTERNS[lang]
        
        # 移除注释
        if "comment_regex" in config:
            content = re.sub(config["comment_regex"], "", content, flags=re.MULTILINE)
        
        # 注意：不移除字符串！因为 import 语句中的模块名就在字符串里
        # 只移除不包含 import 的纯字符串字面量
        # 使用占位符替换字符串，保留 import 中的字符串
        
        return content
    
    def _normalize_import(self, import_path: str, lang: str, filepath: str) -> str:
        """
        标准化 import 路径
        
        将 import 语句转换为相对文件路径
        """
        # Python: module.submodule -> module/submodule.py
        if lang == "python":
            return import_path.replace(".", "/") + ".py"
        
        # JavaScript: ./module -> module.js
        if lang in ["javascript", "typescript"]:
            import_path = import_path.lstrip("./")
            if not import_path.endswith((".js", ".ts", ".jsx", ".tsx")):
                # 尝试添加常见扩展
                for ext in [".ts", ".js", ".tsx", ".jsx"]:
                    potential = import_path + ext
                    if Path(Path(filepath).parent / potential).exists():
                        return potential
                return import_path + ".js"  # 默认
            return import_path
        
        # Java: com.example.Class -> com/example/Class.java
        if lang == "java":
            return import_path.replace(".", "/") + ".java"
        
        # Go: package/subpackage -> package/subpackage/
        if lang == "go":
            return import_path.replace(".", "/")
        
        # Rust: crate::module -> crate/module.rs
        if lang == "rust":
            return import_path.replace("::", "/") + ".rs"
        
        # C/C++: 直接使用
        if lang == "cpp":
            return import_path
        
        # Ruby: require 'module' -> module.rb
        if lang == "ruby":
            return import_path + ".rb"
        
        # PHP: use Namespace\Class -> Namespace/Class.php
        if lang == "php":
            return import_path.replace("\\", "/") + ".php"
        
        # 其他语言：返回原始路径
        return import_path
    
    def parse_file(self, filepath: str) -> Set[str]:
        """
        解析文件系统中的文件
        
        Args:
            filepath: 文件路径
        
        Returns:
            导入的模块/文件集合
        """
        try:
            path = Path(filepath)
            if not path.exists():
                logger.warning(f"文件不存在：{filepath}")
                return set()
            
            content = path.read_text(encoding="utf-8", errors="ignore")
            return self.parse_imports(filepath, content)
        
        except Exception as e:
            logger.error(f"解析文件失败 {filepath}: {e}")
            return set()
    
    def get_language_stats(self, files: List[str]) -> Dict[str, int]:
        """统计各语言文件数量"""
        stats: Dict[str, int] = {}
        
        for filepath in files:
            lang = self.detect_language(filepath)
            if lang:
                stats[lang] = stats.get(lang, 0) + 1
        
        return stats


# 全局单例
_parser: Optional[LanguageDependencyParser] = None


def get_parser() -> LanguageDependencyParser:
    """获取全局依赖解析器单例"""
    global _parser
    if _parser is None:
        _parser = LanguageDependencyParser()
    return _parser


def parse_file_dependencies(filepath: str) -> Set[str]:
    """便捷函数：解析单个文件的依赖"""
    return get_parser().parse_file(filepath)


def detect_file_language(filepath: str) -> Optional[str]:
    """便捷函数：检测文件语言"""
    return get_parser().detect_language(filepath)
