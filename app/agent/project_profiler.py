"""
项目模式识别模块

自动分析项目的架构模式、分层结构、高风险区域和测试约定，生成项目指纹。

v5.15.0 重构：支持多语言分析
- Python (默认) / JavaScript&TypeScript / Go / Rust / Java
- 通过 language 参数切换语言规则
- 各语言独立的扩展名、聚合文件、测试约定、import 语法
- 向后兼容：未传 language 时按 Python 处理
"""
import re
import json
import os
import time
import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional, Set
from collections import defaultdict

from app.utils.performance_metrics import metrics_collector

logger = logging.getLogger(__name__)


# ==================== 语言配置 ====================

@dataclass(frozen=True)
class LanguageProfile:
    """单语言的 profiler 规则"""
    extensions: tuple  # 文件扩展名（含点）
    skip_dirs: tuple   # 跳过的目录名
    init_file: tuple  # 聚合导出文件名集合（空 tuple 表示该语言无此概念）
    test_file_globs: tuple    # 测试文件 glob 模式
    test_dir_names: tuple     # 测试目录名（用于 os.walk 匹配）
    test_fixture_files: tuple # fixture/配置文件名（仅文件名，不含路径）
    test_fixture_marker: str  # 内容中检测 fixture 用的字符串标记
    import_pattern: re.Pattern  # 用于从 import 语句提取模块名


def _make_import_pattern(language: str) -> re.Pattern:
    """构造各语言的 import 提取正则"""
    if language == "python":
        # from xxx import yyy / import xxx.yyy
        return re.compile(r"^(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))")
    if language == "javascript":
        # import x from 'y' / require('y')
        return re.compile(
            r"""(?:import\s+(?:[^'"]+\s+from\s+)?['"]([^'"]+)['"]"""
            r"""|require\(\s*['"]([^'"]+)['"]\s*\))"""
        )
    if language == "go":
        # "package/path" 在 import 块内
        return re.compile(r'^\s*"([^"]+)"')
    if language == "rust":
        # use crate::xxx / use xxx;
        return re.compile(r"^\s*use\s+([\w:]+)")
    if language == "java":
        # import xxx.yyy;
        return re.compile(r"^\s*import\s+([\w.]+)\s*;")
    # 通用 fallback
    return re.compile(r"^\s*(?:import|use|require|include)\s+[\"']?([\w./@-]+)")


LANGUAGE_PROFILES: Dict[str, LanguageProfile] = {
    "python": LanguageProfile(
        extensions=(".py",),
        skip_dirs=("node_modules", "__pycache__", "venv", "env", ".venv", "dist", "build", ".tox"),
        init_file=("__init__.py",),
        test_file_globs=("test_*.py", "*_test.py"),
        test_dir_names=("tests", "test"),
        test_fixture_files=("conftest.py",),
        test_fixture_marker="@pytest.fixture",
        import_pattern=_make_import_pattern("python"),
    ),
    "javascript": LanguageProfile(
        extensions=(".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"),
        skip_dirs=("node_modules", "dist", "build", ".next", ".nuxt", "out", "coverage"),
        init_file=("index.js", "index.ts", "index.jsx", "index.tsx", "index.mjs", "index.cjs"),
        test_file_globs=("*.test.js", "*.spec.js", "*.test.ts", "*.spec.ts", "*.test.jsx", "*.test.tsx"),
        test_dir_names=("tests", "test", "__tests__", "spec"),
        test_fixture_files=("jest.config.js", "jest.config.ts", "vitest.config.js", "vitest.config.ts"),
        test_fixture_marker="describe(",
        import_pattern=_make_import_pattern("javascript"),
    ),
    "go": LanguageProfile(
        extensions=(".go",),
        skip_dirs=("vendor", ".git", "bin"),
        init_file=(),
        test_file_globs=("*_test.go",),
        test_dir_names=(),
        test_fixture_files=(),
        test_fixture_marker="func Test",
        import_pattern=_make_import_pattern("go"),
    ),
    "rust": LanguageProfile(
        extensions=(".rs",),
        skip_dirs=("target", ".git"),
        init_file=("mod.rs",),
        test_file_globs=("*_test.rs",),
        test_dir_names=("tests",),
        test_fixture_files=(),
        test_fixture_marker="#[test]",
        import_pattern=_make_import_pattern("rust"),
    ),
    "java": LanguageProfile(
        extensions=(".java",),
        skip_dirs=("target", "build", ".gradle", ".idea", "out"),
        init_file=(),
        test_file_globs=("*Test.java", "*Tests.java", "*IT.java", "*Spec.java"),
        test_dir_names=("test", "tests"),
        test_fixture_files=(),
        test_fixture_marker="@Test",
        import_pattern=_make_import_pattern("java"),
    ),
}

