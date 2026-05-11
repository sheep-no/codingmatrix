from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class UserLogin(BaseModel):
    """明文登录（兼容旧版）"""
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class UserLoginEncrypted(BaseModel):
    """加密登录请求"""
    # 加密的数据格式：
    # {
    #     "encrypted_data": "base64",  // AES 加密的 {email, password}
    #     "encrypted_key": "base64"    // RSA 加密的 AES 密钥
    # }
    encrypted_data: str
    encrypted_key: str


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    username: str = Field(max_length=51, min_length=1)
