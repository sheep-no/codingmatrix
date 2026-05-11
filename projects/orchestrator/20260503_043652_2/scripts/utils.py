# scripts/utils.py
"""
通用工具函数模块

包含常用工具函数，用于数据处理、验证和日志记录等基础操作
"""

import re
import datetime
import os
from typing import Optional, Union, List, Dict, Any

def log_message(message: str, log_file: Optional[str] = None) -> None:
    """
    记录日志消息到指定文件或默认日志文件
    
    参数:
        message: 要记录的消息内容
        log_file: 可选的日志文件路径，若未指定则使用默认路径
    
    返回:
        None
        
    异常:
        如果无法写入日志文件会抛出IOError
    """
    if log_file is None:
        log_file = os.path.join(os.path.dirname(__file__), 'default.log')
    
    if not os.path.exists(os.path.dirname(log_file)):
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {message}\n")
    except IOError as e:
        raise IOError(f"无法写入日志文件 {log_file}: {str(e)}") from e

def remove_whitespace(text: Union[str, None]) -> str:
    """
    移除字符串中的多余空格
    
    参数:
        text: 输入的字符串
        
    返回:
        处理后的字符串
        
    异常:
        如果输入不是字符串会抛出TypeError
    """
    if text is None:
        return ""
        
    if not isinstance(text, str):
        raise TypeError("输入必须是字符串或None")
        
    return text.strip()

def to_camel_case(snake_str: str) -> str:
    """
    将snake_case字符串转换为camelCase格式
    
    参数:
        snake_str: 输入的snake_case字符串
        
    返回:
        转换后的camelCase字符串
        
    异常:
        如果输入不是字符串会抛出TypeError
    """
    if not isinstance(snake_str, str):
        raise TypeError("输入必须是字符串")
        
    components = snake_str.split('_')
    if len(components) == 1:
        return components[0]
        
    # 将第一个组件小写，其余组件首字母大写并拼接
    return components[0].lower() + ''.join(x.capitalize() for x in components[1:])

def validate_email(email: str) -> bool:
    """
    验证电子邮件地址格式是否有效
    
    参数:
        email: 要验证的电子邮件地址
        
    返回:
        bool: 是否有效
        
    异常:
        如果输入不是字符串会抛出TypeError
    """
    if not isinstance(email, str):
        raise TypeError("输入必须是字符串")
        
    # 简单的电子邮件格式验证
    email_pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(email_pattern, email) is not None

def validate_url(url: str) -> bool:
    """
    验证URL格式是否有效
    
    参数:
        url: 要验证的URL
        
    返回:
        bool: 是否有效
        
    异常:
        如果输入不是字符串会抛出TypeError
    """
    if not isinstance(url, str):
        raise TypeError("输入必须是字符串")
        
    # 简单的URL格式验证
    url_pattern = r'^(https?:\/\/)?([\da-z-._~+|!$&\'*+,;=:@]+\/\/)?' \
                  r'([^\s]*)$'
    return re.match(url_pattern, url) is not None

def format_timestamp(timestamp: Union[str, datetime.datetime], 
                     format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    格式化时间戳
    
    参数:
        timestamp: 时间戳（字符串或datetime对象）
        format_str: 目标格式字符串
        
    返回:
        格式化后的时间字符串
        
    异常:
        如果输入不是有效的时间戳会抛出ValueError
    """
    if isinstance(timestamp, datetime.datetime):
        return timestamp.strftime(format_str)
        
    if isinstance(timestamp, str):
        try:
            # 尝试解析字符串时间戳
            return datetime.datetime.fromisoformat(timestamp).strftime(format_str)
        except ValueError:
            pass
            
        try:
            # 尝试解析其他格式的时间戳
            return datetime.datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").strftime(format_str)
        except ValueError:
            pass
    
    raise ValueError("无效的时间戳格式")