from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.orm.sessionmaker import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

from app.models import Todo
from app.schemas import TodoCreate, TodoUpdate, TodoResponse
import app.database

Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=app.database.engine)


def get_db() -> Session:
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_todos(db: Session) -> List[TodoResponse]:
    """获取所有待办事项"""
    todos = db.query(Todo).all()
    return [TodoResponse(**todo.dict()) for todo in todos]


def create_todo(db: Session, todo: TodoCreate) -> TodoResponse:
    """创建新的待办事项"""
    todo_obj = Todo(
        title=todo.title,
        description=todo.description,
        completed=todo.completed,
    )
    db.add(todo_obj)
    db.commit()
    db.refresh(todo_obj)
    return TodoResponse(**todo_obj.dict())


def get_todo(db: Session, todo_id: int) -> Optional[TodoResponse]:
    """获取特定待办事项"""
    todo = db.query(Todo).filter(Todo.id == todo_id).first()
    if todo is None:
        return None
    return TodoResponse(**todo.dict())


def update_todo(db: Session, todo_id: int, todo: TodoUpdate) -> Optional[TodoResponse]:
    """更新特定待办事项"""
    todo = db.query(Todo).filter(Todo.id == todo_id).first()
    if todo is None:
        return None
    
    update_data = todo.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(todo, key, value)
    
    db.commit()
    db.refresh(todo)
    return TodoResponse(**todo.dict())


def delete_todo(db: Session, todo_id: int) -> bool:
    """删除特定待办事项"""
    todo = db.query(Todo).filter(Todo.id == todo_id).first()
    if todo is None:
        return False
    db.delete(todo)
    db.commit()
    return True