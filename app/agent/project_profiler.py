"""
项目模式识别模块

自动分析项目的架构模式、分层结构、高风险区域和测试约定，生成项目指纹。
"""
import ast
import json
import os
import time
import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional
from collections import defaultdict

from app.utils.performance_metrics import metrics_collector

logger = logging.getLogger(__name__)


@dataclass
class ArchitectureInfo:
    """架构信息"""
    pattern: str = "unknown"  # layered, mvc, mixin-heavy, flat
    layers: Dict[str, List[str]] = field(default_factory=dict)
    aggregate_classes: List[str] = field(default_factory=list)
    export_modules: List[str] = field(default_factory=list)


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


@dataclass
class ProjectProfile:
    """项目指纹"""
    architecture: ArchitectureInfo = field(default_factory=ArchitectureInfo)
    risk_areas: RiskAreas = field(default_factory=RiskAreas)
    test_patterns: TestPatterns = field(default_factory=TestPatterns)
    generated_at: str = ""
    cache_key: str = ""


class ProjectProfiler:
    """项目模式分析器"""

    # 安全关键字
    SECURITY_KEYWORDS = {
        'auth', 'permission', 'security', 'validate', 'verify',
        'token', 'password', 'credential', 'session', 'middleware',
        'encrypt', 'decrypt', 'hash', 'signature'
    }

    # 数据库关键字
    DATABASE_KEYWORDS = {
        'database', 'session', 'transaction', 'commit', 'rollback',
        'query', 'orm', 'model', 'migration', 'db'
    }

    def __init__(self, project_root: str, cache_dir: Optional[str] = None):
        self.project_root = Path(project_root)
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

        # 检查缓存
        cache_key = self._generate_cache_key(root)
        cached_profile = self._load_cache(cache_key)
        if cached_profile:
            metrics_collector.record_cache_hit('ProjectProfiler')
            logger.info(f"使用缓存的项目指纹 | cache_key: {cache_key[:8]}...")
            return cached_profile

        metrics_collector.record_cache_miss('ProjectProfiler')

        start_time = metrics_collector.start_timer('ProjectProfiler')
        logger.info(f"开始项目模式识别 | 项目：{root}")

        profile = ProjectProfile()
        profile.cache_key = cache_key

        # 分析架构模式
        profile.architecture = self._analyze_architecture(root)

        # 分析高风险区域
        profile.risk_areas = self._analyze_risk_areas(root)

        # 分析测试约定
        profile.test_patterns = self._analyze_test_patterns(root)

        profile.generated_at = time.strftime('%Y-%m-%d %H:%M:%S')

        # 保存缓存
        self._save_cache(profile)

        elapsed = time.time() - start_time
        metrics_collector.end_timer('ProjectProfiler', start_time, 'profile', {'file_count': sum(1 for _ in root.rglob('*.py'))})

        logger.info(
            f"项目模式识别完成 | "
            f"架构模式：{profile.architecture.pattern} | "
            f"高风险文件：{len(profile.risk_areas.high_dependency)} | "
            f"耗时：{elapsed:.2f}s"
        )

        return profile

    def _analyze_architecture(self, root: Path) -> ArchitectureInfo:
        """分析架构模式"""
        arch = ArchitectureInfo()

        # 识别分层架构
        layers = self._detect_layers(root)
        if layers:
            arch.pattern = "layered"
            arch.layers = layers

        # 识别 Mixin 模式
        mixin_classes = self._detect_mixins(root)
        if mixin_classes:
            if arch.pattern == "unknown":
                arch.pattern = "mixin-heavy"
            arch.aggregate_classes = mixin_classes

        # 识别聚合导出模块
        export_modules = self._detect_export_modules(root)
        arch.export_modules = export_modules

        return arch

    def _detect_layers(self, root: Path) -> Dict[str, List[str]]:
        """检测分层架构"""
        layer_patterns = {
            'api': ['api', 'router', 'controller', 'view', 'endpoint'],
            'service': ['service', 'business', 'logic', 'usecase'],
            'repository': ['repository', 'repo', 'dao', 'storage', 'data'],
            'model': ['model', 'entity', 'domain', 'schema'],
        }

        layers = {}

        for dirpath, dirnames, filenames in os.walk(root):
            # 跳过隐藏目录和常见非代码目录
            dirnames[:] = [d for d in dirnames if not d.startswith('.') and d not in ['node_modules', '__pycache__', 'venv', 'env']]

            dir_name = os.path.basename(dirpath).lower()

            for layer_name, patterns in layer_patterns.items():
                if any(p in dir_name for p in patterns):
                    rel_path = os.path.relpath(dirpath, root)
                    if rel_path not in layers.get(layer_name, []):
                        layers.setdefault(layer_name, []).append(rel_path)

        return layers if layers else {}

    def _detect_mixins(self, root: Path) -> List[str]:
        """检测 Mixin 类"""
        mixins = []

        for py_file in root.rglob('*.py'):
            # 跳过隐藏目录和常见非代码目录
            if any(part.startswith('.') or part in ['node_modules', '__pycache__', 'venv', 'env'] for part in py_file.parts):
                continue

            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    tree = ast.parse(content)

                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        # 类名包含 Mixin
                        if 'Mixin' in node.name or 'Mixin' in str(node.name):
                            rel_path = os.path.relpath(py_file, root)
                            mixins.append(f"{rel_path}:{node.name}")

            except Exception as e:
                logger.debug(f"项目分析失败：{e}")
                continue

        return mixins[:20]  # 限制数量，避免过多

    def _detect_export_modules(self, root: Path) -> List[str]:
        """检测聚合导出模块（__init__.py 只包含 from .x import y）"""
        export_modules = []

        for init_file in root.rglob('__init__.py'):
            # 跳过隐藏目录
            if any(part.startswith('.') for part in init_file.parts):
                continue

            try:
                with open(init_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    tree = ast.parse(content)

                # 检查是否只有导入语句
                has_only_imports = True
                import_count = 0

                for node in ast.walk(tree):
                    if isinstance(node, (ast.Import, ast.ImportFrom)):
                        import_count += 1
                    elif isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Assign)):
                        has_only_imports = False
                        break

                if has_only_imports and import_count > 0:
                    rel_path = os.path.relpath(init_file, root)
                    export_modules.append(rel_path)

            except Exception as e:
                logger.debug(f"项目分析失败：{e}")
                continue

        return export_modules

    def _analyze_risk_areas(self, root: Path) -> RiskAreas:
        """分析高风险区域"""
        risks = RiskAreas()

        # 统计文件被导入次数
        import_counts = defaultdict(int)

        for py_file in root.rglob('*.py'):
            if any(part.startswith('.') or part in ['node_modules', '__pycache__', 'venv', 'env'] for part in py_file.parts):
                continue

            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # 简单统计 import 语句
                for line in content.split('\n'):
                    line = line.strip()
                    if line.startswith('from ') or line.startswith('import '):
                        # 提取模块名
                        parts = line.split()
                        if len(parts) >= 2:
                            module = parts[1].split('.')[0]
                            import_counts[module] += 1

            except Exception as e:
                logger.debug(f"项目分析失败：{e}")
                continue

        # 被 5 个以上文件依赖的模块标记为高风险
        high_dep_threshold = 5
        risks.high_dependency = [
            f"{module}.py" for module, count in import_counts.items()
            if count >= high_dep_threshold
        ]

        # 搜索安全关键字
        security_files = set()
        data_files = set()

        for py_file in root.rglob('*.py'):
            if any(part.startswith('.') or part in ['node_modules', '__pycache__', 'venv', 'env'] for part in py_file.parts):
                continue

            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read().lower()

                if any(kw in content for kw in self.SECURITY_KEYWORDS):
                    rel_path = os.path.relpath(py_file, root)
                    security_files.add(rel_path)

                if any(kw in content for kw in self.DATABASE_KEYWORDS):
                    rel_path = os.path.relpath(py_file, root)
                    data_files.add(rel_path)

            except Exception as e:
                logger.debug(f"项目分析失败：{e}")
                continue

        risks.security_critical = list(security_files)[:20]
        risks.data_critical = list(data_files)[:20]

        return risks

    def _analyze_test_patterns(self, root: Path) -> TestPatterns:
        """分析测试约定"""
        patterns = TestPatterns()

        # 查找测试目录
        test_dirs = []
        for dirpath, dirnames, filenames in os.walk(root):
            if any(d in dirpath.lower() for d in ['tests', 'test']):
                test_dirs.append(os.path.relpath(dirpath, root))

        if test_dirs:
            patterns.test_location = test_dirs[0]

        # 分析命名约定
        test_files = list(root.rglob('test_*.py')) + list(root.rglob('*_test.py'))
        if test_files:
            # 统计哪种命名更多
            test_prefix = sum(1 for f in test_files if f.name.startswith('test_'))
            test_suffix = sum(1 for f in test_files if f.name.endswith('_test.py'))
            patterns.naming_convention = "test_*.py" if test_prefix >= test_suffix else "*_test.py"

        # 检测 fixture 使用
        conftest_files = list(root.rglob('conftest.py'))
        patterns.fixture_usage = len(conftest_files) > 0

        # 搜索 @pytest.fixture
        if not patterns.fixture_usage:
            for py_file in root.rglob('*.py'):
                try:
                    with open(py_file, 'r', encoding='utf-8') as f:
                        if '@pytest.fixture' in f.read():
                            patterns.fixture_usage = True
                            break
                except Exception as e:
                    logger.debug(f"项目分析失败：{e}")
                    continue

        return patterns

    def _generate_cache_key(self, root: Path) -> str:
        """生成缓存键（基于文件修改时间）"""
        hasher = hashlib.md5()

        for py_file in sorted(root.rglob('*.py')):
            if any(part.startswith('.') or part in ['node_modules', '__pycache__', 'venv', 'env'] for part in py_file.parts):
                continue
            try:
                stat = py_file.stat()
                hasher.update(f"{py_file}:{stat.st_mtime}".encode())
            except Exception as e:
                logger.debug(f"项目分析失败：{e}")
                continue

        return hasher.hexdigest()

    def _load_cache(self, cache_key: str) -> Optional[ProjectProfile]:
        """加载缓存的项目指纹"""
        cache_file = self.cache_dir / f"{cache_key}.json"

        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                profile = ProjectProfile(
                    architecture=ArchitectureInfo(**data.get('architecture', {})),
                    risk_areas=RiskAreas(**data.get('risk_areas', {})),
                    test_patterns=TestPatterns(**data.get('test_patterns', {})),
                    generated_at=data.get('generated_at', ''),
                    cache_key=cache_key
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
                },
                'generated_at': profile.generated_at,
            }

            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.warning(f"保存缓存失败：{e}")
