"""FrameworkDetector 误检修复回归测试（FD1/FD2/FD4/FD6/FD9）。"""
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from app.agent.framework_detector import FrameworkDetector


@pytest.fixture
def project_dir():
    path = Path(tempfile.mkdtemp(prefix="fd_fix_"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _detect(project_dir: Path):
    return FrameworkDetector().detect(project_dir)


def _write_package_json(project_dir: Path, payload: dict) -> None:
    (project_dir / "package.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


class TestJavaScriptRunnerDetection:
    """FD2：test script 不等于 jest。"""

    def test_node_test_script_is_not_jest(self, project_dir):
        _write_package_json(project_dir, {"scripts": {"test": "node --test"}})

        config = _detect(project_dir)

        assert config.language == "javascript"
        assert config.framework == "node_test"
        # node --test 输出为 TAP，不能按 jest JSON 解析。
        assert config.output_format == "generic_text"

    def test_mocha_dependency_is_detected(self, project_dir):
        _write_package_json(
            project_dir,
            {"scripts": {"test": "mocha"}, "devDependencies": {"mocha": "^10.0.0"}},
        )

        config = _detect(project_dir)

        assert config.framework == "mocha"
        assert config.output_format == "generic_text"

    def test_ava_dependency_is_detected(self, project_dir):
        _write_package_json(
            project_dir,
            {"scripts": {"test": "ava"}, "devDependencies": {"ava": "^6.0.0"}},
        )

        config = _detect(project_dir)

        assert config.framework == "ava"
        assert config.output_format == "generic_text"

    def test_unknown_runner_is_not_labelled_jest(self, project_dir):
        _write_package_json(project_dir, {"scripts": {"test": "some-runner"}})

        config = _detect(project_dir)

        assert config.language == "javascript"
        assert config.framework == "npm"
        assert config.output_format == "generic_text"

    def test_empty_test_script_is_ignored(self, project_dir):
        _write_package_json(project_dir, {"scripts": {"test": ""}})

        config = _detect(project_dir)

        # 空 test script 不构成 JavaScript 证据，回落默认 pytest。
        assert config.framework == "pytest"

    def test_jest_dependency_still_detected(self, project_dir):
        _write_package_json(
            project_dir,
            {"scripts": {"test": "jest"}, "devDependencies": {"jest": "^29.0.0"}},
        )

        config = _detect(project_dir)

        assert config.framework == "jest"
        assert config.output_format == "jest_json"

    def test_vitest_uses_vitest_output_format(self, project_dir):
        _write_package_json(
            project_dir,
            {"scripts": {"test": "vitest"}, "devDependencies": {"vitest": "^1.0.0"}},
        )

        config = _detect(project_dir)

        assert config.framework == "vitest"
        assert config.output_format == "vitest_json"


class TestExplicitConfigDetection:
    """FD4：显式配置文件必须真的声明 pytest。"""

    def test_pyproject_comment_is_not_pytest_config(self, project_dir):
        (project_dir / "pyproject.toml").write_text(
            "# pytest will be used\n[project]\nname = \"demo\"\n",
            encoding="utf-8",
        )

        assert FrameworkDetector._pyproject_declares_pytest(
            project_dir / "pyproject.toml"
        ) is False

    def test_pyproject_pytest_section_is_detected(self, project_dir):
        (project_dir / "pyproject.toml").write_text(
            "[tool.pytest.ini_options]\naddopts = \"-q\"\n",
            encoding="utf-8",
        )

        assert FrameworkDetector._pyproject_declares_pytest(
            project_dir / "pyproject.toml"
        ) is True

    def test_pyproject_invalid_toml_is_not_pytest(self, project_dir):
        (project_dir / "pyproject.toml").write_text(
            "[tool.pytest.ini_options\nbroken\n",
            encoding="utf-8",
        )

        assert FrameworkDetector._pyproject_declares_pytest(
            project_dir / "pyproject.toml"
        ) is False

    def test_tox_without_pytest_does_not_force_pytest(self, project_dir):
        (project_dir / "tox.ini").write_text(
            "[testenv]\ncommands = nose\n", encoding="utf-8"
        )
        (project_dir / "sample_test.go").write_text(
            "package main\n", encoding="utf-8"
        )

        config = _detect(project_dir)

        assert config.framework == "go_test"

    def test_tox_with_pytest_is_detected(self, project_dir):
        (project_dir / "tox.ini").write_text(
            "[testenv]\ncommands = pytest -q\n", encoding="utf-8"
        )

        config = _detect(project_dir)

        assert config.framework == "pytest"


class TestMakefileDetection:
    """FD6：Makefile 只认 test target。"""

    def test_makefile_variable_named_test_is_not_cpp(self, project_dir):
        (project_dir / "Makefile").write_text(
            "VERSION = test\nall:\n\ttrue\n", encoding="utf-8"
        )

        config = _detect(project_dir)

        assert config.framework != "make"

    def test_makefile_test_target_is_cpp(self, project_dir):
        (project_dir / "Makefile").write_text("test:\n\t./run_tests\n", encoding="utf-8")

        config = _detect(project_dir)

        assert config.framework == "make"
