from sqlalchemy import Column, String, Integer, ForeignKey
from sqlalchemy import func
from sqlalchemy.orm import relationship

from app.models.base import Base

# 权限级别定义
# normal: 普通用户（基础业务功能）
# admin: 管理员（用户管理、服务管理、系统监控、资源配置等）
# superadmin: 超级管理员（所有权限，含 Nginx 部署、配置恢复、限流管理等高危操作）
PERMISSION_LEVELS = ["normal", "admin", "superadmin"]

class Permission(Base):
    __tablename__ = "permission"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    permission_level = Column(String(20), default="normal", nullable=False, index=True)
    user=relationship("User", back_populates="permission", uselist=False)