"""
统一分页工具

提供标准分页和游标分页支持:
- PageParams: 标准分页参数验证
- CursorParams: 游标分页参数验证
- build_pagination_info: 构建分页元信息
- build_cursor_info: 构建游标分页元信息

标准分页响应格式:
{
    "total": 100,
    "page": 1,
    "size": 20,
    "pages": 5,
    "has_next": true,
    "has_prev": false
}

游标分页响应格式:
{
    "next_cursor": "eyJpZCI6MTAwfQ==",
    "has_more": true
}
"""
import base64
import json
from typing import Any, Dict, List, Optional, TypeVar

from pydantic import BaseModel, Field, field_validator

T = TypeVar("T")

# 默认分页配置
DEFAULT_PAGE = 1
DEFAULT_SIZE = 20
MAX_PAGE_SIZE = 100


class PageParams(BaseModel):
    """标准分页参数"""

    page: int = Field(default=DEFAULT_PAGE, ge=1, description="页码 (从 1 开始)")
    size: int = Field(
        default=DEFAULT_SIZE, ge=1, le=MAX_PAGE_SIZE, description="每页大小"
    )

    @field_validator("page")
    @classmethod
    def validate_page(cls, v: int) -> int:
        if v < 1:
            raise ValueError("页码必须大于等于 1")
        return v

    @field_validator("size")
    @classmethod
    def validate_size(cls, v: int) -> int:
        if v < 1:
            raise ValueError("每页大小必须大于等于 1")
        if v > MAX_PAGE_SIZE:
            raise ValueError(f"每页大小不能超过 {MAX_PAGE_SIZE}")
        return v

    @property
    def offset(self) -> int:
        """计算 SQL OFFSET"""
        return (self.page - 1) * self.size

    @property
    def limit(self) -> int:
        """计算 SQL LIMIT"""
        return self.size


class CursorParams(BaseModel):
    """游标分页参数"""

    cursor: Optional[str] = Field(
        default=None, description="游标 (Base64 编码的 JSON)"
    )
    size: int = Field(
        default=DEFAULT_SIZE, ge=1, le=MAX_PAGE_SIZE, description="每页大小"
    )

    @field_validator("cursor")
    @classmethod
    def validate_cursor(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                decode_cursor(v)
            except (ValueError, json.JSONDecodeError):
                raise ValueError("游标格式无效")
        return v


def build_pagination_info(
    total: int, page: int, size: int
) -> Dict[str, Any]:
    """构建标准分页元信息

    Args:
        total: 总记录数
        page: 当前页码
        size: 每页大小

    Returns:
        Dict: 分页元信息
    """
    pages = (total + size - 1) // size if total > 0 else 0
    return {
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
        "has_next": page < pages,
        "has_prev": page > 1,
    }


def build_cursor_info(
    next_cursor: Optional[str] = None,
    has_more: bool = False,
) -> Dict[str, Any]:
    """构建游标分页元信息

    Args:
        next_cursor: 下一页游标
        has_more: 是否还有更多数据

    Returns:
        Dict: 游标分页元信息
    """
    return {
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


def encode_cursor(data: Dict[str, Any]) -> str:
    """将字典编码为游标字符串

    Args:
        data: 需要编码的数据 (通常包含 id、timestamp 等)

    Returns:
        str: Base64 编码的游标
    """
    json_str = json.dumps(data, separators=(",", ":"))
    return base64.urlsafe_b64encode(json_str.encode()).decode()


def decode_cursor(cursor: str) -> Dict[str, Any]:
    """将游标字符串解码为字典

    Args:
        cursor: Base64 编码的游标

    Returns:
        Dict: 解码后的数据

    Raises:
        ValueError: 游标格式无效
    """
    try:
        json_str = base64.urlsafe_b64decode(cursor.encode()).decode()
        return json.loads(json_str)
    except (ValueError, json.JSONDecodeError) as e:
        raise ValueError(f"游标解码失败: {e}") from e


def paginate_list(data: List[T], page: int, size: int) -> List[T]:
    """对列表进行分页切片

    Args:
        data: 完整数据列表
        page: 当前页码
        size: 每页大小

    Returns:
        List[T]: 当前页数据
    """
    start = (page - 1) * size
    end = start + size
    return data[start:end]
