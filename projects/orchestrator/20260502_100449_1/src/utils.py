# src/utils.py
"""
辅助函数库
包含项目中常用的通用工具函数，用于日志处理、数据验证、文件操作等场景
"""

import os
import uuid
import secrets
import string
import datetime
from typing import Optional, Any, List, Dict, Union

def generate_unique_id() -> str:
    """
    生成一个全局唯一标识符（UUID）
    
    返回:
        str: 格式化后的UUID字符串
        
    抛出:
        RuntimeError: 如果UUID生成失败
    """
    try:
        # 生成版本4的UUID，基于随机数
        return str(uuid.uuid4())
    except Exception as e:
        raise RuntimeError("生成唯一ID失败") from e

def ensure_output_directory(directory: str) -> None:
    """
    确保指定的输出目录存在，如果不存在则创建
    
    参数:
        directory (str): 目标目录路径
        
    抛出:
        RuntimeError: 如果目录创建失败
    """
    try:
        os.makedirs(directory, exist_ok=True)
        # 验证目录是否存在，确保操作成功
        if not os.path.exists(directory):
            raise RuntimeError(f"目录创建失败: {directory}")
    except OSError as e:
        raise RuntimeError(f"无法创建输出目录: {directory}") from e
    except Exception as e:
        raise RuntimeError("目录操作失败") from e

def generate_random_string(length: int = 16) -> str:
    """
    生成指定长度的随机字符串（包含大小写字母和数字）
    
    参数:
        length (int): 字符串长度，默认16
        
    返回:
        str: 随机生成的字符串
        
    抛出:
        ValueError: 如果长度参数无效
        RuntimeError: 如果随机字符串生成失败
    """
    if length <= 0:
        raise ValueError("长度必须大于0")
        
    try:
        # 使用secrets模块生成更安全的随机字符串
        characters = string.ascii_letters + string.digits
        return ''.join(secrets.choice(characters) for _ in range(length))
    except Exception as e:
        raise RuntimeError("生成随机字符串失败") from e

def validate_integer(value: Any) -> bool:
    """
    验证输入值是否为有效整数
    
    参数:
        value (Any): 要验证的值
        
    返回:
        bool: 验证结果
        
    示例:
        validate_integer("123") 返回 True
        validate_integer("abc") 返回 False
    """
    if isinstance(value, int):
        return True
    if isinstance(value, str):
        try:
            int(value)
            return True
        except ValueError:
            return False
    return False

def format_timestamp(timestamp: Optional[datetime.datetime] = None) -> str:
    """
    格式化当前或指定时间戳为ISO 8601格式字符串
    
    参数:
        timestamp (datetime.datetime, optional): 要格式化的时间对象，若未提供则使用当前时间
        
    返回:
        str: 格式化后的ISO 8601时间字符串（例如: "2026-05-02T10:49:59.123456")
        
    抛出:
        TypeError: 如果输入参数类型不正确
    """
    if timestamp is None:
        timestamp = datetime.datetime.now()
        
    if not isinstance(timestamp, datetime.datetime):
        raise TypeError("输入参数必须是datetime对象或None")
        
    # 精确到微秒的ISO格式
    return timestamp.isoformat(timespec='microseconds')

def validate_list_elements(lst: List[Any], 
                          element_type: Union[type, List[type]], 
                          min_length: Optional[int] = None,
                          max_length: Optional[int] = None) -> bool:
    """
    验证列表元素类型和长度是否符合要求
    
    参数:
        lst (List[Any]): 要验证的列表
        element_type (type 或 List[type]): 元素类型要求，可支持单类型或多种类型
        min_length (int, optional): 列表最小长度
        max_length (int, optional): 列表最大长度
        
    返回:
        bool: 验证结果
        
    示例:
        validate_list_elements([1,2,3], int) 返回 True
        validate_list_elements(["a", 1], [str, int]) 返回 True
    """
    # 类型验证
    if not isinstance(lst, list):
        return False
    
    # 长度验证
    if min_length is not None and len(lst) < min_length:
        return False
        
    if max_length is not None and len(lst) > max_length:
        return False
        
    # 元素类型验证
    if isinstance(element_type, list):
        # 支持多类型验证
        return all(isinstance(item, t) for t in element_type for item in lst)
    
    return all(isinstance(item, element_type) for item in lst)

def safe_dict_merge(dict1: Dict[Any, Any], 
                    dict2: Dict[Any, Any]) -> Dict[Any, Any]:
    """
    安全地将两个字典合并，处理可能出现的键冲突
    
    参数:
        dict1 (Dict): 第一个字典
        dict2 (Dict): 第二个字典
        
    返回:
        Dict: 合并后的字典（dict2的键会覆盖dict1的键）
        
    抛出:
        TypeError: 如果输入参数不是字典类型
    """
    if not isinstance(dict1, dict) or not isinstance(dict2, dict):
        raise TypeError("输入参数必须为字典类型")
        
    try:
        # 使用dict的update方法进行合并
        merged_dict = dict1.copy()
        merged_dict.update(dict2)
        return merged_dict
    except Exception as e:
        raise RuntimeError("字典合并失败") from e

def is_valid_percentage(value: Any) -> bool:
    """
    验证输入值是否为有效百分比（0-100之间的数字）
    
    参数:
        value (Any): 要验证的数值
        
    返回:
        bool: 验证结果
        
    示例:
        is_valid_percentage(50) 返回 True
        is_valid_percentage("75%") 返回 True
        is_valid_percentage("abc") 返回 False
    """
    if isinstance(value, str):
        # 处理带百分号的字符串
        try:
            num = float(value.strip('%'))
            return 0 <= num <= 100
        except ValueError:
            return False
    elif isinstance(value, (int, float)):
        return 0 <= value <= 100
    return False

def get_file_extension(filename: str) -> str:
    """
    获取文件扩展名
    
    参数:
        filename (str): 文件名字符串
        
    返回:
        str: 文件扩展名（不包含点号）
        
    抛出:
        ValueError: 如果输入不是字符串或不包含点号
    """
    if not isinstance(filename, str):
        raise ValueError("文件名必须是字符串")
        
    if '.' not in filename:
        raise ValueError("文件名必须包含扩展名")
        
    # 分割文件名和扩展名（从最后一个点号开始分割）
    return filename.split('.')[-1]