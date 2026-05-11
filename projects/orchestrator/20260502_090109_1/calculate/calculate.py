# projects/orchestrator/20260502_090109_1/calculate/calculate.py
from typing import Union

def calculate(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """
    计算两个数字参数的和
    
    参数:
        a (int/float): 第一个数字参数
        b (int/float): 第二个数字参数
    
    返回:
        int/float: 两个参数的和
        
    抛出:
        TypeError: 如果参数不是数字类型
    """
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise TypeError("Both inputs must be numbers.")
    return a + b