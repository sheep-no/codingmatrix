# src/db_config.py
from typing import Optional
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
import os

class DatabaseConfig:
    """
    数据库连接配置类
    提供SQLite数据库的连接配置和会话工厂
    """

    def __init__(self, app: Optional['Flask'] = None):
        """
        初始化数据库配置
        
        Args:
            app: Flask应用实例（可选）
        """
        self.app = app
        self.db: Optional[SQLAlchemy] = None
        self.engine: Optional[create_engine] = None
        self.Session: Optional[sessionmaker] = None
        self.init_db()

    def init_db(self) -> None:
        """
        初始化数据库连接
        配置SQLite数据库URI并创建SQLAlchemy实例
        """
        if self.app is None:
            # 当前仅用于配置，不直接绑定应用
            self.engine = create_engine('sqlite:///instance/database.sqlite', echo=False)
            self.Session = sessionmaker(bind=self.engine)
            return

        # 配置数据库URI
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///instance/database.sqlite'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        
        # 初始化SQLAlchemy
        self.db = SQLAlchemy(self.app)
        
        # 创建数据库及其表（如果不存在）
        try:
            self.db.create_all()
        except SQLAlchemyError as e:
            self.app.logger.error(f"数据库初始化失败: {str(e)}")
            raise

    def get_session(self) -> sessionmaker:
        """
        获取数据库会话工厂
        
        Returns:
            SQLAlchemy会话工厂实例
        """
        if self.Session is None:
            raise RuntimeError("数据库未正确初始化")
        return self.Session

    def get_db(self) -> SQLAlchemy:
        """
        获取SQLAlchemy实例
        
        Returns:
            SQLAlchemy数据库实例
        """
        if self.db is None:
            raise RuntimeError("数据库未正确初始化")
        return self.db

# 初始化数据库配置（可选）
# 通常在应用启动时通过Flask应用实例初始化
db_config = DatabaseConfig()