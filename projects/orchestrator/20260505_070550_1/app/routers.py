from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from datetime import datetime, timedelta

# 导入 Pydantic 模型（假设这些已经定义在其他文件中）
from app.models import User, Category, Article, Comment, Tag, UserRole, SiteSetting
from app.schemas import (
    UserCreate, UserLogin, TokenResponse,
    ArticleCreate, ArticleResponse, ArticleUpdate,
    CommentCreate, CommentResponse,
    CategoryResponse, TagResponse,
    SiteSettingResponse
)
from app.dependencies import get_db, get_current_active_user, get_current_user_by_token, get_current_superuser

# 创建 API 路由器
router = APIRouter(prefix="/api", tags=["auth"])

# 依赖注入
def get_db_session(db: Session = Depends(get_db)):
    return db

# 认证相关路由
@router.post("/auth/register", response_model=TokenResponse)
async def register(user_data: UserCreate, db: Session = Depends(get_db_session)):
    # 检查用户名是否已存在
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # 创建新用户
    hashed_password = get_password_hash(user_data.password)
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        password=hashed_password,
        role_id=1  # 默认角色为普通用户
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # 创建访问令牌
    access_token = create_access_token(data={"sub": new_user.username})
    refresh_token = create_refresh_token(data={"sub": new_user.username})
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

@router.post("/auth/login", response_model=TokenResponse)
async def login(user_data: UserLogin, db: Session = Depends(get_db_session)):
    # 查找用户
    user = db.query(User).filter(User.username == user_data.username).first()
    if not user or not verify_password(user_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    # 创建访问令牌
    access_token = create_access_token(data={"sub": user.username})
    refresh_token = create_refresh_token(data={"sub": user.username})
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh_token(refresh_token: str, db: Session = Depends(get_db_session)):
    # 验证刷新令牌
    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
    except jwt.JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    # 重新创建访问令牌
    access_token = create_access_token(data={"sub": username})
    new_refresh_token = create_refresh_token(data={"sub": username})
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

# 文章管理路由
@router.get("/articles", response_model=List[ArticleResponse])
async def get_articles(
    db: Session = Depends(get_db_session),
    skip: int = 0,
    limit: int = 10,
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    user_id: Optional[int] = None
):
    query = db.query(Article)
    
    if search:
        query = query.filter(
            Article.title.ilike(f"%{search}%") |
            Article.content.ilike(f"%{search}%") |
            Article.tags.any(Tag.name.ilike(f"%{search}%"))
        )
    
    if category_id:
        query = query.filter(Article.category_id == category_id)
    
    if user_id:
        query = query.filter(Article.user_id == user_id)
    
    articles = query.order_by(Article.created_at.desc()).offset(skip).limit(limit).all()
    return articles

@router.get("/articles/{article_id}", response_model=ArticleResponse)
async def get_article(article_id: int, db: Session = Depends(get_db_session)):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found"
        )
    return article

@router.post("/articles", response_model=ArticleResponse)
async def create_article(
    article_data: ArticleCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db_session)
):
    # 检查用户是否有创建文章的权限
    if current_user.role_id != 2 and current_user.role_id != 3:  # 假设2是编辑，3是管理员
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to create article"
        )
    
    new_article = Article(
        title=article_data.title,
        content=article_data.content,
        category_id=article_data.category_id,
        user_id=current_user.id,
        status=article_data.status,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    if article_data.tags:
        # 处理标签关联
        for tag_id in article_data.tags:
            tag = db.query(Tag).filter(Tag.id == tag_id).first()
            if tag:
                new_article.tags.append(tag)
    
    db.add(new_article)
    db.commit()
    db.refresh(new_article)
    
    return new_article

@router.put("/articles/{article_id}", response_model=ArticleResponse)
async def update_article(
    article_id: int,
    article_data: ArticleUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db_session)
):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found"
        )
    
    # 检查用户是否有更新文章的权限
    if (current_user.id != article.user_id and 
        current_user.role_id != 2 and 
        current_user.role_id != 3):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this article"
        )
    
    # 更新文章数据
    if article_data.title:
        article.title = article_data.title
    if article_data.content:
        article.content = article_data.content
    if article_data.category_id:
        article.category_id = article_data.category_id
    if article_data.status:
        article.status = article_data.status
    article.updated_at = datetime.utcnow()
    
    # 处理标签更新
    if article_data.tags:
        article.tags.clear()
        for tag_id in article_data.tags:
            tag = db.query(Tag).filter(Tag.id == tag_id).first()
            if tag:
                article.tags.append(tag)
    
    db.commit()
    db.refresh(article)
    return article

@router.delete("/articles/{article_id}", response_model=dict)
async def delete_article(
    article_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db_session)
):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found"
        )
    
    # 检查用户是否有删除文章的权限
    if (current_user.id != article.user_id and 
        current_user.role_id != 2 and 
        current_user.role_id != 3):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this article"
        )
    
    db.delete(article)
    db.commit()
    return {"detail": "Article deleted successfully"}

