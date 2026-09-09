from typing import Optional
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.models import Todo
from app.database import get_db, engine
from app.schemas import TodoCreate, TodoRead, TodoUpdate


def get_todos(db: Session):
    """获取所有待办事项"""
    query = select(Todo).order_by(Todo.created_at.desc())
    result = db.execute(query).scalars().all()
    return [TodoRead(**todo.__dict__) for todo in result]


def get_todo(db: Session, todo_id: int) -> Optional[TodoRead]:
    """获取指定待办事项"""
    query = select(Todo).where(Todo.id == todo_id)
    result = db.execute(query).scalars().first()
    if result:
        return TodoRead(**result.__dict__)
    return None


def create_todo(db: Session, todo_data: TodoCreate) -> TodoRead:
    """创建新待办事项"""
    db_todo = Todo(**todo_data.model_dump())
    db.add(db_todo)
    db.commit()
    db.refresh(db_todo)
    return TodoRead(**db_todo.__dict__)


def update_todo(db: Session, todo_id: int, todo_data: TodoUpdate) -> Optional[TodoRead]:
    """更新指定待办事项"""
    query = select(Todo).where(Todo.id == todo_id)
    result = db.execute(query).scalars().first()
    
    if result is None:
        return None
    
    update_data = todo_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(result, field, value)
    
    db.commit()
    db.refresh(result)
    return TodoRead(**result.__dict__)


def delete_todo(db: Session, todo_id: int) -> bool:
    """删除指定待办事项"""
    query = select(Todo).where(Todo.id == todo_id)
    result = db.execute(query).scalars().first()
    
    if result is None:
        return False
    
    db.delete(result)
    try:
        db.commit()
        return True
    except SQLAlchemyError:
        db.rollback()
        return False