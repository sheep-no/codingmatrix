from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from typing import Optional, Dict, Any

# 导入数据库模型（假设已定义）
from core.models import User, Product, Article

# 导入配置
from config import settings

# 导入密码哈希工具
from passlib.context import CryptContext

# 导入JWT工具
import jwt

# 导入数据库依赖
from fastapi import Request
from sqlalchemy.orm import Session

# 创建路由器
router = APIRouter()

# 密码哈希上下文
pwd_context = CryptContext(
    schemes=["bcrypt"],
    default="bcrypt",
    deprecated="auto"
)

# JWT设置
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# 依赖注入 - 数据库会话
def get_db():
    # 实际实现中应该从数据库连接池获取会话
    # 这里简化为返回一个空的数据库会话对象
    db = Session(settings.SQLALCHEMY_DATABASE_URI)
    try:
        yield db
    finally:
        db.close()

# 用户服务类
class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.user_model = User

    def register_user(self, email: str, password: str) -> User:
        """
        注册新用户
        """
        db_user = self.user_model(email=email)
        db_user.hashed_password = pwd_context.hash(password)
        self.db.add(db_user)
        self.db.commit()
        self.db.refresh(db_user)
        return db_user

    def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """
        认证用户
        """
        user = self.db.query(self.user_model).filter(self.user_model.email == email).first()
        if not user:
            return None
        if not pwd_context.verify(password, user.hashed_password):
            return None
        return user

    def create_access_token(self, data: Dict[str, Any], expires_delta: Optional[int] = None) -> str:
        """
        创建访问令牌
        """
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + timedelta(minutes=expires_delta)
        else:
            expire = datetime.utcnow() + timedelta(minutes=15)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        return encoded_jwt

# 创建认证服务实例
auth_service = AuthService(get_db())

# 路由 - 用户登录
@router.post("/login")
async def login(email: str, password: str):
    """
    用户登录接口
    """
    user = auth_service.authenticate_user(email, password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    access_token = auth_service.create_access_token({
        "sub": user.email,
        "user_id": str(user.user_id)
    })
    
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

# 路由 - 获取当前用户信息
@router.get("/me")
async def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """
    获取当前用户信息
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        email = payload.get("sub")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials"
            )
    except jwt.JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    
    user = auth_service.db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return {
        "user_id": str(user.user_id),
        "email": user.email
    }