from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean, Numeric, ARRAY, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import ARRAY as ARRAY_type

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    display_name = Column(String(50), nullable=True)
    bio = Column(Text, nullable=True)
    avatar_url = Column(String(200), nullable=True)
    role_ids = Column(JSON, default=[], nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    roles = relationship('Role', secondary='user_roles', back_populates='users')
    articles = relationship('Article', back_populates='author')
    comments = relationship('Comment', back_populates='user')
    likes = relationship('ArticleLike', back_populates='user')

class Role(Base):
    __tablename__ = 'roles'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    
    users = relationship('User', secondary='user_roles', back_populates='roles')

class UserRole(Base):
    __tablename__ = 'user_roles'
    
    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    role_id = Column(Integer, ForeignKey('roles.id'), primary_key=True)
    
    user = relationship('User', back_populates='roles')
    role = relationship('Role', back_populates='users')

class Category(Base):
    __tablename__ = 'categories'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    slug = Column(String(50), unique=True, nullable=False)
    parent_id = Column(Integer, ForeignKey('categories.id'), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    parent = relationship('Category', remote_side='Category.id', back_populates='children')
    children = relationship('Category', back_populates='parent')
    articles = relationship('Article', back_populates='category')

class Article(Base):
    __tablename__ = 'articles'
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    content = Column(Text, nullable=False)
    author_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    category_id = Column(Integer, ForeignKey('categories.id'), nullable=True)
    status = Column(String(20), default='draft', nullable=False)
    published_at = Column(DateTime, nullable=True)
    views_count = Column(Integer, default=0, nullable=False)
    likes_count = Column(Integer, default=0, nullable=False)
    comments_count = Column(Integer, default=0, nullable=False)
    featured = Column(Boolean, default=False, nullable=False)
    meta_description = Column(Text, nullable=True)
    meta_keywords = Column(Text, nullable=True)
    tags = Column(JSON, default=[], nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    author = relationship('User', back_populates='articles')
    category = relationship('Category', back_populates='articles')
    comments = relationship('Comment', back_populates='article')
    tags_list = relationship('Tag', secondary='article_tags', back_populates='articles')
    likes = relationship('ArticleLike', back_populates='article')

class Tag(Base):
    __tablename__ = 'tags'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    slug = Column(String(50), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    articles = relationship('Article', secondary='article_tags', back_populates='tags_list')

class ArticleTag(Base):
    __tablename__ = 'article_tags'
    
    article_id = Column(Integer, ForeignKey('articles.id'), primary_key=True)
    tag_id = Column(Integer, ForeignKey('tags.id'), primary_key=True)
    
    article = relationship('Article', back_populates='tags_list')
    tag = relationship('Tag', back_populates='articles')

class Comment(Base):
    __tablename__ = 'comments'
    
    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey('articles.id'), nullable=False)
    parent_id = Column(Integer, ForeignKey('comments.id'), nullable=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String(20), default='pending', nullable=False)
    likes_count = Column(Integer, default=0, nullable=False)
    depth = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    article = relationship('Article', back_populates='comments')
    user = relationship('User', back_populates='comments')
    parent = relationship('Comment', remote_side='Comment.id', back_populates='children')
    children = relationship('Comment', back_populates='parent')
    likes = relationship('CommentLike', back_populates='comment')

class CommentLike(Base):
    __tablename__ = 'comment_likes'
    
    id = Column(Integer, primary_key=True, index=True)
    comment_id = Column(Integer, ForeignKey('comments.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    comment = relationship('Comment', back_populates='likes')
    user = relationship('User', back_populates='comment_likes')

class ArticleLike(Base):
    __tablename__ = 'article_likes'
    
    id = Column(Integer, primary_key=True, index=True)
    article_id = Column(Integer, ForeignKey('articles.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    article = relationship('Article', back_populates='likes')
    user = relationship('User', back_populates='article_likes')

class SiteSetting(Base):
    __tablename__ = 'site_settings'
    
    id = Column(Integer, primary_key=True, index=True)
    site_name = Column(String(100), nullable=False)
    site_description = Column(Text, nullable=True)
    site_logo_url = Column(String(200), nullable=True)
    enable_comments = Column(Boolean, default=True, nullable=False)
    comment_moderation = Column(Boolean, default=False, nullable=False)
    enable_registration = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Statistics(Base):
    __tablename__ = 'statistics'
    
    id = Column(Integer, primary_key=True, index=True)
    total_users = Column(Integer, default=0, nullable=False)
    total_articles = Column(Integer, default=0, nullable=False)
    total_comments = Column(Integer, default=0, nullable=False)
    daily_visitors = Column(Integer, default=0, nullable=False)
    monthly_visitors = Column(Integer, default=0, nullable=False)
    yearly_visitors = Column(Integer, default=0, nullable=False)
    top_articles = Column(JSON, default=[], nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Pydantic models for API request/response validation
class UserBase(BaseModel):
    id: Optional[int]
    username: str
    email: str
    display_name: Optional[str]
    bio: Optional[str]
    avatar_url: Optional[str]
    role_ids: List[int]

    class Config:
        orm_mode = True

class RoleBase(BaseModel):
    id: int
    name: str
    description: Optional[str]

    class Config:
        orm_mode = True

class CategoryBase(BaseModel):
    id: Optional[int]
    name: str
    slug: str
    description: Optional[str]
    parent_id: Optional[int]
    created_at: Optional[datetime]

    class Config:
        orm_mode = True

class ArticleBase(BaseModel):
    id: Optional[int]
    title: str
    slug: str
    content: str
    author_id: Optional[int]
    category_id: Optional[int]
    status: str
    published_at: Optional[datetime]
    views_count: Optional[int]
    likes_count: Optional[int]
    comments_count: Optional[int]
    featured: Optional[bool]
    meta_description: Optional[str]
    meta_keywords: Optional[str]
    tags: List[str]

    class Config:
        orm_mode = True

class TagBase(BaseModel):
    id: Optional[int]
    name: str
    slug: str
    description: Optional[str]

    class Config:
        orm_mode = True

class CommentBase(BaseModel):
    id: Optional[int]
    article_id: Optional[int]
    parent_id: Optional[int]
    user_id: Optional[int]
    content: str
    status: str
    likes_count: Optional[int]
    depth: Optional[int]
    created_at: Optional[datetime]

    class Config:
        orm_mode = True

class SiteSettingBase(BaseModel):
    id: Optional[int]
    site_name: str
    site_description: Optional[str]
    site_logo_url: Optional[str]
    enable_comments: bool
    comment_moderation: bool
    enable_registration: bool

    class Config:
        orm_mode = True

class StatisticsBase(BaseModel):
    id: Optional[int]
    total_users: int
    total_articles: int
    total_comments: int
    daily_visitors: int
    monthly_visitors: int
    yearly_visitors: int
    top_articles: List[Dict[str, Any]]

    class Config:
        orm_mode = True