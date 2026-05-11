# src/generate_script.py
import os
from typing import Dict, Any, Optional, Union

def generate_script(
    script_type: str, 
    parameters: Dict[str, Any], 
    output_dir: Optional[str] = None
) -> Union[str, Dict[str, Any]]:
    """
    核心脚本生成器，根据类型和参数生成对应格式的脚本内容
    
    参数:
        script_type (str): 脚本类型，支持 'test' 和 'config'
        parameters (Dict[str, Any]): 生成所需的参数字典
        output_dir (Optional[str]): 输出目录，默认为当前目录下的 'generated_scripts' 文件夹
    
    返回:
        如果成功生成脚本，返回包含文件路径的字典
        如果生成失败，返回包含错误信息的字典
    
    异常:
        ValueError: 当传入的script_type不支持时抛出
        OSError: 当无法创建输出目录或写入文件时抛出
    """
    try:
        # 设置默认输出目录
        if output_dir is None:
            output_dir = os.path.join(os.getcwd(), "generated_scripts")
        
        # 验证输出目录权限
        if not os.access(output_dir, os.W_OK):
            raise OSError(f"无法写入输出目录: {output_dir}")
        
        # 创建输出目录（如果不存在）
        os.makedirs(output_dir, exist_ok=True)
        
        # 根据脚本类型生成内容
        if script_type == "test":
            script_content = _generate_test_script(parameters)
        elif script_type == "config":
            script_content = _generate_config_script(parameters)
        else:
            raise ValueError(f"不支持的脚本类型: {script_type}")
        
        # 生成文件路径
        filename = f"{script_type}_script.py"
        filepath = os.path.join(output_dir, filename)
        
        # 写入文件
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(script_content)
            
        return {
            "status": "success",
            "message": "脚本生成成功",
            "file_path": filepath
        }
    
    except ValueError as ve:
        return {
            "status": "error",
            "message": str(ve)
        }
    
    except OSError as ose:
        return {
            "status": "error",
            "message": f"文件操作失败: {str(ose)}"
        }
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"生成脚本时发生未知错误: {str(e)}"
        }

def _generate_test_script(params: Dict[str, Any]) -> str:
    """
    生成测试脚本内容
    
    参数:
        params (Dict[str, Any]): 包含测试相关信息的字典
        
    返回:
        str: 测试脚本内容
        
    示例参数结构:
        {
            "test_name": "example_test",
            "test_description": "测试示例功能",
            "assertions": ["assert 1 == 1", "assert 2 == 2"]
        }
    """
    test_name = params.get("test_name", "default_test")
    test_description = params.get("test_description", "This is an automated test script")
    assertions = params.get("assertions", ["assert True"])
    
    # 验证参数完整性
    if not test_name:
        raise ValueError("必须提供测试名称参数")
    
    script = f"""# 自动化测试脚本 - {test_description}
import pytest

@pytest.mark.{test_name}
def test_{test_name}():
    """{test_description}"""
    {'\n    '.join(assertions)}
"""
    return script

def _generate_config_script(params: Dict[str, Any]) -> str:
    """
    生成配置文件内容
    
    参数:
        params (Dict[str, Any]): 包含配置键值对的字典
        
    返回:
        str: 配置文件内容
        
    示例参数结构:
        {
            "config": {
                "database": {"host": "localhost", "port": 3306},
                "api": {"endpoint": "/v1/data", "timeout": 10}
            }
        }
    """
    config = params.get("config", {})
    
    # 验证配置参数
    if not config:
        raise ValueError("配置参数不能为空")
    
    config_content = "config = {\n"
    for section, section_params in config.items():
        config_content += f"    '{section}': {{\n"
        for key, value in section_params.items():
            config_content += f"        '{key}': {value},\n"
        config_content += "    },\n"
    config_content += "}"
    
    return config_content