# src/main.py
"""
项目入口文件，负责调用增量生成逻辑

主要功能：
1. 加载配置参数
2. 调用数据生成核心模块
3. 处理运行时异常
"""

from typing import Dict, Any
import logging
import src.config as config
import src.data_generator as data_generator

# 配置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main() -> None:
    """
    项目主函数，负责初始化配置并启动增量生成流程
    
    该函数会：
    1. 从配置文件加载参数
    2. 验证参数有效性
    3. 调用数据生成器执行增量生成
    4. 捕获并处理运行时异常
    
    Raises:
        ValueError: 当配置参数缺失或无效时
        RuntimeError: 当生成过程发生意外错误时
    """
    try:
        # 加载配置参数
        generation_params: Dict[str, Any] = config.load_config()
        
        # 验证必要参数
        required_params = ['num_records', 'batch_size', 'output_path']
        if not all(param in generation_params for param in required_params):
            raise ValueError(f"缺少必要参数: {required_params}")
            
        # 转换参数类型
        num_records = int(generation_params['num_records'])
        batch_size = int(generation_params['batch_size'])
        
        # 验证参数范围
        if num_records <= 0:
            raise ValueError("num_records 必须为正整数")
        if batch_size <= 0:
            raise ValueError("batch_size 必须为正整数")
            
        # 执行增量数据生成
        logging.info("开始执行增量数据生成流程")
        data_generator.generate_data(
            num_records=num_records,
            batch_size=batch_size,
            output_path=generation_params['output_path']
        )
        logging.info("增量数据生成流程完成")
        
    except ValueError as ve:
        logging.error(f"配置参数验证失败: {str(ve)}")
        raise RuntimeError("配置参数验证失败，请检查 config.py 文件") from ve
        
    except Exception as e:
        logging.error(f"发生未知错误: {str(e)}")
        raise RuntimeError("系统发生错误，请检查日志获取更多详情") from e

if __name__ == "__main__":
    """当文件作为主程序运行时执行"""
    try:
        main()
    except Exception as e:
        logging.error(f"主程序执行失败: {str(e)}")
        exit(1)