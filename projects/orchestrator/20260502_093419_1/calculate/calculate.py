# calculate/calculate.py
from typing import Union

def add(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """
    将两个数字相加并返回结果
    
    参数:
        a (int/float): 第一个数字参数
        b (int/float): 第二个数字参数
    
    返回:
        int/float: 两个参数的和
    
    异常:
        TypeError: 如果参数不是整数或浮点数类型
    """
    # 检查参数类型是否为数字
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise TypeError("Both arguments must be numbers (int or float)")
    
    # 执行加法运算并返回结果
    return a + b