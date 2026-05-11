# hello_world_project/utils.py
from typing import Optional
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class HelloMessage(Base):
    """
    数据库模型类，用于存储Hello World消息
    包含主键id和消息内容message字段
    """
    __tablename__ = 'hello_messages'
    id = Column(Integer, primary_key=True)
    message = Column(String, nullable=False)

def get_hello_message() -> str:
    """
    获取预定义的Hello World消息字符串
    返回固定内容"Hello, World!"
    """
    return "Hello, World!"

def initialize_database() -> None:
    """
    初始化数据库连接并创建所需的表结构
    使用SQLite内存数据库（:memory:）创建hello_messages表
    """
    try:
        # 使用内存数据库进行初始化，避免创建实际文件
        engine = create_engine('sqlite:///:memory:', echo=False)
        Base.metadata.create_all(engine)
    except Exception as e:
        raise RuntimeError("数据库初始化失败") from e

def save_hello_message() -> None:
    """
    将Hello World消息保存到数据库
    创建新的记录并提交事务
    """
    try:
        # 使用内存数据库进行存储测试
        engine = create_engine('sqlite:///:memory:', echo=False)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # 创建新记录
        new_message = HelloMessage(message=get_hello_message())
        session.add(new_message)
        session.commit()
        
        # 返回成功状态
        return True
    except Exception as e:
        # 事务回滚并抛出运行时错误
        session.rollback()
        raise RuntimeError("保存消息到数据库失败") from e
    finally:
        # 确保会话关闭
        session.close()