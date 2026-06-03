"""
TestFrameworkConfig - 测试框架配置与预设

v4.8.0 新增：
- 6 种测试框架预设配置
- 每种框架的 Docker 镜像、命令、输出格式
- 支持自定义参数
"""

import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TestFrameworkConfig:
    """测试框架配置"""
    language: str
    framework: str
    test_command: str
    setup_commands: List[str] = field(default_factory=list)
    docker_image: str = ""
    output_format: str = ""
    custom_args: List[str] = field(default_factory=list)


FRAMEWORK_PRESETS: Dict[str, TestFrameworkConfig] = {
    "python_pytest": TestFrameworkConfig(
        language="python",
        framework="pytest",
        test_command="pytest -xvs --tb=short",
        setup_commands=["pip install -r requirements.txt"],
        docker_image="python:3.11-slim",
        output_format="pytest_xml",
    ),
    "javascript_jest": TestFrameworkConfig(
        language="javascript",
        framework="jest",
        test_command="npm test",
        setup_commands=["npm install"],
        docker_image="node:20-slim",
        output_format="jest_json",
    ),
    "java_maven": TestFrameworkConfig(
        language="java",
        framework="maven",
        test_command="mvn verify",
        setup_commands=["mvn dependency:resolve"],
        docker_image="maven:3.9-eclipse-temurin-17",
        output_format="junit_xml",
    ),
    "go_test": TestFrameworkConfig(
        language="go",
        framework="go_test",
        test_command="go test ./... -v",
        setup_commands=["go mod download"],
        docker_image="golang:1.22-alpine",
        output_format="go_json",
    ),
    "rust_cargo": TestFrameworkConfig(
        language="rust",
        framework="cargo",
        test_command="cargo test -- --nocapture",
        setup_commands=["cargo build"],
        docker_image="rust:1.77-slim",
        output_format="rust_text",
    ),
    "cpp_make": TestFrameworkConfig(
        language="cpp",
        framework="make",
        test_command="make test",
        setup_commands=["make build"],
        docker_image="gcc:13",
        output_format="cpp_text",
    ),
}


def get_framework_config(framework_key: str) -> Optional[TestFrameworkConfig]:
    """获取框架预设配置"""
    return FRAMEWORK_PRESETS.get(framework_key)


def get_default_config() -> TestFrameworkConfig:
    """获取默认配置 (pytest)"""
    return FRAMEWORK_PRESETS["python_pytest"]
