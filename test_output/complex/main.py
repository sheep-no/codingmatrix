import os
import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends, status, Security
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
import bcrypt
import jwt
from jwt import PyJWTError
from datetime import timedelta

# 项目配置
SECRET_KEY = "mysecretkey"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# 允许跨域请求
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 数据库配置
SQLALCHEMY_DATABASE_URL = "sqlite:///todos.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# 用户模型
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True)
    email = Column(String(100), unique=True, index=True)
    hashed_password = Column(String(100))
    todos = relationship("Todo", back_populates="user")
    
    def __repr__(self):
        return f"User(id={self.id}, username='{self.username}', email='{self.email}')"

# 待办事项模型
class Todo(Base):
    __tablename__ = "todos"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(String(10), default="中", index=True)
    due_date = Column(DateTime, nullable=True)
    completed = Column(Integer, default=0)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    user = relationship("User", back_populates="todos")
    
    def __repr__(self):
        return f"Todo(id={self.id}, title='{self.title}', completed={self.completed})"

# 创建表
Base.metadata.create_all(bind=engine)

# Pydantic 模型
class UserCreate(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    
    class Config:
        orm_mode = True

class TodoCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: Optional[str] = "中"
    due_date: Optional[str] = None

class TodoUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None
    completed: Optional[bool] = None

class TodoResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    priority: str
    due_date: Optional[str] = None
    completed: bool
    user_id: int
    
    class Config:
        orm_mode = True

# 密码加密函数
def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

# JWT 函数
def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode.update({"iat": datetime.datetime.now()})
    to_encode.update({"exp": datetime.datetime.now() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(OAuth2PasswordBearer(token_url="/login/token")):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
            )
    except PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token or expired token",
        )
    
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == int(user_id)).first()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        return user
    finally:
        db.close()

# 用户管理路由
@app.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user: UserCreate):
    db = SessionLocal()
    try:
        # 检查用户名是否已存在
        existing_user = db.query(User).filter(User.username == user.username).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Username already registered")
        
        # 检查邮箱是否已存在
        existing_email = db.query(User).filter(User.email == user.email).first()
        if existing_email:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # 创建新用户
        hashed_password = get_password_hash(user.password)
        new_user = User(
            username=user.username,
            email=user.email,
            hashed_password=hashed_password
        )
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        return new_user
    finally:
        db.close()

@app.post("/login/token", response_model=dict)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    db = SessionLocal()
    try:
        # 查找用户
        user = db.query(User).filter(User.username == form_data.username).first()
        if not user or not verify_password(form_data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password"
            )
        
        # 创建JWT令牌
        access_token = create_access_token({"sub": str(user.id)})
        
        return {"access_token": access_token, "token_type": "bearer"}
    finally:
        db.close()

@app.get("/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

# 待办事项路由
@app.post("/todos/", response_model=TodoResponse, status_code=status.HTTP_201_CREATED)
def create_todo(todo: TodoCreate, current_user: User = Depends(get_current_user)):
    db = SessionLocal()
    try:
        # 处理日期
        due_date = None
        if todo.due_date:
            try:
                due_date = datetime.datetime.strptime(todo.due_date, "%Y-%m-%dT%H:%M")
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid date format. Use format: YYYY-MM-DDTHH:MM"
                )
        
        new_todo = Todo(
            title=todo.title,
            description=todo.description,
            priority=todo.priority,
            due_date=due_date,
            completed=False,
            user_id=current_user.id
        )
        
        db.add(new_todo)
        db.commit()
        db.refresh(new_todo)
        
        return new_todo
    finally:
        db.close()

@app.get("/todos/", response_model=List[TodoResponse])
def read_todos(
    db: Session = Depends(),
    skip: int = 0,
    limit: int = 10,
    priority: Optional[str] = None,
    due_date: Optional[str] = None,
    completed: Optional[bool] = None
):
    query = db.query(Todo)
    
    # 筛选条件
    if priority:
        query = query.filter(Todo.priority == priority)
    if due_date:
        try:
            due_date_filter = datetime.datetime.strptime(due_date, "%Y-%m-%dT%H:%M")
            query = query.filter(Todo.due_date == due_date_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid date format. Use format: YYYY-MM-DDTHH:MM"
            )
    if completed is not None:
        query = query.filter(Todo.completed == completed)
    
    # 分页
    todos = query.order_by(Todo.due_date.desc(), Todo.priority).offset(skip).limit(limit).all()
    
    return todos

@app.get("/todos/{todo_id}", response_model=TodoResponse)
def read_todo(todo_id: int, current_user: User = Depends(get_current_user)):
    db = SessionLocal()
    try:
        todo = db.query(Todo).filter(Todo.id == todo_id, Todo.user_id == current_user.id).first()
        if not todo:
            raise HTTPException(status_code=404, detail="Todo not found")
        return todo
    finally:
        db.close()

@app.put("/todos/{todo_id}", response_model=TodoResponse)
def update_todo(
    todo_id: int,
    todo_update: TodoUpdate,
    current_user: User = Depends(get_current_user)
):
    db = SessionLocal()
    try:
        todo = db.query(Todo).filter(Todo.id == todo_id, Todo.user_id == current_user.id).first()
        if not todo:
            raise HTTPException(status_code=404, detail="Todo not found")
        
        # 更新字段
        if todo_update.title is not None:
            todo.title = todo_update.title
        if todo_update.description is not None:
            todo.description = todo_update.description
        if todo_update.priority is not None:
            todo.priority = todo_update.priority
        if todo_update.due_date is not None:
            try:
                due_date_filter = datetime.datetime.strptime(todo_update.due_date, "%Y-%m-%dT%H:%M")
                todo.due_date = due_date_filter
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid date format. Use format: YYYY-MM-DDTHH:MM"
                )
        if todo_update.completed is not None:
            todo.completed = 1 if todo_update.completed else 0
        
        db.commit()
        db.refresh(todo)
        return todo
    finally:
        db.close()

@app.delete("/todos/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_todo(todo_id: int, current_user: User = Depends(get_current_user)):
    db = SessionLocal()
    try:
        todo = db.query(Todo).filter(Todo.id == todo_id, Todo.user_id == current_user.id).first()
        if not todo:
            raise HTTPException(status_code=404, detail="Todo not found")
        
        db.delete(todo)
        db.commit()
    finally:
        db.close()

# 错误处理中间件
@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request, exc):
    return {
        "success": False,
        "status_code": exc.status_code,
        "detail": exc.detail
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)