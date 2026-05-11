# src/main.py
"""
项目入口文件，负责初始化和调用增量生成逻辑
"""

import argparse
from typing import List, Optional

from increment_generator import IncrementGenerator

def generate_increments(start: int, count: int) -> List[int]:
    """
    调用增量生成核心逻辑
    
    Args:
        start: 增量起始值
        count: 需要生成的增量数量
        
    Returns:
        生成的增量列表
        
    Raises:
        ValueError: 当参数不符合要求时抛出
    """
    if count <= 0:
        raise ValueError("生成数量必须大于0")
    
    try:
        # 初始化增量生成器
        generator = IncrementGenerator(start=start)
        
        # 生成指定数量的增量
        increments = generator.generate(count)
        
        return increments
        
    except Exception as e:
        # 捕获并处理生成过程中的异常
        raise RuntimeError(f"增量生成失败: {str(e)}") from e

def main() -> None:
    """
    项目主入口函数，处理命令行参数并执行增量生成
    """
    parser = argparse.ArgumentParser(description="增量生成工具")
    parser.add_argument("--start", type=int, required=True, help="增量起始值")
    parser.add_argument("--count", type=int, required=True, help="需要生成的增量数量")
    
    args = parser.parse_args()
    
    try:
        result = generate_increments(args.start, args.count)
        print("生成的增量序列：")
        print(result)
        
    except ValueError as ve:
        print(f"参数错误: {ve}")
    except RuntimeError as re:
        print(f"操作失败: {re}")
    except Exception as e:
        print(f"发生未知错误: {str(e)}")

if __name__ == "__main__":
    main()