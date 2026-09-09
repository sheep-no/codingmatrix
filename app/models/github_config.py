"""User-scoped GitHub configuration; tokens are encrypted envelopes."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from app.models.base import Base


class GithubUserConfig(Base):
    __tablename__ = "github_user_configs"
    user_id = Column(Integer, ForeignKey("user.id"), primary_key=True)
    username = Column(String(39), nullable=False, default="")
    encrypted_token = Column(Text, nullable=False, default="")
    use_github = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
