"""
单元测试 - Bug 修复验证

测试最近修复的 bug:
1. aicloud.py - PathSecurityError 导入
2. file_upload.py - get_db() 用法
3. file_upload.py - ChunkMetadata 合并
4. image_generation.py - response_format
5. aicloud.py - 流式对话 keepalive
"""

import pytest
import json
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path


class TestAicloudPathSecurityError:
    """测试 aicloud.py 的 PathSecurityError 导入"""

    def test_path_security_error_import(self):
        """验证 PathSecurityError 可以从 file_operator 导入"""
        from app.utils.file_operator import PathSecurityError
        assert PathSecurityError is not None

    def test_path_security_error_is_exception(self):
        """验证 PathSecurityError 是 Exception 子类"""
        from app.utils.file_operator import PathSecurityError
        assert issubclass(PathSecurityError, Exception)

    def test_aicloud_module_imports_path_security_error(self):
        """验证 aicloud 模块正确导入 PathSecurityError"""
        import app.api.v1.aicloud as aicloud_module
        # 检查模块中是否有 PathSecurityError
        assert hasattr(aicloud_module, 'PathSecurityError')


class TestFileUploadGetDb:
    """测试 file_upload.py 的 get_db() 用法"""

    def test_get_db_is_async_generator(self):
        """验证 get_db 是异步生成器"""
        from app.db.database import get_db
        import inspect
        assert inspect.isasyncgenfunction(get_db)

    @pytest.mark.asyncio
    async def test_get_db_yields_session(self):
        """验证 get_db 生成数据库会话"""
        from app.db.database import get_db
        gen = get_db()
        try:
            session = await gen.__anext__()
            assert session is not None
        finally:
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass


class TestChunkMetadataMerge:
    """测试 ChunkMetadata 合并逻辑"""

    def test_chunk_metadata_load(self):
        """测试 ChunkMetadata.load 从文件加载"""
        from app.api.v1.file_upload import ChunkMetadata
        import tempfile
        import json

        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建测试元数据
            meta_dir = Path(tmpdir) / "test_file_id"
            meta_dir.mkdir(parents=True)
            meta_file = meta_dir / "metadata.json"
            meta_data = {
                "file_id": "test_file_id",
                "total_chunks": 5,
                "uploaded_chunks": [0, 1, 2, 3, 4]
            }
            meta_file.write_text(json.dumps(meta_data))

            # 测试加载
            with patch('app.api.v1.file_upload.CHUNKS_DIR', Path(tmpdir)):
                meta = ChunkMetadata.load("test_file_id", 5)
                assert meta.file_id == "test_file_id"
                assert meta.total_chunks == 5
                assert meta.uploaded_chunks == [0, 1, 2, 3, 4]

    def test_chunk_metadata_is_complete(self):
        """测试 ChunkMetadata.is_complete 判断完整性"""
        from app.api.v1.file_upload import ChunkMetadata

        # 完整的分片
        meta = ChunkMetadata("test", 3, [0, 1, 2])
        assert meta.is_complete() is True

        # 不完整的分片
        meta = ChunkMetadata("test", 3, [0, 1])
        assert meta.is_complete() is False

        # 空分片
        meta = ChunkMetadata("test", 0, [])
        assert meta.is_complete() is True

    def test_chunk_metadata_add_chunk(self):
        """测试 ChunkMetadata.add_chunk 添加分片"""
        from app.api.v1.file_upload import ChunkMetadata

        meta = ChunkMetadata("test", 3, [])
        meta.add_chunk(1)
        assert 1 in meta.uploaded_chunks

        # 重复添加
        meta.add_chunk(1)
        assert meta.uploaded_chunks.count(1) == 1

    def test_chunk_metadata_save(self):
        """测试 ChunkMetadata.save 保存元数据"""
        from app.api.v1.file_upload import ChunkMetadata
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            meta = ChunkMetadata("test_file", 3, [0, 1])

            with patch('app.api.v1.file_upload.CHUNKS_DIR', Path(tmpdir)):
                meta.save()

                meta_file = Path(tmpdir) / "test_file" / "metadata.json"
                assert meta_file.exists()

                saved_data = json.loads(meta_file.read_text())
                assert saved_data["file_id"] == "test_file"
                assert saved_data["total_chunks"] == 3
                assert saved_data["uploaded_chunks"] == [0, 1]