# 跳过目录的公共集合（任何语言都跳过）
_COMMON_SKIP_DIRS: Set[str] = {".git", "node_modules", "__pycache__", ".idea", ".vscode", ".DS_Store"}


# ==================== 数据类 ====================

@dataclass
class ArchitectureInfo:
    """架构信息"""
    pattern: str = "unknown"  # layered, mvc, mixin-heavy, flat
    layers: Dict[str, List[str]] = field(default_factory=dict)
    aggregate_classes: List[str] = field(default_factory=list)
    export_modules: List[str] = field(default_factory=list)
    language: str = "python"


@dataclass
class RiskAreas:
    """高风险区域"""
    high_dependency: List[str] = field(default_factory=list)
    security_critical: List[str] = field(default_factory=list)
    data_critical: List[str] = field(default_factory=list)


@dataclass
class TestPatterns:
    """测试约定"""
    test_location: str = "tests/"
    naming_convention: str = "test_*.py"
    fixture_usage: bool = False
    framework: str = "unknown"  # pytest / jest / go test / cargo test / junit


@dataclass
class ProjectProfile:
    """项目指纹"""
    architecture: ArchitectureInfo = field(default_factory=ArchitectureInfo)
    risk_areas: RiskAreas = field(default_factory=RiskAreas)
    test_patterns: TestPatterns = field(default_factory=TestPatterns)
    generated_at: str = ""
    cache_key: str = ""
    language: str = "python"


# ==================== Profiler ====================

