from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from datetime import datetime, timedelta
import bcrypt
import jwt
from typing import Optional, Dict, Any

# 导入数据库模型
class User(BaseModel):
    user_id: str
    email: str
    password_hash: str
    created_at: datetime

# 导入配置
class Settings:
    SECRET_KEY = "mysecretkey"  # 在实际应用中应使用环境变量
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = 15

# 创建路由
router = APIRouter(prefix="/auth", tags=["auth"])

# OAuth2 密码承载令牌方案
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

# 模拟数据库（在实际应用中应使用数据库）
fake_db = {
    "user1": User(
        user_id="user1",
        email="user1@example.com",
        password_hash=bcrypt.hashpw(b"password1", bcrypt.gensalt()).decode(),
        created_at=datetime.utcnow(),
    ),
}

# 生成访问令牌
def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=Settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, Settings.SECRET_KEY, algorithm=Settings.ALGORITHM)
    return encoded_jwt

# 用户凭据模型
class UserCredentials(BaseModel):
    email: str
    password: str

# 检查用户凭据
def verify_user_credentials(credentials: UserCredentials) -> Optional[User]:
    user_id = None
    for uid, user in fake_db.items():
        if user.email == credentials.email:
            if bcrypt.checkpw(credentials.password.encode(), user.password_hash.encode()):
                user_id = uid
                break
    return fake_db.get(user_id) if user_id else None

# 登录端点
@router.post("/login")
async def login(credentials: UserCredentials):
    user = verify_user_credentials(credentials)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # 创建访问令牌
    access_token = create_access_token(
        data={"sub": user.user_id},
        expires_delta=timedelta(minutes=Settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return {"access_token": access_token}

# 获取当前用户信息
@router.get("/me")
async def get_current_user(token: str = Depends(oauth2_scheme)):
    # 验证令牌
    try:
        payload = jwt.decode(token, Settings.SECRET_KEY, algorithms=[Settings.ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    # 从数据库获取用户信息
    user = fake_db.get(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    return user.dict()