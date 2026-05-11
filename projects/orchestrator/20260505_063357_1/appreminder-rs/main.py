from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, BaseSettings
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Optional, List, Dict, Any
import jwt
import datetime
import hashlib
import secrets
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 配置CORS
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SQLAlchemy配置
SQLALCHEMY_DATABASE_URL = "sqlite:///./blog.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 定义Base模型
Base = declarative_base()

# 用户模型
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True)
    password_hash = Column(String(255))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# 角色模型
class Role(Base):
    __tablename__ = "roles"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# 用户角色关联模型
class UserRole(Base):
    __tablename__ = "user_roles"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    role_id = Column(Integer, ForeignKey("roles.id"))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# 文章模型
class Article(Base):
    __tablename__ = "articles"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255))
    content = Column(Text)
    category_id = Column(Integer, ForeignKey("categories.id"))
    status = Column(String(20), default="published")  # draft, published, archived
    author_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# 分类模型
class Category(Base):
    __tablename__ = "categories"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100))
    parent_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# 评论模型
class Comment(Base):
    __tablename__ = "comments"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    article_id = Column(Integer, ForeignKey("articles.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    parent_id = Column(Integer, ForeignKey("comments.id"), nullable=True)
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# 评论点赞模型
class CommentLike(Base):
    __tablename__ = "comment_likes"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    comment_id = Column(Integer, ForeignKey("comments.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# 文章点赞模型
class ArticleLike(Base):
    __tablename__ = "article_likes"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    article_id = Column(Integer, ForeignKey("articles.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# 站点设置模型
class SiteSetting(Base):
    __tablename__ = "site_settings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    setting_key = Column(String(50), unique=True)
    value = Column(Text)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# 统计数据模型
class Statistic(Base):
    __tablename__ = "statistics"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    metric = Column(String(50))
    value = Column(Text)
    date_range = Column(String(50))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# 创建数据库表
@app.on_event("startup")
def create_tables():
    Base.metadata.create_all(bind=engine)

# JWT配置
JWT_SECRET = os.getenv("JWT_SECRET", "default-secret-key")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

# 用户依赖
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Pydantic模型定义
class UserCreate(BaseModel):
    email: str
    password: str

class UserRead(BaseModel):
    id: int
    email: str
    class Config:
        orm_mode = True

class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class ArticleBase(BaseModel):
    title: str
    content: str
    category_id: int
    status: str = "published"

class ArticleCreate(ArticleBase):
    pass

class ArticleUpdate(ArticleBase):
    pass

class CommentCreate(BaseModel):
    content: str
    parent_id: Optional[int] = None

class CommentRead(BaseModel):
    id: int
    content: str
    created_at: datetime.datetime
    replies: List["CommentRead"] = []

class CommentUpdate(BaseModel):
    content: str

class CommentReadWithReplies(CommentRead):
    replies: List[CommentRead] = []

# 认证依赖
oauth2_scheme = OAuth2PasswordBearer(token_url="/api/v1/auth/login")

# 密码哈希函数
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# 验证密码
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return hash_password(plain_password) == hashed_password

# 获取当前用户
def get_current_user(token: str = Depends(oauth2_scheme)) -> UserRead:
    credentials = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    user_id = credentials.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return UserRead(id=user.id, email=user.email)

# 注册路由
@app.post("/api/v1/auth/register", response_model=UserRead)
def register(user: UserCreate, db: Session = Depends(get_db)):
    hashed_password = hash_password(user.password)
    db_user = User(email=user.email, password_hash=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    # 默认角色
    admin_role = db.query(Role).filter(Role.name == "admin").first()
    if not admin_role:
        new_role = Role(name="admin")
        db.add(new_role)
        db.commit()
    
    # 创建用户角色关联
    user_role = UserRole(user_id=db_user.id, role_id=1)  # 1是admin角色ID
    db.add(user_role)
    db.commit()
    
    return db_user

@app.post("/api/v1/auth/login", response_model=TokenResponse)
def login(login_data: LoginRequest, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == login_data.email).first()
    if not db_user or not verify_password(login_data.password, db_user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # 生成JWT令牌
    access_token_expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = jwt.encode({"sub": str(db_user.id), "exp": access_token_expires}, JWT_SECRET, algorithm=JWT_ALGORITHM)
    
    refresh_token = secrets.token_urlsafe(32)
    
    # 存储刷新令牌（在实际应用中，应该存储在数据库或缓存中）
    # 在本示例中，我们简化处理，实际生产环境应使用更安全的方式
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }

@app.post("/api/v1/auth/refresh", response_model=TokenResponse)
def refresh_token(refresh_token: RefreshTokenRequest, db: Session = Depends(get_db)):
    # 在实际应用中，应该验证刷新令牌的有效性
    # 这里简化处理，实际生产环境应使用更安全的方式
    
    access_token_expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = jwt.encode({"sub": "refresh-token"}, JWT_SECRET, algorithm=JWT_ALGORITHM)
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token.refresh_token,  # 实际应用中应该生成新的刷新令牌
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }

@app.get("/api/v1/articles", response_model=List[ArticleRead])
def get_articles(
    db: Session = Depends(get_db),
    page: int = 1,
    search: str = None,
    category_id: int = None
):
    skip = (page - 1) * 10
    query = db.query(Article).order_by(Article.created_at.desc())
    
    if search:
        query = query.filter(
            Article.title.ilike(f"%{search}%") |
            Article.content.ilike(f"%{search}%")
        )
    
    if category_id:
        query = query.filter(Article.category_id == category_id)
    
    articles = query.offset(skip).limit(10).all()
    
    # 计算总页数
    total = query.count()
    total_pages = (total + 9) // 10
    
    return {
        "articles": articles,
        "total_pages": total_pages,
        "current_page": page
    }

# 其他路由需要根据需求继续实现...
# 这里只实现了部分核心功能，完整实现需要继续开发其他API端点