class ProjectProfiler:
    """项目模式分析器（多语言支持）

    Args:
        project_root: 项目根目录
        language: 目标语言（python/javascript/go/rust/java），None 时自动检测
        cache_dir: 缓存目录
    """

    # 安全关键字（跨语言通用，含语言特定的关键字）
    SECURITY_KEYWORDS = {
        # 通用
        'auth', 'permission', 'security', 'validate', 'verify',
        'token', 'password', 'credential', 'session', 'middleware',
        'encrypt', 'decrypt', 'hash', 'signature',
        # JS/TS 框架相关
        'passport', 'jwt', 'bcrypt', 'helmet', 'cors', 'csrf',
        # Java 框架相关
        'spring-security', 'shiro', 'oauth',
        # Go 框架相关
        'gorilla', 'gin-auth', 'casbin',
    }

    # 数据库关键字
    DATABASE_KEYWORDS = {
        'database', 'session', 'transaction', 'commit', 'rollback',
        'query', 'orm', 'model', 'migration', 'db',
        # JS ORM
        'sequelize', 'typeorm', 'mongoose', 'prisma', 'knex',
        # Go ORM
        'gorm', 'sqlx', 'ent',
        # Java ORM
        'hibernate', 'mybatis', 'jpa', 'jooq',
        # Rust ORM
        'diesel', 'sqlx', 'sea-orm',
    }

    # 分层架构的目录名模式（跨语言通用）
    LAYER_PATTERNS = {
        'api': ('api', 'router', 'controller', 'view', 'endpoint', 'route', 'handler'),
        'service': ('service', 'business', 'logic', 'usecase', 'bll'),
        'repository': ('repository', 'repo', 'dao', 'storage', 'data', 'persistence'),
        'model': ('model', 'entity', 'domain', 'schema', 'dto', 'po', 'vo'),
    }

    # 测试框架 → 默认命名约定
    TEST_FRAMEWORK_NAMING = {
        "python": "test_*.py",
        "javascript": "*.test.js",
        "go": "*_test.go",
        "rust": "*_test.rs",
        "java": "*Test.java",
    }

    TEST_FRAMEWORK_NAMES = {
        "python": "pytest",
        "javascript": "jest/vitest",
        "go": "go test",
        "rust": "cargo test",
        "java": "junit",
    }

    def __init__(
        self,
        project_root: str,
        language: Optional[str] = None,
        cache_dir: Optional[str] = None,
    ):
        self.project_root = Path(project_root)
        self.language = (language or "python").lower()
        if self.language not in LANGUAGE_PROFILES:
            logger.warning(f"不支持的语言 '{self.language}'，回退到 'python'")
            self.language = "python"
        self.profile_rules = LANGUAGE_PROFILES[self.language]
        self.cache_dir = Path(cache_dir) if cache_dir else self.project_root / '.cache' / 'profiler'
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def profile(self, project_root: Optional[str] = None) -> ProjectProfile:
        """
        分析项目结构，生成项目指纹

        Args:
            project_root: 项目根目录（可选，使用构造函数中的值）

        Returns:
            ProjectProfile: 项目指纹
        """
        root = Path(project_root) if project_root else self.project_root

        # 检查缓存（缓存键包含语言，不同语言不同缓存）
        cache_key = self._generate_cache_key(root)
        cached_profile = self._load_cache(cache_key)
        if cached_profile and cached_profile.language == self.language:
            metrics_collector.record_cache_hit('ProjectProfiler')
            logger.info(f"使用缓存的项目指纹 | cache_key: {cache_key[:8]}... | language={self.language}")
            return cached_profile

        metrics_collector.record_cache_miss('ProjectProfiler')

        start_time = metrics_collector.start_timer('ProjectProfiler')
        logger.info(f"开始项目模式识别 | 项目：{root} | language={self.language}")

        profile = ProjectProfile(language=self.language, cache_key=cache_key)

        # 分析架构模式
        profile.architecture = self._analyze_architecture(root)
        profile.architecture.language = self.language

        # 分析高风险区域
        profile.risk_areas = self._analyze_risk_areas(root)

        # 分析测试约定
        profile.test_patterns = self._analyze_test_patterns(root)
        profile.test_patterns.framework = self.TEST_FRAMEWORK_NAMES.get(self.language, "unknown")

        profile.generated_at = time.strftime('%Y-%m-%d %H:%M:%S')

        # 保存缓存
        self._save_cache(profile)

        elapsed = time.time() - start_time
        file_count = self._count_source_files(root)
        metrics_collector.end_timer('ProjectProfiler', start_time, 'profile', {
            'file_count': file_count,
            'language': self.language,
        })

        logger.info(
            f"项目模式识别完成 | language={self.language} | "
            f"架构模式：{profile.architecture.pattern} | "
            f"高风险文件：{len(profile.risk_areas.high_dependency)} | "
            f"耗时：{elapsed:.2f}s"
        )

        return profile

    # ---------- 文件枚举（多语言） ----------

    def _iter_source_files(self, root: Path):
        """迭代所有源文件（按语言扩展名过滤、跳过常见目录）"""
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in self.profile_rules.extensions:
                continue
            # 跳过隐藏目录与语言特定目录
            if any(
                part.startswith('.') or part in self.profile_rules.skip_dirs or part in _COMMON_SKIP_DIRS
                for part in path.parts
            ):
                continue
            yield path

    def _count_source_files(self, root: Path) -> int:
        return sum(1 for _ in self._iter_source_files(root))

    def _is_test_file(self, path: Path) -> bool:
        """判断文件是否是测试文件（按语言的 glob 模式）"""
        name = path.name.lower()
        for glob_pattern in self.profile_rules.test_file_globs:
            # 简单 fnmatch（处理 * 通配符）
            regex = "^" + re.escape(glob_pattern).replace(r"\*", ".*") + "$"
            if re.match(regex, name):
                return True
        return False

    def _is_test_dir(self, dirpath: str) -> bool:
        """判断目录是否是测试目录（按语言的目录名）"""
        dir_name = os.path.basename(dirpath).lower()
        return any(t in dir_name for t in self.profile_rules.test_dir_names)

    # ---------- 架构分析 ----------

    def _analyze_architecture(self, root: Path) -> ArchitectureInfo:
        """分析架构模式"""
        arch = ArchitectureInfo(language=self.language)

        # 识别分层架构
        layers = self._detect_layers(root)
        if layers:
            arch.pattern = "layered"
            arch.layers = layers

        # 识别 Mixin 模式（仅 Python 适用）
        if self.language == "python":
            mixin_classes = self._detect_python_mixins(root)
            if mixin_classes:
                if arch.pattern == "unknown":
                    arch.pattern = "mixin-heavy"
                arch.aggregate_classes = mixin_classes

        # 识别聚合导出模块
        export_modules = self._detect_export_modules(root)
        arch.export_modules = export_modules

        return arch

    def _detect_layers(self, root: Path) -> Dict[str, List[str]]:
        """检测分层架构（跨语言通用，按目录名匹配）"""
        layers: Dict[str, List[str]] = {}

        for dirpath, dirnames, _ in os.walk(root):
            # 跳过隐藏目录与语言特定目录
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith('.')
                and d not in _COMMON_SKIP_DIRS
                and d not in self.profile_rules.skip_dirs
            ]

            dir_name = os.path.basename(dirpath).lower()

            for layer_name, patterns in self.LAYER_PATTERNS.items():
                if any(p in dir_name for p in patterns):
                    rel_path = os.path.relpath(dirpath, root)
                    if rel_path not in layers.get(layer_name, []):
                        layers.setdefault(layer_name, []).append(rel_path)

        return layers

    def _detect_python_mixins(self, root: Path) -> List[str]:
        """检测 Python Mixin 类（仅 Python）"""
        mixins: List[str] = []
        for py_file in self._iter_source_files(root):
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef) and 'Mixin' in node.name:
                        rel_path = os.path.relpath(py_file, root)
                        mixins.append(f"{rel_path}:{node.name}")
            except Exception as e:
                logger.debug(f"Mixin 检测失败 {py_file}: {e}")
                continue
        return mixins[:20]

    def _detect_export_modules(self, root: Path) -> List[str]:
        """检测聚合导出模块（多语言版本）

        - Python: __init__.py（只包含 import 语句）
        - JavaScript: index.js / index.ts（只包含 export 语句）
        - Rust: mod.rs
        - Go/Java: 无此概念（返回空）
        """
        if not self.profile_rules.init_file:
            return []

        export_modules: List[str] = []
        init_names = set(self.profile_rules.init_file)

        for path in self._iter_source_files(root):
            if path.name not in init_names:
                continue
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()

                if self.language == "python":
                    if self._is_python_pure_export(content):
                        rel_path = os.path.relpath(path, root)
                        export_modules.append(rel_path)
                elif self.language == "javascript":
                    if self._is_js_pure_export(content):
                        rel_path = os.path.relpath(path, root)
                        export_modules.append(rel_path)
                elif self.language == "rust":
                    # Rust mod.rs：通常包含 mod xxx; 声明
                    if re.search(r"^\s*(?:pub\s+)?mod\s+\w+", content, re.M):
                        rel_path = os.path.relpath(path, root)
                        export_modules.append(rel_path)
            except Exception as e:
                logger.debug(f"聚合导出检测失败 {path}: {e}")
                continue

        return export_modules

    def _is_python_pure_export(self, content: str) -> bool:
        """判断 Python 文件是否纯聚合导出（只有 import 语句）"""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return False
        has_only_imports = True
        import_count = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                import_count += 1
            elif isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Assign)):
                has_only_imports = False
                break
        return has_only_imports and import_count > 0

    def _is_js_pure_export(self, content: str) -> bool:
        """判断 JS/TS 文件是否纯聚合导出（只有 import / re-export / 简单声明导出）"""
        lines = [l.strip() for l in content.split('\n') if l.strip() and not l.strip().startswith('//')]
        if not lines:
            return False
        allowed = re.compile(
            r"^(?:"
            r"import\s"                           # import ...
            r"|export\s+(?:\{.*?\}|\*|\*?from)"   # export { ... } / export * / export ... from
            r"|export\s+default"                  # export default ...
            r"|export\s+(?:const|let|var|function|class|async|type|interface|enum)"
            r")"
        )
        export_count = 0
        non_export_count = 0
        for line in lines:
            if allowed.match(line):
                export_count += 1
            else:
                non_export_count += 1
        return export_count > 0 and non_export_count == 0

    # ---------- 风险分析 ----------

    def _analyze_risk_areas(self, root: Path) -> RiskAreas:
        """分析高风险区域（多语言）"""
        risks = RiskAreas()

        # 统计文件被引用次数
        import_counts = self._count_imports(root)

        # 阈值 5 适用于所有语言
        high_dep_threshold = 5
        risks.high_dependency = [
            self._module_to_filename(module)
            for module, count in import_counts.items()
            if count >= high_dep_threshold
        ][:20]

        # 搜索安全 / 数据库关键字
        security_files: Set[str] = set()
        data_files: Set[str] = set()

        for src_file in self._iter_source_files(root):
            try:
                with open(src_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read().lower()
                rel_path = os.path.relpath(src_file, root)
                if any(kw in content for kw in self.SECURITY_KEYWORDS):
                    security_files.add(rel_path)
                if any(kw in content for kw in self.DATABASE_KEYWORDS):
                    data_files.add(rel_path)
            except Exception as e:
                logger.debug(f"风险扫描失败 {src_file}: {e}")
                continue

        risks.security_critical = list(security_files)[:20]
        risks.data_critical = list(data_files)[:20]

        return risks

    def _count_imports(self, root: Path) -> Dict[str, int]:
        """按语言规则统计 import 引用次数"""
        import_counts: Dict[str, int] = defaultdict(int)
        pattern = self.profile_rules.import_pattern

        for src_file in self._iter_source_files(root):
            try:
                with open(src_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                for line in content.split('\n'):
                    line = line.strip()
                    m = pattern.match(line)
                    if not m:
                        continue
                    # 多个 group 中取第一个非空
                    module = next((g for g in m.groups() if g), None)
                    if not module:
                        continue
                    # 跳过标准库/外部包启发：项目内模块通常以小写字母开头、不含点（python）/不含反斜杠
                    if self._is_project_module(module):
                        import_counts[module] += 1
            except Exception as e:
                logger.debug(f"import 统计失败 {src_file}: {e}")
                continue

        return import_counts

    def _is_project_module(self, module: str) -> bool:
        """粗略判断是否是项目内模块（避免被大量外部 import 污染）"""
        if not module:
            return False
        # 绝对路径或系统路径
        if module.startswith('/') or module.startswith('C:\\') or module.startswith('.'):
            return True
        # 标准库前缀（不同语言）
        stdlib_prefixes = {
            "python": ("os", "sys", "re", "json", "time", "logging", "pathlib", "typing",
                       "collections", "asyncio", "functools", "itertools", "dataclasses",
                       "abc", "io", "hashlib", "datetime", "subprocess", "threading",
                       "ast", "enum", "copy", "traceback", "tempfile"),
            "javascript": ("node:", "fs", "path", "http", "https", "url", "util", "events",
                           "stream", "buffer", "crypto", "os", "child_process"),
            "go": ("fmt", "os", "io", "net", "http", "time", "errors", "context", "sync",
                   "strings", "strconv", "log", "testing", "bufio", "bytes"),
            "rust": ("std", "core", "alloc", "crate"),
            "java": ("java.", "javax.", "org.springframework", "org.apache",
                     "com.google", "android.", "kotlin."),
        }
        prefixes = stdlib_prefixes.get(self.language, ())
        # 检查前缀
        for prefix in prefixes:
            if module == prefix or module.startswith(prefix + ".") or module.startswith(prefix + "/"):
                return False
        return True

    def _module_to_filename(self, module: str) -> str:
        """将模块名转回文件路径（按语言）"""
        if self.language == "python":
            return f"{module.replace('.', '/')}.py"
        if self.language in ("javascript", "typescript"):
            # 简单回退：保留原样（实际可能需特殊处理 index.*）
            return f"{module}.js"
        if self.language == "go":
            # Go import 路径通常就是仓库路径，无简单映射
            return module
        if self.language == "rust":
            return f"src/{module.replace('::', '/')}.rs"
        if self.language == "java":
            return f"{module.replace('.', '/')}.java"
        return module

    # ---------- 测试约定分析 ----------

    def _analyze_test_patterns(self, root: Path) -> TestPatterns:
        """分析测试约定（多语言）"""
        patterns = TestPatterns(
            naming_convention=self.TEST_FRAMEWORK_NAMING.get(self.language, "test_*.py"),
        )

        # 查找测试目录
        if self.profile_rules.test_dir_names:
            test_dirs: List[str] = []
            for dirpath, dirnames, _ in os.walk(root):
                dirnames[:] = [
                    d for d in dirnames
                    if not d.startswith('.')
                    and d not in _COMMON_SKIP_DIRS
                    and d not in self.profile_rules.skip_dirs
                ]
                if self._is_test_dir(dirpath):
                    test_dirs.append(os.path.relpath(dirpath, root))
            if test_dirs:
                patterns.test_location = test_dirs[0]

        # 分析测试文件命名（按语言）
        test_files: List[Path] = []
        for src_file in self._iter_source_files(root):
            if self._is_test_file(src_file):
                test_files.append(src_file)

        if test_files:
            # 按语言提取主要命名约定
            patterns.naming_convention = self._detect_naming_convention(test_files)

        # 检测 fixture 使用
        patterns.fixture_usage = self._detect_fixture_usage(root, test_files)

        return patterns

    def _detect_naming_convention(self, test_files: List[Path]) -> str:
        """按语言规则检测测试文件命名约定"""
        if self.language == "python":
            prefix = sum(1 for f in test_files if f.name.startswith("test_"))
            suffix = sum(1 for f in test_files if f.name.endswith("_test.py"))
            return "test_*.py" if prefix >= suffix else "*_test.py"
        if self.language in ("javascript", "typescript"):
            spec = sum(1 for f in test_files if ".spec." in f.name)
            test = sum(1 for f in test_files if ".test." in f.name)
            return "*.spec.js" if spec >= test else "*.test.js"
        if self.language == "go":
            return "*_test.go"
        if self.language == "rust":
            return "*_test.rs"
        if self.language == "java":
            test = sum(1 for f in test_files if f.name.endswith("Test.java"))
            it = sum(1 for f in test_files if f.name.endswith("IT.java"))
            return "*Test.java" if test >= it else "*IT.java"
        return self.profile_rules.test_file_globs[0]

    def _detect_fixture_usage(self, root: Path, test_files: List[Path]) -> bool:
        """按语言检测 fixture/配置使用"""
        # 方法 1：检查 fixture 配置文件
        if self.profile_rules.test_fixture_files:
            for fixture_name in self.profile_rules.test_fixture_files:
                for src_file in self._iter_source_files(root):
                    if src_file.name == fixture_name:
                        return True

        # 方法 2：在测试文件/源文件中搜索 marker
        marker = self.profile_rules.test_fixture_marker
        if not marker:
            return False

        # 仅在测试文件中搜索
        for test_file in test_files[:10]:  # 限制 10 个
            try:
                with open(test_file, 'r', encoding='utf-8', errors='ignore') as f:
                    if marker in f.read():
                        return True
            except Exception:
                continue

        return False

    # ---------- 缓存 ----------

    def _generate_cache_key(self, root: Path) -> str:
        """生成缓存键（基于语言 + 文件修改时间）"""
        hasher = hashlib.md5()
        hasher.update(f"lang:{self.language}".encode())
        for src_file in sorted(self._iter_source_files(root)):
            try:
                stat = src_file.stat()
                hasher.update(f"{src_file}:{stat.st_mtime}".encode())
            except Exception as e:
                logger.debug(f"缓存键生成失败 {src_file}: {e}")
                continue
        return hasher.hexdigest()

    def _load_cache(self, cache_key: str) -> Optional[ProjectProfile]:
        """加载缓存的项目指纹"""
        cache_file = self.cache_dir / f"{cache_key}.json"
        if not cache_file.exists():
            return None
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            profile = ProjectProfile(
                architecture=ArchitectureInfo(**data.get('architecture', {})),
                risk_areas=RiskAreas(**data.get('risk_areas', {})),
                test_patterns=TestPatterns(**data.get('test_patterns', {})),
                generated_at=data.get('generated_at', ''),
                cache_key=cache_key,
                language=data.get('language', 'python'),
            )
            return profile
        except Exception as e:
            logger.warning(f"加载缓存失败：{e}")
            return None

    def _save_cache(self, profile: ProjectProfile):
        """保存项目指纹到缓存"""
        cache_file = self.cache_dir / f"{profile.cache_key}.json"
        try:
            data = {
                'architecture': {
                    'pattern': profile.architecture.pattern,
                    'layers': profile.architecture.layers,
                    'aggregate_classes': profile.architecture.aggregate_classes,
                    'export_modules': profile.architecture.export_modules,
                    'language': profile.architecture.language,
                },
                'risk_areas': {
                    'high_dependency': profile.risk_areas.high_dependency,
                    'security_critical': profile.risk_areas.security_critical,
                    'data_critical': profile.risk_areas.data_critical,
                },
                'test_patterns': {
                    'test_location': profile.test_patterns.test_location,
                    'naming_convention': profile.test_patterns.naming_convention,
                    'fixture_usage': profile.test_patterns.fixture_usage,
                    'framework': profile.test_patterns.framework,
                },
                'generated_at': profile.generated_at,
                'language': profile.language,
            }
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存缓存失败：{e}")


# ==================== 自动语言检测 ====================

def detect_project_language(project_root: str) -> str:
    """根据项目根目录的文件分布自动检测主语言

    Returns:
        语言字符串（python/javascript/go/rust/java），无法识别时返回 'python'
    """
    root = Path(project_root)
    if not root.exists():
        return "python"

    counts: Dict[str, int] = defaultdict(int)
    # 优先看 lockfile/manifest
    manifest_hints = {
        "go.mod": "go", "go.sum": "go",
        "Cargo.toml": "rust", "Cargo.lock": "rust",
        "package.json": "javascript", "tsconfig.json": "javascript",
        "pyproject.toml": "python", "requirements.txt": "python", "setup.py": "python",
        "pom.xml": "java", "build.gradle": "java",
    }
    for filename, lang in manifest_hints.items():
        if (root / filename).exists():
            counts[lang] += 100  # manifest 权重极高

    # 次看文件扩展名
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part.startswith('.') or part in _COMMON_SKIP_DIRS for part in path.parts):
            continue
        ext = path.suffix.lower()
        if ext in (".py",):
            counts["python"] += 1
        elif ext in (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"):
            counts["javascript"] += 1
        elif ext == ".go":
            counts["go"] += 1
        elif ext == ".rs":
            counts["rust"] += 1
        elif ext == ".java":
            counts["java"] += 1

    if not counts:
        return "python"
    return max(counts.items(), key=lambda x: x[1])[0]


# 延迟导入 ast 以避免在 JavaScript/Go 等场景下不必要的开销
import ast  # noqa: E402
