"""
智能测试过滤模块

基于目录关联、高依赖模块和冒烟测试三层策略，选择最小但充分的测试集。
"""
import logging
import re
from pathlib import Path
from typing import List, Optional, Sequence

from app.utils.performance_metrics import metrics_collector
from .impact_analyzer import ChangeSummary
from .project_profiler import ProjectProfile

logger = logging.getLogger(__name__)


# 各语言测试文件命名；缺失时回退到 profile 检测出的 naming_convention
_TEST_FILE_GLOBS = {
    "python": ("test_*.py", "*_test.py"),
    "javascript": (
        "*.test.js", "*.spec.js", "*.test.jsx", "*.spec.jsx",
        "*.test.ts", "*.spec.ts", "*.test.tsx", "*.spec.tsx",
    ),
    "typescript": (
        "*.test.js", "*.spec.js", "*.test.jsx", "*.spec.jsx",
        "*.test.ts", "*.spec.ts", "*.test.tsx", "*.spec.tsx",
    ),
    "go": ("*_test.go",),
    "rust": ("*_test.rs",),
    "java": ("*Test.java", "*Tests.java", "*IT.java", "*Spec.java"),
}

# 源码根目录名，映射测试目录时跳过
_SOURCE_ROOT_NAMES = ("src", "app", "lib", "source")

# 测试文件名去掉测试词缀的规则（作用于去扩展名后的 stem）
_TEST_AFFIX_PATTERNS = (
    (re.compile(r"^test_(.+)$"), 1),
    (re.compile(r"^(.+)_test$"), 1),
    (re.compile(r"^(.+)\.(?:test|spec)$"), 1),
    (re.compile(r"^(.+?)(?:Tests?|IT|Spec)$"), 1),
)


def _test_source_stem(test_name: str) -> str:
    """从测试文件名反推被测源文件 stem（小写）。"""
    stem = Path(test_name).stem
    for pattern, group in _TEST_AFFIX_PATTERNS:
        match = pattern.match(stem)
        if match:
            stem = match.group(group)
            break
    return stem.lower()


def _path_boundary_match(risk: str, path: str) -> bool:
    """按路径边界判断 risk 是否指向 path，避免 auth 误命中 my_author。"""
    risk_norm = risk.replace("\\", "/").strip("/")
    path_norm = path.replace("\\", "/").strip("/")
    if not risk_norm or not path_norm:
        return False
    if risk_norm == path_norm:
        return True
    return (
        path_norm.endswith("/" + risk_norm)
        or risk_norm.endswith("/" + path_norm)
    )


