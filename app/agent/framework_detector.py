"""
FrameworkDetector - 项目测试框架自动检测

v4.8.0 新增：
- 从项目元数据自动检测测试框架
- 检测优先级：显式配置 → 包清单 → 源文件模式 → 默认 pytest
- 支持 6 种语言/框架
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.agent.test_framework_config import (
    TestFrameworkConfig,
    FRAMEWORK_PRESETS,
    get_default_config,
)

logger = logging.getLogger(__name__)


class FrameworkDetector:
    """
    项目测试框架自动检测器

    Detection priority:
    1. Explicit config (settings.json, tox.ini, .github/workflows)
    2. Package manifests (package.json, pom.xml, go.mod, Cargo.toml, Makefile)
    3. Source file patterns (*_test.go, *Test.java, test_*.py)
    4. Default fallback (pytest)
    """

    def detect(self, project_path: Path) -> TestFrameworkConfig:
        """
        自动检测项目的测试框架

        Args:
            project_path: 项目根目录

        Returns:
            匹配的 TestFrameworkConfig，未识别时返回默认 pytest
        """
        checks = [
            self._check_explicit_config,
            self._check_package_manifests,
            self._check_source_patterns,
        ]

        for check in checks:
            result = check(project_path)
            if result:
                logger.info(f"检测到测试框架: {result.framework} (language: {result.language})")
                return result

        logger.warning("未检测到测试框架，使用默认 pytest")
        return get_default_config()

    def _check_explicit_config(self, project_path: Path) -> Optional[TestFrameworkConfig]:
        """检查显式配置文件"""
        config_files = {
            "tox.ini": "python_pytest",
            "setup.cfg": "python_pytest",
            ".github/workflows/test.yml": None,
        }

        for file_name, preset_key in config_files.items():
            file_path = project_path / file_name
            if file_path.exists():
                if preset_key:
                    return FRAMEWORK_PRESETS.get(preset_key)

                content = file_path.read_text(encoding="utf-8", errors="ignore")
                return self._parse_ci_config(content)

        pyproject = project_path / "pyproject.toml"
        if pyproject.exists():
            content = pyproject.read_text(encoding="utf-8", errors="ignore")
            if "pytest" in content:
                return FRAMEWORK_PRESETS["python_pytest"]

        return None

    def _check_package_manifests(self, project_path: Path) -> Optional[TestFrameworkConfig]:
        """检查包清单文件"""
        package_json = project_path / "package.json"
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text(encoding="utf-8"))
                deps = data.get("dependencies", {})
                dev_deps = data.get("devDependencies", {})
                all_deps = {**deps, **dev_deps}

                if "jest" in all_deps or any(
                    k.startswith("jest") for k in all_deps
                ):
                    return FRAMEWORK_PRESETS["javascript_jest"]
                if "vitest" in all_deps:
                    config = FRAMEWORK_PRESETS["javascript_jest"]
                    return TestFrameworkConfig(
                        language="javascript",
                        framework="vitest",
                        test_command="npm run test",
                        setup_commands=["npm install"],
                        docker_image=config.docker_image,
                        output_format="jest_json",
                    )
                if "test" in data.get("scripts", {}):
                    return FRAMEWORK_PRESETS["javascript_jest"]
            except (json.JSONDecodeError, OSError):
                pass

        pom_xml = project_path / "pom.xml"
        if pom_xml.exists():
            return FRAMEWORK_PRESETS["java_maven"]

        build_gradle = project_path / "build.gradle"
        if build_gradle.exists():
            return TestFrameworkConfig(
                language="java",
                framework="gradle",
                test_command="gradle test",
                setup_commands=["gradle build"],
                docker_image="gradle:8.5-jdk17",
                output_format="junit_xml",
            )

        go_mod = project_path / "go.mod"
        if go_mod.exists():
            return FRAMEWORK_PRESETS["go_test"]

        cargo_toml = project_path / "Cargo.toml"
        if cargo_toml.exists():
            return FRAMEWORK_PRESETS["rust_cargo"]

        makefile = project_path / "Makefile"
        if makefile.exists():
            content = makefile.read_text(encoding="utf-8", errors="ignore")
            if "test" in content:
                return FRAMEWORK_PRESETS["cpp_make"]

        cmake = project_path / "CMakeLists.txt"
        if cmake.exists():
            return TestFrameworkConfig(
                language="cpp",
                framework="cmake",
                test_command="cmake --build . --target test",
                setup_commands=["cmake -B build", "cmake --build build"],
                docker_image="gcc:13",
                output_format="cpp_text",
            )

        return None

    def _check_source_patterns(self, project_path: Path) -> Optional[TestFrameworkConfig]:
        """检查源文件模式"""
        go_test_files = list(project_path.rglob("*_test.go"))
        if go_test_files:
            return FRAMEWORK_PRESETS["go_test"]

        java_test_files = list(project_path.rglob("*Test.java"))
        if java_test_files:
            return FRAMEWORK_PRESETS["java_maven"]

        py_test_files = list(project_path.rglob("test_*.py"))
        if py_test_files:
            return FRAMEWORK_PRESETS["python_pytest"]

        rust_test_files = list(project_path.rglob("tests/*.rs"))
        if rust_test_files:
            return FRAMEWORK_PRESETS["rust_cargo"]

        return None

    def _parse_ci_config(self, content: str) -> Optional[TestFrameworkConfig]:
        """从 CI 配置文件解析测试框架"""
        if "pytest" in content:
            return FRAMEWORK_PRESETS["python_pytest"]
        if "npm test" in content or "jest" in content:
            return FRAMEWORK_PRESETS["javascript_jest"]
        if "mvn" in content:
            return FRAMEWORK_PRESETS["java_maven"]
        if "go test" in content:
            return FRAMEWORK_PRESETS["go_test"]
        if "cargo test" in content:
            return FRAMEWORK_PRESETS["rust_cargo"]
        return None