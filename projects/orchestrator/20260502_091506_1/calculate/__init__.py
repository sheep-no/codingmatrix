# calculate/__init__.py
# 这是 calculate 包的初始化文件，声明公共 API 接口

from numbers import Number

def calculate(a: Number, b: Number) -> Number:
    """
    计算两个数字的和
    
    参数:
        a (Number): 第一个加数，必须是数字类型（int, float, complex 等）
        b (Number): 第二个加数，必须是数字类型
    
    返回:
        Number: 两个加数的和
    
    异常:
        TypeError: 当参数不是数字类型时抛出
    """
    if not isinstance(a, Number) or not isinstance(b, Number):
        raise TypeError("Both arguments must be numbers (int, float, complex, etc.)")
    return a + b