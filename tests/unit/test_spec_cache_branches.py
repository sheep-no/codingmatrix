"""SpecCache 全分支回归。"""

import asyncio
import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.agent import spec_cache as sc
from app.agent.spec_cache import CacheEntry, SpecCache


@pytest.fixture
def cache(tmp_path):
    return SpecCache(tmp_path)


SAVE_KW = dict(
    specs={"s": 1},
    architecture={"tech_stack": ["Flask"], "language": "python"},
    file_plan=[{"path": "main.py"}],
    complexity={"level": "medium", "key_technologies": ["mysql"]},
    tech_stack=["Docker"],
    complexity_level="medium",
)


def _save(cache, requirement="开发博客系统，使用 flask 和 mysql", **kw):
    params = dict(SAVE_KW)
    params.update(kw)
    return cache.save(requirement, **params)


def _expired_entry(**kw):
    data = dict(
        requirement_hash="h",
        requirement_preview="p",
        created_at=(datetime.now() - timedelta(days=30)).isoformat(),
        last_accessed=datetime.now().isoformat(),
        requirement="r",
    )
    data.update(kw)
    return CacheEntry(**data)


class TestBatchCosine:
    def test_empty_vectors(self):
        assert sc.batch_cosine_similarity([1.0], []) == []

    def test_zero_query_norm(self):
        assert sc.batch_cosine_similarity([0.0, 0.0], [[1.0, 0.0]]) == [0.0]

    def test_zero_vector_norm(self):
        assert sc.batch_cosine_similarity([1.0, 0.0], [[0.0, 0.0]]) == [0.0]

    def test_dimension_mismatch_logs(self, monkeypatch):
        messages = []
        monkeypatch.setattr(sc.logger, "warning", messages.append)
        result = sc.batch_cosine_similarity([1.0, 0.0], [[1.0]])
        assert result == [0.0]
        assert "维度不一致" in messages[0]

    def test_normal(self):
        result = sc.batch_cosine_similarity([3.0, 4.0], [[3.0, 4.0]])
        assert result == pytest.approx([1.0])


class TestCacheEntry:
    def test_is_expired_true(self):
        assert _expired_entry().is_expired() is True

    def test_is_expired_false(self):
        entry = _expired_entry(created_at=datetime.now().isoformat())
        assert entry.is_expired() is False


class TestNormalization:
    def test_normalize_requirement(self, cache):
        assert cache._normalize_requirement("  Hello,  World!! ") == "hello world"

    def test_hash_changes_with_level(self, cache):
        plain = cache._compute_requirement_hash("Req")
        leveled = cache._compute_requirement_hash("Req", "medium")
        assert plain != leveled

    def test_normalize_tech_stack_handles_invalid_sources(self, cache):
        result = cache._normalize_tech_stack(
            "not-a-dict", [" Flask ", "", 1, "flask", "MYSQL"], None
        )
        assert result == ["flask", "mysql"]

    def test_normalize_tech_stack_non_dict_complexity(self, cache):
        result = cache._normalize_tech_stack({}, ["Docker"], "bad")
        assert result == ["docker"]

    def test_complexity_level_of_non_dict(self):
        entry = _expired_entry(complexity="bad")
        assert SpecCache._complexity_level_of(entry) == ""

    def test_complexity_level_of_missing(self):
        entry = _expired_entry(complexity={})
        assert SpecCache._complexity_level_of(entry) == ""

    def test_extract_keywords_chinese_and_action(self, cache):
        keywords = cache.extract_keywords("开发博客系统，实现登录功能，使用 Flask")
        assert "flask" in keywords
        assert "博客" in keywords
        assert "开发博客" in keywords


class TestComputeSimilarity:
    def test_both_empty_but_text_present(self, cache):
        # 无技术/动作关键词时回退到归一化文本词集
        assert cache.compute_similarity("!!!", "???") == 1.0

    def test_both_fully_empty(self, cache):
        assert cache.compute_similarity("", "") == 1.0

    def test_normalized_words_union_empty(self, cache):
        assert cache.compute_similarity("\u3000", "\u3000") == 1.0

    def test_one_side_empty_keywords(self, cache):
        assert cache.compute_similarity("普通文本", "使用 flask 开发博客系统") == 0.0

    def test_normalized_fallback_ratio(self, cache):
        similarity = cache.compute_similarity("alpha beta", "alpha gamma")
        assert similarity == pytest.approx(1 / 3)


