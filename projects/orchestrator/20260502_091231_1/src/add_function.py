# src/add_function.py
from typing import Union

def add_numbers(a: Union[int, float, str], b: Union[int, float, str]) -> float:
    """
    计算两个数的和，支持整数、浮点数和字符串形式的数字输入。
    
    参数:
        a: 第一个数，可以是整数、浮点数或字符串形式的数字。
        b: 第二个数，可以是整数、浮点数或字符串形式的数字。
        
    返回:
        两个数的和，作为浮点数类型返回。
        
    异常:
        ValueError: 如果输入无法转换为数字类型。
    """
    try:
        # 尝试将输入转换为浮点数，自动处理字符串表示的数字
        num_a = float(a)
        num_b = float(b)
        return num_a + num_b
    except (TypeError, ValueError) as e:
        # 捕获类型错误或值错误，例如传入布尔值、非字符串数字等
        raise ValueError("Both inputs must be numbers or convertible to numbers.") from e