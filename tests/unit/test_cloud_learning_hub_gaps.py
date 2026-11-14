"""CloudLearningHub 边界补测：缓存载入/裁剪、匹配过滤与单例并发。"""

import asyncio

import pytest

from app.agent.cloud_learning_hub import (
    CloudLearningHub,
    CloudPattern,
    get_cloud_learning_hub,
)
from app.agent.feedback_learner import FixPattern


def _fix(error_type="import", message="boom", **overrides):
    values = dict(
        error_type=error_type,
        error_message=message,
        error_pattern=message,
        fix_description="修复",
        fix_example="",
        file_types=["python"],
    )
    values.update(overrides)
    return FixPattern(**values)


def _cloud_pattern(**overrides):
    values = dict(
        pattern=_fix().__dict__,
        project_id="p",
        project_type="web",
        tech_stack=[],
        upload_time="now",
        download_count=0,
        success_votes=0,
        failure_votes=0,
    )
    values.update(overrides)
    return CloudPattern(**values)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    knowledge = tmp_path / "cloud" / "cloud_knowledge.json"
    knowledge.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("app.agent.cloud_learning_hub.CLOUD_KNOWLEDGE_FILE", knowledge)
    monkeypatch.setattr("app.agent.cloud_learning_hub.CLOUD_CACHE_DIR", knowledge.parent)
    return knowledge


def test_quality_score_without_votes(isolated, tmp_path):
    pattern = _cloud_pattern()

    assert pattern.quality_score == 0.5
    assert pattern.is_high_quality() is False


def test_quality_score_uses_download_weight(isolated):
    pattern = _cloud_pattern(success_votes=1, download_count=200)

    assert pattern.quality_score == pytest.approx(0.7 + 0.3)
    assert pattern.is_high_quality() is True


def test_load_local_cache_restores_patterns(isolated, tmp_path):
    import json

    data = {"patterns": {"abc": _cloud_pattern().__dict__}}
    isolated.write_text(json.dumps(data), encoding="utf-8")

    hub = CloudLearningHub(cache_dir=tmp_path)

    assert list(hub._local_patterns) == ["abc"]


def test_load_local_cache_corrupt_file_is_logged(isolated, tmp_path):
    isolated.write_text("{broken", encoding="utf-8")

    hub = CloudLearningHub(cache_dir=tmp_path)

    assert hub._local_patterns == {}


def test_save_local_cache_trims_to_max(isolated, tmp_path, monkeypatch):
    hub = CloudLearningHub(cache_dir=tmp_path)
    hub._local_patterns = {
        f"p{i}": _cloud_pattern(success_votes=1, download_count=i) for i in range(5)
    }
    monkeypatch.setattr("app.agent.cloud_learning_hub.MAX_CACHED_PATTERNS", 2)

    hub._save_local_cache()

    assert len(hub._local_patterns) == 2
    assert "p4" in hub._local_patterns


def test_save_local_cache_failure_is_logged(isolated, tmp_path, monkeypatch):
    hub = CloudLearningHub(cache_dir=tmp_path)

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("builtins.open", boom)
    hub._save_local_cache()


def test_upload_pattern_vote_branches(isolated, tmp_path):
    hub = CloudLearningHub(cache_dir=tmp_path)
    pattern = _fix()

    first = hub.upload_pattern(pattern, success=False)
    second = hub.upload_pattern(pattern, success=True)

    assert first == second
    stored = hub._local_patterns[first]
    assert stored.failure_votes == 1
    assert stored.success_votes == 1
    assert stored.download_count == 1


def test_download_filters_error_type_keywords_and_quality(isolated, tmp_path):
    hub = CloudLearningHub(cache_dir=tmp_path)
    hub._local_patterns = {
        "keep": _cloud_pattern(success_votes=10),
        "other_type": _cloud_pattern(pattern=_fix(error_type="syntax").__dict__, success_votes=10),
        "no_keyword": _cloud_pattern(pattern=_fix(message="different").__dict__, success_votes=10),
        "low_quality": _cloud_pattern(success_votes=0, failure_votes=10),
    }

    results = hub.download_similar_patterns("import", ["boom"])

    assert [p for p in results] == [hub._local_patterns["keep"]]
    assert results[0].download_count == 1


