from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from pydantic import BaseModel, EmailStr
from jose import jwt
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer
from app import schemas, models, crud, auth
from app.database import SessionLocal, engine

# 创建路由器
router = APIRouter(prefix="/api", tags=["todos"])

# 依赖：获取数据库会话
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 密码安全上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT配置
SECRET_KEY = "your-secret-key"  # 实际应用中应使用环境变量
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60  # 1小时

# OAuth2密码承载令牌方案
oauth2_scheme = OAuth2PasswordBearer(token_url="/api/auth/login")

# 创建用户
@router.post("/users/", response_model=schemas.User)
def create_user(user: schemas.UserCreate):
    # 检查用户名是否已存在
    db = next(get_db())
    if crud.get_user_by_name(db, name=user.name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在"
        )
    
    # 创建新用户
    db_user = crud.create_user(db=db, user=user)
    return db_user

# 用户登录
@router.post("/auth/login", response_model=schemas.Token)
def login(user: schemas.UserLogin):
    db = next(get_db())
    
    # 验证用户名是否存在
    db_user = crud.get_user_by_name(db, name=user.name)
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )
    
    # 验证密码
    if not auth.verify_password(user.password, db_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )
    
    # 创建JWT令牌
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": db_user.name}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

# 获取当前用户
async def get_current_user(token: str = Depends(oauth2_scheme)) -> schemas.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # 验证JWT令牌
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.JWTError:
        raise credentials_exception
    
    db = next(get_db())
    user = crud.get_user_by_name(db, name=username)
    if user is None:
        raise credentials_exception
    
    return user

# 获取待办事项列表
@router.get("/todos/", response_model=List[schemas.Todo])
async def read_todos(
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user),
    priority: Optional[schemas.Priority] = Query(None),
    due_date: Optional[str] = None,
    completed: Optional[bool] = None
):
    # 检查用户是否存在
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未授权")
    
    # 获取待办事项
    todos = crud.get_todos(
        db,
        user_id=current_user.id,
        priority=priority,
        due_date=due_date,
        completed=completed
    )
    return todos

# 创建待办事项
@router.post("/todos/", response_model=schemas.Todo)
async def create_todo(
    db: Session = Depends(get_db),
    todo: schemas.TodoCreate = Depends(),
    current_user: schemas.User = Depends(get_current_user)
):
    # 检查用户是否存在
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未授权")
    
    # 创建待办事项
    db_todo = crud.create_todo(db=db, todo=todo, user_id=current_user.id)
    return db_todo

# 获取单个待办事项
@router.get("/todos/{todo_id}", response_model=schemas.Todo)
async def read_todo(
    todo_id: int,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user)
):
    # 检查用户是否存在
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未授权")
    
    # 获取待办事项
    db_todo = crud.get_todo(db, todo_id=todo_id, user_id=current_user.id)
    if db_todo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="待办事项未找到"
        )
    return db_todo

# 更新待办事项
@router.put("/todos/{todo_id}", response_model=schemas.Todo)
async def update_todo(
    todo_id: int,
    todo: schemas.TodoUpdate = Depends(),
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user)
):
    # 检查用户是否存在
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未授权")
    
    # 更新待办事项
    db_todo = crud.update_todo(db=db, todo_id=todo_id, todo=todo, user_id=current_user.id)
    if db_todo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="待办事项未找到或未授权"
        )
    return db_todo

# 删除待办事项
@router.delete("/todos/{todo_id}", response_model=schemas.Message)
async def delete_todo(
    todo_id: int,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user)
):
    # 检查用户是否存在
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未授权")
    
    # 删除待办事项
    if not crud.delete_todo(db=db, todo_id=todo_id, user_id=current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="待办事项未找到或未授权"
        )
    
    return {"message": "待办事项删除成功"}

# 获取用户信息
@router.get("/users/me/", response_model=schemas.User)
async def read_users_me(current_user: schemas.User = Depends(get_current_user)):
    return current_user

# 用户注销
@router.post("/auth/logout")
async def logout(current_user: schemas.User = Depends(get_current_user)):
    # 在实际应用中，可能需要在前端清除token
    return {"detail": "登出成功"}