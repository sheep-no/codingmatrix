from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    ForeignKey,
    DateTime,
    Boolean,
    Float,
    ARRAY,
    func,
    text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import uuid
import datetime
from typing import List, Optional

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role_id = Column(String, ForeignKey("roles.id"))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # Relationships
    roles = relationship("Role", back_populates="users")
    articles = relationship("Article", back_populates="author")
    comments = relationship("Comment", back_populates="user")
    site_settings = relationship("SiteSetting", back_populates="user", uselist=False)

class Role(Base):
    __tablename__ = "roles"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(50), unique=True, nullable=False)
    permissions = Column(ARRAY(String), default=["read"])
    
    # Relationships
    users = relationship("User", back_populates="roles")

class UserRole(Base):
    __tablename__ = "user_roles"
    
    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    role_id = Column(String, ForeignKey("roles.id"), primary_key=True)
    assigned_at = Column(DateTime, default=datetime.datetime.utcnow)

class Category(Base):
    __tablename__ = "categories"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), unique=True, nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    parent_id = Column(String, ForeignKey("categories.id"))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # Relationships
    parent = relationship("Category", remote_side="Category.id", back_populates="child_categories")
    child_categories = relationship("Category", back_populates="parent", cascade="all, delete-orphan")
    articles = relationship("Article", back_populates="category")

class Article(Base):
    __tablename__ = "articles"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(200), nullable=False)
    slug = Column(String(200), unique=True, nullable=False)
    content = Column(Text, nullable=False)
    author_id = Column(String, ForeignKey("users.id"), nullable=False)
    category_id = Column(String, ForeignKey("categories.id"))
    status = Column(String(20), default="draft")
    published_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    view_count = Column(Integer, default=0)
    
    # Relationships
    author = relationship("User", back_populates="articles")
    category = relationship("Category", back_populates="articles")
    tags = relationship("ArticleTag", back_populates="article", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="article")

class ArticleTag(Base):
    __tablename__ = "article_tags"
    
    article_id = Column(String, ForeignKey("articles.id"), primary_key=True)
    tag_id = Column(String, ForeignKey("tags.id"), primary_key=True)
    
    # Relationships
    article = relationship("Article", back_populates="tags")
    tag = relationship("Tag", back_populates="articles")

class Tag(Base):
    __tablename__ = "tags"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), unique=True, nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # Relationships
    articles = relationship("ArticleTag", back_populates="tag", cascade="all, delete-orphan")

class Comment(Base):
    __tablename__ = "comments"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    content = Column(Text, nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    article_id = Column(String, ForeignKey("articles.id"), nullable=False)
    parent_id = Column(String, ForeignKey("comments.id"))
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="comments")
    article = relationship("Article", back_populates="comments")
    parent = relationship("Comment", remote_side="Comment.id", back_populates="replies")
    replies = relationship("Comment", back_populates="parent", cascade="all, delete-orphan")

class CommentLike(Base):
    __tablename__ = "comment_likes"
    
    comment_id = Column(String, ForeignKey("comments.id"), primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    comment = relationship("Comment", back_populates="likes")
    user = relationship("User", back_populates="comment_likes")

class ArticleLike(Base):
    __tablename__ = "article_likes"
    
    article_id = Column(String, ForeignKey("articles.id"), primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationships
    article = relationship("Article", back_populates="likes")
    user = relationship("User", back_populates="article_likes")

class SiteSetting(Base):
    __tablename__ = "site_settings"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    site_title = Column(String(100), nullable=False, default="My Blog")
    site_description = Column(Text, default="My personal blog")
    site_logo = Column(String(255), default="")
    is_comment_enabled = Column(Boolean, default=True)
    comment_moderation = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    user_id = Column(String, ForeignKey("users.id"))
    
    # Relationships
    user = relationship("User", back_populates="site_settings")

class Statistic(Base):
    __tablename__ = "statistics"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    total_users = Column(Integer, default=0)
    total_articles = Column(Integer, default=0)
    total_comments = Column(Integer, default=0)
    daily_visitors = Column(Integer, default=0)
    monthly_visitors = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    user_id = Column(String, ForeignKey("users.id"))
    
    # Relationships
    user = relationship("User", back_populates="statistics")