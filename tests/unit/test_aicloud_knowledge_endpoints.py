"""aicloud_knowledge 端点补测：鉴权、文件保存、列表、删除与检索。"""

import io
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from starlette.datastructures import UploadFile

import app.api.v1.aicloud_knowledge as api
from app.models.aicloud_knowledge import AicloudKnowledgeChunk, AicloudKnowledgeDoc


async def _allow(*_args, **_kwargs):
    return None


@pytest.fixture(autouse=True)
def _permission(monkeypatch):
    monkeypatch.setattr(api, "check_aicloud_permission", _allow)


def _upload(payload: bytes, filename: str = "doc.txt") -> UploadFile:
    return UploadFile(file=io.BytesIO(payload), filename=filename, size=len(payload))


class TestCurrentUser:
    @pytest.mark.asyncio
    async def test_returns_int_from_sub(self):
        assert await api.get_current_user_id({"sub": "7"}) == 7

    @pytest.mark.asyncio
    async def test_missing_sub_raises_401(self):
        with pytest.raises(HTTPException) as error:
            await api.get_current_user_id({})
        assert error.value.status_code == 401


class TestUploadFailures:
    @pytest.mark.asyncio
    async def test_unsupported_extension_raises_400(self, monkeypatch, tmp_path):
        monkeypatch.setattr(api, "KNOWLEDGE_STORAGE_PATH", str(tmp_path))

        with pytest.raises(HTTPException) as error:
            await api.upload_document(
                file=_upload(b"data", "virus.exe"),
                collection="default",
                description=None,
                tags=None,
                chunk_size=500,
                chunk_overlap=50,
                db=SimpleNamespace(),
                user_id=1,
            )

        assert error.value.status_code == 400
        assert "不支持的文件类型" in error.value.detail

    @pytest.mark.asyncio
    async def test_http_exception_during_save_removes_partial_file(self, monkeypatch, tmp_path):
        real_open = open
        created = []

        class FailingWriter:
            def __init__(self, path):
                self.path = path
                created.append(path)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def write(self, _chunk):
                raise HTTPException(status_code=400, detail="write rejected")

        def fake_open(path, mode="r", *args, **kwargs):
            if "wb" in mode:
                return FailingWriter(path)
            return real_open(path, mode, *args, **kwargs)

        monkeypatch.setattr(api, "KNOWLEDGE_STORAGE_PATH", str(tmp_path))
        monkeypatch.setattr("builtins.open", fake_open)

        with pytest.raises(HTTPException) as error:
            await api.upload_document(
                file=_upload(b"data"),
                collection="default",
                description=None,
                tags=None,
                chunk_size=500,
                chunk_overlap=50,
                db=SimpleNamespace(),
                user_id=1,
            )

        assert error.value.status_code == 400
        assert created

    @pytest.mark.asyncio
    async def test_generic_save_error_returns_500(self, monkeypatch, tmp_path):
        def boom(*_args, **_kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(api, "KNOWLEDGE_STORAGE_PATH", str(tmp_path))
        monkeypatch.setattr("builtins.open", boom)

        with pytest.raises(HTTPException) as error:
            await api.upload_document(
                file=_upload(b"data"),
                collection="default",
                description=None,
                tags=None,
                chunk_size=500,
                chunk_overlap=50,
                db=SimpleNamespace(),
                user_id=1,
            )

        assert error.value.status_code == 500
        assert error.value.detail == "文件保存失败"

    @pytest.mark.asyncio
    async def test_generic_save_error_removes_existing_partial_file(self, monkeypatch, tmp_path):
        created = []

        class PartialWriter:
            def __init__(self, path):
                self.path = path
                created.append(path)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def write(self, _chunk):
                raise OSError("disk full")

        monkeypatch.setattr(api, "KNOWLEDGE_STORAGE_PATH", str(tmp_path))
        monkeypatch.setattr(api, "uuid", SimpleNamespace(uuid4=lambda: "fixed-id"))
        monkeypatch.setattr("builtins.open", lambda path, *a, **k: PartialWriter(path))
        # 文件在清理前已存在（模拟写入了一部分）
        monkeypatch.setattr(api.os.path, "exists", lambda _p: True)
        removed = []
        monkeypatch.setattr(api.os, "remove", removed.append)

        with pytest.raises(HTTPException) as error:
            await api.upload_document(
                file=_upload(b"data"),
                collection="default",
                description=None,
                tags=None,
                chunk_size=500,
                chunk_overlap=50,
                db=SimpleNamespace(),
                user_id=1,
            )

        assert error.value.status_code == 500
        assert removed == created

    @pytest.mark.asyncio
    async def test_empty_parsed_content_marks_document_failed(self, test_db, monkeypatch, tmp_path):
        monkeypatch.setattr(api, "KNOWLEDGE_STORAGE_PATH", str(tmp_path))
        monkeypatch.setattr(api, "parse_document", lambda _path: "")
        monkeypatch.setattr(api, "chunk_text", lambda *_a, **_k: [])

        with pytest.raises(HTTPException) as error:
            await api.upload_document(
                file=_upload(b"data", "empty.txt"),
                collection="default",
                description=None,
                tags=None,
                chunk_size=500,
                chunk_overlap=50,
                db=test_db,
                user_id=1,
            )

        assert error.value.status_code == 400
        doc = (
            await test_db.execute(
                select(AicloudKnowledgeDoc).where(AicloudKnowledgeDoc.filename == "empty.txt")
            )
        ).scalars().one()
        assert doc.status == "failed"
        assert doc.error_message == "文档内容为空或无法解析"

    @pytest.mark.asyncio
    async def test_failure_status_recording_error_is_swallowed(self, test_db, monkeypatch, tmp_path):
        monkeypatch.setattr(api, "KNOWLEDGE_STORAGE_PATH", str(tmp_path))

        def broken_parse(_path):
            raise RuntimeError("parse boom")

        monkeypatch.setattr(api, "parse_document", broken_parse)

        class FailingLookup:
            def __getattr__(self, name):
                return getattr(test_db, name)

            async def rollback(self):
                await test_db.rollback()

            async def get(self, *_args, **_kwargs):
                raise RuntimeError("lookup failed")

        with pytest.raises(HTTPException) as error:
            await api.upload_document(
                file=_upload(b"data", "broken.txt"),
                collection="default",
                description=None,
                tags=None,
                chunk_size=500,
                chunk_overlap=50,
                db=FailingLookup(),
                user_id=1,
            )

        assert error.value.status_code == 500
        assert error.value.detail == "文档处理失败，请稍后重试"

    @pytest.mark.asyncio
    async def test_missing_document_during_failure_recording_is_tolerated(
        self, test_db, monkeypatch, tmp_path
    ):
        monkeypatch.setattr(api, "KNOWLEDGE_STORAGE_PATH", str(tmp_path))

        def broken_parse(_path):
            raise RuntimeError("parse boom")

        monkeypatch.setattr(api, "parse_document", broken_parse)

        class MissingLookup:
            def __getattr__(self, name):
                return getattr(test_db, name)

            async def rollback(self):
                await test_db.rollback()

            async def get(self, *_args, **_kwargs):
                return None

        with pytest.raises(HTTPException):
            await api.upload_document(
                file=_upload(b"data", "gone.txt"),
                collection="default",
                description=None,
                tags=None,
                chunk_size=500,
                chunk_overlap=50,
                db=MissingLookup(),
                user_id=1,
            )


class TestSearchWithoutCollection:
    @pytest.mark.asyncio
    async def test_collection_none_skips_collection_filter(self, monkeypatch):
        async def embedding(_text, model=None):
            return [1.0, 0.0]

        captured = {}

        class FakeDb:
            async def execute(self, statement):
                captured["sql"] = str(statement)
                return _FakeResult(scalars=[])

        monkeypatch.setattr(api, "get_embedding", embedding)

        await api.search_knowledge(
            request=api.KnowledgeSearchRequest(query="hello", collection=None),
            db=FakeDb(),
            user_id=1,
        )

        assert "collection =" not in captured["sql"].lower()


class _FakeResult:
    def __init__(self, scalars=None, one=None):
        self._scalars = scalars or []
        self._one = one

    def scalars(self):
        return self

    def all(self):
        return self._scalars

    def scalar_one_or_none(self):
        return self._one


class TestListDocuments:
    @pytest.mark.asyncio
    async def test_lists_documents_with_collection_filter(self):
        captured = {}

        doc = SimpleNamespace(
            id="d1",
            filename="a.txt",
            file_type=".txt",
            file_size=3,
            status="completed",
            chunk_count=1,
            description=None,
            tags=None,
            created_at=None,
            error_message=None,
        )

        class FakeDb:
            async def execute(self, statement):
                captured["sql"] = str(statement)
                return _FakeResult(scalars=[doc])

        result = await api.list_documents(collection="default", db=FakeDb(), user_id=1)

        assert result[0]["id"] == "d1"
        assert result[0]["created_at"] is None
        assert "JOIN" in captured["sql"].upper()

    @pytest.mark.asyncio
    async def test_collection_none_skips_join(self):
        captured = {}

        class FakeDb:
            async def execute(self, statement):
                captured["sql"] = str(statement)
                return _FakeResult(scalars=[])

        assert await api.list_documents(collection=None, db=FakeDb(), user_id=1) == []
        assert "JOIN" not in captured["sql"].upper()


class TestDeleteDocument:
    @pytest.mark.asyncio
    async def test_missing_document_raises_404(self, test_db):
        with pytest.raises(HTTPException) as error:
            await api.delete_document(doc_id="missing", db=test_db, user_id=1)
        assert error.value.status_code == 404

    @pytest.mark.asyncio
    async def test_document_without_path_is_deleted(self, test_db):
        doc = AicloudKnowledgeDoc(
            id="doc-nopath",
            user_id=1,
            filename="nopath.txt",
            file_type=".txt",
            file_size=1,
            file_path=None,
            status="completed",
        )
        test_db.add(doc)
        await test_db.commit()

        result = await api.delete_document(doc_id="doc-nopath", db=test_db, user_id=1)

        assert result["status"] == "success"
        assert await test_db.get(AicloudKnowledgeDoc, "doc-nopath") is None

    @pytest.mark.asyncio
    async def test_file_removal_error_is_logged(self, test_db, monkeypatch, tmp_path):
        target = tmp_path / "doc.txt"
        target.write_text("x")
        monkeypatch.setattr(api, "KNOWLEDGE_STORAGE_PATH", str(tmp_path))

        doc = AicloudKnowledgeDoc(
            id="doc-remove-error",
            user_id=1,
            filename="doc.txt",
            file_type=".txt",
            file_size=1,
            file_path=str(target),
            status="completed",
        )
        test_db.add(doc)
        await test_db.commit()

        def boom(_path):
            raise OSError("locked")

        monkeypatch.setattr(api.os, "remove", boom)

        result = await api.delete_document(
            doc_id="doc-remove-error", db=test_db, user_id=1
        )

        assert result["status"] == "success"
        assert target.exists()


class TestSearchKnowledge:
    @pytest.mark.asyncio
    async def test_blank_query_raises_400(self):
        request = api.KnowledgeSearchRequest(query="   ")

        with pytest.raises(HTTPException) as error:
            await api.search_knowledge(request=request, db=SimpleNamespace(), user_id=1)

        assert error.value.status_code == 400

    @pytest.mark.asyncio
    async def test_embedding_failure_returns_500(self, monkeypatch):
        async def boom(_text, model=None):
            raise RuntimeError("no embedding")

        monkeypatch.setattr(api, "get_embedding", boom)
        request = api.KnowledgeSearchRequest(query="hello")

        with pytest.raises(HTTPException) as error:
            await api.search_knowledge(request=request, db=SimpleNamespace(), user_id=1)

        assert error.value.status_code == 500
        assert error.value.detail == "查询向量化失败"

    @pytest.mark.asyncio
    async def test_empty_knowledge_base_returns_message(self, monkeypatch):
        async def embedding(_text, model=None):
            return [1.0, 0.0]

        class FakeDb:
            async def execute(self, _statement):
                return _FakeResult(scalars=[])

        monkeypatch.setattr(api, "get_embedding", embedding)

        result = await api.search_knowledge(
            request=api.KnowledgeSearchRequest(query="hello"),
            db=FakeDb(),
            user_id=1,
        )

        assert result == {"query": "hello", "results": [], "message": "知识库为空"}

    @pytest.mark.asyncio
    async def test_invalid_embedding_json_is_skipped(self, monkeypatch):
        async def embedding(_text, model=None):
            return [1.0, 0.0]

        chunk = AicloudKnowledgeChunk(
            id="c1",
            doc_id="d1",
            user_id=1,
            content="broken",
            chunk_index=0,
            collection="default",
            embedding="not-json",
        )

        class FakeDb:
            async def execute(self, _statement):
                return _FakeResult(scalars=[chunk])

        monkeypatch.setattr(api, "get_embedding", embedding)

        result = await api.search_knowledge(
            request=api.KnowledgeSearchRequest(query="hello"),
            db=FakeDb(),
            user_id=1,
        )

        assert result["results"] == []

    @pytest.mark.asyncio
    async def test_results_include_filename_and_unknown_fallback(self, monkeypatch, test_db):
        async def embedding(_text, model=None):
            return [1.0, 0.0]

        monkeypatch.setattr(api, "get_embedding", embedding)

        test_db.add(
            AicloudKnowledgeDoc(
                id="doc-1",
                user_id=1,
                filename="known.txt",
                file_type=".txt",
                file_size=1,
                status="completed",
            )
        )
        test_db.add_all([
            AicloudKnowledgeChunk(
                id="c-known",
                doc_id="doc-1",
                user_id=1,
                content="known content",
                chunk_index=0,
                collection="default",
                embedding=json.dumps([1.0, 0.0]),
            ),
            AicloudKnowledgeChunk(
                id="c-orphan",
                doc_id="doc-gone",
                user_id=1,
                content="orphan content",
                chunk_index=1,
                collection="default",
                embedding=json.dumps([1.0, 0.0]),
            ),
        ])
        await test_db.commit()

        result = await api.search_knowledge(
            request=api.KnowledgeSearchRequest(query="hello", top_k=5),
            db=test_db,
            user_id=1,
        )

        filenames = {entry["filename"] for entry in result["results"]}
        assert "known.txt" in filenames
        assert "Unknown" in filenames
        assert result["total_found"] == len(result["results"])
