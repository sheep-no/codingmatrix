from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    permission_level: str
    created_at: str


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6)
    permission_level: str = Field("normal", pattern="^(normal|admin|superadmin)$")


class UserUpdateRequest(BaseModel):
    email: Optional[EmailStr] = None
    username:Optional[str] = None
    permission_level: Optional[str] = Field(None, pattern="^(normal|admin|superadmin)$")


class UserListResponse(BaseModel):
    total: int
    users: List[UserResponse]
    page: int
    page_size: int


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=6)