# 分类和标签路由
@router.get("/categories", response_model=List[CategoryResponse])
async def get_categories(db: Session = Depends(get_db_session)):
    categories = db.query(Category).all()
    return categories

@router.get("/tags", response_model=List[TagResponse])
async def get_tags(db: Session = Depends(get_db_session)):
    tags = db.query(Tag).all()
    return tags

# 评论管理路由
@router.post("/articles/{article_id}/comments", response_model=CommentResponse)
async def create_comment(
    article_id: int,
    comment_data: CommentCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db_session)
):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found"
        )
    
    # 检查用户是否有评论权限
    if current_user.role_id == 1:  # 如果是普通用户，需要登录
        if not current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Login required to comment"
            )
    
    new_comment = Comment(
        article_id=article_id,
        user_id=current_user.id if current_user else None,
        content=comment_data.content,
        parent_id=comment_data.parent_id if hasattr(comment_data, 'parent_id') and comment_data.parent_id else None,
        created_at=datetime.utcnow()
    )
    
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)
    return new_comment

@router.get("/articles/{article_id}/comments", response_model=List[CommentResponse])
async def get_comments(
    article_id: int,
    db: Session = Depends(get_db_session),
    skip: int = 0,
    limit: int = 10
):
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found"
        )
    
    comments = db.query(Comment).filter(
        Comment.article_id == article_id,
        Comment.parent_id == None  # 只获取顶级评论
    ).order_by(Comment.created_at.desc()).offset(skip).limit(limit).all()
    
    # 递归获取子评论
    def get_nested_comments(comment):
        return [
            {
                "id": c.id,
                "user": c.user.username if c.user else None,
                "content": c.content,
                "created_at": c.created_at,
                "replies": [get_nested_comments(rc) for rc in c.replies] if c.replies else []
            }
            for c in comment.replies
        ]
    
    return [{
        "id": c.id,
        "user": c.user.username if c.user else None,
        "content": c.content,
        "created_at": c.created_at,
        "replies": get_nested_comments(c) if c.replies else []
    } for c in comments]

@router.post("/comments/{comment_id}/like", response_model=dict)
async def like_comment(
    comment_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db_session)
):
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Comment not found"
        )
    
    # 检查用户是否已经点赞过
    existing_like = db.query(CommentLike).filter(
        CommentLike.comment_id == comment_id,
        CommentLike.user_id == current_user.id if current_user else None
    ).first()
    
    if existing_like:
        # 取消点赞
        db.delete(existing_like)
        db.commit()
        return {"detail": "Comment disliked"}
    
    # 创建新点赞记录
    new_like = CommentLike(
        comment_id=comment_id,
        user_id=current_user.id if current_user else None,
        created_at=datetime.utcnow()
    )
    db.add(new_like)
    db.commit()
    db.refresh(new_like)
    
    # 更新评论点赞数
    comment.likes_count += 1
    db.commit()
    
    return {"detail": "Comment liked", "likes_count": comment.likes_count}

# 统计和设置路由
@router.get("/stats", response_model=dict)
async def get_stats(db: Session = Depends(get_db_session)):
    stats = {
        "total_articles": db.query(Article).count(),
        "total_users": db.query(User).count(),
        "total_comments": db.query(Comment).count(),
        "popular_tags": [
            tag.name for tag in 
            db.query(Tag)
            .join(ArticleTag)
            .join(Article)
            .group_by(Tag.id)
            .order_by(func.count(ArticleTag.article_id).desc())
            .limit(5)
            .all()
        ]
    }
    return stats

@router.get("/settings", response_model=SiteSettingResponse)
async def get_settings(db: Session = Depends(get_db_session)):
    # 获取站点设置（假设只有一个站点设置）
    site_settings = db.query(SiteSetting).first()
    if not site_settings:
        # 如果不存在，则创建默认设置
        new_settings = SiteSetting(
            site_title="My Blog",
            site_description="My personal blog",
            allow_comments=True,
            comment_moderation=False
        )
        db.add(new_settings)
        db.commit()
        db.refresh(new_settings)
        site_settings = new_settings
    
    return site_settings

# 安全注意：这些密钥应该在环境变量中配置
SECRET_KEY = "your-secret-key-here-should-be-32-bytes-long"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15

# 辅助函数（这些应该也在其他文件中定义）
def verify_password(plain_password, hashed_password):
    # 实现密码验证逻辑
    return True  # 这里需要实际实现

def get_password_hash(password):
    # 实现密码哈希逻辑
    return password  # 这里需要实际实现

def create_access_token(data: dict):
    # 实现访问令牌创建逻辑
    return "access-token"  # 这里需要实际实现

def create_refresh_token(data: dict):
    # 实现刷新令牌创建逻辑
    return "refresh-token"  # 这里需要实际实现