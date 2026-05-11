# src/app/config.py
import os
from typing import Optional, Dict, Any
from pydantic import BaseSettings
from fastapi import HTTPException

class Config(BaseSettings):
    # ===== 数据库配置 =====
    # 数据库驱动
    DB_DRIVER: str = "sqlite"
    # 数据库连接字符串
    DB_CONNECTION: str = "todos.db"
    # SQLAlchemy 连接字符串
    SQLALCHEMY_DATABASE_URI: str = f"{DB_DRIVER}:///todos.db"
    # SQLAlchemy 连接池大小
    SQLALCHEMY_POOL_SIZE: int = 5
    # SQLAlchemy 连接池回收时间（秒）
    SQLALCHEMY_POOL_TIMEOUT: int = 30
    # SQLAlchemy 连接池使用后回退
    SQLALCHEMY_ECHO: bool = False  # 生产环境应设为 False
    # 连接池预填充
    SQLALCHEMY_PRE_POD: bool = False
    
    # ===== JWT 配置 =====
    # JWT 密钥（生产环境应使用强密钥）
    JWT_SECRET_KEY: str = "your-secret-key-here"  # 默认密钥，生产环境需替换
    # JWT 算法
    JWT_ALGORITHM: str = "HS256"
    # JWT 令牌过期时间（分钟）
    JWT_EXPIRATION_TIME: int = 15
    # 是否在令牌中包含 JWT 标准声明
    JWT_INCLUDE_ISSUER: bool = True
    JWT_INCLUDE_AUDIENCE: bool = False
    
    # ===== 项目配置 =====
    # 项目名称
    PROJECT_NAME: str = "Todo Management System"
    # 项目版本
    PROJECT_VERSION: str = "1.0.0"
    # 调试模式
    DEBUG: bool = False
    
    # ===== 其他配置 =====
    # 跨域配置
    CORS_ORIGINS: str = "*"
    # 允许的HTTP方法
    ALLOWED_METHODS: str = "GET, POST, PUT, DELETE, OPTIONS"
    # 允许的请求头
    ALLOWED_HEADERS: str = "*"
    # 错误响应模式
    ERROR_RESPONSE_MODE: str = "json"
    
    # ===== 安全配置 =====
    # 跨站点请求伪造保护
    CSRF_PROTECTION: bool = True
    # 安全头
    SECURITY_HEADERS: bool = True
    # 会话过期时间（秒）
    SESSION_EXPIRATION: int = 60 * 60 * 24  # 1天
    
    # ===== 测试配置 =====
    # 测试模式
    TESTING: bool = False
    # 测试数据库
    TEST_DB_NAME: str = "test_todos.db"
    # 测试模式下不使用连接池
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    
    # 验证配置是否有效
    def validate_config(self) -> None:
        """验证配置参数的有效性"""
        if not self.JWT_SECRET_KEY:
            raise ValueError("JWT_SECRET_KEY must be set")
        
        if self.SQLALCHEMY_ECHO and not self.DEBUG:
            raise ValueError("SQLALCHEMY_ECHO should only be True in debug mode")
        
        if self.CSRF_PROTECTION and not self.SECURITY_HEADERS:
            raise ValueError("Both CSRF_PROTECTION and SECURITY_HEADERS should be enabled")
    
    # 配置文件类的实例
    config = None

    @classmethod
    def get_config(cls) -> "Config":
        """获取配置实例，支持单例模式"""
        if cls.config is None:
            cls.config = cls()
            cls.config.validate_config()
        return cls.config

# 导出配置类
config = Config.get_config()