class TestIndexLoad:
    def test_load_index_sync_missing_file(self, cache):
        cache._load_index_sync()
        assert cache._cache == {}

    def test_load_index_sync_corrupt_logs(self, cache, tmp_path, monkeypatch):
        (tmp_path / "index.json").write_text("{broken", encoding="utf-8")
        messages = []
        monkeypatch.setattr(sc.logger, "error", messages.append)
        cache._load_index_sync()
        assert "加载缓存索引失败" in messages[0]

    def test_load_index_sync_reads_entries(self, tmp_path):
        data = {
            "h": {
                "requirement_hash": "h",
                "requirement_preview": "p",
                "created_at": datetime.now().isoformat(),
                "last_accessed": datetime.now().isoformat(),
                "requirement": "r",
                "tech_stack": ["flask"],
                "requirement_vector": [1.0, 0.0],
            }
        }
        (tmp_path / "index.json").write_text(json.dumps(data), encoding="utf-8")
        cache = SpecCache(tmp_path)
        cache._load_index()
        assert cache._index_loaded is True
        assert cache._tech_index["flask"] == ["h"]
        assert cache._vector_cache["h"] == [1.0, 0.0]

    def test_build_indices_skips_expired(self, cache):
        cache._cache["x"] = _expired_entry(tech_stack=["flask"])
        cache._build_indices()
        assert cache._tech_index == {}

    def test_build_indices_appends_to_existing_group(self, cache):
        now = datetime.now().isoformat()
        cache._cache["a"] = _expired_entry(
            requirement_hash="a", created_at=now, tech_stack=["flask"]
        )
        cache._cache["b"] = _expired_entry(
            requirement_hash="b", created_at=now, tech_stack=["flask"]
        )
        cache._build_indices()
        assert cache._tech_index["flask"] == ["a", "b"]

    def test_ensure_index_loaded_sync_only_once(self, cache, monkeypatch):
        calls = []
        monkeypatch.setattr(cache, "_load_index_sync", lambda: calls.append(1))
        cache._ensure_index_loaded_sync()
        cache._ensure_index_loaded_sync()
        assert calls == [1]

    @pytest.mark.asyncio
    async def test_ensure_index_loaded_async_double_checked(self, cache, monkeypatch):
        calls = []

        async def _fake():
            calls.append(1)

        monkeypatch.setattr(cache, "_async_load_index", _fake)
        await cache._ensure_index_loaded()
        await cache._ensure_index_loaded()
        assert calls == [1]

    @pytest.mark.asyncio
    async def test_ensure_index_loaded_returns_inside_lock(self, cache):
        calls = []

        class _Lock:
            async def __aenter__(self):
                cache._index_loaded = True

            async def __aexit__(self, *args):
                return False

        cache._index_lock = _Lock()
        await cache._ensure_index_loaded()
        assert calls == []

    @pytest.mark.asyncio
    async def test_async_load_index(self, cache, monkeypatch):
        loaded = []
        monkeypatch.setattr(cache, "_load_index_sync", lambda: loaded.append("load"))
        monkeypatch.setattr(cache, "_build_indices", lambda: loaded.append("build"))
        await cache._async_load_index()
        assert loaded == ["load", "build"]
        assert cache._index_loaded is True


