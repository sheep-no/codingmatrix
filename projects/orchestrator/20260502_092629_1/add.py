# add.py
# 核心功能：计算两个数的和
# 支持类型：整数(int)、浮点数(float)
# 抛出异常：当输入参数非数值类型时

from typing import Union

def add(param1: Union[int, float], param2: Union[int, float]) -> Union[int, float]:
    """
    计算两个数的和
    
    参数:
        param1 (int/float): 第一个加数
        param2 (int/float): 第二个加数
    
    返回:
        int/float: 两个数相加的结果
        
    异常:
        TypeError: 当参数不是整数或浮点数时抛出
    """
    # 类型验证
    if not isinstance(param1, (int, float)) or not isinstance(param2, (int, float)):
        raise TypeError("Both parameters must be integers or floats")
    
    # 执行加法运算
    return param1 + param2

# 示例说明：
# 调用方式：add(3, 5) 返回 8
#          add(2.5, 4.3) 返回 6.8
#          add(-1, 1) 返回 0
# 异常示例：add("3", 5) 会抛出 TypeError