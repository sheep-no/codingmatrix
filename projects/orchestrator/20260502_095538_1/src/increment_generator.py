# src/increment_generator.py
from typing import Generator, Optional

def generate_increments(
    start: int, 
    step: int, 
    max_value: Optional[int] = None
) -> Generator[int, None, None]:
    """
    生成递增的整数序列
    
    参数:
        start (int): 起始值，必须为非负整数
        step (int): 步长，必须为正整数
        max_value (Optional[int]): 最大值，当提供时生成序列直到当前值超过该最大值
        
    返回:
        Generator[int, None, None]: 递增数值生成器
        
    异常:
        ValueError: 当参数不符合要求时抛出
    """
    # 参数验证
    if start < 0:
        raise ValueError("起始值不能为负数")
    if step <= 0:
        raise ValueError("步长必须大于零")
    if max_value is not None and max_value < start:
        raise ValueError("最大值必须大于等于起始值")
    
    # 生成数值
    current = start
    while True:
        if max_value is not None and current > max_value:
            break
        yield current
        current += step

# 示例使用方式（可选）
if __name__ == "__main__":
    """演示增量生成器的使用方式"""
    print("生成1-10的增量序列：")
    for value in generate_increments(1, 1, 10):
        print(value)
    
    print("\n生成2-15的步长3序列：")
    for value in generate_increments(2, 3, 15):
        print(value)
    
    print("\n无限递增序列（前10个）：")
    counter = 0
    for value in generate_increments(1, 1):
        if counter >= 10:
            break
        print(value)
        counter += 1