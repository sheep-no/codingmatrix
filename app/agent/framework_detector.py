"""
FrameworkDetector - 项目测试框架自动检测

v4.8.0 新增：
- 从项目元数据自动检测测试框架
- 检测优先级：显式配置 → 包清单 → 源文件模式 → 默认 pytest
- 支持 6 种语言/框架
"""

import json
import logging
import os
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


# 源文件模式扫描时跳过的依赖/构建目录，避免 vendored 文件造成误判（FD5）。
_EXCLUDED_SCAN_DIRS = {
    "node_modules", ".venv", "venv", "env", "vendor", "target",
    ".git", "dist", "build", "__pycache__", ".tox",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
}

# CI 配置关键词（带词边界），按此顺序收集命中（FD3）。
_CI_FRAMEWORK_PATTERNS = (
    ("python_pytest", re.compile(r"\bpytest\b")),
    ("javascript_jest", re.compile(r"\bjest\b|\bnpm\s+test\b|\byarn\s+test\b|\bpnpm\s+test\b")),
    ("java_maven", re.compile(r"\bmvn\b")),
    ("go_test", re.compile(r"\bgo\s+test\b")),
    ("rust_cargo", re.compile(r"\bcargo\s+test\b")),
)

# 源文件测试特征，顺序用于数量并列时的稳定裁决（FD5）。
_SOURCE_PATTERNS = (
    ("go_test", lambda path, name: name.endswith("_test.go")),
    ("java_maven", lambda path, name: name.endswith("Test.java")),
    ("python_pytest", lambda path, name: name.startswith("test_") and name.endswith(".py")),
    ("rust_cargo", lambda path, name: path.parent.name == "tests" and name.endswith(".rs")),
)


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

        workflows_dir = project_path / ".github" / "workflows"
        if workflows_dir.is_dir():
            # 扫描所有 workflow（*.yml / *.yaml），不再只认硬编码的 test.yml（FD7）。
            for workflow in sorted(workflows_dir.glob("*.y*ml")):
                content = workflow.read_text(encoding="utf-8", errors="ignore")
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
        """按源文件测试数量检测，数量最多的语言获胜。

        原实现按 go→java→py→rust 固定顺序返回首个命中，且 rglob 会扫到
        node_modules/.venv 等依赖目录：真实测试文件少时被 vendored 文件抢先（FD5）。
        现跳过依赖/构建目录，并按测试文件数量裁决，数量并列时沿用上述顺序。
        """
        counts = {key: 0 for key, _ in _SOURCE_PATTERNS}
        for path in self._iter_source_files(project_path):
            for key, predicate in _SOURCE_PATTERNS:
                if predicate(path, path.name):
                    counts[key] += 1
                    break

        matched = [(key, count) for key, count in counts.items() if count > 0]
        if not matched:
            return None
        # max 返回首个最大值，即并列时取 _SOURCE_PATTERNS 顺序中最靠前的语言。
        best_key = max(matched, key=lambda item: item[1])[0]
        return FRAMEWORK_PRESETS[best_key]

    @staticmethod
    def _iter_source_files(project_path: Path):
        """遍历项目文件，跳过依赖/构建目录（FD5）。"""
        for dirpath, dirnames, filenames in os.walk(project_path):
            dirnames[:] = [d for d in dirnames if d not in _EXCLUDED_SCAN_DIRS]
            for filename in filenames:
                yield Path(dirpath) / filename

    def _parse_ci_config(self, content: str) -> Optional[TestFrameworkConfig]:
        """从 CI 配置内容解析测试框架。

        原实现按固定顺序返回首个命中的关键词，monorepo 多语言 CI（同一文件含
        pytest 与 mvn 等多个 job）会被第一个关键词带偏（FD3）。现用词边界收集
        全部命中，唯一命中才返回；多语言命中返回 None，交由后续「按项目文件
        证据」的检查项裁决。
        """
        matched = [
            preset
            for preset, pattern in _CI_FRAMEWORK_PATTERNS
            if pattern.search(content)
        ]
        if len(matched) == 1:
            return FRAMEWORK_PRESETS[matched[0]]
        return None
