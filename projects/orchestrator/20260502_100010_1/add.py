# add.py
# 核心功能：实现计算两个数之和的函数
# 支持类型：整数 int 和浮点数 float
# 错误处理：非数值类型输入时抛出 TypeError

from typing import Union

def add(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """
    计算两个数的和
    
    参数:
        a (int/float): 第一个加数
        b (int/float): 第二个加数
    
    返回:
        int/float: 两个数的和
        
    示例:
        >>> add(2, 3)
        5
        >>> add(2.5, 3.5)
        6.0
        >>> add(-1, 1)
        0
    """
    # 类型验证：确保两个参数都是数值类型
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise TypeError("参数必须为整数或浮点数")
    
    # 执行加法运算并返回结果
    return a + b