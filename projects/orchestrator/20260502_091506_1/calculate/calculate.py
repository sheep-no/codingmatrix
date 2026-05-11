# calculate/calculate.py
from typing import Union

def calculate(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """
    计算两个数字的和。
    
    参数:
        a (int 或 float): 第一个加数
        b (int 或 float): 第二个加数
    
    返回:
        int 或 float: a 和 b 的和
        
    异常:
        TypeError: 如果 a 或 b 不是整数或浮点数值类型
    """
    # 类型验证
    if not isinstance(a, (int, float)):
        raise TypeError("参数 a 必须是整数或浮点数值类型")
    if not isinstance(b, (int, float)):
        raise TypeError("参数 b 必须是整数或浮点数值类型")
    
    # 严格类型转换（可选，根据需求决定是否需要）
    # 例如处理字符串形式的数字输入
    # return float(a) + float(b)
    
    # 直接返回运算结果
    return a + b