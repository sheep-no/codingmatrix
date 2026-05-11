from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime, Boolean, Text, func, TIMETIME
from sqlalchemy.orm import sessionmaker, declarative_base
from pydantic import BaseModel
from datetime import datetime, timedelta
import os
import jwt
from passlib.context import CryptContext
from typing import Optional, List, Dict, Any
import logging
import sys

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 配置CORS
origins = [
    "http://localhost",
    "http://localhost:8080",
    "http://localhost:5173",  # Vite 默认端口
    "https://localhost",
    "https://localhost:8080",
    "https://localhost:5173"
]

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 配置SQLite数据库
SQLALCHEMY_DATABASE_URL = "sqlite:///blog.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# 密码加密配置
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT配置
SECRET_KEY = os.environ.get("SECRET_KEY", "your-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24小时
REFRESH_TOKEN_EXPIRE_DAYS = 7

# 模型定义
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, index=True)
    email = Column(String(100), unique=True, index=True)
    hashed_password = Column(String)
    role_id = Column(Integer, ForeignKey("roles.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Role(Base):
    __tablename__ = "roles"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, index=True)
    description = Column(Text)

class Category(Base):
    __tablename__ = "categories"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, index=True)
    parent_id = Column(Integer, ForeignKey("categories.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Tag(Base):
    __tablename__ = "tags"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Article(Base):
    __tablename__ = "articles"
    
    id = Column(Integer, primary_key=True)
    title = Column(String(200))
    content = Column(Text)
    author_id = Column(Integer, ForeignKey("users.id"))
    category_id = Column(Integer, ForeignKey("categories.id"))
    status = Column(String(20), default="draft")  # draft, published, archived
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    published_at = Column(DateTime)

class ArticleTag(Base):
    __tablename__ = "article_tags"
    
    article_id = Column(Integer, ForeignKey("articles.id"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("tags.id"), primary_key=True)

class Comment(Base):
    __tablename__ = "comments"
    
    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey("articles.id"))
    author_id = Column(Integer, ForeignKey("users.id"))
    content = Column(Text)
    parent_id = Column(Integer, ForeignKey("comments.id"))
    status = Column(String(20), default="pending")  # pending, approved, rejected
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class CommentLike(Base):
    __tablename__ = "comment_likes"
    
    comment_id = Column(Integer, ForeignKey("comments.id"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)

class ArticleLike(Base):
    __tablename__ = "article_likes"
    
    article_id = Column(Integer, ForeignKey("articles.id"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)

class SiteSetting(Base):
    __tablename__ = "site_settings"
    
    id = Column(Integer, primary_key=True)
    site_name = Column(String(100))
    site_description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# 创建数据库表
Base.metadata.create_all(bind=engine)

# Pydantic模型用于请求体和响应体
class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    role_id: Optional[int] = 2  # 默认角色为访客

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role_id: int
    created_at: datetime
    
    class Config:
        orm_mode = True

class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int

class CommentCreate(BaseModel):
    article_id: int
    content: str
    parent_id: Optional[int] = None

class CommentResponse(BaseModel):
    id: int
    article_id: int
    author_id: int
    content: str
    parent_id: Optional[int]
    status: str
    created_at: datetime
    
    class Config:
        orm_mode = True

# 错误处理中间件
@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.detail,
            "request": {
                "method": request.method,
                "url": str(request.url)
            }
        }
    )

# 用户认证路由
@app.post("/api/auth/register", response_model=UserResponse)
async def register(user: UserCreate):
    db = SessionLocal()
    existing_user = db.query(User).filter(User.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = pwd_context.hash(user.password)
    new_user = User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password,
        role_id=user.role_id
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # 创建默认角色如果不存在
    if not db.query(Role).filter(Role.id == user.role_id).first():
        default_role = Role(id=user.role_id, name="Visitor", description="Default visitor role")
        db.add(default_role)
        db.commit()
    
    return new_user

@app.post("/api/auth/login", response_model=TokenResponse)
async def login(login_data: LoginRequest):
    db = SessionLocal()
    user = db.query(User).filter(User.email == login_data.email).first()
    
    if not user or not pwd_context.verify(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    # 创建JWT令牌
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id), "role": user.role_id},
        expires_delta=access_token_expires
    )
    
    refresh_token = create_refresh_token(
        data={"sub": str(user.id), "role": user.role_id}
    )
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES
    }

