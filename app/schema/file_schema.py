"""
文件管理 Schema
"""
from pydantic import BaseModel, ConfigDict
from typing import Optional, List


class FileUploadResponse(BaseModel):
    """文件上传响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    file_size: int
    content_type: Optional[str]
    created_at: str
    download_url: str


class FileListResponse(BaseModel):
    """文件列表响应"""
    total: int
    files: List[FileUploadResponse]
    page: int
    page_size: int
