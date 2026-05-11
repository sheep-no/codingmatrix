from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from passlib.context import CryptContext
from jose import jwt
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import os

# 配置CORS
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 数据库配置
SQLALCHEMY_DATABASE_URL = "sqlite:///blog.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 密码加密
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT配置
SECRET_KEY = "your-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_MINUTES = 60*24  # 1天

# 用户模型
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, default=datetime.utcnow)

# 角色模型
class Role(Base):
    __tablename__ = "roles"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(20), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# 用户角色关联模型
class UserRole(Base):
    __tablename__ = "user_roles"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role_id = Column(Integer, ForeignKey("roles.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# 文章分类模型
class Category(Base):
    __tablename__ = "categories"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    parent_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

# 文章模型
class Article(Base):
    __tablename__ = "articles"
    
    id = Column(Integer, primary_key=True)
    title = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String(20), default="draft")  # draft, published, archived
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

# 标签模型
class Tag(Base):
    __tablename__ = "tags"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# 文章标签关联模型
class ArticleTag(Base):
    __tablename__ = "article_tags"
    
    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey("articles.id"), nullable=False)
    tag_id = Column(Integer, ForeignKey("tags.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# 评论模型
class Comment(Base):
    __tablename__ = "comments"
    
    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey("articles.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("comments.id"), nullable=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

# 评论点赞模型
class CommentLike(Base):
    __tablename__ = "comment_likes"
    
    id = Column(Integer, primary_key=True)
    comment_id = Column(Integer, ForeignKey("comments.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# 文章点赞模型
class ArticleLike(Base):
    __tablename__ = "article_likes"
    
    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey("articles.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

# 站点设置模型
class SiteSetting(Base):
    __tablename__ = "site_settings"
    
    id = Column(Integer, primary_key=True)
    site_title = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    logo_url = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

# 统计模型
class Statistics(Base):
    __tablename__ = "statistics"
    
    id = Column(Integer, primary_key=True)
    total_articles = Column(Integer, default=0)
    total_users = Column(Integer, default=0)
    total_comments = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

# Pydantic 模型用于 API 请求和响应
class UserCreate(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    created_at: datetime

class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str

class RefreshRequest(BaseModel):
    refresh_token: str

class ArticleCreate(BaseModel):
    title: str
    content: str
    status: str = "draft"

class ArticleUpdate(BaseModel):
    title: Optional[str]
    content: Optional[str]
    status: Optional[str]

class CommentCreate(BaseModel):
    content: str
    parent_id: Optional[int] = None

class CommentResponse(BaseModel):
    id: int
    article_id: int
    content: str
    created_at: datetime
    user_id: Optional[int] = None

class CommentLikeRequest(BaseModel):
    comment_id: int

class ArticleLikeRequest(BaseModel):
    article_id: int

class StatsRequest(BaseModel):
    time_frame: str = "monthly"

class SettingsRequest(BaseModel):
    site_title: Optional[str]
    description: Optional[str]
    logo_url: Optional[str]

# JWT工具函数
def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode.update({"exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode.update({"exp": datetime.utcnow() + timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES)})
    return jwt.decode(to_encode, SECRET_KEY, algorithms=[ALGORITHM])

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def get_current_user(token: str = Depends()) -> User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
        # 在实际应用中，这里应该从数据库获取用户
        # 这里我们简化处理，只返回用户ID
        return {"id": int(user_id)}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 创建数据库和表
Base.metadata.create_all(bind=engine)

# API路由
@app.post("/api/auth/register", response_model=UserResponse)
def register(user: UserCreate):
    db = next(get_db())
    
    # 检查邮箱是否已存在
    existing_user = db.query(User).filter(User.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # 创建新用户
    hashed_password = get_password_hash(user.password)
    db_user = User(email=user.email, password_hash=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return {"id": db_user.id, "email": db_user.email, "created_at": db_user.created_at}

@app.post("/api/auth/login", response_model=TokenResponse)
def login(login_data: LoginRequest):
    db = next(get_db())
    
    # 获取用户
    user = db.query(User).filter(User.email == login_data.email).first()
    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # 创建JWT令牌
    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES,
        "token_type": "Bearer"
    }

@app.post("/api/auth/refresh", response_model=TokenResponse)
def refresh_token(refresh_data: RefreshRequest):
    try:
        payload = jwt.decode(refresh_data.refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # 重新创建令牌
        access_token = create_access_token({"sub": user_id})
        refresh_token = create_refresh_token({"sub": user_id})
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES,
            "token_type": "Bearer"
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.get("/api/articles", response_model=List[dict])
def get_articles(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    articles = db.query(Article).offset(skip).limit(limit).all()
    return articles

@app.get("/api/articles/{article_id}", response_model=dict)
def get_article(article_id: int, db: Session = Depends(get_db)):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article

@app.post("/api/articles", response_model=dict)
def create_article(article: ArticleCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    db_article = Article(**article.dict(), user_id=current_user["id"])
    db.add(db_article)
    db.commit()
    db.refresh(db_article)
    return db_article

@app.put("/api/articles/{article_id}", response_model=dict)
def update_article(article_id: int, article: ArticleUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    db_article = db.query(Article).filter(Article.id == article_id).first()
    if not db_article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    # 检查权限（只有作者或管理员可以更新）
    if current_user["id"] != db_article.user_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this article")
    
    update_data = article.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_article, key, value)
    db.commit()
    db.refresh(db_article)
    return db_article

@app.delete("/api/articles/{article_id}", response_model=dict)
def delete_article(article_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    db_article = db.query(Article).filter(Article.id == article_id).first()
    if not db_article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    # 检查权限（只有作者或管理员可以删除）
    if current_user["id"] != db_article.user_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this article")
    
    db.delete(db_article)
    db.commit()
    return {"detail": "Article deleted successfully"}

@app.post("/api/articles/{article_id}/comments", response_model=CommentResponse)
def create_comment(article_id: int, comment: CommentCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    db_comment = Comment(**comment.dict(), article_id=article_id, user_id=current_user["id"] if current_user else None)
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)
    return db_comment

@app.get("/api/articles/{article_id}/comments", response_model=List[CommentResponse])
def get_comments(article_id: int, db: Session = Depends(get_db)):
    comments = db.query(Comment).filter(Comment.article_id == article_id).all()
    return comments

@app.post("/api/comments/{comment_id}/like", response_model=dict)
def like_comment(comment_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    db_comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not db_comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    
    # 检查是否已经点赞过
    existing_like = db.query(CommentLike).filter(
        CommentLike.comment_id == comment_id,
        CommentLike.user_id == current_user["id"]
    ).first()
    
    if existing_like:
        db.delete(existing_like)
        db.commit()
        return {"detail": "Comment unlike successfully"}
    
    # 添加新点赞
    db_like = CommentLike(comment_id=comment_id, user_id=current_user["id"])
    db.add(db_like)
    db.commit()
    db.refresh(db_like)
    
    # 更新评论点赞数
    db_comment.likes += 1
    db.commit()
    
    return {"detail": "Comment liked successfully"}

@app.post("/api/comments/{comment_id}/like", response_model=dict)
def like_comment(comment_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    db_comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not db_comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    
    # 检查是否已经点赞过
    existing_like = db.query(CommentLike).filter(
        CommentLike.comment_id == comment_id,
        CommentLike.user_id == current_user["id"]
    ).first()
    
    if existing_like:
        db.delete(existing_like)
        db.commit()
        return {"detail": "Comment unlike successfully"}
    
    # 添加新点赞
    db_like = CommentLike(comment_id=comment_id, user_id=current_user["id"])
    db.add(db_like)
    db.commit()
    db.refresh(db_like)
    
    # 更新评论点赞数
    db_comment.likes += 1
    db.commit()
    
    return {"detail": "Comment liked successfully"}

@app.post("/api/articles/{article_id}/like", response_model=dict)
def like_article(article_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    db_article = db.query(Article).filter(Article.id == article_id).first()
    if not db_article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    # 检查是否已经点赞过
    existing_like = db.query(ArticleLike).filter(
        ArticleLike.article_id == article_id,
        ArticleLike.user_id == current_user["id"]
    ).first()
    
    if existing_like:
        db.delete(existing_like)
        db.commit()
        return {"detail": "Article unlike successfully"}
    
    # 添加新点赞
    db_like = ArticleLike(article_id=article_id, user_id=current_user["id"])
    db.add(db_like)
    db.commit()
    db.refresh(db_like)
    
    # 更新文章点赞数
    db_article.likes += 1
    db.commit()
    
    return {"detail": "Article liked successfully"}

@app.get("/api/stats", response_model=dict)
def get_stats(request: StatsRequest = Depends(), db: Session = Depends(get_db)):
    # 在实际应用中，这里应该查询数据库获取统计信息
    # 这里我们简化处理，返回模拟数据
    return {
        "total_articles": 120,
        "total_users": 50,
        "total_comments": 300,
        "popular_articles": [
            {"id": 1, "title": "Getting Started with FastAPI", "likes": 45},
            {"id": 2, "title": "SQLAlchemy ORM Basics", "likes": 32},
            {"id": 3, "title": "Building RESTful APIs with FastAPI", "likes": 28}
        ]
    }

@app.get("/api/settings", response_model=dict)
def get_settings(db: Session = Depends(get_db)):
    # 在实际应用中，这里应该查询数据库获取设置
    # 这里我们简化处理，返回模拟数据
    return {
        "site_title": "My Blog",
        "description": "A blog about FastAPI and SQLAlchemy",
        "logo_url": "https://example.com/logo.png"
    }

# 健康检查端点
@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.utcnow()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)