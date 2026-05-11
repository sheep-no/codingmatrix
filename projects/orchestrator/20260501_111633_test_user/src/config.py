# src/config.py
"""
基础配置参数（环境变量等）
"""
import os
from typing import Optional, Dict, Any

class Config:
    """应用配置类"""
    
    # 环境配置
    ENVIRONMENT: str = os.getenv('ENVIRONMENT', 'development')
    
    # 调试模式
    DEBUG: bool = os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes')
    
    # 主机地址
    HOST: str = os.getenv('HOST', '0.0.0.0')
    
    # 端口配置
    PORT: int = int(os.getenv('PORT', '5000'))
    
    # API文档配置
    API_DOC_TITLE: str = os.getenv('API_DOC_TITLE', 'Hello World API')
    API_DOC_DESCRIPTION: str = os.getenv('API_DOC_DESCRIPTION', 'Simple Hello World API')
    
    # 跨域资源共享
    CORS_ORIGINS: str = os.getenv('CORS_ORIGINS', '["*"]')
    CORS_METHODS: str = os.getenv('CORS_METHODS', '["GET", "POST"]')
    CORS_HEADERS: str = os.getenv('CORS_HEADERS', '["Content-Type"]')
    
    # 安全配置
    SECRET_KEY: str = os.getenv('SECRET_KEY', 'fallback-secret-key')
    JWT_SECRET: str = os.getenv('JWT_SECRET', 'fallback-jwt-secret')
    
    # 数据库配置
    SQLALCHEMY_DATABASE_URI: str = os.getenv(
        'DATABASE_URL', 
        'sqlite:///app.db'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = (
        os.getenv('SQLALCHEMY_TRACK_MODIFICATIONS', 'False').lower() in ('true', '1', 'yes')
    )
    
    # 日志配置
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FORMAT: str = os.getenv('LOG_FORMAT', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # 请求限制
    REQUEST_MAX_SIZE: str = os.getenv('REQUEST_MAX_SIZE', '16MB')
    REQUEST_TIMEOUT: int = int(os.getenv('REQUEST_TIMEOUT', '30'))
    
    # 全局配置字典
    @staticmethod
    def get_config() -> Dict[str, Any]:
        return {
            'environment': Config.ENVIRONMENT,
            'debug': Config.DEBUG,
            'host': Config.HOST,
            'port': Config.PORT,
            'api_doc_title': Config.API_DOC_TITLE,
            'api_doc_description': Config.API_DOC_DESCRIPTION,
            'cors_origins': Config.CORS_ORIGINS,
            'cors_methods': Config.CORS_METHODS,
            'cors_headers': Config.CORS_HEADERS,
            'secret_key': Config.SECRET_KEY,
            'jwt_secret': Config.JWT_SECRET,
            'database_uri': Config.SQLALCHEMY_DATABASE_URI,
            'track_modifications': Config.SQLALCHEMY_TRACK_MODIFICATIONS,
            'log_level': Config.LOG_LEVEL,
            'log_format': Config.LOG_FORMAT,
            'request_max_size': Config.REQUEST_MAX_SIZE,
            'request_timeout': Config.REQUEST_TIMEOUT
        }

    @staticmethod
    def load_from_dict(config_dict: Dict[str, Any]) -> None:
        """从字典加载配置"""
        if not config_dict:
            return
            
        Config.ENVIRONMENT = config_dict.get('environment', Config.ENVIRONMENT)
        Config.DEBUG = config_dict.get('debug', Config.DEBUG)
        Config.HOST = config_dict.get('host', Config.HOST)
        Config.PORT = config_dict.get('port', Config.PORT)
        Config.API_DOC_TITLE = config_dict.get('api_doc_title', Config.API_DOC_TITLE)
        Config.API_DOC_DESCRIPTION = config_dict.get('api_doc_description', Config.API_DOC_DESCRIPTION)
        Config.CORS_ORIGINS = config_dict.get('cors_origins', Config.CORS_ORIGINS)
        Config.CORS_METHODS = config_dict.get('cors_methods', Config.CORS_METHODS)
        Config.CORS_HEADERS = config_dict.get('cors_headers', Config.CORS_HEADERS)
        Config.SECRET_KEY = config_dict.get('secret_key', Config.SECRET_KEY)
        Config.JWT_SECRET = config_dict.get('jwt_secret', Config.JWT_SECRET)
        Config.SQLALCHEMY_DATABASE_URI = config_dict.get('database_uri', Config.SQLALCHEMY_DATABASE_URI)
        Config.SQLALCHEMY_TRACK_MODIFICATIONS = config_dict.get('track_modifications', Config.SQLALCHEMY_TRACK_MODIFICATIONS)
        Config.LOG_LEVEL = config_dict.get('log_level', Config.LOG_LEVEL)
        Config.LOG_FORMAT = config_dict.get('log_format', Config.LOG_FORMAT)
        Config.REQUEST_MAX_SIZE = config_dict.get('request_max_size', Config.REQUEST_MAX_SIZE)
        Config.REQUEST_TIMEOUT = config_dict.get('request_timeout', Config.REQUEST_TIMEOUT)

# 导出配置类
__all__ = ['Config']