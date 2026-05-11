# app/models.py
from datetime import datetime
from typing import List, Optional

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.exc import SQLAlchemyError

# 初始化SQLAlchemy数据库对象
db = SQLAlchemy()

class IncrementalData(db.Model):
    """
    增量数据模型类，用于存储每次新增的数据条目
    
    表结构说明:
    - id: 主键，自动递增的唯一标识符
    - data: 存储的增量数据内容，最大长度255，不能为空
    - created_at: 数据创建时间戳，默认使用当前时间
    """
    
    __tablename__ = 'incremental_data'
    
    id: Column[int] = Column(Integer, primary_key=True, autoincrement=True)
    data: Column[str] = Column(String(255), nullable=False)
    created_at: Column[datetime] = Column(DateTime, default=func.now())
    
    def __repr__(self) -> str:
        """返回模型的字符串表示"""
        return f'<IncrementalData {self.id}>'
    
    @staticmethod
    def create_data(data_content: str) -> Optional[int]:
        """
        创建新的增量数据条目
        
        参数:
            data_content (str): 要存储的数据内容
            
        返回:
            int: 创建成功时返回生成的ID，失败时返回None
        
        异常处理:
            捕获SQLAlchemy操作异常并记录日志
        """
        try:
            new_entry = IncrementalData(data=data_content)
            db.session.add(new_entry)
            db.session.commit()
            return new_entry.id
        except SQLAlchemyError as e:
            # 记录数据库操作错误日志（实际项目中应添加日志记录逻辑）
            db.session.rollback()
            print(f"数据库操作错误: {str(e)}")
            return None

    @staticmethod
    def get_all_data() -> List['IncrementalData']:
        """
        获取所有增量数据条目
        
        返回:
            List[IncrementalData]: 包含所有数据条目的列表
            
        异常处理:
            捕获数据库查询异常并记录日志
        """
        try:
            return IncrementalData.query.all()
        except SQLAlchemyError as e:
            # 记录数据库查询错误日志（实际项目中应添加日志记录逻辑）
            print(f"数据库查询错误: {str(e)}")
            return []