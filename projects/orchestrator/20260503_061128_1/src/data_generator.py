# src/data_generator.py
"""
数据生成器模块：实现增量数据生成算法

该模块提供核心的增量数据生成功能，支持多种数据类型和配置参数
"""

import datetime
from typing import List, Dict, Optional
from .config import Config  # 从配置文件导入参数

def generate_single_data(data_type: str, start_value: int, increment: int) -> Dict[str, any]:
    """
    生成单个增量数据项
    
    参数:
        data_type (str): 数据类型（'numeric' 或 'timestamp'）
        start_value (int): 初始值
        increment (int): 增量步长
    
    返回:
        Dict[str, any]: 包含数据类型和生成值的字典
    
    异常:
        ValueError: 当数据类型不支持时抛出
    """
    if data_type == "numeric":
        return {"type": "numeric", "value": start_value}
    
    elif data_type == "timestamp":
        # 生成初始时间戳
        initial_time = datetime.datetime.now() - datetime.timedelta(days=30)
        return {"type": "timestamp", "value": initial_time.strftime("%Y-%m-%d %H:%M:%S")}
    
    else:
        raise ValueError(f"Unsupported data type: {data_type}. Supported types: 'numeric', 'timestamp'")

def generate_increments(
    data_type: str = Config.DEFAULT_DATA_TYPE,
    count: int = Config.DEFAULT_COUNT,
    start_value: int = Config.START_VALUE,
    increment: int = Config.INCREMENT
) -> List[Dict[str, any]]:
    """
    生成指定数量的增量数据
    
    参数:
        data_type (str): 数据类型（默认从配置文件读取）
        count (int): 要生成的数据项数量（默认从配置文件读取）
        start_value (int): 初始值（默认从配置文件读取）
        increment (int): 增量步长（默认从配置文件读取）
    
    返回:
        List[Dict[str, any]]: 生成的增量数据列表
    
    异常:
        ValueError: 当参数验证失败时抛出
        RuntimeError: 当生成过程中发生内部错误时抛出
    """
    # 参数验证
    if not isinstance(count, int) or count <= 0:
        raise ValueError("Count must be a positive integer")
        
    if not isinstance(start_value, int):
        raise ValueError("Start value must be an integer")
        
    if not isinstance(increment, int) or increment <= 0:
        raise ValueError("Increment must be a positive integer")
    
    try:
        # 初始化数据列表
        data_list = []
        
        # 根据数据类型生成数据
        if data_type == "numeric":
            for i in range(count):
                current_value = start_value + increment * i
                data_list.append({"type": "numeric", "value": current_value})
                
        elif data_type == "timestamp":
            # 生成时间戳数据
            initial_time = datetime.datetime.now() - datetime.timedelta(days=30)
            for i in range(count):
                current_time = initial_time + datetime.timedelta(seconds=increment * i)
                data_list.append({"type": "timestamp", "value": current_time.strftime("%Y-%m-%d %H:%M:%S")})
                
        else:
            raise ValueError(f"Unsupported data type: {data_type}. Supported types: 'numeric', 'timestamp'")
            
        return data_list
    
    except Exception as e:
        # 捕获并处理生成过程中的异常
        error_msg = f"Error generating increments: {str(e)}"
        raise RuntimeError(error_msg) from e

def validate_config(config: Dict[str, any]) -> bool:
    """
    验证配置参数
    
    参数:
        config (Dict[str, any]): 配置参数字典
    
    返回:
        bool: 验证是否通过
    
    异常:
        ValueError: 当配置参数缺失或无效时抛出
    """
    required_params = ["DATA_TYPE", "COUNT", "START_VALUE", "INCREMENT"]
    
    # 检查必需参数是否存在
    for param in required_params:
        if param not in config:
            raise ValueError(f"Missing required configuration parameter: {param}")
    
    # 验证数据类型
    if config["DATA_TYPE"] not in ["numeric", "timestamp"]:
        raise ValueError("Invalid data type configuration. Must be 'numeric' or 'timestamp'")
    
    # 验证计数是否为正整数
    if not isinstance(config["COUNT"], int) or config["COUNT"] <= 0:
        raise ValueError("Invalid count configuration. Must be a positive integer")
    
    # 验证起始值是否为整数
    if not isinstance(config["START_VALUE"], int):
        raise ValueError("Invalid start value configuration. Must be an integer")
    
    # 验证步长是否为正整数
    if not isinstance(config["INCREMENT"], int) or config["INCREMENT"] <= 0:
        raise ValueError("Invalid increment configuration. Must be a positive integer")
    
    return True