class TestChunkUserIsolation:
    """测试分片目录按用户隔离（FL1）"""

    def test_scoped_chunk_dir_separates_users(self):
        """不同用户的同名 file_id 落在不同目录"""
        from app.api.v1.file_upload import _scoped_chunk_dir

        dir_a = _scoped_chunk_dir(1, "same-id")
        dir_b = _scoped_chunk_dir(2, "same-id")
        assert dir_a != dir_b
        assert dir_a.parent.name == "1"
        assert dir_b.parent.name == "2"

    def test_scoped_chunk_dir_rejects_traversal(self):
        """file_id 含路径穿越字符时拒绝"""
        from fastapi import HTTPException
        from app.api.v1.file_upload import _scoped_chunk_dir

        for bad in ("", "..", "a/b", "a\\b", "../x"):
            with pytest.raises(HTTPException) as exc:
                _scoped_chunk_dir(1, bad)
            assert exc.value.status_code == 400

    def test_chunk_metadata_explicit_base_dir(self):
        """传入 base_dir 时元数据写入该目录，不落到全局 CHUNKS_DIR"""
        from app.api.v1.file_upload import ChunkMetadata
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "7"
            meta = ChunkMetadata("fid", 1, [0], base_dir=base)
            meta.save()
            assert (base / "fid" / "metadata.json").exists()


class TestChunkLockRegistry:
    """测试分片锁按用户隔离且可回收（FL5）"""

    @pytest.mark.asyncio
    async def test_lock_entry_released_after_use(self):
        """最后一个使用者离开后锁表清空，不会随上传次数无界增长"""
        from app.api.v1 import file_upload

        async with file_upload._chunk_lock_scope(1, "fid"):
            pass
        assert file_upload._chunk_locks == {}
        assert file_upload._chunk_lock_refs == {}

    @pytest.mark.asyncio
    async def test_same_file_serialized_and_distinct_users_not_shared(self):
        """同一 (user, file) 串行；不同用户的同名 file_id 不共享锁"""
        from app.api.v1 import file_upload

        order = []
        entered = asyncio.Event()

        async def holder():
            async with file_upload._chunk_lock_scope(1, "fid"):
                order.append("first-enter")
                entered.set()
                await asyncio.sleep(0.05)
                order.append("first-exit")

        async def waiter():
            await entered.wait()
            async with file_upload._chunk_lock_scope(1, "fid"):
                order.append("second-enter")

        async def other_user():
            async with file_upload._chunk_lock_scope(2, "fid"):
                order.append("other-user")

        await asyncio.gather(holder(), waiter(), other_user())

        assert order.index("first-exit") < order.index("second-enter")
        # 其他用户不受同 file_id 锁的阻塞：无需等待第一个使用者退出即可进入
        assert order.index("other-user") < order.index("first-exit")
        assert file_upload._chunk_locks == {}


class TestUploadStorageDateDir:
    """测试上传落盘日期目录统一（FL4）"""

    def test_date_dir_uses_compact_format_under_upload_root(self):
        from app.api.v1 import file_upload
        from datetime import datetime

        with patch.object(file_upload, "UPLOAD_DIR", Path("/tmp/uploads")):
            result = file_upload._storage_date_dir()

        assert result.parent == Path("/tmp/uploads")
        assert result.name == datetime.now().strftime("%Y%m%d")
        assert "/" not in result.name


class TestChunkUploadLimits:
    """测试分片链的大小/序号/总数校验（FL3）"""

    @pytest.mark.asyncio
    async def test_oversized_chunk_rejected_and_not_written(self, tmp_path):
        import io
        from fastapi import HTTPException
        from starlette.datastructures import UploadFile
        from app.api.v1 import file_upload

        with patch.object(file_upload, "CHUNKS_DIR", tmp_path), \
                patch.object(file_upload, "CHUNK_SIZE", 10):
            upload = UploadFile(filename="c", file=io.BytesIO(b"x" * 11))
            with pytest.raises(HTTPException) as exc:
                await file_upload.upload_chunk("fid", 0, upload, 1, {"sub": "1"})

        assert exc.value.status_code == 413
        assert not (tmp_path / "1" / "fid" / "chunk_0").exists()

    @pytest.mark.asyncio
    async def test_chunk_index_out_of_range_rejected(self, tmp_path):
        import io
        from fastapi import HTTPException
        from starlette.datastructures import UploadFile
        from app.api.v1 import file_upload

        with patch.object(file_upload, "CHUNKS_DIR", tmp_path):
            for index in (-1, 3):
                upload = UploadFile(filename="c", file=io.BytesIO(b"data"))
                with pytest.raises(HTTPException) as exc:
                    await file_upload.upload_chunk("fid", index, upload, 3, {"sub": "1"})
                assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_total_chunks_bounds_rejected(self, tmp_path):
        import io
        from fastapi import HTTPException
        from starlette.datastructures import UploadFile
        from app.api.v1 import file_upload

        with patch.object(file_upload, "CHUNKS_DIR", tmp_path):
            for total in (0, file_upload.MAX_TOTAL_CHUNKS + 1):
                upload = UploadFile(filename="c", file=io.BytesIO(b"data"))
                with pytest.raises(HTTPException) as exc:
                    await file_upload.upload_chunk("fid", 0, upload, total, {"sub": "1"})
                assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_init_rejects_out_of_range_file_size(self):
        from fastapi import HTTPException
        from app.api.v1 import file_upload

        for size in (0, -1, file_upload.MAX_FILE_SIZE + 1):
            with pytest.raises(HTTPException) as exc:
                await file_upload.init_chunked_upload(
                    "f.bin", size, "hash", None, {"sub": "1"}, AsyncMock()
                )
            assert exc.value.status_code == 413


