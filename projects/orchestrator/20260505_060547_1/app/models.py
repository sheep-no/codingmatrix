from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, ARRAY, Numeric
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
from enum import Enum

Base = declarative_base()

class UserRole(Enum):
    ADMIN = "admin"
    EDITOR = "editor"
    USER = "user"
    GUEST = "guest"

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, default=datetime.utcnow)
    
    roles = relationship('Role', secondary='user_roles', back_populates='users')
    articles = relationship('Article', back_populates='author')
    comments = relationship('Comment', back_populates='author')
    
    def __repr__(self):
        return f"<User {self.email}>"

class Role(Base):
    __tablename__ = 'roles'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(20), unique=True, nullable=False)
    
    users = relationship('User', secondary='user_roles', back_populates='roles')
    permissions = relationship('Permission', back_populates='role')
    
    def __repr__(self):
        return f"<Role {self.name}>"

class UserRoles(Base):
    __tablename__ = 'user_roles'
    
    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    role_id = Column(Integer, ForeignKey('roles.id'), primary_key=True)
    
    def __repr__(self):
        return f"<UserRole user_id={self.user_id}, role_id={self.role_id}>"

class Permission(Base):
    __tablename__ = 'permissions'
    
    id = Column(Integer, primary_key=True)
    action = Column(String(50), nullable=False)
    role_id = Column(Integer, ForeignKey('roles.id'))
    
    role = relationship('Role', back_populates='permissions')
    
    def __repr__(self):
        return f"<Permission action={self.action}, role_id={self.role_id}>"

class Category(Base):
    __tablename__ = 'categories'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    parent_id = Column(Integer, ForeignKey('categories.id'))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    parent = relationship('Category', remote_side='Category.id', back_populates='subcategories')
    subcategories = relationship('Category', back_populates='parent')
    articles = relationship('Article', back_populates='category')
    
    def __repr__(self):
        return f"<Category {self.name}>"

class Article(Base):
    __tablename__ = 'articles'
    
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    author_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    category_id = Column(Integer, ForeignKey('categories.id'))
    status = Column(String(20), default="published")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    view_count = Column(Integer, default=0)
    like_count = Column(Integer, default=0)
    
    author = relationship('User', back_populates='articles')
    category = relationship('Category', back_populates='articles')
    tags = relationship('Tag', secondary='article_tags', back_populates='articles')
    
    def __repr__(self):
        return f"<Article {self.title}>"

class Tag(Base):
    __tablename__ = 'tags'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    
    articles = relationship('Article', secondary='article_tags', back_populates='tags')
    
    def __repr__(self):
        return f"<Tag {self.name}>"

class ArticleTags(Base):
    __tablename__ = 'article_tags'
    
    article_id = Column(Integer, ForeignKey('articles.id'), primary_key=True)
    tag_id = Column(Integer, ForeignKey('tags.id'), primary_key=True)
    
    def __repr__(self):
        return f"<ArticleTag article_id={self.article_id}, tag_id={self.tag_id}>"

class Comment(Base):
    __tablename__ = 'comments'
    
    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey('articles.id'), nullable=False)
    author_id = Column(Integer, ForeignKey('users.id'))
    content = Column(Text, nullable=False)
    parent_id = Column(Integer, ForeignKey('comments.id'))
    created_at = Column(DateTime, default=datetime.utcnow)
    is_approved = Column(Boolean, default=True)
    
    article = relationship('Article', back_populates='comments')
    author = relationship('User', back_populates='comments')
    replies = relationship('Comment', foreign_keys=[parent_id], back_populates='parent')
    parent = relationship('Comment', remote_side=[id], back_populates='replies')
    
    def __repr__(self):
        return f"<Comment {self.content[:20]}..."

class CommentLike(Base):
    __tablename__ = 'comment_likes'
    
    id = Column(Integer, primary_key=True)
    comment_id = Column(Integer, ForeignKey('comments.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<CommentLike comment_id={self.comment_id}, user_id={self.user_id}>"

class ArticleLike(Base):
    __tablename__ = 'article_likes'
    
    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey('articles.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<ArticleLike article_id={self.article_id}, user_id={self.user_id}>"

class SiteSetting(Base):
    __tablename__ = 'site_settings'
    
    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=False)
    
    def __repr__(self):
        return f"<SiteSetting {self.key}={self.value}>"

class Statistic(Base):
    __tablename__ = 'statistics'
    
    id = Column(Integer, primary_key=True)
    metric = Column(String(50), nullable=False)
    value = Column(Numeric(precision=10, scale=2), nullable=False)
    date = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<Statistic metric={self.metric}, value={self.value}>"