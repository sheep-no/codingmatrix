# calculate/calculate.py
from typing import Union

def add(a: Union[int, float], b: Union[int, float]) -> Union[int, float]:
    """
    将两个数字相加并返回结果
    
    参数:
        a (int/float): 第一个加数，必须为整数或浮点数类型
        b (int/float): 第二个加数，必须为整数或浮点数类型
    
    返回:
        int/float: 两个参数的和
        
    异常:
        TypeError: 如果参数不是数字类型时抛出
    """
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise TypeError("Both arguments must be numeric (int or float)")
    
    try:
        return a + b
    except Exception as e:
        # 捕获可能的意外异常（如超出范围的数值操作）
        raise RuntimeError(f"Unexpected error during calculation: {str(e)}") from e

# 该文件包含核心计算函数实现
# 通过类型注解确保参数类型安全
# 添加异常处理防止运行时错误
# 保持函数简洁符合简单复杂度要求