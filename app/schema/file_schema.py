"""
文件管理 Schema
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime


class FileUploadResponse(BaseModel):
    """文件上传响应"""
    id: int
    filename: str
    file_size: int
    content_type: Optional[str]
    created_at: str
    download_url: str
    
    class Config:
        from_attributes = True


class FileListResponse(BaseModel):
    """文件列表响应"""
    total: int
    files: List[FileUploadResponse]
    page: int
    page_size: int


class FileDownloadResponse(BaseModel):
    """文件下载响应"""
    filename: str
    content_type: Optional[str]
    file_size: int


class FileCreate(BaseModel):
    """文件创建请求"""
    filename: str = Field(..., description="文件名")
    file_size: int = Field(..., description="文件大小")
    content_type: Optional[str] = Field(None, description="文件类型")

    class Config:
        from_attributes = True


class FileResponse(BaseModel):
    """文件响应"""
    id: int
    filename: str
    file_size: int
    content_type: Optional[str]
    created_at: str
    download_url: str

    class Config:
        from_attributes = True


# 分页参数验证
def validate_page(value):
    if value < 1:
        raise ValueError("页码必须大于 0")
    return value

def validate_page_size(value):
    if value < 1 or value > 100:
        raise ValueError("每页数量必须在 1-100 之间")
    return value