class TestSelector:
    """智能测试选择器"""

    DEFAULT_SMOKE_KEYWORDS = ("smoke", "core", "basic", "critical", "essential")

    def __init__(
        self,
        project_root: str,
        smoke_keywords: Optional[Sequence[str]] = None,
    ):
        self.project_root = Path(project_root)
        self.smoke_keywords = tuple(
            kw.lower() for kw in (smoke_keywords or self.DEFAULT_SMOKE_KEYWORDS)
        )

    def select_tests(self, changes: ChangeSummary, profile: ProjectProfile) -> List[str]:
        """
        选择相关测试用例

        Args:
            changes: 变更摘要
            profile: 项目指纹

        Returns:
            测试文件路径列表
        """
        start_time = metrics_collector.start_timer('TestSelector')
        selected_tests = []

        # 第 1 层：同源文件关联测试
        same_dir_tests = self._select_same_directory_tests(changes.modified_files, profile)
        selected_tests.extend(same_dir_tests)

        # 第 2 层：高依赖模块测试
        high_dep_tests = self._select_high_dependency_tests(changes, profile)
        selected_tests.extend(high_dep_tests)

        # 第 3 层：冒烟测试
        smoke_tests = self._select_smoke_tests(profile)
        selected_tests.extend(smoke_tests)

        # 去重
        unique_tests = list(dict.fromkeys(selected_tests))

        # 记录测试覆盖率
        total_tests = len(self._iter_all_tests(profile))
        coverage = (len(unique_tests) / total_tests * 100) if total_tests > 0 else 0
        metrics_collector.record_test_coverage('TestSelector', coverage)
        metrics_collector.end_timer('TestSelector', start_time, 'select_tests', {'selected': len(unique_tests), 'coverage': coverage})

        # 回退逻辑：如果没有选择到任何测试，运行全部测试
        if not unique_tests:
            logger.warning("智能测试过滤未选择到任何测试，回退到运行全部测试")
            unique_tests = [self._to_rel(tf) for tf in self._iter_all_tests(profile)]

        logger.info(
            f"智能测试过滤完成 | "
            f"同目录测试：{len(same_dir_tests)} | "
            f"高依赖测试：{len(high_dep_tests)} | "
            f"冒烟测试：{len(smoke_tests)} | "
            f"最终选择：{len(unique_tests)}"
        )

        return unique_tests

    def _select_same_directory_tests(self, modified_files: List[str], profile: ProjectProfile) -> List[str]:
        """
        选择与修改文件关联的测试

        匹配策略（按优先级）：
        1. 修改文件本身即测试文件 → 直接选中
        2. 文件名对应：`foo.py` ↔ `test_foo.py` / `foo_test.py` / `foo.test.js` 等
        3. 目录对应：源码目录前缀替换为测试目录后，同目录下的测试文件

        Args:
            modified_files: 修改的文件列表
            profile: 项目指纹

        Returns:
            测试文件列表
        """
        tests = []
        all_tests = self._iter_all_tests(profile)
        all_test_lookup = {self._to_rel(tf): tf for tf in all_tests}

        modified_stems = set()
        modified_test_files = []
        for file_path in modified_files:
            rel = file_path.replace("\\", "/")
            if rel in all_test_lookup:
                modified_test_files.append(rel)
            modified_stems.add(Path(rel).stem.lower())

        for rel in modified_test_files:
            tests.append(rel)

        # 文件名对应：测试文件 stem 去掉测试词缀后与源文件 stem 一致
        for tf in all_tests:
            if _test_source_stem(tf.name) in modified_stems:
                tests.append(self._to_rel(tf))

        # 目录对应：镜像目录内的测试文件
        for file_path in modified_files:
            mirrored = self._mirrored_test_dir(file_path, profile)
            if mirrored is None:
                continue
            for glob in self._test_globs(profile):
                for tf in mirrored.glob(glob):
                    tests.append(self._to_rel(tf))

        return list(dict.fromkeys(tests))

    def _select_high_dependency_tests(self, changes: ChangeSummary, profile: ProjectProfile) -> List[str]:
        """
        选择与高风险模块相关的测试

        Args:
            changes: 变更摘要
            profile: 项目指纹

        Returns:
            测试文件列表
        """
        tests = []
        risk_files = profile.risk_areas.high_dependency + profile.risk_areas.security_critical

        # 按路径边界匹配高风险模块，避免子串假阳性
        modified_risk_files = [
            f for f in changes.modified_files
            if any(_path_boundary_match(risk, f) for risk in risk_files)
        ]
        if not modified_risk_files:
            return tests

        # 高风险模块影响面大：除同名测试外，扩大选择其镜像测试目录下的全部测试
        tests.extend(self._select_same_directory_tests(modified_risk_files, profile))
        for file_path in modified_risk_files:
            mirrored = self._mirrored_test_dir(file_path, profile)
            if mirrored is None:
                continue
            # 仅在镜像目录严格位于测试根目录之下时扩大范围，避免退化为全量
            test_root = self.project_root / profile.test_patterns.test_location
            if test_root in mirrored.parents:
                for tf in self._iter_dir_tests(mirrored, profile):
                    tests.append(self._to_rel(tf))

        return list(dict.fromkeys(tests))

    def _select_smoke_tests(self, profile: ProjectProfile) -> List[str]:
        """
        选择冒烟测试

        Args:
            profile: 项目指纹

        Returns:
            测试文件列表（最多 10 个）
        """
        tests = []

        # 优先选择名称包含冒烟关键字的测试
        for tf in self._iter_all_tests(profile):
            if any(kw in tf.name.lower() for kw in self.smoke_keywords):
                tests.append(self._to_rel(tf))
                if len(tests) >= 10:
                    break

        return tests[:10]

    def _iter_all_tests(self, profile: ProjectProfile) -> List[Path]:
        """遍历测试根目录下所有测试文件（按语言 glob）。"""
        test_root = self.project_root / profile.test_patterns.test_location
        return self._iter_dir_tests(test_root, profile)

    def _iter_dir_tests(self, directory: Path, profile: ProjectProfile) -> List[Path]:
        """遍历指定目录下所有测试文件（按语言 glob）。"""
        if not directory.exists() or not directory.is_dir():
            return []
        test_files = []
        for glob in self._test_globs(profile):
            test_files.extend(directory.rglob(glob))
        return sorted(set(test_files))

    def _test_globs(self, profile: ProjectProfile) -> Sequence[str]:
        """返回该语言对应的测试文件 glob；未知语言回退 naming_convention。"""
        globs = _TEST_FILE_GLOBS.get(getattr(profile, "language", ""))
        if globs:
            return globs
        return (profile.test_patterns.naming_convention,)

    def _mirrored_test_dir(self, file_path: str, profile: ProjectProfile) -> Optional[Path]:
        """源码目录映射到测试目录；目录不存在时返回 None。"""
        parts = list(Path(file_path.replace("\\", "/")).parts[:-1])
        while parts and parts[0] in _SOURCE_ROOT_NAMES:
            parts.pop(0)
        # 源文件位于源码根目录时，镜像目录即测试根目录——交由文件名对应处理
        if not parts:
            return None
        candidate = self.project_root / profile.test_patterns.test_location
        candidate = candidate.joinpath(*parts)
        if candidate.exists() and candidate.is_dir():
            return candidate
        return None

    def _to_rel(self, path: Path) -> str:
        return str(path.relative_to(self.project_root))

    def _select_all_tests(self, profile: ProjectProfile) -> List[str]:
        """选择所有测试（兼容旧接口，内部走 _iter_all_tests）。"""
        tests = []
        for tf in self._iter_all_tests(profile):
            tests.append(self._to_rel(tf))
        return tests
