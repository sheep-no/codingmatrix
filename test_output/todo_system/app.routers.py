from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
import bcrypt
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

# 导入模型
from app.models import User, Todo, Base, engine
from sqlalchemy import create_engine, sessionmaker

# 创建数据库会话
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建路由器
router = APIRouter(
    prefix="/api",
    tags=["auth", "todos"]
)

# JWT配置
SECRET_KEY = "your-secret-key-here"  # 在实际应用中应使用强密钥
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60  # 1小时

# OAuth2密码授权
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# 创建数据库表
Base.metadata.create_all(bind=engine)

# 用户注册模型
class UserCreate(BaseModel):
    username: str
    password: str
    email: Optional[str] = None

# 用户登录模型
class UserLogin(BaseModel):
    username: str
    password: str

# Todo项目模型
class TodoCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: int = 1
    due_date: Optional[str] = None
    completed: bool = False

# Todo项目响应模型
class Todo(TodoCreate):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

# 获取数据库会话
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 密码哈希函数
def get_password_hash(password: str) -> bytes:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

# 验证密码
def verify_password(plain_password: str, hashed_password: bytes) -> bool:
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password)

# 创建访问令牌
def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode.update({"exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# 获取当前用户
async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.JWTError:
        raise credentials_exception
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            raise credentials_exception
        return user
    finally:
        db.close()

# 注册端点
@router.post("/auth/register", response_model=User)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    # 检查用户名是否已存在
    db_user = db.query(User).filter(User.username == user_data.username).first()
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # 创建新用户
    hashed_password = get_password_hash(user_data.password)
    new_user = User(
        username=user_data.username,
        password_hash=hashed_password,
        email=user_data.email
    )
    
    # 添加到数据库并保存
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return new_user

# 登录端点
@router.post("/auth/token", response_model=dict)
async def login(user_data: UserLogin, db: Session = Depends(get_db)):
    # 检查用户名是否存在
    db_user = db.query(User).filter(User.username == user_data.username).first()
    if not db_user or not verify_password(user_data.password, db_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    # 创建访问令牌
    access_token = create_access_token(data={"sub": user_data.username})
    
    return {"access_token": access_token, "token_type": "bearer"}

# 获取当前用户信息
@router.get("/auth/me", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

# 获取所有待办事项
@router.get("/todos", response_model=list[Todo])
async def read_todos(skip: int = 0, limit: int = 10, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    todos = db.query(Todo).filter(Todo.user_id == current_user.id).offset(skip).limit(limit).all()
    return todos

# 获取单个待办事项
@router.get("/todos/{todo_id}", response_model=Todo)
async def read_todo(todo_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    todo = db.query(Todo).filter(Todo.id == todo_id, Todo.user_id == current_user.id).first()
    if todo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Todo not found")
    return todo

# 创建待办事项
@router.post("/todos", response_model=Todo)
async def create_todo(todo: TodoCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    new_todo = Todo(
        title=todo.title,
        description=todo.description,
        priority=todo.priority,
        due_date=todo.due_date,
        completed=todo.completed,
        user_id=current_user.id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(new_todo)
    db.commit()
    db.refresh(new_todo)
    
    return new_todo

# 更新待办事项
@router.put("/todos/{todo_id}", response_model=Todo)
async def update_todo(
    todo_id: int,
    todo_update: TodoCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 获取待更新的待办事项
    todo = db.query(Todo).filter(Todo.id == todo_id, Todo.user_id == current_user.id).first()
    if todo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Todo not found")
    
    # 更新字段
    todo.title = todo_update.title
    todo.description = todo_update.description
    todo.priority = todo_update.priority
    todo.due_date = todo_update.due_date
    todo.completed = todo_update.completed
    todo.updated_at = datetime.utcnow()
    
    # 提交更改
    db.commit()
    db.refresh(todo)
    
    return todo

# 删除待办事项
@router.delete("/todos/{todo_id}", response_model=dict)
async def delete_todo(
    todo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 获取待删除的待办事项
    todo = db.query(Todo).filter(Todo.id == todo_id, Todo.user_id == current_user.id).first()
    if todo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Todo not found")
    
    # 删除待办事项
    db.delete(todo)
    db.commit()
    
    return {"detail": "Todo deleted successfully"}

# 完成待办事项
@router.patch("/todos/{todo_id}/complete")
async def complete_todo(
    todo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 获取待完成的待办事项
    todo = db.query(Todo).filter(Todo.id == todo_id, Todo.user_id == current_user.id).first()
    if todo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Todo not found")
    
    # 更新完成状态
    todo.completed = True
    todo.updated_at = datetime.utcnow()
    
    # 提交更改
    db.commit()
    db.refresh(todo)
    
    return {"detail": "Todo marked as completed"}