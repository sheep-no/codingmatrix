"""FixPatternCache 缓存生命周期、反模式与 BM25 检索测试。"""

import json
import time
from pathlib import Path

import pytest

import app.agent.fix_pattern_cache as fpc
from app.agent.error_classifier import ErrorClassification
from app.agent.fix_pattern_cache import FixPattern, FixPatternCache


def _classification(error_type="NameError", subtype="undefined"):
    return ErrorClassification(
        error_type=error_type,
        error_subtype=subtype,
        description="d",
        suggested_fix_strategy="s",
        confidence=0.9,
    )


def _pattern(signature="sig", **overrides):
    data = dict(
        error_signature=signature,
        error_type="NameError",
        error_subtype="undefined",
        project_type="python",
        file_type=".py",
        fix_strategy="import missing module",
        model_used="m",
        fixed_code_snippet="pass",
        success_rate=0.6,
        usage_count=2,
        last_hit_time=time.time(),
        hit_count=1,
    )
    data.update(overrides)
    return FixPattern(**data)


@pytest.fixture
def cache(tmp_path):
    return FixPatternCache(cache_file=tmp_path / "cache.json")


class TestLoad:
    def test_missing_file_starts_empty(self, tmp_path):
        instance = FixPatternCache(cache_file=tmp_path / "absent.json")

        assert instance.patterns == {}

    def test_loads_legacy_entries_with_defaults(self, tmp_path):
        path = tmp_path / "cache.json"
        payload = {
            "legacy": {
                "error_signature": "legacy",
                "error_type": "E",
                "error_subtype": "S",
                "project_type": "p",
                "file_type": ".py",
                "fix_strategy": "x",
                "model_used": "m",
                "fixed_code_snippet": "",
                "success_rate": 0.5,
                "usage_count": 1,
            }
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

        instance = FixPatternCache(cache_file=path)

        pattern = instance.patterns["legacy"]
        assert pattern.failed_count == 0
        assert pattern.last_failed_at is None
        assert pattern.failure_reason is None

    def test_corrupt_json_is_ignored(self, tmp_path, monkeypatch):
        warnings = []
        monkeypatch.setattr(fpc.logger, "warning", lambda message: warnings.append(message))
        path = tmp_path / "cache.json"
        path.write_text("{ not json", encoding="utf-8")

        instance = FixPatternCache(cache_file=path)

        assert instance.patterns == {}
        assert warnings and warnings[0].startswith("加载修复模式缓存失败")

    def test_open_error_is_ignored(self, tmp_path, monkeypatch):
        path = tmp_path / "cache.json"
        path.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(fpc.json, "load", lambda _fh: (_ for _ in ()).throw(OSError("io")))

        assert FixPatternCache(cache_file=path).patterns == {}


class TestSave:
    def test_save_only_keeps_used_patterns(self, cache, tmp_path):
        cache.patterns["used"] = _pattern("used")
        cache.patterns["unused"] = _pattern("unused", usage_count=0)

        cache._save_cache()

        saved = json.loads((tmp_path / "cache.json").read_text(encoding="utf-8"))
        assert set(saved) == {"used"}

    def test_save_failure_logs_warning(self, cache, monkeypatch):
        warnings = []
        monkeypatch.setattr(fpc.logger, "warning", lambda message: warnings.append(message))
        monkeypatch.setattr(
            fpc.json, "dump", lambda *a, **k: (_ for _ in ()).throw(OSError("disk"))
        )

        cache._save_cache()

        assert warnings == ["保存修复模式缓存失败：disk"]

    def test_async_save_runs_in_thread_body(self, cache, monkeypatch):
        calls = []

        class ImmediateThread:
            def __init__(self, target=None, daemon=None):
                calls.append(daemon)
                target()

            def start(self):
                pass

        monkeypatch.setattr(fpc.threading, "Thread", ImmediateThread)
        cache.patterns["p"] = _pattern()

        cache._save_cache_async()

        assert calls == [True]
        assert (cache.cache_file).exists()

    def test_async_save_swallows_errors(self, cache, monkeypatch):
        warnings = []
        monkeypatch.setattr(fpc.logger, "warning", lambda message: warnings.append(message))

        class ImmediateThread:
            def __init__(self, target=None, daemon=None):
                target()

            def start(self):
                pass

        monkeypatch.setattr(fpc.threading, "Thread", ImmediateThread)
        monkeypatch.setattr(cache, "_save_cache", lambda: (_ for _ in ()).throw(OSError("x")))

        cache._save_cache_async()

        assert warnings == ["异步保存修复模式缓存失败：x"]


class TestEvictionPriority:
    def test_anti_pattern_sorts_before_normal(self, cache):
        anti = _pattern("anti", failed_count=5, success_rate=0.1)
        normal = _pattern("normal", success_rate=0.9)

        assert cache._get_eviction_priority("anti", anti) < cache._get_eviction_priority(
            "normal", normal
        )

    def test_missing_hit_time_sorts_oldest(self, cache):
        old = _pattern("old", last_hit_time=None)
        recent = _pattern("recent")

        assert cache._get_eviction_priority("old", old) < cache._get_eviction_priority(
            "recent", recent
        )


class TestFindAndAdd:
    def test_signature_is_stable(self, cache):
        first = cache._generate_error_signature(_classification(), "python", ".py")
        second = cache._generate_error_signature(_classification(), "python", ".py")

        assert first == second
        assert len(first) == 32

    def test_find_hit_increments_usage(self, cache, monkeypatch):
        monkeypatch.setattr(cache, "_save_cache_async", lambda: None)
        signature = cache._generate_error_signature(_classification(), "python", ".py")
        cache.patterns[signature] = _pattern(signature, usage_count=4)

        result = cache.find_pattern(_classification(), "python", ".py")

        assert result is not None
        assert result.usage_count == 5

    def test_find_skips_anti_pattern(self, cache, monkeypatch):
        warnings = []
        monkeypatch.setattr(fpc.logger, "warning", lambda message: warnings.append(message))
        signature = cache._generate_error_signature(_classification(), "python", ".py")
        cache.patterns[signature] = _pattern(
            signature, failed_count=3, success_rate=0.2
        )

        assert cache.find_pattern(_classification(), "python", ".py") is None
        assert "反模式" in warnings[0]

    def test_find_miss_returns_none(self, cache):
        assert cache.find_pattern(_classification(), "python", ".py") is None

    def test_add_pattern_sets_fields(self, cache, monkeypatch):
        monkeypatch.setattr(cache, "_save_cache_async", lambda: None)

        cache.add_pattern(
            _classification(), "python", ".py", "strategy", "model", "pass", strategy_version=4
        )

        pattern = next(iter(cache.patterns.values()))
        assert pattern.success_rate == 1.0
        assert pattern.usage_count == 1
        assert pattern.hit_count == 1
        assert pattern.strategy_version == 4


class TestUpdateSuccess:
    def test_success_increases_rate(self, cache, monkeypatch):
        monkeypatch.setattr(cache, "_save_cache_async", lambda: None)
        cache.patterns["s"] = _pattern("s", success_rate=0.95, hit_count=1)

        cache.update_pattern_success("s", True)

        assert cache.patterns["s"].success_rate == 1.0
        assert cache.patterns["s"].hit_count == 2

    def test_failure_decreases_rate_and_tracks_reason(self, cache, monkeypatch):
        monkeypatch.setattr(cache, "_save_cache_async", lambda: None)
        cache.patterns["s"] = _pattern("s", success_rate=0.1)

        cache.update_pattern_success("s", False, failure_reason="tests still fail")

        pattern = cache.patterns["s"]
        assert pattern.success_rate == 0.0
        assert pattern.failed_count == 1
        assert pattern.failure_reason == "tests still fail"
        assert pattern.last_failed_at

    def test_unknown_signature_is_noop(self, cache):
        cache.update_pattern_success("missing", True)

        assert cache.patterns == {}


class TestDecayAndCleanup:
    def test_old_hit_halves_success_rate(self, cache):
        old = time.time() - 31 * 24 * 3600
        cache.patterns["s"] = _pattern("s", success_rate=0.8, last_hit_time=old)

        cache._apply_decay_and_cleanup()

        assert cache.patterns["s"].success_rate == pytest.approx(0.4)
        assert cache.patterns["s"].last_hit_time > old

    def test_low_success_rate_is_not_decayed(self, cache):
        old = time.time() - 31 * 24 * 3600
        cache.patterns["s"] = _pattern("s", success_rate=0.1, last_hit_time=old)

        cache._apply_decay_and_cleanup()

        assert cache.patterns["s"].success_rate == pytest.approx(0.1)
        assert cache.patterns["s"].last_hit_time == old

    def test_never_hit_is_skipped(self, cache):
        cache.patterns["s"] = _pattern("s", last_hit_time=None)

        cache._apply_decay_and_cleanup()

        assert "s" in cache.patterns

    def test_stale_entry_is_archived(self, cache):
        old = time.time() - 61 * 24 * 3600
        cache.patterns["s"] = _pattern("s", last_hit_time=old)

        cache._apply_decay_and_cleanup()

        assert cache.patterns == {}

    def test_capacity_evicts_lowest_priority(self, tmp_path):
        instance = FixPatternCache(cache_file=tmp_path / "c.json", max_size=1)
        instance.patterns["keep"] = _pattern("keep", success_rate=0.9)
        instance.patterns["drop"] = _pattern("drop", success_rate=0.1)

        instance._apply_decay_and_cleanup()

        assert set(instance.patterns) == {"keep"}

    def test_expired_entry_also_evicted_by_capacity_is_safe(self, tmp_path):
        instance = FixPatternCache(cache_file=tmp_path / "c.json", max_size=1)
        old = time.time() - 61 * 24 * 3600
        instance.patterns["expired"] = _pattern("expired", last_hit_time=old)
        instance.patterns["fresh"] = _pattern("fresh")

        instance._apply_decay_and_cleanup()

        assert set(instance.patterns) == {"fresh"}


class TestSimilarity:
    def test_tokenize_strips_punctuation(self, cache):
        assert cache._tokenize("Hello, World! foo_bar") == ["hello", "world", "foo_bar"]

    def test_tokenize_skips_tokens_without_alphanumerics(self, cache):
        assert cache._tokenize("hello !!! ---") == ["hello"]

    def test_bm25_zero_for_absent_query_term(self, cache):
        cache.patterns["p"] = _pattern("p", fix_strategy="alpha beta")

        assert cache._bm25_score(["gamma"], ["alpha", "beta"], 2.0) == 0.0

    def test_bm25_positive_for_match(self, cache):
        cache.patterns["p"] = _pattern("p", fix_strategy="alpha beta")

        assert cache._bm25_score(["alpha"], ["alpha", "beta"], 2.0) > 0

    def test_empty_query_returns_empty(self, cache):
        assert cache.find_similar_patterns(_classification("", ""), "", "") == []

    def test_only_anti_patterns_returns_empty(self, cache):
        cache.patterns["p"] = _pattern(
            "p", failed_count=4, success_rate=0.1, fix_strategy="alpha"
        )

        assert cache.find_similar_patterns(_classification(), "python", ".py") == []

    def test_threshold_filters_and_sorts(self, cache):
        cache.patterns["a"] = _pattern(
            "a", fix_strategy="nameerror undefined python py", success_rate=0.9
        )
        cache.patterns["b"] = _pattern(
            "b", fix_strategy="unrelated content", success_rate=0.9
        )

        results = cache.find_similar_patterns(
            _classification(), "python", ".py", similarity_threshold=0.0
        )

        assert [p.error_signature for p in results][0] == "a"
        assert {p.error_signature for p in results} == {"a", "b"}

    def test_no_result_above_threshold(self, cache):
        cache.patterns["a"] = _pattern(
            "a", fix_strategy="unrelated content", success_rate=0.9
        )

        assert cache.find_similar_patterns(
            _classification(), "python", ".py", similarity_threshold=10.0
        ) == []
