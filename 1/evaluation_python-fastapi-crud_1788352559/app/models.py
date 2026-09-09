import os
from datetime import datetime
from typing import Optional, List

from sqlalchemy import Column, Integer, String, Boolean, DateTime, create_engine, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, Session
from sqlalchemy.sql import func

from app.database import Base

Base = declarative_base()
Engine = create_engine("sqlite:///data.json", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=Engine)


class Record(Base):
    __tablename__ = "records"

    id = Column(Integer, primary_key=True, index=True)
    user: str = Column(String, nullable=False, index=True)
    date: datetime = Column(DateTime, nullable=False, server_default=func.now())
    income: Optional[float] = Column(Float, nullable=True)
    expense: Optional[float] = Column(Float, nullable=True)
    category: str = Column(String, nullable=False)
    amount: float = Column(Float, nullable=False)
    note: Optional[str] = Column(String, nullable=True)

    def __str__(self) -> str:
        return f"{self.user} on {self.date} - {self.category} ({self.amount})"

    __repr__ = __str__


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username: str = Column(String, unique=True, nullable=False, index=True)
    email: str = Column(String, nullable=False, index=True)
    created_at: datetime = Column(DateTime, nullable=False, server_default=func.now())
    updated_at: datetime = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    records = relationship("Record", back_populates="user")

    def __str__(self) -> str:
        return f"{self.username} ({self.email})"

    __repr__ = __str__