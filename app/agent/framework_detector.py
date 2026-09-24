"""
FrameworkDetector - 项目测试框架自动检测

v4.8.0 新增：
- 从项目元数据自动检测测试框架
- 检测优先级：显式配置 → 包清单 → 源文件模式 → 默认 pytest
- 支持 6 种语言/框架
"""

import json
import logging
import re
import tomllib
from pathlib import Path
from typing import Optional

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
        for file_name in ("tox.ini", "setup.cfg"):
            file_path = project_path / file_name
            if file_path.exists():
                # 文件存在不等于配置了 pytest：必须真的出现 pytest（FD4）。
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                if "pytest" in content:
                    return FRAMEWORK_PRESETS["python_pytest"]

        test_workflow = project_path / ".github/workflows/test.yml"
        if test_workflow.exists():
            content = test_workflow.read_text(encoding="utf-8", errors="ignore")
            result = self._parse_ci_config(content)
            if result:
                return result

        pyproject = project_path / "pyproject.toml"
        if pyproject.exists() and self._pyproject_declares_pytest(pyproject):
            return FRAMEWORK_PRESETS["python_pytest"]

        return None

    @staticmethod
    def _pyproject_declares_pytest(pyproject: Path) -> bool:
        """判断 pyproject.toml 是否真的声明了 pytest 配置。

        原实现用 `"pytest" in content`，注释或描述里的 pytest 也会误判（FD4）。
        这里解析 TOML，以 `[tool.pytest...]` 配置节为准。
        """
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8", errors="ignore"))
        except (tomllib.TOMLDecodeError, OSError):
            return False
        tool = data.get("tool", {})
        return isinstance(tool, dict) and "pytest" in tool

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
                        output_format="vitest_json",
                    )
                test_script = data.get("scripts", {}).get("test", "")
                runner = self._detect_js_runner(all_deps, test_script)
                if runner:
                    return runner
                if test_script:
                    # 有 test script 但依赖里没有可识别的框架：仍执行 npm test，
                    # 但用通用文本解析，不再伪装成 jest（FD2）。
                    return TestFrameworkConfig(
                        language="javascript",
                        framework="npm",
                        test_command="npm test",
                        setup_commands=["npm install"],
                        docker_image=FRAMEWORK_PRESETS["javascript_jest"].docker_image,
                        output_format="generic_text",
                    )
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
            # 只认 test target，避免 `VERSION=test` 之类的变量/注释误判（FD6）。
            if re.search(r"(?m)^test\s*:", content):
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

    @staticmethod
    def _detect_js_runner(
        all_deps: dict, test_script: str
    ) -> Optional[TestFrameworkConfig]:
        """按依赖与 test script 识别 jest 之外的 JS 测试运行器（FD2）。"""
        docker_image = FRAMEWORK_PRESETS["javascript_jest"].docker_image

        def build(framework: str, command: str) -> TestFrameworkConfig:
            return TestFrameworkConfig(
                language="javascript",
                framework=framework,
                test_command="npm test" if test_script else command,
                setup_commands=["npm install"],
                docker_image=docker_image,
                output_format="generic_text",
            )

        if any(dep == "mocha" or dep.startswith("mocha") for dep in all_deps):
            return build("mocha", "npx mocha")
        if "ava" in all_deps:
            return build("ava", "npx ava")
        if re.search(r"\bnode\s+--test\b|\bnode\s+--experimental-test\b", test_script):
            return build("node_test", "node --test")
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
