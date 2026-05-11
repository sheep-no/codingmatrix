# scripts/main.py
import sys
from typing import Optional
import logging
import argparse

# 配置日志记录
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

def main() -> None:
    """
    项目主入口函数，负责解析命令行参数、执行核心功能及错误处理
    支持两个主要命令行参数：
    - --input: 必须提供，表示需要处理的输入数据
    - --output: 可选参数，表示处理结果的输出路径
    """
    try:
        # 命令行参数解析
        parser = argparse.ArgumentParser(description="项目核心功能执行脚本")
        parser.add_argument("--input", type=str, required=True, help="需要处理的输入数据")
        parser.add_argument("--output", type=str, help="处理后结果的输出文件路径")
        args = parser.parse_args()

        # 执行核心处理逻辑
        result = process_core_function(args.input, args.output)
        logging.info("核心功能执行完成")

    except argparse.ArgumentError as e:
        logging.error(f"命令行参数错误: {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"未处理的异常: {e}")
        sys.exit(1)

def process_core_function(input_data: str, output_path: Optional[str] = None) -> str:
    """
    核心业务逻辑处理函数
    
    参数:
        input_data (str): 输入数据，用于核心处理
        output_path (Optional[str]): 可选的输出路径，处理结果会写入该文件
    
    返回:
        str: 处理后的结果
    
    异常:
        ValueError: 当输入数据为空时抛出
        IOError: 当文件写入失败时抛出
    """
    if not input_data:
        raise ValueError("输入数据不能为空，请提供有效的输入参数")
    
    # 示例核心逻辑：将输入数据转换为大写格式
    processed_data = input_data.upper()
    
    # 示例输出处理逻辑：将结果写入指定文件
    if output_path:
        try:
            with open(output_path, 'w') as f:
                f.write(processed_data)
            logging.info(f"结果已写入文件: {output_path}")
        except IOError as e:
            logging.error(f"无法写入输出文件: {e}")
            raise
    
    return processed_data

if __name__ == "__main__":
    main()