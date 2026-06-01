"""
PPT 文件存储管理器单元测试

测试文件存储管理器的核心功能：
- 保存文件
- 获取文件元数据
- 删除文件
- 清理过期文件
- 检查存储使用率
"""

import asyncio
import json
import pytest
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.services.ppt.file_storage import (
    FileStorageManager,
    FileMetadata,
    FileStorageError,
    FileNotFoundError,
    StorageQuotaExceededError,
)


@pytest.fixture
def storage_dir(tmp_path):
    """创建临时存储目录"""
    return tmp_path / "ppt-files"


@pytest.fixture
def storage_manager(storage_dir):
    """创建文件存储管理器实例"""
    return FileStorageManager(
        storage_dir=storage_dir,
        retention_days=7,
        max_total_size_gb=1.0,
    )


@pytest.fixture
def sample_file(tmp_path):
    """创建示例文件"""
    file_path = tmp_path / "test_presentation.pptx"
    file_path.write_text("Mock PPTX content")
    return file_path


class TestFileStorageManager:
    """文件存储管理器测试类"""
    
    @pytest.mark.asyncio
    async def test_save_file_success(self, storage_manager, sample_file):
        """测试成功保存文件"""
        file_id = await storage_manager.save(
            task_id="task-123",
            file_path=sample_file,
            user_id=1,
            output_format="pptx",
        )
        
        # 验证文件 ID 生成
        assert file_id is not None
        assert isinstance(file_id, str)
        
        # 验证文件目录创建
        file_dir = storage_manager._storage_dir / file_id
        assert file_dir.exists()
        
        # 验证文件被复制
        saved_file = file_dir / "task-123.pptx"
        assert saved_file.exists()
        
        # 验证元数据文件
        metadata_path = file_dir / "metadata.json"
        assert metadata_path.exists()
    
    @pytest.mark.asyncio
    async def test_save_file_source_not_exists(self, storage_manager, tmp_path):
        """测试保存不存在的源文件"""
        non_existent = tmp_path / "non_existent.pptx"
        
        with pytest.raises(FileStorageError):
            await storage_manager.save(
                task_id="task-123",
                file_path=non_existent,
                user_id=1,
            )
    
    @pytest.mark.asyncio
    async def test_get_metadata_exists(self, storage_manager, sample_file):
        """测试获取存在的文件元数据"""
        # 先保存文件
        file_id = await storage_manager.save(
            task_id="task-123",
            file_path=sample_file,
            user_id=1,
        )
        
        # 获取元数据
        metadata = await storage_manager.get(file_id)
        
        # 验证元数据
        assert metadata is not None
        assert metadata.file_id == file_id
        assert metadata.task_id == "task-123"
        assert metadata.user_id == 1
        assert metadata.format == "pptx"
        assert metadata.access_count == 1
    
    @pytest.mark.asyncio
    async def test_get_metadata_not_exists(self, storage_manager):
        """测试获取不存在的文件元数据"""
        metadata = await storage_manager.get("non-existent-file-id")
        
        assert metadata is None
    
    @pytest.mark.asyncio
    async def test_get_file_path_exists(self, storage_manager, sample_file):
        """测试获取存在的文件路径"""
        file_id = await storage_manager.save(
            task_id="task-123",
            file_path=sample_file,
            user_id=1,
        )
        
        file_path = await storage_manager.get_file_path(file_id)
        
        assert file_path is not None
        assert file_path.exists()
    
    @pytest.mark.asyncio
    async def test_get_file_path_not_exists(self, storage_manager):
        """测试获取不存在的文件路径"""
        file_path = await storage_manager.get_file_path("non-existent")
        
        assert file_path is None
    
    @pytest.mark.asyncio
    async def test_delete_file_success(self, storage_manager, sample_file):
        """测试成功删除文件"""
        file_id = await storage_manager.save(
            task_id="task-123",
            file_path=sample_file,
            user_id=1,
        )
        
        # 删除文件
        success = await storage_manager.delete(file_id)
        
        assert success is True
        
        # 验证文件目录被删除
        file_dir = storage_manager._storage_dir / file_id
        assert not file_dir.exists()
        
        # 验证元数据不可获取
        metadata = await storage_manager.get(file_id)
        assert metadata is None
    
    @pytest.mark.asyncio
    async def test_delete_file_not_exists(self, storage_manager):
        """测试删除不存在的文件"""
        success = await storage_manager.delete("non-existent")
        
        assert success is False
    
    @pytest.mark.asyncio
    async def test_cleanup_expired_files(self, storage_manager, sample_file):
        """测试清理过期文件"""
        # 保存一个文件
        file_id = await storage_manager.save(
            task_id="task-123",
            file_path=sample_file,
            user_id=1,
        )
        
        # 手动修改元数据，使其过期
        metadata = await storage_manager.get(file_id)
        # 设置为 30 天前
        old_timestamp = time.time() - (30 * 86400)
        from datetime import datetime, timezone
        metadata.created_at = datetime.fromtimestamp(old_timestamp, tz=timezone.utc).isoformat()
        await storage_manager._save_metadata(file_id, metadata)
        
        # 清理过期文件
        cleaned_count = await storage_manager.cleanup_expired(retention_days=7)
        
        # 验证清理成功
        assert cleaned_count == 1
        
        # 验证文件已被删除
        metadata = await storage_manager.get(file_id)
        assert metadata is None
    
    @pytest.mark.asyncio
    async def test_cleanup_expired_no_expired_files(self, storage_manager, sample_file):
        """测试没有过期文件时不清理"""
        # 保存一个文件（当前时间）
        file_id = await storage_manager.save(
            task_id="task-123",
            file_path=sample_file,
            user_id=1,
        )
        
        # 清理过期文件
        cleaned_count = await storage_manager.cleanup_expired(retention_days=7)
        
        # 应该没有文件被清理
        assert cleaned_count == 0
    
    @pytest.mark.asyncio
    async def test_check_storage_usage(self, storage_manager, sample_file):
        """测试检查存储使用情况"""
        # 保存一个文件
        await storage_manager.save(
            task_id="task-123",
            file_path=sample_file,
            user_id=1,
        )
        
        # 检查存储使用
        usage = await storage_manager.check_storage_usage()
        
        # 验证返回数据
        assert usage["total_files"] == 1
        assert usage["total_size_bytes"] > 0
        assert usage["total_files"] == 1
        assert usage["usage_percentage"] >= 0
    
    @pytest.mark.asyncio
    async def test_get_user_files(self, storage_manager, sample_file):
        """测试获取用户的所有文件"""
        # 保存多个文件
        await storage_manager.save(
            task_id="task-1",
            file_path=sample_file,
            user_id=1,
        )
        await storage_manager.save(
            task_id="task-2",
            file_path=sample_file,
            user_id=1,
        )
        await storage_manager.save(
            task_id="task-3",
            file_path=sample_file,
            user_id=2,  # 不同用户
        )
        
        # 获取用户 1 的文件
        user_files = await storage_manager.get_user_files(1)
        
        # 应该只有 2 个文件
        assert len(user_files) == 2
        assert all(f.user_id == 1 for f in user_files)
    
    @pytest.mark.asyncio
    async def test_save_multiple_formats(self, storage_manager, tmp_path):
        """测试保存不同格式的文件"""
        formats = ["pptx", "pdf", "html", "markdown"]
        
        for fmt in formats:
            file_path = tmp_path / f"test.{fmt}"
            file_path.write_text(f"Mock {fmt} content")
            
            file_id = await storage_manager.save(
                task_id=f"task-{fmt}",
                file_path=file_path,
                user_id=1,
                output_format=fmt,
            )
            
            metadata = await storage_manager.get(file_id)
            assert metadata.format == fmt
    
    @pytest.mark.asyncio
    async def test_metadata_json_structure(self, storage_manager, sample_file):
        """测试元数据 JSON 结构"""
        file_id = await storage_manager.save(
            task_id="task-123",
            file_path=sample_file,
            user_id=1,
        )
        
        # 读取元数据文件
        metadata_path = storage_manager._storage_dir / file_id / "metadata.json"
        
        with open(metadata_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 验证必要字段
        assert "file_id" in data
        assert "task_id" in data
        assert "user_id" in data
        assert "filename" in data
        assert "format" in data
        assert "size_bytes" in data
        assert "created_at" in data
        assert "last_accessed" in data


class TestFileMetadata:
    """文件元数据测试类"""
    
    def test_file_metadata_defaults(self):
        """测试文件元数据默认值"""
        metadata = FileMetadata(
            file_id="test",
            task_id="task-123",
            user_id=1,
            filename="test.pptx",
            format="pptx",
            size_bytes=1000,
            created_at="2026-05-30T10:00:00+00:00",
            last_accessed="2026-05-30T10:00:00+00:00",
        )
        
        assert metadata.access_count == 0
        assert metadata.download_url == ""
        assert metadata.error_message is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
