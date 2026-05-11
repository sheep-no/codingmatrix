from sqlalchemy import Column, String, Integer, TIMESTAMP, ForeignKey
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from typing import Optional

Base = declarative_base()

class User(Base):
    """Database model for User entities"""
    
    __tablename__ = "users"
    
    user_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        nullable=False
    )
    
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False
    )
    
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    
    created_at: Mapped[TIMESTAMP] = mapped_column(
        TIMESTAMP,
        default=lambda: datetime.utcnow(),
        nullable=False
    )

class Product(Base):
    """Database model for Product entities"""
    
    __tablename__ = "products"
    
    product_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        nullable=False
    )
    
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    
    description: Mapped[Optional[str]] = mapped_column(
        String(1000),
        nullable=True
    )
    
    price: Mapped[float] = mapped_column(
        nullable=False
    )
    
    created_at: Mapped[TIMESTAMP] = mapped_column(
        TIMESTAMP,
        default=lambda: datetime.utcnow(),
        nullable=False
    )
    
    updated_at: Mapped[Optional[TIMESTAMP]] = mapped_column(
        TIMESTAMP,
        default=lambda: datetime.utcnow(),
        onupdate=lambda: datetime.utcnow(),
        nullable=True
    )

class Article(Base):
    """Database model for Article entities"""
    
    __tablename__ = "articles"
    
    article_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        nullable=False
    )
    
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    
    content: Mapped[str] = mapped_column(
        String(5000),
        nullable=False
    )
    
    created_at: Mapped[TIMESTAMP] = mapped_column(
        TIMESTAMP,
        default=lambda: datetime.utcnow(),
        nullable=False
    )
    
    updated_at: Mapped[Optional[TIMESTAMP]] = mapped_column(
        TIMESTAMP,
        default=lambda: datetime.utcnow(),
        onupdate=lambda: datetime.utcnow(),
        nullable=True
    )