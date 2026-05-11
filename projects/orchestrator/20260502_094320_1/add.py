# add.py
# 实现计算两个数之和的核心函数

from typing import Union

def add(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """
    计算两个数之和

    Args:
        a (int | float): 第一个加数，可以是整数或浮点数
        b (int | float): 第二个加数，可以是整数或浮点数

    Returns:
        int | float: 两个数的和，返回类型与输入类型一致（整数相加返回整数，浮点数相加返回浮点数）

    Raises:
        TypeError: 如果传入的参数不是整数或浮点数
    """
    if not isinstance(a, (int, float)):
        raise TypeError("参数a必须为整数或浮点数")
    if not isinstance(b, (int, float)):
        raise TypeError("参数b必须为整数或浮点数")
    
    result = a + b
    # 如果两个参数都是整数，返回整数类型
    if isinstance(a, int) and isinstance(b, int):
        return int(result)
    # 否则返回浮点数类型
    return float(result)