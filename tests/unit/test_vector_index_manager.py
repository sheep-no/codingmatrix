"""VectorIndexManager 的索引加载/重建/检索与持久化分支。

使用真实 faiss（已安装）但把索引目录指向 tmp_path，避免污染 ``data/vector_index``。
"""

import json
import types

import numpy as np
import pytest

from app.agent import vector_index as vi_mod
from app.agent.vector_index import VectorIndexManager


@pytest.fixture
def paths(monkeypatch, tmp_path):
    index_dir = tmp_path / "vector_index"
    monkeypatch.setattr(vi_mod, "VECTOR_INDEX_DIR", index_dir)
    monkeypatch.setattr(vi_mod, "METADATA_PATH", index_dir / "project_metadata.json")
    monkeypatch.setattr(vi_mod, "INDEX_PATH", index_dir / "faiss_index.bin")
    monkeypatch.setattr(vi_mod, "IDS_PATH", index_dir / "id_map.json")
    return types.SimpleNamespace(
        dir=index_dir,
        metadata=index_dir / "project_metadata.json",
        index=index_dir / "faiss_index.bin",
        ids=index_dir / "id_map.json",
    )


def _fake_embedding(dim=vi_mod.EMBEDDING_DIM):
    async def _embed(text):
        # 用文本长度生成可区分的向量，保证同文本相似度为 1
        vec = [0.0] * dim
        vec[0] = 1.0
        vec[1] = float(len(text) % 7) / 10
        return vec

    return _embed


class TestLoadOrCreate:
    def test_creates_empty_index_when_files_missing(self, paths):
        manager = VectorIndexManager()

        assert manager.load_or_create() is True
        assert manager._loaded is True
        assert manager._index.ntotal == 0
        assert manager._id_map == {}
        assert manager._next_id == 0

    def test_loads_existing_index_and_id_map(self, paths):
        first = VectorIndexManager()
        first.load_or_create()
        first._index.add(np.array([[0.6, 0.8] + [0.0] * 766], dtype=np.float32))
        first._id_map[0] = {"project_id": "p1"}
        first._next_id = 1
        first._save_index()

        second = VectorIndexManager()
        assert second.load_or_create() is True
        assert second._index.ntotal == 1
        assert second._id_map == {0: {"project_id": "p1"}}
        assert second._next_id == 1

    def test_corrupt_index_falls_back_to_empty(self, paths):
        paths.dir.mkdir(parents=True, exist_ok=True)
        paths.index.write_bytes(b"not a faiss index")
        paths.ids.write_text("{}", encoding="utf-8")

        manager = VectorIndexManager()

        assert manager.load_or_create() is True
        assert manager._index.ntotal == 0