class TestSaveIndexErrors:
    def test_save_index_error(self, cache, monkeypatch):
        messages = []
        monkeypatch.setattr(sc.logger, "error", messages.append)

        def _boom(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(sc.json, "dump", _boom)
        cache._cache["h"] = _expired_entry(
            requirement_hash="h", created_at=datetime.now().isoformat()
        )
        cache._save_index()
        assert "保存缓存索引失败" in messages[0]


class TestLookup:
    def test_exact_hit_increments(self, cache):
        req_hash = _save(cache)
        entry = cache.lookup("开发博客系统，使用 flask 和 mysql", complexity_level="medium")
        assert entry is not None
        assert cache._cache[req_hash].access_count == 1
        assert cache._stats["hits"] == 1

    def test_exact_hit_expired_is_removed(self, cache):
        req_hash = cache._compute_requirement_hash("req")
        cache._cache[req_hash] = _expired_entry(requirement_hash=req_hash)
        cache._vector_cache[req_hash] = [1.0]
        cache._index_loaded = True
        (cache.cache_dir / f"{req_hash}.json").write_text("{}", encoding="utf-8")
        assert cache.lookup("req") is None
        assert req_hash not in cache._cache
        assert req_hash not in cache._vector_cache
        assert not (cache.cache_dir / f"{req_hash}.json").exists()
        assert cache._stats["misses"] == 1

    def test_exact_hit_expired_without_vector(self, cache):
        req_hash = cache._compute_requirement_hash("req")
        cache._cache[req_hash] = _expired_entry(requirement_hash=req_hash)
        cache._index_loaded = True
        (cache.cache_dir / f"{req_hash}.json").write_text("{}", encoding="utf-8")
        assert cache.lookup("req") is None
        assert cache._stats["misses"] == 1

    def test_no_valid_candidates(self, cache):
        cache._index_loaded = True
        assert cache.lookup("unknown requirement") is None
        assert cache._stats["misses"] == 1

    def test_expired_candidate_removed_during_fuzzy(self, cache):
        req_hash = _save(cache)
        cache._cache[req_hash].created_at = (datetime.now() - timedelta(days=30)).isoformat()
        cache._vector_cache[req_hash] = [1.0]
        (cache.cache_dir / f"{req_hash}.json").write_text("{}", encoding="utf-8")
        assert cache.lookup("使用 flask 开发博客系统") is None
        assert req_hash not in cache._cache
        assert req_hash not in cache._vector_cache
        assert not (cache.cache_dir / f"{req_hash}.json").exists()

    def test_expired_candidate_without_vector(self, cache):
        req_hash = _save(cache)
        cache._cache[req_hash].created_at = (datetime.now() - timedelta(days=30)).isoformat()
        cache._vector_cache.clear()
        (cache.cache_dir / f"{req_hash}.json").write_text("{}", encoding="utf-8")
        assert cache.lookup("使用 flask 开发博客系统") is None
        assert req_hash not in cache._cache

    def test_stale_index_hash_is_skipped(self, cache):
        _save(cache)
        cache._tech_index["flask"].append("ghost")
        assert cache.lookup("使用 flask 开发博客系统", complexity_level="medium") is not None

    def test_candidate_without_embedding_is_filtered(self, cache):
        _save(cache)
        # 候选没有向量且关键词不相似时，embedding 阈值下无命中
        assert cache.lookup("完全无关的普通文本", requirement_vector=[1.0, 0.0]) is None

    def test_embedding_hit_from_memory(self, cache):
        req_hash = _save(cache, requirement_vector=[1.0, 0.0])
        hit = cache.lookup("完全不同的需求", requirement_vector=[1.0, 0.0], complexity_level="medium")
        assert hit is not None
        assert hit.access_count == 1
        assert cache._vector_cache[req_hash] == [1.0, 0.0]

    def test_embedding_hit_loads_from_disk(self, cache):
        req_hash = _save(cache, requirement_vector=[1.0, 0.0])
        cache._vector_cache.clear()
        hit = cache.lookup("完全不同的需求", requirement_vector=[1.0, 0.0], complexity_level="medium")
        assert hit is not None
        assert cache._vector_cache[req_hash] == [1.0, 0.0]

    def test_embedding_best_index_resets(self, cache):
        _save(cache, requirement_vector=[1.0, 0.0])
        assert cache.lookup("完全不同", requirement_vector=[0.0, 1.0]) is None

    def test_embedding_no_match_falls_back_to_jaccard(self, cache):
        _save(cache, requirement_vector=[0.99, 0.01])
        hit = cache.lookup(
            "开发博客系统，使用 flask 和 mysql",
            requirement_vector=[0.0, 1.0],
            complexity_level="medium",
        )
        assert hit is not None

    def test_fuzzy_uses_preview_when_requirement_empty(self, cache):
        _save(cache)
        entry = next(iter(cache._cache.values()))
        entry.requirement = ""
        cache._index_loaded = True
        hit = cache.lookup("开发博客系统，使用 flask 和 mysql", complexity_level="medium")
        assert hit is not None

    def test_complexity_filter_rejects_other_level(self, cache):
        _save(cache, complexity_level="medium")
        assert cache.lookup("使用 flask 开发博客系统", complexity_level="simple") is None

    def test_tech_keyword_prefilter_hit(self, cache):
        _save(cache)
        hit = cache.lookup("使用 flask 开发博客系统", complexity_level="medium")
        assert hit is not None

    def test_fuzzy_no_match_increments_misses(self, cache):
        _save(cache)
        assert cache.lookup("完全无关的普通文本", complexity_level="medium") is None
        assert cache._stats["misses"] == 1


class TestSave:
    def test_lru_eviction_removes_oldest(self, cache, monkeypatch):
        monkeypatch.setattr(sc, "MAX_CACHE_ENTRIES", 2)
        first = _save(cache, requirement="first req")
        second = _save(cache, requirement="second req")
        cache._cache[first].last_accessed = "2000-01-01T00:00:00"
        cache._vector_cache[first] = [1.0]
        third = _save(cache, requirement="third req", requirement_vector=[2.0])
        assert first not in cache._cache
        assert first not in cache._tech_index.get("flask", [])
        assert second in cache._cache
        assert third in cache._cache

    def test_lru_does_not_remove_new_entry(self, cache, monkeypatch):
        monkeypatch.setattr(sc, "MAX_CACHE_ENTRIES", 1)
        first = _save(cache, requirement="first req")
        second = _save(cache, requirement="second req")
        assert second in cache._cache
        assert first not in cache._cache

    def test_lru_skips_when_new_entry_is_oldest(self, cache, monkeypatch):
        monkeypatch.setattr(sc, "MAX_CACHE_ENTRIES", 1)
        first = _save(cache, requirement="first req")
        cache._cache[first].last_accessed = "9999-01-01T00:00:00"
        _save(cache, requirement="second req")
        # 新条目自身最旧时不得移除自己
        assert len(cache._cache) == 2

    def test_lru_keeps_unrelated_tech_group(self, cache, monkeypatch):
        monkeypatch.setattr(sc, "MAX_CACHE_ENTRIES", 2)
        first = _save(cache, requirement="first req")
        cache._tech_index["other"] = ["unrelated"]
        cache._cache[first].last_accessed = "2000-01-01T00:00:00"
        _save(cache, requirement="second req")
        _save(cache, requirement="third req")
        assert first not in cache._cache
        assert cache._tech_index["other"] == ["unrelated"]

    def test_save_does_not_duplicate_index_entry(self, cache):
        req_hash = _save(cache)
        _save(cache)
        assert cache._tech_index["flask"].count(req_hash) == 1

    def test_save_index_file_written(self, cache):
        req_hash = _save(cache)
        assert json.loads((cache.cache_dir / "index.json").read_text())[req_hash]


class TestGetStatsAndClear:
    def test_stats(self, cache):
        _save(cache)
        cache.lookup("开发博客系统，使用 flask 和 mysql", complexity_level="medium")
        stats = cache.get_stats()
        assert stats["total_requests"] == 1
        assert stats["cache_hits"] == 1
        assert stats["hit_rate"] == 1.0
        assert stats["cached_entries"] == 1
        assert stats["vector_index_size"] == 0
        assert stats["tech_index_groups"] >= 1

    def test_stats_empty(self, cache):
        stats = cache.get_stats()
        assert stats["hit_rate"] == 0.0

    def test_clear_expired_default(self, cache):
        expired = _expired_entry(requirement_hash="h")
        cache._cache["h"] = expired
        cache._vector_cache["h"] = [1.0]
        cache._tech_index["flask"] = ["h"]
        (cache.cache_dir / "h.json").write_text("{}", encoding="utf-8")
        assert cache.clear_expired() == 1
        assert cache._cache == {}
        assert cache._vector_cache == {}
        assert cache._tech_index == {}

    def test_clear_expired_default_keeps_fresh(self, cache):
        _save(cache)
        cache._cache["old"] = _expired_entry(requirement_hash="old")
        assert cache.clear_expired() == 1
        assert "old" not in cache._cache
        assert len(cache._cache) == 1

    def test_clear_expired_min_age_removes_old(self, cache):
        req_hash = _save(cache)
        cache._cache[req_hash].created_at = (datetime.now() - timedelta(days=30)).isoformat()
        assert cache.clear_expired(min_age=timedelta(days=1)) == 1
        assert req_hash not in cache._cache

    def test_clear_expired_by_min_age(self, cache):
        fresh = _save(cache)
        assert cache.clear_expired(min_age=timedelta(days=1)) == 0
        assert fresh in cache._cache

    def test_clear_expired_keeps_other_tech_groups(self, cache):
        cache._cache["h"] = _expired_entry(requirement_hash="h")
        cache._tech_index["flask"] = ["h"]
        cache._tech_index["mysql"] = ["h", "other"]
        cache.clear_expired()
        assert "flask" not in cache._tech_index
        assert cache._tech_index["mysql"] == ["other"]

    def test_clear_expired_tech_group_without_key(self, cache):
        cache._cache["h"] = _expired_entry(requirement_hash="h")
        cache._tech_index["mysql"] = ["other"]
        cache.clear_expired()
        assert cache._tech_index["mysql"] == ["other"]

    def test_clear_all(self, cache):
        req_hash = _save(cache)
        assert cache.clear_all() == 1
        assert cache._cache == {}
        assert cache._vector_cache == {}
        assert cache._tech_index == {}
        assert not (cache.cache_dir / f"{req_hash}.json").exists()


class TestLoadFullEntry:
    def test_loads_disk_entry(self, cache):
        req_hash = _save(cache)
        entry = cache._cache[req_hash]
        loaded = cache._load_full_entry(entry)
        assert loaded.file_plan == [{"path": "main.py"}]

    def test_corrupt_disk_entry_returns_memory(self, cache, monkeypatch):
        req_hash = _save(cache)
        (cache.cache_dir / f"{req_hash}.json").write_text("{broken", encoding="utf-8")
        messages = []
        monkeypatch.setattr(sc.logger, "error", messages.append)
        loaded = cache._load_full_entry(cache._cache[req_hash])
        assert loaded is cache._cache[req_hash]
        assert "加载缓存文件失败" in messages[0]

    def test_missing_disk_entry_returns_memory(self, cache):
        entry = _expired_entry(requirement_hash="missing")
        assert cache._load_full_entry(entry) is entry


class TestSaveEntryErrors:
    def test_save_entry_error(self, cache, monkeypatch):
        messages = []
        monkeypatch.setattr(sc.logger, "error", messages.append)

        def _boom(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(sc.json, "dump", _boom)
        cache._save_entry(_expired_entry())
        assert "保存缓存文件失败" in messages[0]


class TestRemoveCacheFile:
    def test_remove_error(self, cache, monkeypatch):
        messages = []
        monkeypatch.setattr(sc.logger, "error", messages.append)
        path = cache.cache_dir / "x.json"
        path.write_text("{}", encoding="utf-8")

        def _boom(self):
            raise OSError("locked")

        monkeypatch.setattr(Path, "unlink", _boom)
        cache._remove_cache_file("x")
        assert "删除缓存文件失败" in messages[0]

    def test_missing_file_is_noop(self, cache):
        cache._remove_cache_file("nope")

    def test_get_cache_size_mb(self, cache):
        (cache.cache_dir / "a.json").write_text("x" * 1024, encoding="utf-8")
        assert cache._get_cache_size_mb() > 0


class TestAsyncWrappers:
    @pytest.mark.asyncio
    async def test_async_save_lookup(self, cache):
        req_hash = await cache.async_save(
            "开发博客系统，使用 flask 和 mysql",
            SAVE_KW["specs"],
            SAVE_KW["architecture"],
            SAVE_KW["file_plan"],
            SAVE_KW["complexity"],
            SAVE_KW["tech_stack"],
            complexity_level="medium",
        )
        assert req_hash in cache._cache
        hit = await cache.async_lookup("开发博客系统，使用 flask 和 mysql", complexity_level="medium")
        assert hit is not None

    @pytest.mark.asyncio
    async def test_async_clear_expired_and_all(self, cache):
        _save(cache)
        assert await cache.async_clear_expired(timedelta(days=1)) == 0
        assert await cache.async_clear_all() == 1
