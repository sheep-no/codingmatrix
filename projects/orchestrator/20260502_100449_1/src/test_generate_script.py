# src/test_generate_script.py
"""
测试用例文件: 验证generate_script.py中的生成逻辑
"""

import pytest
from src.generate_script import generate_script
from src.utils import validate_script

def test_generate_python_script():
    """测试生成Python脚本的正确性"""
    # 测试正常生成Python脚本
    script_type = "python"
    content = "print('Hello, World!')"
    
    result = generate_script(script_type, content)
    
    # 验证脚本是否符合预期格式
    assert isinstance(result, str)
    assert result.startswith("#!/usr/bin/env python")
    assert "print('Hello, World!')" in result
    assert validate_script(result, script_type)
    
    # 测试生成带有函数定义的Python脚本
    script_type = "python"
    content = """
def add(a, b):
    return a + b
"""
    result = generate_script(script_type, content)
    assert "def add(a, b):" in result
    assert validate_script(result, script_type)

def test_generate_shell_script():
    """测试生成Shell脚本的正确性"""
    # 测试正常生成Shell脚本
    script_type = "shell"
    content = "echo 'Hello from Shell'"
    
    result = generate_script(script_type, content)
    
    # 验证脚本是否符合预期格式
    assert isinstance(result, str)
    assert result.startswith("#!/bin/sh")
    assert "echo 'Hello from Shell'" in result
    assert validate_script(result, script_type)
    
    # 测试生成包含条件判断的Shell脚本
    script_type = "shell"
    content = """
if [ -f "file.txt" ]; then
    echo "File exists"
fi
"""
    result = generate_script(script_type, content)
    assert "if [ -f \"file.txt\" ]; then" in result
    assert validate_script(result, script_type)

def test_invalid_script_type():
    """测试无效脚本类型时的异常处理"""
    with pytest.raises(ValueError, match="Unsupported script type: invalid_type"):
        generate_script("invalid_type", "test content")

def test_empty_content():
    """测试空内容时的异常处理"""
    with pytest.raises(ValueError, match="Content cannot be empty"):
        generate_script("python", "")

def test_generate_with_metadata():
    """测试生成包含元数据的脚本"""
    script_type = "python"
    content = "print('Main logic')"
    metadata = {
        "author": "Test User",
        "description": "This is a test script",
        "version": "1.0.0"
    }
    
    result = generate_script(script_type, content, metadata=metadata)
    
    # 验证元数据是否正确插入
    assert "# Author: Test User" in result
    assert "# Description: This is a test script" in result
    assert "# Version: 1.0.0" in result
    assert validate_script(result, script_type)

def test_script_generation_with_special_characters():
    """测试包含特殊字符的脚本生成"""
    script_type = "shell"
    content = 'echo "Special characters: $@&*!"'
    
    result = generate_script(script_type, content)
    
    # 验证特殊字符是否被正确转义
    assert 'echo "Special characters: $@&*!"' in result
    assert validate_script(result, script_type)

@pytest.mark.parametrize("script_type, content, expected_start", [
    ("python", "print(1+1)", "#!/usr/bin/env python"),
    ("shell", "ls -la", "#!/bin/sh"),
    ("bash", "echo $HOME", "#!/bin/bash"),
    ("powershell", "Write-Output 'Hello'", "#!/usr/bin/powershell")
])
def test_script shebang_line(script_type: str, content: str, expected_start: str):
    """测试不同脚本类型生成的shebang行"""
    result = generate_script(script_type, content)
    assert result.startswith(expected_start)