class TestBuildFromMetadata:
    @pytest.mark.asyncio
    async def test_missing_metadata_returns_zero(self, paths, monkeypatch):
        monkeypatch.setattr(
            "app.utils.AiCodeUtil.get_embedding", _fake_embedding()
        )

        manager = VectorIndexManager()

        assert await manager.build_from_metadata() == 0

    @pytest.mark.asyncio
    async def test_indexes_eligible_projects_and_skips_others(self, paths, monkeypatch):
        paths.dir.mkdir(parents=True, exist_ok=True)
        paths.metadata.write_text(
            json.dumps(
                [
                    {
                        "project_id": "p1",
                        "requirement": "登录系统",
                        "domain": "auth",
                        "feature_list": ["登录", "注册"],
                        "feature_source": "llm",
                    },
                    {
                        "project_id": "skip-fallback",
                        "feature_list": ["x"],
                        "feature_source": "file_fallback",
                    },
                    {"project_id": "no-features", "feature_list": []},
                ]
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "app.utils.AiCodeUtil.get_embedding", _fake_embedding()
        )

        manager = VectorIndexManager()
        count = await manager.build_from_metadata()

        assert count == 1
        assert manager._index.ntotal == 1
        assert manager._id_map[0]["project_id"] == "p1"
        assert manager._id_map[0]["feature_count"] == 2
        assert paths.index.exists()
        assert paths.ids.exists()

    @pytest.mark.asyncio
    async def test_embedding_failure_skips_project(self, paths, monkeypatch):
        paths.dir.mkdir(parents=True, exist_ok=True)
        paths.metadata.write_text(
            json.dumps(
                [
                    {"project_id": "bad", "feature_list": ["a"], "feature_source": "llm"},
                    {"project_id": "good", "feature_list": ["b"], "feature_source": "llm"},
                ]
            ),
            encoding="utf-8",
        )
        calls = {"n": 0}

        async def flaky_embed(text):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("embedding down")
            return await _fake_embedding()(text)

        monkeypatch.setattr("app.utils.AiCodeUtil.get_embedding", flaky_embed)

        manager = VectorIndexManager()
        count = await manager.build_from_metadata()

        assert count == 1
        assert manager._id_map[0]["project_id"] == "good"


class TestAddProject:
    @pytest.mark.asyncio
    async def test_rejects_project_without_feature_list(self, paths, monkeypatch):
        manager = VectorIndexManager()
        assert await manager.add_project({}) is False

    @pytest.mark.asyncio
    async def test_rejects_file_fallback_project(self, paths, monkeypatch):
        manager = VectorIndexManager()
        assert (
            await manager.add_project(
                {"feature_list": ["a"], "feature_source": "file_fallback"}
            )
            is False
        )

    @pytest.mark.asyncio
    async def test_lazy_loads_then_adds(self, paths, monkeypatch):
        monkeypatch.setattr(
            "app.utils.AiCodeUtil.get_embedding", _fake_embedding()
        )
        manager = VectorIndexManager()

        ok = await manager.add_project(
            {
                "project_id": "p1",
                "requirement": "需求",
                "feature_list": ["a", "b"],
                "feature_source": "llm",
            }
        )

        assert ok is True
        assert manager._loaded is True
        assert manager.total_count() == 1
        assert manager._id_map[0]["feature_count"] == 2

    @pytest.mark.asyncio
    async def test_embedding_failure_returns_false(self, paths, monkeypatch):
        async def broken(text):
            raise RuntimeError("boom")

        monkeypatch.setattr("app.utils.AiCodeUtil.get_embedding", broken)
        manager = VectorIndexManager()
        manager._loaded = True
        manager._create_empty_index()

        assert await manager.add_project(
            {"feature_list": ["a"], "feature_source": "llm"}
        ) is False


class TestSearch:
    @pytest.mark.asyncio
    async def test_lazy_loads_then_returns_empty_for_empty_index(self, paths, monkeypatch):
        monkeypatch.setattr(
            "app.utils.AiCodeUtil.get_embedding", _fake_embedding()
        )
        manager = VectorIndexManager()

        assert await manager.search("任意查询") == []
        assert manager._loaded is True

    @pytest.mark.asyncio
    async def test_returns_matches_above_threshold(self, paths, monkeypatch):
        monkeypatch.setattr(
            "app.utils.AiCodeUtil.get_embedding", _fake_embedding()
        )
        manager = VectorIndexManager()
        await manager.add_project(
            {
                "project_id": "p1",
                "requirement": "登录系统",
                "feature_list": ["登录"],
                "feature_source": "llm",
            }
        )

        results = await manager.search("登录系统 领域: auth 登录", top_k=5)

        assert results
        assert results[0][0]["project_id"] == "p1"
        assert results[0][1] >= vi_mod.SIMILARITY_THRESHOLD

    @pytest.mark.asyncio
    async def test_below_threshold_is_filtered_out(self, paths, monkeypatch):
        async def orthogonal(text):
            vec = [0.0] * vi_mod.EMBEDDING_DIM
            vec[0] = 1.0
            return vec

        monkeypatch.setattr("app.utils.AiCodeUtil.get_embedding", orthogonal)
        manager = VectorIndexManager()
        await manager.add_project(
            {"project_id": "p1", "feature_list": ["a"], "feature_source": "llm"}
        )

        async def opposite(text):
            vec = [0.0] * vi_mod.EMBEDDING_DIM
            vec[0] = -1.0
            return vec

        monkeypatch.setattr("app.utils.AiCodeUtil.get_embedding", opposite)

        assert await manager.search("query") == []

    @pytest.mark.asyncio
    async def test_id_missing_from_map_is_skipped(self, paths, monkeypatch):
        monkeypatch.setattr(
            "app.utils.AiCodeUtil.get_embedding", _fake_embedding()
        )
        manager = VectorIndexManager()
        await manager.add_project(
            {"project_id": "p1", "feature_list": ["a"], "feature_source": "llm"}
        )
        manager._id_map.clear()

        assert await manager.search("query") == []

    @pytest.mark.asyncio
    async def test_embedding_failure_returns_empty(self, paths, monkeypatch):
        async def broken(text):
            raise RuntimeError("boom")

        monkeypatch.setattr("app.utils.AiCodeUtil.get_embedding", broken)
        manager = VectorIndexManager()
        manager._loaded = True
        manager._create_empty_index()
        manager._index.add(np.array([[1.0] + [0.0] * 767], dtype=np.float32))

        assert await manager.search("query") == []


class TestTotalCount:
    def test_not_loaded_returns_zero(self, paths):
        assert VectorIndexManager().total_count() == 0

    def test_loaded_returns_index_ntotal(self, paths):
        manager = VectorIndexManager()
        manager._create_empty_index()
        manager._loaded = True
        assert manager.total_count() == 0


class TestProjectToText:
    def test_includes_requirement_domain_and_capped_features(self, paths):
        manager = VectorIndexManager()
        text = manager._project_to_text(
            {
                "requirement": "登录",
                "domain": "auth",
                "feature_list": [f"f{i}" for i in range(40)],
            }
        )

        assert text.startswith("登录 领域: auth ")
        assert "f29" in text
        assert "f30" not in text

    def test_empty_project_returns_empty_string(self, paths):
        assert VectorIndexManager()._project_to_text({}) == ""


class TestSaveIndexFailure:
    def test_save_failure_is_swallowed(self, paths, monkeypatch):
        manager = VectorIndexManager()
        manager._create_empty_index()

        def broken(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(vi_mod.faiss, "write_index", broken)

        manager._save_index()
