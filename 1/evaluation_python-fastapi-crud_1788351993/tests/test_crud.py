pytest
httpx
fastapi
fastapi.testclient
sqlalchemy
sqlalchemy.orm
sqlalchemy.ext.declarative
pydantic
app.models
app.schemas
app.crud
import os
import tempfile
import sqlite3
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from typing import Optional

Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False)
engine = None

class Todo(Base):
    __tablename__ = "todos"
    
    todo_id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

def create_engine():
    return create_engine("sqlite:///:memory:")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_database():
    global engine, Base
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

def get_session():
    return SessionLocal()

def run_sync_tests():
    init_database()
    todo = Todo(todo_id=1, title="Test", description="Test Desc", completed=False)
    SessionLocal().add(todo)
    SessionLocal().commit()
    print(f"Inserted todo with id: {todo.todo_id}")

if __name__ == "__main__":
    run_sync_tests()