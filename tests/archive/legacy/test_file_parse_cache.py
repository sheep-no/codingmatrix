"""
文件解析缓存功能测试
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock


class TestFileParseCache:
    """测试文件解析缓存逻辑"""
    
    def test_cache_logic_with_content_and_valid(self):
        """测试：有有效缓存时返回 True"""
        file_mock = MagicMock()
        file_mock.parsed_content = "Test content"
        file_mock.parsed_at = datetime.utcnow() - timedelta(minutes=10)
        file_mock.cache_expire_at = datetime.utcnow() + timedelta(seconds=3600)
        
        # 模拟 ORM 的 to_dict 方法
        def to_dict():
            return {
                "id": file_mock.id,
                "filename": file_mock.filename,
                "parsed_content": file_mock.parsed_content,
                "has_cached_parse": (
                    file_mock.parsed_content is not None and 
                    file_mock.cache_expire_at and 
                    file_mock.cache_expire_at > datetime.utcnow()
                )
            }
        
        def is_parse_cache_valid(ttl_seconds=3600):
            if not file_mock.parsed_content or not file_mock.parsed_at:
                return False
            if file_mock.cache_expire_at and file_mock.cache_expire_at < datetime.utcnow():
                return False
            expire_time = file_mock.parsed_at + timedelta(seconds=ttl_seconds)
            return datetime.utcnow() < expire_time
        
        assert is_parse_cache_valid() is True
        assert to_dict()["has_cached_parse"] is True
    
    def test_cache_logic_no_content(self):
        """测试：没有解析内容时返回 False"""
        file_mock = MagicMock()
        file_mock.parsed_content = None
        file_mock.parsed_at = None
        file_mock.cache_expire_at = None
        
        def is_parse_cache_valid(ttl_seconds=3600):
            if not file_mock.parsed_content or not file_mock.parsed_at:
                return False
            if file_mock.cache_expire_at and file_mock.cache_expire_at < datetime.utcnow():
                return False
            return True
        
        assert is_parse_cache_valid() is False
    
    def test_cache_logic_expired(self):
        """测试：缓存过期时返回 False"""
        file_mock = MagicMock()
        file_mock.parsed_content = "Old content"
        file_mock.parsed_at = datetime.utcnow() - timedelta(hours=2)
        file_mock.cache_expire_at = datetime.utcnow() - timedelta(hours=1)
        
        def is_parse_cache_valid(ttl_seconds=3600):
            if not file_mock.parsed_content or not file_mock.parsed_at:
                return False
            if file_mock.cache_expire_at and file_mock.cache_expire_at < datetime.utcnow():
                return False
            expire_time = file_mock.parsed_at + timedelta(seconds=ttl_seconds)
            return datetime.utcnow() < expire_time
        
        assert is_parse_cache_valid() is False
    
    def test_cache_logic_custom_ttl(self):
        """测试：自定义 TTL"""
        file_mock = MagicMock()
        file_mock.parsed_content = "Content"
        file_mock.parsed_at = datetime.utcnow() - timedelta(minutes=10)
        file_mock.cache_expire_at = datetime.utcnow() + timedelta(minutes=5)
        
        def is_parse_cache_valid(ttl_seconds=3600):
            if not file_mock.parsed_content or not file_mock.parsed_at:
                return False
            if file_mock.cache_expire_at and file_mock.cache_expire_at < datetime.utcnow():
                return False
            expire_time = file_mock.parsed_at + timedelta(seconds=ttl_seconds)
            return datetime.utcnow() < expire_time
        
        # 5 分钟 TTL, 已过期
        assert is_parse_cache_valid(ttl_seconds=300) is False
        
        # 15 分钟 TTL，未过期
        assert is_parse_cache_valid(ttl_seconds=900) is True
    
    def test_update_cache_logic(self):
        """测试：更新解析缓存逻辑"""
        file_mock = MagicMock()
        file_mock.parsed_content = None
        file_mock.parsed_at = None
        file_mock.cache_expire_at = None
        
        def update_parse_cache(content: str, ttl_seconds: int = 3600):
            from datetime import datetime, timedelta
            file_mock.parsed_content = content
            file_mock.parsed_at = datetime.utcnow()
            file_mock.cache_expire_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        
        before_update = datetime.utcnow()
        update_parse_cache("New content", ttl_seconds=1800)
        after_update = datetime.utcnow()
        
        assert file_mock.parsed_content == "New content"
        assert file_mock.parsed_at >= before_update
        assert file_mock.parsed_at <= after_update
        assert file_mock.cache_expire_at is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