def test_download_respects_max_results(isolated, tmp_path):
    hub = CloudLearningHub(cache_dir=tmp_path)
    hub._local_patterns = {
        f"p{i}": _cloud_pattern(success_votes=10) for i in range(5)
    }

    results = hub.download_similar_patterns("import", max_results=2)

    assert len(results) == 2


def test_vote_pattern_missing_hash_is_noop(isolated, tmp_path):
    hub = CloudLearningHub(cache_dir=tmp_path)

    hub.vote_pattern("missing", success=True)

    assert hub._local_patterns == {}


def test_vote_pattern_failure_increments(isolated, tmp_path):
    hub = CloudLearningHub(cache_dir=tmp_path)
    pattern_hash = hub.upload_pattern(_fix(), success=True)

    hub.vote_pattern(pattern_hash, success=False)

    assert hub._local_patterns[pattern_hash].failure_votes == 1


def test_stats_with_empty_cache(isolated, tmp_path):
    hub = CloudLearningHub(cache_dir=tmp_path)

    stats = hub.get_project_knowledge_stats()

    assert stats["total_patterns"] == 0
    assert stats["overall_success_rate"] == 0
    assert stats["top_patterns"] == []


def test_clear_cache_removes_file(isolated, tmp_path):
    hub = CloudLearningHub(cache_dir=tmp_path)
    hub.upload_pattern(_fix())
    assert isolated.exists()

    hub.clear_cache()

    assert hub._local_patterns == {}
    assert not isolated.exists()


@pytest.mark.asyncio
async def test_singleton_is_created_once(isolated, tmp_path, monkeypatch):
    import app.agent.cloud_learning_hub as hub_module

    monkeypatch.setattr(hub_module, "_cloud_hub", None)
    calls = []
    original = hub_module.CloudLearningHub

    def factory(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(hub_module, "CloudLearningHub", factory)

    first, second = await asyncio.gather(
        get_cloud_learning_hub(project_id="a"),
        get_cloud_learning_hub(project_id="b"),
    )

    assert first is second
    assert len(calls) == 1


def test_upload_existing_pattern_failure_false_branch(isolated, tmp_path):
    hub = CloudLearningHub(cache_dir=tmp_path)
    pattern = _fix()
    pattern_hash = hub.upload_pattern(pattern, success=True)
    hub._local_patterns[pattern_hash] = _cloud_pattern(success_votes=0)

    hub.upload_pattern(pattern, success=False)

    assert hub._local_patterns[pattern_hash].failure_votes == 1


@pytest.mark.asyncio
async def test_singleton_reuses_existing_instance(isolated, monkeypatch):
    import app.agent.cloud_learning_hub as hub_module

    sentinel = object()
    monkeypatch.setattr(hub_module, "_cloud_hub", sentinel)

    assert await get_cloud_learning_hub() is sentinel


@pytest.mark.asyncio
async def test_singleton_double_checked_lock(isolated, monkeypatch):
    import app.agent.cloud_learning_hub as hub_module

    monkeypatch.setattr(hub_module, "_cloud_hub", None)
    sentinel = object()

    class _RacingLock:
        async def __aenter__(self):
            hub_module._cloud_hub = sentinel
            return self

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(hub_module, "_hub_lock", _RacingLock())

    assert await get_cloud_learning_hub() is sentinel


@pytest.mark.asyncio
async def test_singleton_second_waiter_observes_created_instance(isolated, monkeypatch):
    import app.agent.cloud_learning_hub as hub_module

    monkeypatch.setattr(hub_module, "_cloud_hub", None)
    original = hub_module.CloudLearningHub
    created = []

    async def pause():
        await asyncio.sleep(0.01)

    class _SlowHub(original):
        def __init__(self, **kwargs):
            created.append(kwargs)
            super().__init__(**kwargs)

    monkeypatch.setattr(hub_module, "CloudLearningHub", _SlowHub)

    async def first():
        await pause()
        return await get_cloud_learning_hub(project_id="a")

    hub_a, hub_b = await asyncio.gather(
        first(), get_cloud_learning_hub(project_id="b")
    )

    assert hub_a is hub_b
    assert len(created) == 1
