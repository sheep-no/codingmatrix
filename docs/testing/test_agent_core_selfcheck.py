#!/usr/bin/env python3
"""
Agent Core 功能自检测试脚本
验证 Model Adapter 集成后 agent_core.py 的核心功能是否正常
"""
import sys
import asyncio
from pathlib import Path

# 添加路径
sys.path.insert(0, '/workspace')

print("=" * 70)
print("Agent Core 功能自检测试")
print("=" * 70)

# ==================== 测试 1: 基础导入 ====================
print("\n[测试 1/6] 基础模块导入...", end=" ")
try:
    from app.utils.agent_core import (
        ProjectGeneratorAgent,
        ToolRegistry,
        TokenEncoder
    )
    from app.schema.codeRequest import AgentConfig
    print("✅ PASS")
except Exception as e:
    print(f"❌ FAIL: {e}")
    sys.exit(1)

# ==================== 测试 2: Model Adapter 导入 ====================
print("\n[测试 2/6] Model Adapter 导入...", end=" ")
try:
    from app.adapter import ModelAdapter
    print("✅ PASS")
    print(f"          ModelAdapter 已加载")
except Exception as e:
    print(f"❌ FAIL: {e}")
    sys.exit(1)

# ==================== 测试 3: Model Adapter 初始化 ====================
print("\n[测试 3/6] Model Adapter 初始化...", end=" ")
try:
    models_to_test = [
        "Qwen/Qwen3.5-4B",
        "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
    ]
    for model_name in models_to_test:
        adapter = ModelAdapter(model_name)
        assert adapter is not None
        assert adapter.model_name == model_name
        print(f"\n          ✅ {model_name}: strict={adapter.config.require_strict_json}, few_shot={adapter.config.enable_few_shot}")
    print("          ✅ PASS")
except Exception as e:
    print(f"❌ FAIL: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ==================== 测试 4: System Prompt 构建 ====================
print("\n[测试 4/6] System Prompt 构建...", end=" ")
try:
    adapter = ModelAdapter("Qwen/Qwen3.5-4B")
    tools_schema = [
        {
            "name": "create_project_file",
            "description": "创建项目文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["file_path", "content"]
            }
        }
    ]
    prompt = adapter.build_system_prompt(tools_schema)
    assert len(prompt) > 0
    assert "create_project_file" in prompt
    print(f"✅ PASS (长度：{len(prompt)} 字符)")
except Exception as e:
    print(f"❌ FAIL: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ==================== 测试 5: JSON 解析测试 ====================
print("\n[测试 5/6] JSON 解析器测试...", end=" ")
try:
    adapter = ModelAdapter("Qwen/Qwen3.5-4B")
    
    # 测试 1: 标准 JSON 代码块
    test1 = '''```json
{
    "tool_calls": [
        {
            "id": "call_001",
            "function": {
                "name": "create_file",
                "arguments": {"path": "test.py", "content": "print('hello')"}
            }
        }
    ]
}
```'''
    tc1, text1, success1 = adapter.parse_response(test1)
    assert success1 == True
    assert len(tc1) == 1
    print(f"\n          ✅ 标准 JSON: success={success1}, count={len(tc1)}")
    
    # 测试 2: 纯 JSON 对象
    test2 = '''
{
    "tool_calls": [
        {
            "id": "call_002",
            "function": {
                "name": "create_file",
                "arguments": {"path": "test2.py", "content": "x=1"}
            }
        }
    ]
}
'''
    tc2, text2, success2 = adapter.parse_response(test2)
    assert success2 == True
    assert len(tc2) == 1
    print(f"          ✅ 纯 JSON: success={success2}, count={len(tc2)}")
    
    # 测试 3: 纯文本（无工具调用）
    test3 = "我已经完成了代码生成，请查看生成的文件。"
    tc3, text3, success3 = adapter.parse_response(test3)
    assert success3 == False
    assert len(tc3) == 0
    assert len(text3) > 0
    print(f"          ✅ 纯文本：success={success3}, text_len={len(text3)}")
    
    print("          ✅ PASS")
except Exception as e:
    print(f"❌ FAIL: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ==================== 测试 6: Agent 配置与 Model Adapter 配置兼容性 ====================
print("\n[测试 6/6] Agent 配置与 Model Adapter 配置兼容性...", end=" ")
try:
    # 测试 AgentConfig 与 ModelAdapter 配置兼容
    config1 = AgentConfig(model='Qwen/Qwen3.5-4B')
    agent1 = ProjectGeneratorAgent(config=config1)

    # 验证 Agent 配置可以用于初始化 ModelAdapter
    adapter1 = ModelAdapter(config1.model)
    assert adapter1.model_name == config1.model
    assert adapter1.require_strict_json == True
    assert adapter1.enable_few_shot == True
    print(f"\n          ✅ Agent 配置 -> ModelAdapter: {config1.model}")

    # 测试 DeepSeek-R1
    config2 = AgentConfig(model='deepseek-ai/DeepSeek-R1-0528-Qwen3-8B')
    agent2 = ProjectGeneratorAgent(config=config2)
    adapter2 = ModelAdapter(config2.model)
    assert adapter2.model_name == config2.model
    print(f"          ✅ Agent 配置 -> ModelAdapter: {config2.model}")

    # 验证 Agent 可以正常初始化
    assert agent1.config.model == 'Qwen/Qwen3.5-4B'
    assert agent2.config.model == 'deepseek-ai/DeepSeek-R1-0528-Qwen3-8B'
    print(f"          ✅ Agent 配置兼容性验证通过")

    print("          ✅ PASS")
except Exception as e:
    print(f"❌ FAIL: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ==================== 测试结果汇总 ====================
print("\n" + "=" * 70)
print("✅ 所有测试通过！Agent Core 功能正常")
print("=" * 70)
print("\n测试总结:")
print("  • 基础模块导入：正常")
print("  • Model Adapter 导入：正常")
print("  • Model Adapter 初始化：正常")
print("  • System Prompt 构建：正常")
print("  • JSON 解析器：正常 (3/3 测试用例)")
print("  • Agent 集成：正常 (2 个模型)")
print("\nModel Adapter 已成功集成到 agent_core.py")
print("=" * 70)
