# app/config.py
"""
基础配置文件，存储服务器运行的基本配置
"""

import os
from enum import Enum

class LogLevel(Enum):
    """日志级别枚举"""
    DEBUG = 'DEBUG'
    INFO = 'INFO'
    WARNING = 'WARNING'
    ERROR = 'ERROR'
    CRITICAL = 'CRITICAL'

class BaseConfig:
    """基础配置类"""
    
    # 服务器配置
    SERVER_HOST = os.environ.get('SERVER_HOST', '0.0.0.0')
    SERVER_PORT = int(os.environ.get('SERVER_PORT', 5000))
    SERVER_NAME = os.environ.get('SERVER_NAME', 'api.example.com')
    
    # 应用配置
    APP_NAME = os.environ.get('APP_NAME', 'hello-world-api')
    APP_VERSION = os.environ.get('APP_VERSION', '0.0.1')
    DEBUG = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 'yes')
    
    # 日志配置
    LOG_LEVEL = os.environ.get('LOG_LEVEL', LogLevel.INFO.value)
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    LOG_DATEFORMAT = '%Y-%m-%d %H:%M:%S'
    
    # 安全配置
    SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(24).hex())
    SESSION_COOKIE_NAME = 'session'
    
    # 请求限制
    REQUEST_MAX_SIZE = int(os.environ.get('REQUEST_MAX_SIZE', 1024 * 1024))  # 1MB
    REQUEST_TIMEOUT = int(os.environ.get('REQUEST_TIMEOUT', 30))  # 30秒
    
    # 环境信息
    ENVIRONMENT = os.environ.get('ENVIRONMENT', 'development')
    CREATED_AT = os.environ.get('CREATED_AT', '2023-01-01')
    
    # 跨域配置
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*').split(',') if os.environ.get('CORS_ORIGINS') else ['*']
    CORS_METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
    CORS_HEADERS = ['Content-Type', 'Authorization']

    @classmethod
    def validate(cls) -> bool:
        """验证配置有效性"""
        # 确保必要的配置项存在
        required_keys = ['SERVER_HOST', 'SERVER_PORT']
        for key in required_keys:
            if not hasattr(cls, key) or getattr(cls, key) is None:
                return False
        
        # 确保日志级别有效
        valid_levels = [level.value for level in LogLevel]
        if hasattr(cls, 'LOG_LEVEL') and getattr(cls, 'LOG_LEVEL') not in valid_levels:
            return False
            
        return True

# 导出配置类
__all__ = ['BaseConfig']