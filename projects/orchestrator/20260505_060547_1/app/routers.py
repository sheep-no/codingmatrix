from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User, Article, Comment, Tag, Category, UserRole, Role

# 创建路由实例
router = APIRouter(prefix="/api", tags=["routers"])

# 用户认证依赖
oauth2_scheme = OAuth2PasswordBearer(token_url="/auth/token")

# 请求体模型

class RegisterRequest(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str

class UpdateUserRequest(BaseModel):
    username: Optional[str] = None
    bio: Optional[str] = None
    avatar: Optional[str] = None

class UserResponse(BaseModel):
    id: int
    email: str
    username: Optional[str]
    bio: Optional[str]
    avatar: Optional[str]
    role: Optional[str] = None

class ArticleRequest(BaseModel):
    title: str
    content: str
    category_id: Optional[int] = None
    tags: Optional[List[int]] = None
    status: str = "draft"

class CommentRequest(BaseModel):
    content: str
    parent_id: Optional[int] = None

class LikeRequest(BaseModel):
    article_id: Optional[int] = None
    comment_id: Optional[int] = None

class TagRequest(BaseModel):
    name: str

class CategoryRequest(BaseModel):
    name: str
    parent_id: Optional[int] = None

class SettingsRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    allow_comments: Optional[bool] = None
    comment_moderation: Optional[bool] = None

class StatsRequest(BaseModel):
    period: str = "month"

# 路由定义

@router.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user_data: RegisterRequest, db: Session = Depends(get_db)):
    # 检查用户是否已存在
    if db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # 创建新用户
    hashed_password = get_password_hash(user_data.password)
    new_user = User(
        email=user_data.email,
        password_hash=hashed_password,
        created_at=datetime.utcnow()
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # 默认角色
    admin_role = db.query(Role).filter(Role.name == "admin").first()
    if not admin_role:
        new_role = Role(name="admin")
        db.add(new_role)
        db.commit()
    
    # 添加用户角色关联
    user_role = UserRole(user_id=new_user.id, role_id=1)
    db.add(user_role)
    db.commit()
    
    return new_user

@router.post("/auth/login", response_model=TokenResponse)
def login(login_data: LoginRequest, db: Session = Depends(get_db)):
    # 查找用户
    user = db.query(User).filter(User.email == login_data.email).first()
    if not user or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # 创建JWT令牌
    access_token = create_access_token(data={"sub": user.email})
    refresh_token = create_refresh_token(data={"sub": user.email})
    
    return {"access_token": access_token, "refresh_token": refresh_token}

@router.post("/auth/refresh", response_model=TokenResponse)
def refresh_token(refresh_token_data: RefreshRequest):
    # 验证和刷新令牌
    payload = decode_refresh_token(refresh_token_data.refresh_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    access_token = create_access_token(data=payload)
    new_refresh_token = create_refresh_token(data=payload)
    
    return {"access_token": access_token, "refresh_token": new_refresh_token}

@router.get("/users/me", response_model=UserResponse)
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    # 验证JWT令牌
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # 查找用户
    user = db.query(User).filter(User.email == payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # 添加角色信息
    user.roles = db.query(Role).join(UserRole).filter(UserRole.user_id == user.id).all()
    
    return user

@router.put("/users/me", response_model=UserResponse)
def update_user(update_data: UpdateUserRequest, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    # 验证JWT令牌
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # 查找用户
    user = db.query(User).filter(User.email == payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # 更新用户信息
    for key, value in update_data.dict().items():
        if value is not None:
            setattr(user, key, value)
    
    db.commit()
    db.refresh(user)
    user.roles = db.query(Role).join(UserRole).filter(UserRole.user_id == user.id).all()
    return user

@router.get("/articles", response_model=List[ArticleResponse])
def get_articles(
    db: Session = Depends(get_db),
    page: int = 1,
    per_page: int = 10,
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    tag_ids: Optional[List[int]] = None,
    status: Optional[str] = None
):
    # 查询构建
    query = db.query(Article).order_by(Article.created_at.desc())
    
    # 添加过滤条件
    if search:
        query = query.filter(
            Article.title.ilike(f"%{search}%") |
            Article.content.ilike(f"%{search}%") |
            Article.tags.any(Tag.name.ilike(f"%{search}%"))
        )
    
    if category_id:
        query = query.filter(Article.category_id == category_id)
    
    if tag_ids:
        query = query.filter(Article.tags.any(Tag.id.in_(tag_ids)))
    
    if status:
        query = query.filter(Article.status == status)
    
    # 分页
    total = query.count()
    articles = query.offset((page-1)*per_page).limit(per_page).all()
    
    # 转换结果
    result = []
    for article in articles:
        article_data = article.to_dict()
        article_data["tags"] = [tag.name for tag in article.tags]
        article_data["categories"] = db.query(Category).filter(Category.id == article.category_id).first().name if article.category_id else None
        result.append(article_data)
    
    return {"total": total, "page": page, "per_page": per_page, "articles": result}

@router.get("/articles/{article_id}", response_model=ArticleResponse)
def get_article(article_id: int, db: Session = Depends(get_db)):
    # 查找文章
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    # 转换结果
    article_data = article.to_dict()
    article_data["tags"] = [tag.name for tag in article.tags]
    article_data["categories"] = db.query(Category).filter(Category.id == article.category_id).first().name if article.category_id else None
    
    return article_data

@router.post("/articles", response_model=ArticleResponse, status_code=status.HTTP_201_CREATED)
def create_article(
    article_data: ArticleRequest,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    # 验证JWT令牌
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # 查找用户
    user = db.query(User).filter(User.email == payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # 创建文章
    new_article = Article(
        title=article_data.title,
        content=article_data.content,
        user_id=user.id,
        category_id=article_data.category_id,
        status=article_data.status,
        created_at=datetime.utcnow()
    )
    
    db.add(new_article)
    db.flush()
    
    # 添加标签
    if article_data.tags:
        for tag_id in article_data.tags:
            tag = db.query(Tag).filter(Tag.id == tag_id).first()
            if tag:
                new_article.tags.append(tag)
    
    db.commit()
    db.refresh(new_article)
    
    # 添加类别
    if article_data.category_id:
        category = db.query(Category).filter(Category.id == article_data.category_id).first()
        if category:
            new_article.category_id = category_id
    
    # 转换结果
    article_data = new_article.to_dict()
    article_data["tags"] = [tag.name for tag in new_article.tags]
    article_data["categories"] = db.query(Category).filter(Category.id == new_article.category_id).first().name if new_article.category_id else None
    
    return article_data

@router.put("/articles/{article_id}", response_model=ArticleResponse)
def update_article(
    article_id: int,
    article_data: ArticleRequest,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    # 验证JWT令牌
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # 查找用户
    user = db.query(User).filter(User.email == payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # 查找文章
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    # 检查权限
    if article.user_id != user.id and not has_admin_role(token, db):
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # 更新文章
    article.title = article_data.title
    article.content = article_data.content
    article.category_id = article_data.category_id
    article.status = article_data.status
    article.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(article)
    
    # 更新标签
    if article_data.tags:
        article.tags.clear()
        for tag_id in article_data.tags:
            tag = db.query(Tag).filter(Tag.id == tag_id).first()
            if tag:
                article.tags.append(tag)
    
    # 转换结果
    article_data = article.to_dict()
    article_data["tags"] = [tag.name for tag in article.tags]
    article_data["categories"] = db.query(Category).filter(Category.id == article.category_id).first().name if article.category_id else None
    
    return article_data

@router.delete("/articles/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_article(
    article_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    # 验证JWT令牌
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # 查找用户
    user = db.query(User).filter(User.email == payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # 查找文章
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    # 检查权限
    if article.user_id != user.id and not has_admin_role(token, db):
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # 删除文章
    db.delete(article)
    db.commit()

@router.post("/articles/{article_id}/comments", response_model=CommentResponse)
def create_comment(
    article_id: int,
    comment_data: CommentRequest,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    # 验证JWT令牌
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # 查找用户
    user = db.query(User).filter(User.email == payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # 查找文章
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    # 创建评论
    new_comment = Comment(
        content=comment_data.content,
        article_id=article_id,
        user_id=user.id,
        parent_id=comment_data.parent_id,
        created_at=datetime.utcnow()
    )
    
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)
    
    return new_comment

@router.get("/articles/{article_id}/comments", response_model=List[CommentResponse])
def get_comments(article_id: int, db: Session = Depends(get_db)):
    # 查找文章
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    
    # 获取评论
    comments = db.query(Comment).filter(Comment.article_id == article_id).order_by(Comment.created_at.asc()).all()
    
    # 转换结果
    result = []
    for comment in comments:
        comment_data = comment.to_dict()
        comment_data["user"] = db.query(User).filter(User.id == comment.user_id).first().username if comment.user_id else None
        result.append(comment_data)
    
    return result

@router.post("/comments/{comment_id}/like", response_model=CommentResponse)
def like_comment(
    comment_id: int,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    # 验证JWT令牌
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # 查找用户
    user = db.query(User).filter(User.email == payload.get("sub")).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # 查找评论
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    
    # 检查是否已点赞
    if comment in db.query(CommentLike).filter(CommentLike.user_id == user.id, CommentLike.comment_id == comment_id).first():
        raise HTTPException(status_code=400, detail="Already liked")
    
    # 创建点赞记录
    new_like = CommentLike(user_id=user.id, comment_id=comment_id)
    db.add(new_like)
    db.commit()
    db.refresh(comment)
    
    return comment

@router.get("/tags", response_model=List[TagResponse])
def get_tags(db: Session = Depends(get_db)):
    # 获取标签
    tags = db.query(Tag).all()
    
    # 转换结果
    result = []
    for tag in tags:
        result.append({"id": tag.id, "name": tag.name})
    
    return result

@router.get("/categories", response_model=List[CategoryResponse])
def get_categories(db: Session = Depends(get_db)):
    # 获取分类
    categories = db.query(Category).order_by(Category.parent_id.asc()).all()
    
    # 转换结果
    result = []
    for category in categories:
        result.append({"id": category.id, "name": category.name, "parent_id": category.parent_id})
    
    return result

@router.get("/stats", response_model=StatsResponse)
def get_stats(
    stats_request: StatsRequest = Depends(),
    db: Session = Depends(get_db)
):
    # 获取统计信息
    # 这里简化处理，实际项目需要根据时间段和具体需求查询数据库
    total_articles = db.query(Article).count()
    total_users = db.query(User).count()
    total_comments = db.query(Comment).count()
    
    # 返回示例数据
    return {
        "total_articles": total_articles,
        "total_users": total_users,
        "total_comments": total_comments,
        "popular_articles": [],
        "user_activity": []
    }

@router.get("/settings", response_model=SettingsResponse)
def get_settings(db: Session = Depends(get_db)):
    # 获取站点设置
    settings = db.query(SiteSettings).first()
    
    # 转换结果
    if not settings:
        return {"title": "My Blog", "description": "My personal blog", "allow_comments": True, "comment_moderation": False}
    
    return {
        "title": settings.title,
        "description": settings.description,
        "allow_comments": settings.allow_comments,
        "comment_moderation": settings.comment_moderation
    }

# 辅助函数

def get_password_hash(password: str) -> str:
    # 在实际项目中使用更安全的哈希算法，如bcrypt
    return password

def verify_password(plain_password: str, hashed_password: str) -> bool:
    # 在实际项目中使用更安全的验证算法
    return plain_password == hashed_password

def create_access_token(data: dict) -> str:
    # 创建JWT访问令牌
    to_encode = data.copy()
    # 添加到期时间
    to_encode.update({"iat": datetime.utcnow(), "exp": datetime.utcnow() + timedelta(minutes=15)})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict) -> str:
    # 创建JWT刷新令牌
    to_encode = data.copy()
    # 添加到期时间
    to_encode.update({"iat": datetime.utcnow(), "exp": datetime.utcnow() + timedelta(days=7)})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> dict:
    # 解码JWT访问令牌
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

def decode_refresh_token(refresh_token: str) -> dict:
    # 解码JWT刷新令牌
    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="Refresh token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="Invalid refresh token")

def has_admin_role(token: str, db: Session) -> bool:
    # 检查用户是否具有管理员角色
    payload = decode_access_token(token)
    user_email = payload.get("sub")
    user = db.query(User).filter(User.email == user_email).first()
    
    if not user:
        return False
    
    # 获取用户的角色
    user_roles = db.query(Role).join(UserRole).filter(UserRole.user_id == user.id).all()
    return any(role.name == "admin" for role in user_roles)

# 导出路由
def init_routes(app):
    app.include_router(router)