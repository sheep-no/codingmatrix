# projects/orchestrator/20260502_095504_1/add.py
from typing import Union

def add_numbers(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """
    计算两个数的和。
    
    参数:
        a (int 或 float): 第一个加数
        b (int 或 float): 第二个加数
    
    返回:
        int 或 float: 两个数的和
        
    异常:
        TypeError: 如果参数不为整数或浮点数类型时抛出
    """
    # 严格类型检查，排除布尔类型
    if isinstance(a, bool) or isinstance(b, bool):
        raise TypeError("Boolean values are not allowed as inputs")
    
    # 验证参数类型
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise TypeError("Both arguments must be integers or floats")
    
    # 计算并返回和值
    return a + b