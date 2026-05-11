# projects/orchestrator/20260502_085954_1/add.py
from typing import Union

def add_numbers(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """
    计算两个数的和。
    
    参数:
        a (int 或 float): 第一个数字，可以是整数或浮点数。
        b (int 或 float): 第二个数字，可以是整数或浮点数。
    
    返回:
        int 或 float: 两个数相加的结果，保留输入的数值类型（整数结果返回int，浮点数结果返回float）。
    
    异常:
        TypeError: 如果输入类型不是整数或浮点数。
    """
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise TypeError("Both inputs must be integers or floats.")
    return a + b