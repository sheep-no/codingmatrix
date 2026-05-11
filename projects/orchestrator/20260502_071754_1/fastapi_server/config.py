# fastapi_server/config.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from typing import Optional, Dict, Any
from pydantic import BaseSettings

# 数据库配置
class DatabaseConfig(BaseSettings):
    # SQLite数据库文件路径
    SQLALCHEMY_DATABASE_URI: str = "sqlite:///./chess_games.db"
    
    # 是否回滚事务（用于测试）
    SQLALCHEMY_ECHO: bool = False
    
    # 连接池大小
    SQLALCHEMY_POOL_SIZE: int = 20
    
    # 连接池超时
    SQLALCHEMY_POOL_TIMEOUT: int = 30
    
    # 连接池回收
    SQLALCHEMY_POOL_RECycle: int = -1
    
    # 是否跟踪对象修改
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False

# 全局配置
class Settings(BaseSettings):
    # 项目名称
    PROJECT_NAME: str = "FiveInARow Chess Game"
    
    # API版本
    API_VERSION: str = "v1"
    
    # 跨域允许的源
    ALLOWED_ORIGINS: str = "http://localhost:8080"
    
    # 跨域允许的HTTP方法
    ALLOWED_METHODS: str = "GET, POST, PUT, DELETE, OPTIONS"
    
    # 跨域允许的头部
    ALLOWED_HEADERS: str = "*"
    
    # 跨域允许的凭据
    EXPOSE_HEADERS: str = "Authorization"
    
    # 数据库配置
    DB_CONFIG: DatabaseConfig = DatabaseConfig()
    
    # 超时设置（秒）
    TIMEOUT: int = 60
    
    # 每页记录数
    ITEMS_PER_PAGE: int = 20
    
    # 时区
    TIMEZONE: str = "Asia/Shanghai"
    
    # 胜利棋子数量
    VICTORY_COUNT: int = 5
    
    # 日志级别
    LOG_LEVEL: str = "INFO"
    
    # 服务器配置
    SERVER_CONFIG: Dict[str, Any] = {
        "host": "0.0.0.0",
        "port": 8000,
        "debug": False,
        "reload": False
    }

# 创建SQLAlchemy基础类
Base = declarative_base()

# 创建数据库引擎
engine = create_engine(
    Settings.DB_CONFIG.SQLALCHEMY_DATABASE_URI,
    pool_pre_ping=True,
    pool_use_limiting=False
)

# 创建数据库会话工厂
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False
)

def get_db():
    """获取数据库会话"""
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()

# 配置字典
config_dict = {
    "settings": Settings(),
    "db_engine": engine,
    "db_session": SessionLocal()
}

# 导出配置
__all__ = [
    "config_dict",
    "DatabaseConfig",
    "Settings"
]