"""FrameworkDetector CI 解析与源文件扫描修复回归测试（FD3/FD5/FD7）。"""
import shutil
import tempfile
from pathlib import Path

import pytest

from app.agent.framework_detector import FrameworkDetector


@pytest.fixture
def project_dir():
    path = Path(tempfile.mkdtemp(prefix="fd_ci_"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _detect(project_dir: Path):
    return FrameworkDetector().detect(project_dir)


def _write(project_dir: Path, relpath: str, content: str = "") -> None:
    path = project_dir / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestCiConfigParsing:
    """FD3：CI 关键词不能按固定顺序首命中。"""

    def test_single_framework_is_returned(self):
        detector = FrameworkDetector()

        config = detector._parse_ci_config("- run: mvn verify\n")

        assert config is not None
        assert config.framework == "maven"

    def test_multi_language_ci_is_ambiguous(self):
        detector = FrameworkDetector()

        content = "jobs:\n  py:\n    steps:\n      - run: pytest -q\n  java:\n    steps:\n      - run: mvn verify\n"

        assert detector._parse_ci_config(content) is None

    def test_keyword_requires_word_boundary(self):
        detector = FrameworkDetector()

        # `pytest_plugins` 不是 pytest 运行命令，词边界匹配应忽略。
        assert detector._parse_ci_config("- run: pytest_plugins\n") is None

    def test_npm_test_is_recognized(self):
        detector = FrameworkDetector()

        config = detector._parse_ci_config("- run: npm test\n")

        assert config is not None
        assert config.framework == "jest"


class TestWorkflowScanning:
    """FD7：扫描所有 workflow 文件，不限于 test.yml。"""

    def test_ci_yml_is_scanned(self, project_dir):
        _write(
            project_dir,
            ".github/workflows/ci.yml",
            "jobs:\n  test:\n    steps:\n      - run: go test ./...\n",
        )

        config = _detect(project_dir)

        assert config.framework == "go_test"

    def test_ci_yaml_is_scanned(self, project_dir):
        _write(
            project_dir,
            ".github/workflows/ci.yaml",
            "jobs:\n  test:\n    steps:\n      - run: cargo test\n",
        )

        config = _detect(project_dir)

        assert config.framework == "cargo"


class TestSourcePatternScanning:
    """FD5：跳过依赖目录并按测试文件数量裁决。"""

    def test_vendored_tests_do_not_win(self, project_dir):
        # 依赖目录里的 go 测试不应压过项目内真实的 rust 测试。
        _write(project_dir, "node_modules/dep/y_test.go", "package x\n")
        _write(project_dir, "tests/real.rs", "#[test]\nfn t() {}\n")

        config = _detect(project_dir)

        assert config.framework == "cargo"

    def test_majority_language_wins(self, project_dir):
        # 1 个 Java 测试 vs 3 个 Python 测试，应按数量取 Python。
        _write(project_dir, "src/OneTest.java", "class OneTest {}\n")
        _write(project_dir, "test_a.py")
        _write(project_dir, "test_b.py")
        _write(project_dir, "test_c.py")

        config = _detect(project_dir)

        assert config.framework == "pytest"

    def test_vendored_only_does_not_detect(self, project_dir):
        _write(project_dir, "venv/lib/test_vendor.py")

        # 依赖目录被跳过 → 无源文件证据 → 回落默认 pytest，而非「检测到」。
        assert FrameworkDetector()._check_source_patterns(project_dir) is None

    def test_tie_falls_back_to_declared_order(self, project_dir):
        # 各 1 个测试文件，并列时取 _SOURCE_PATTERNS 顺序（go 先于 py）。
        _write(project_dir, "a_test.go", "package x\n")
        _write(project_dir, "test_b.py")

        config = _detect(project_dir)

        assert config.framework == "go_test"
