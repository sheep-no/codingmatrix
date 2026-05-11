from pydantic import BaseModel
from typing import Optional, List


class PptRequest(BaseModel):
    """PPT 生成请求（重构版）"""
    prompt: str
    model: str
    conversation_id: Optional[int] = None  # 会话 ID（用于携带历史上下文）
    session_id: Optional[str] = None  # 可选：指定会话 ID 用于素材隔离
    material_file_ids: Optional[List[int]] = None  # 已上传素材的文件 ID 列表
