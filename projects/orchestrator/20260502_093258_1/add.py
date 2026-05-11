# projects/orchestrator/20260502_093258_1/add.py
from typing import Union

def add_numbers(a: Union[int, float, str], b: Union[int, float, str]) -> float:
    """
    计算两个数的和。
    
    参数:
    a: 第一个数，可以是整数、浮点数或字符串形式的数字。
    b: 第二个数，可以是整数、浮点数或字符串形式的数字。
    
    返回:
    两个数的和，作为 float 类型返回。
    
    异常:
    ValueError: 如果参数无法转换为数字类型时抛出。
    """
    try:
        # 尝试将输入参数转换为浮点数
        num_a = float(a)
        num_b = float(b)
        # 返回两个数值的和
        return num_a + num_b
    except ValueError as e:
        # 如果转换失败，抛出包含详细错误信息的异常
        raise ValueError(f"Both inputs must be convertible to numbers. Error: {e}")

# 示例用法（可选）
if __name__ == "__main__":
    # 测试不同类型的输入
    print(add_numbers(3, 5))          # 输出: 8.0
    print(add_numbers(2.5, 3))        # 输出: 5.5
    print(add_numbers("4", "5.6"))    # 输出: 9.6
    # 测试非法输入
    try:
        add_numbers("abc", 5)
    except ValueError as e:
        print(f"Error: {e}")           # 输出: Error: invalid literal for float(): 'abc'