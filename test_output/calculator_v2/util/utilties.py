"""
util/utilties.py: 通用工具函数文件，主要提供输入验证功能。
该文件包含验证数字类型、检查数字有效性、处理除零异常等通用验证函数。
"""

from typing import Any, Union
import math

def is_number(value: Any) -> bool:
    """
    检查值是否为数字类型（整数或浮点数）
    
    参数:
        value: 要检查的值
        
    返回:
        bool: 如果值是数字类型则返回True，否则返回False
    """
    return isinstance(value, (int, float))

def is_valid_number(value: Any) -> bool:
    """
    检查值是否为有效的数字（非NaN，无穷大，整数或浮点数）
    
    参数:
        value: 要检查的值
        
    返回:
        bool: 如果值是有效的数字则返回True，否则返回False
    """
    if not is_number(value):
        return False
        
    if math.isnan(value) or math.isinf(value):
        return False
        
    return True

def validate_divisor(divisor: Union[int, float]) -> Union[int, float]:
    """
    验证除数不为零，并返回有效值
    
    参数:
        divisor: 除数
        
    返回:
        Union[int, float]: 验证后的除数
        
    异常:
        ValueError: 当除数为零时抛出
    """
    if divisor == 0:
        raise ValueError("Divisor cannot be zero")
    return divisor

def validate_operation_args(a: Union[int, float], b: Union[int, float]) -> tuple:
    """
    验证操作数是否为有效数字
    
    参数:
        a: 第一个操作数
        b: 第二个操作数
        
    返回:
        tuple: 验证后的操作数对
        
    异常:
        TypeError: 当操作数不是数字类型时抛出
        ValueError: 当操作数无效（NaN或无穷大）时抛出
    """
    if not is_valid_number(a):
        raise ValueError(f"Invalid operation number: {a}")
        
    if not is_valid_number(b):
        raise ValueError(f"Invalid operation number: {b}")
        
    return (float(a), float(b))

def convert_to_float(value: Any) -> float:
    """
    尝试将值转换为浮点数，如果失败则抛出异常
    
    参数:
        value: 要转换的值
        
    返回:
        float: 转换后的浮点数
        
    异常:
        ValueError: 当无法转换为浮点数时抛出
    """
    if isinstance(value, (int, float)):
        return float(value)
        
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Could not convert to float: {value}")

def validate_operation_type(operation_type: str) -> str:
    """
    验证操作类型是否有效
    
    参数:
        operation_type: 操作类型字符串
        
    返回:
        str: 验证后的操作类型
        
    异常:
        ValueError: 当操作类型无效时抛出
    """
    valid_operations = ["add", "subtract", "multiply", "divide"]
    if operation_type.lower() not in valid_operations:
        raise ValueError(f"Invalid operation type: {operation_type}")
    return operation_type.lower()