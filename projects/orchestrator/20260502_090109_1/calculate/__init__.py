# calculate/__init__.py
# 该文件用于声明公共API，使calculate包能够被其他模块直接调用

from typing import Union

def calculate(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """
    返回两个数字的和。
    
    参数:
    a (int 或 float): 第一个加数，支持整数和浮点数类型
    b (int 或 float): 第二个加数，支持整数和浮点数类型
    
    返回:
    int 或 float: a 与 b 相加的结果
    
    异常:
    TypeError: 如果 a 或 b 不是数字类型（int/float）
    """
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise TypeError("Both a and b must be numeric types (int or float)")
    return a + b