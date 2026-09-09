from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from datetime import datetime

Base = declarative_base()


class Todo(Base):
    __tablename__ = 'todos'

    id = Column(Integer, primary_key=True)
    title = Column(String(100), nullable=False)
    description = Column(String(255))
    completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)