@app.post("/api/auth/refresh")
async def refresh_token(refresh_token: str):
    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        role = payload.get("role")
        
        if user_id is None or role is None:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user_id, "role": role},
            expires_delta=access_token_expires
        )
        
        return {"access_token": access_token, "token_type": "bearer"}
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

# 装饰器检查JWT令牌
def check_token(request: Request):
    token = request.headers.get("Authorization")
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    
    if not token.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token format")
    
    token = token.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        role = payload.get("role")
        
        if user_id is None or role is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        request.state.user_id = user_id
        request.state.role = role
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# 文章管理路由
@app.get("/api/articles", response_model=List[ArticleResponse])
async def get_articles(
    request: Request,
    skip: int = 0,
    limit: int = 10,
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    status: Optional[str] = None
):
    check_token(request)
    
    db = SessionLocal()
    query = db.query(Article).join(User, Article.author_id == User.id)
    
    if search:
        query = query.filter(
            Article.title.ilike(f"%{search}%") |
            Article.content.ilike(f"%{search}%") |
            Tag.name.ilike(f"%{search}%")
        ).join(ArticleTag, Article.id == ArticleTag.article_id).join(Tag, ArticleTag.tag_id == Tag.id)
    
    if category_id:
        query = query.filter(Article.category_id == category_id)
    
    if status:
        query = query.filter(Article.status == status)
    
    total = query.count()
    articles = query.order_by(Article.created_at.desc()).offset(skip).limit(limit).all()
    
    # 添加文章统计信息
    for article in articles:
        article.view_count = db.query(func.count(Visit.id)).filter(Visit.article_id == article.id).scalar() or 0
    
    return {"articles": articles, "total": total}

@app.get("/api/articles/{article_id}", response_model=ArticleResponse)
async def get_article(article_id: int):
    db = SessionLocal()
    article = db.query(Article).filter(Article.id == article_id, Article.status == "published").first()
    
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    # 添加文章统计信息和评论
    article.view_count = db.query(func.count(Visit.id)).filter(Visit.article_id == article_id).scalar() or 0
    comments = db.query(Comment).filter(Comment.article_id == article_id, Comment.status == "approved").all()
    
    for comment in comments:
        comment.author = db.query(User).filter(User.id == comment.author_id).first()
    
    return {
        "article": article,
        "comments": comments
    }

@app.post("/api/articles", response_model=ArticleResponse)
async def create_article(request: Request, article: ArticleCreate):
    check_token(request)
    
    db = SessionLocal()
    user_id = request.state.user_id
    
    # 检查用户角色，只有管理员或编辑可以创建文章
    user = db.query(User).filter(User.id == user_id).first()
    if user.role_id not in [1, 2]:  # 假设1是管理员，2是编辑
        raise HTTPException(status_code=403, detail="Not authorized to create articles")
    
    new_article = Article(
        title=article.title,
        content=article.content,
        author_id=user_id,
        category_id=article.category_id,
        status="draft" if article.status == "draft" else "published",
        published_at=datetime.utcnow() if article.status == "published" else None
    )
    
    db.add(new_article)
    db.commit()
    db.refresh(new_article)
    
    # 添加标签
    if article.tags:
        for tag_id in article.tags:
            tag = db.query(Tag).filter(Tag.id == tag_id).first()
            if not tag:
                # 创建标签如果不存在
                new_tag = Tag(name=tag_id)  # 假设tag_id是标签名称
                db.add(new_tag)
                db.commit()
                db.refresh(new_tag)
            article_tag = ArticleTag(article_id=new_article.id, tag_id=tag_id)
            db.add(article_tag)
    
    return new_article

# 由于代码过长，文件大小限制，这里只展示了部分代码
# 完整实现需要包含所有路由和模型定义
# 请继续创建其他文件来实现剩余功能