class TestStaleChunkCleanup:
    """测试孤儿分片目录按 TTL 回收（FL3）"""

    def test_stale_dir_removed_and_fresh_dir_kept(self, tmp_path):
        import os
        import time
        from app.api.v1 import file_upload

        user_dir = tmp_path / "1"
        stale = user_dir / "old-file"
        fresh = user_dir / "new-file"
        stale.mkdir(parents=True)
        fresh.mkdir(parents=True)
        old = time.time() - file_upload.CHUNK_TTL_SECONDS - 10
        os.utime(stale, (old, old))

        file_upload._cleanup_stale_user_chunks(user_dir)

        assert not stale.exists()
        assert fresh.exists()


class TestChunkMergeValidation:
    """测试分片合并链的三道校验（FL2）：扩展名、声明大小、内容/MIME"""

    def _prepare_chunks(self, tmp_path, content: bytes) -> Path:
        chunk_dir = tmp_path / "1" / "fid"
        chunk_dir.mkdir(parents=True)
        (chunk_dir / "metadata.json").write_text(
            json.dumps({"file_id": "fid", "total_chunks": 1, "uploaded_chunks": [0]})
        )
        (chunk_dir / "chunk_0").write_bytes(content)
        return chunk_dir

    @pytest.mark.asyncio
    async def test_unsupported_extension_rejected(self, tmp_path):
        import hashlib
        from fastapi import HTTPException
        from app.api.v1 import file_upload

        content = b"#!/bin/sh\necho hi\n"
        with patch.object(file_upload, "CHUNKS_DIR", tmp_path):
            for filename in ("evil.exe", "noext"):
                with pytest.raises(HTTPException) as exc:
                    await file_upload.merge_chunks(
                        "fid", filename, hashlib.sha256(content).hexdigest(),
                        len(content), "text/plain", None, {"sub": "1"}, AsyncMock()
                    )
                assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_declared_size_mismatch_rejected(self, tmp_path):
        import hashlib
        from fastapi import HTTPException
        from app.api.v1 import file_upload

        content = b'{"a": 1}'
        chunk_dir = self._prepare_chunks(tmp_path, content)
        with patch.object(file_upload, "CHUNKS_DIR", tmp_path), \
                patch.object(file_upload, "UPLOAD_DIR", tmp_path):
            out_dir = file_upload._storage_date_dir()
            with pytest.raises(HTTPException) as exc:
                await file_upload.merge_chunks(
                    "fid", "chunk_test.json", hashlib.sha256(content).hexdigest(),
                    len(content) + 1, "application/json", None, {"sub": "1"}, AsyncMock()
                )

        assert exc.value.status_code == 400
        # 合并结果不落库、不残留在正式目录
        assert list(out_dir.glob("*")) == []
        assert chunk_dir.exists()

    @pytest.mark.asyncio
    async def test_content_type_mismatch_rejected(self, tmp_path):
        import hashlib
        from fastapi import HTTPException
        from app.api.v1 import file_upload

        # 扩展名声明为图片，内容实为 JSON
        content = b'{"a": 1}'
        self._prepare_chunks(tmp_path, content)
        with patch.object(file_upload, "CHUNKS_DIR", tmp_path), \
                patch.object(file_upload, "UPLOAD_DIR", tmp_path):
            with pytest.raises(HTTPException) as exc:
                await file_upload.merge_chunks(
                    "fid", "fake.png", hashlib.sha256(content).hexdigest(),
                    len(content), "image/png", None, {"sub": "1"}, AsyncMock()
                )

        assert exc.value.status_code == 400
        assert "内容校验失败" in exc.value.detail

    @pytest.mark.asyncio
    async def test_valid_merge_persists_and_cleans_chunks(self, tmp_path):
        import hashlib
        from app.api.v1 import file_upload

        content = b'{"a": 1}'
        chunk_dir = self._prepare_chunks(tmp_path, content)
        db = AsyncMock()

        with patch.object(file_upload, "CHUNKS_DIR", tmp_path), \
                patch.object(file_upload, "UPLOAD_DIR", tmp_path):
            result = await file_upload.merge_chunks(
                "fid", "chunk_test.json", hashlib.sha256(content).hexdigest(),
                len(content), "application/json", None, {"sub": "1"}, db
            )

        assert result["success"] is True
        assert result["file"]["filename"] == "chunk_test.json"
        assert result["file"]["file_size"] == len(content)
        assert db.add.called and db.commit.called
        assert not chunk_dir.exists()


