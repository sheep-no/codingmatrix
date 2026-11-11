"""aicloud 内容安全分析回归。

覆盖恶意模式检测、写操作告警、深度分析风险分级。历史缺陷：经典 bash
fork bomb 带空格写法 `:(){ :|:& };:` 未被识别，只因正则写死了无空格形态。
"""

import pytest

from app.utils.aicloud.content_analyzer import (
    analyze_content,
    check_malicious_pattern,
    deep_content_analysis,
    filter_file_content,
)


@pytest.mark.parametrize(
    "payload",
    [
        "rm -rf /",
        "rm -rf ~/",
        "rm -rf *",
        "rm -rf $HOME",
        "os.system('ls')",
        "os . system('ls')",
        "os.popen('ls')",
        "subprocess.call(['ls'])",
        "subprocess.run(['ls'])",
        "subprocess.Popen(['ls'])",
        "subprocess.check_call(['ls'])",
        "subprocess.check_output(['ls'])",
        "eval('1+1')",
        "exec('import os; os.system(\"ls\")')",
        "__import__('os').system('x')",
        "__import__('subprocess').run(['ls'])",
        "pty.spawn('/bin/sh')",
        "import socket; socket.socket().connect(('h', 1))",
    ],
)
def test_obvious_malicious_payloads_are_detected(payload):
    detected, found = check_malicious_pattern(payload)
    assert detected is True
    assert found


@pytest.mark.parametrize(
    "payload",
    [
        ":(){ :|:& };:",
        ":(){:|:&};:",
        " :(){ :|:& };: ",
        ": () { : | : & }; :",
    ],
)
def test_fork_bomb_variants_are_detected(payload):
    """回归：带空格的 fork bomb 与紧凑写法同样危险，必须识别。"""
    detected, _ = check_malicious_pattern(payload)
    assert detected is True


@pytest.mark.parametrize(
    "payload",
    [
        "print('hello')",
        "def add(a, b):\n    return a + b",
        "正常的中文内容",
        "The rm -rf command is dangerous (documentation only)",
        "",
    ],
)
def test_benign_content_is_not_flagged(payload):
    detected, found = check_malicious_pattern(payload)
    assert detected is False
    assert found == []


@pytest.mark.parametrize(
    "payload",
    [
        "foo() { bar | baz & };",
        "if (a) { b | c & }",
        "x = a | b & c",
        "def foo():\n    return a | b & c",
        "func main() { a | b & }",
    ],
)
def test_pipe_and_background_are_not_mistaken_for_fork_bomb(payload):
    """普通管道与后台运算不得被 fork bomb 规则误报。"""
    detected, _ = check_malicious_pattern(payload)
    assert detected is False


@pytest.mark.asyncio
async def test_analyze_content_empty_passes():
    passed, warnings = await analyze_content("", "read")
    assert passed is True
    assert warnings == []


@pytest.mark.asyncio
async def test_analyze_content_read_clean():
    passed, warnings = await analyze_content("print('hi')", "read")
    assert passed is True
    assert warnings == []


@pytest.mark.asyncio
async def test_analyze_content_write_warns():
    passed, warnings = await analyze_content("data", "write")
    assert passed is True
    assert warnings == ["File write requires review for safety"]


@pytest.mark.asyncio
async def test_analyze_content_malicious_blocks():
    passed, warnings = await analyze_content("subprocess.run(['rm', '-rf', '/'])", "write")
    assert passed is False
    assert any("Dangerous pattern detected" in warning for warning in warnings)


@pytest.mark.asyncio
async def test_deep_analysis_high_risk():
    result = await deep_content_analysis("os.system('rm -rf /')", "write", 1)
    assert result["passed"] is False
    assert result["risk_level"] == "high"
    assert result["action"] == "require_human_review"
    assert result["content_length"] == len("os.system('rm -rf /')")


@pytest.mark.asyncio
async def test_deep_analysis_medium_risk_on_write():
    result = await deep_content_analysis("harmless data", "write", 1)
    assert result["passed"] is True
    assert result["risk_level"] == "medium"
    assert result["action"] == "require_human_review"


@pytest.mark.asyncio
async def test_deep_analysis_low_risk_on_read():
    result = await deep_content_analysis("harmless data", "read", 1)
    assert result["passed"] is True
    assert result["risk_level"] == "low"
    assert result["action"] == "auto_approve"


def test_filter_file_content_delegates_to_sensitive_filter():
    assert isinstance(filter_file_content("password=abc123"), str)
