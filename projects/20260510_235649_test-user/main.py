from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from pydantic import BaseModel

# 创建数据库引擎
SQLALCHEMY_DATABASE_URL = "sqlite:///./todos.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 定义SQLAlchemy模型
Base = declarative_base()
class Todo(Base):
    __tablename__ = 'todos'
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(100), nullable=False)
    description = Column(String(200))
    is_completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# 定义Pydantic模型用于数据验证
class TodoCreate(BaseModel):
    title: str
    description: str = None
    is_completed: bool = False
class TodoUpdate(BaseModel):
    title: str = None
    description: str = None
    is_completed: bool = None

# 创建FastAPI应用实例
app = FastAPI()

# 依赖函数获取数据库会话
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# CRUD端点
@app.get("/todos")
def read_all_todos(db: SessionLocal = Depends(get_db)):
    todos = db.query(Todo).all()
    return todos

@app.get("/todos/{id}")
def read_todo(id: int, db: SessionLocal = Depends(get_db)):
    todo = db.query(Todo).filter(Todo.id == id).first()
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    return todo

@app.post("/todos/")
def create_todo(todo: TodoCreate, db: SessionLocal = Depends(get_db)):
    new_todo = Todo(**todo.dict())
    db.add(new_todo)
    db.commit()
    db.refresh(new_todo)
    return new_todo

@app.put("/todos/{id}")
def update_todo(id: int, todo: TodoUpdate, db: SessionLocal = Depends(get_db)):
    db_todo = db.query(Todo).filter(Todo.id == id).first()
    if not db_todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    update_data = todo.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_todo, key, value)
    db.commit()
    db.refresh(db_todo)
    return db_todo

@app.delete("/todos/{id}")
def delete_todo(id: int, db: SessionLocal = Depends(get_db)):
    todo = db.query(Todo).filter(Todo.id == id).first()
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    db.delete(todo)
    db.commit()
    return {"message": "Todo deleted successfully"}

# 错误处理示例：可以添加全局异常处理，但已使用HTTPException

# 启动服务器时的命令：使用 uvicorn main:app --reload