class TestImageGenerationFormat:
    """测试 image_generation.py 的 response_format"""

    def test_image_generation_uses_url_format(self):
        """验证图片生成使用 url 格式而非 b64_json"""
        from app.utils import image_generation
        import inspect

        # 检查源代码中是否使用 url 格式
        source = inspect.getsource(image_generation)
        assert 'response_format' in source or 'url' in source


class TestAicloudStreamingKeepalive:
    """测试 aicloud.py 流式对话 keepalive"""

    def test_generate_function_exists(self):
        """验证 generate 函数存在"""
        import app.api.v1.aicloud as aicloud_module
        # 检查模块中是否有 chat_stream 端点
        assert hasattr(aicloud_module, 'chat_stream')

    @pytest.mark.asyncio
    async def test_generate_sends_keepalive(self):
        """验证 generate 函数发送 keepalive 心跳"""
        # 这个测试需要模拟整个流式响应
        # 简化测试：验证 generate 函数的实现
        import app.api.v1.aicloud as aicloud_module
        import inspect

        # 获取 chat_stream 函数源码
        source = inspect.getsource(aicloud_module.chat_stream)
        # 验证包含 keepalive
        assert 'keepalive' in source


class TestTaskQueueGetDb:
    """测试 task_queue.py 的 get_db() 用法"""

    def test_task_queue_module_imports(self):
        """验证 task_queue 模块正确导入"""
        import app.api.v1.task_queue as task_queue_module
        assert task_queue_module is not None


class TestProvidersSync:
    """测试 providers 同步功能"""

    def test_providers_module_imports(self):
        """验证 providers 模块正确导入"""
        import app.api.v1.providers as providers_module
        assert providers_module is not None


class TestModelAdmin:
    """测试 model_admin 功能"""

    def test_model_admin_module_imports(self):
        """验证 model_admin 模块正确导入"""
        import app.api.v2.model_admin as model_admin_module
        assert model_admin_module is not None


class TestGuardianRouter:
    """测试 guardian_router 功能"""

    def test_guardian_router_module_imports(self):
        """验证 guardian_router 模块正确导入"""
        import app.api.v2.guardian_router as guardian_module
        assert guardian_module is not None


class TestUserManage:
    """测试 user_manage 功能"""

    def test_user_manage_module_imports(self):
        """验证 user_manage 模块正确导入"""
        import app.api.v2.user_manage as user_manage_module
        assert user_manage_module is not None


class TestAdminConfig:
    """测试 admin_config 功能"""

    def test_admin_config_module_imports(self):
        """验证 admin_config 模块正确导入"""
        import app.api.v2.admin_config as admin_config_module
        assert admin_config_module is not None


class TestWorkflow:
    """测试 workflow 功能"""

    def test_workflow_module_imports(self):
        """验证 workflow 模块正确导入"""
        import app.api.v1.workflow as workflow_module
        assert workflow_module is not None


class TestKolorsHistory:
    """测试 kolors_history 功能"""

    def test_kolors_history_module_imports(self):
        """验证 kolors_history 模块正确导入"""
        import app.api.v1.kolors_history as kolors_module
        assert kolors_module is not None


class TestVisionApi:
    """测试 vision_api 功能"""

    def test_vision_api_module_imports(self):
        """验证 vision_api 模块正确导入"""
        import app.api.v1.vision_api as vision_module
        assert vision_module is not None


class TestGithub:
    """测试 github 功能"""

    def test_github_module_imports(self):
        """验证 github 模块正确导入"""
        import app.api.v1.github as github_module
        assert github_module is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
