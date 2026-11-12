"""Layer 2 语义/关键词联想全分支回归。"""

import sys
import types

import pytest

from app.agent.orchestrator_requirements import layer2_semantic as l2
from app.agent.orchestrator_requirements.constants import (
    MIN_HISTORY_PROJECTS,
    MIN_HISTORY_WITH_FEATURES,
    MIN_VECTOR_RESULTS,
)


class _FakeVectorIndex:
    instance = None

    def __init__(self):
        self._count = 0
        self._results = []
        _FakeVectorIndex.instance = self

    def load_or_create(self):
        return True

    def total_count(self):
        return self._count

    async def search(self, requirement, top_k=10):
        return self._results


class _FakeMetadata:
    instance = None
    projects = []
    total = MIN_HISTORY_PROJECTS
    features = MIN_HISTORY_WITH_FEATURES
    raise_on_get = False

    def __init__(self):
        _FakeMetadata.instance = self

    def total_count(self):
        return self.total

    def count_with_features(self):
        return self.features

    def get_all_projects(self):
        if self.raise_on_get:
            raise RuntimeError("metadata down")
        return self.projects


@pytest.fixture
def fake_modules(monkeypatch):
    vi_module = types.ModuleType("app.agent.vector_index")
    vi_module.VectorIndexManager = _FakeVectorIndex
    md_module = types.ModuleType("app.agent.project_metadata")
    md_module.ProjectMetadataManager = _FakeMetadata
    monkeypatch.setitem(sys.modules, "app.agent.vector_index", vi_module)
    monkeypatch.setitem(sys.modules, "app.agent.project_metadata", md_module)
    _FakeVectorIndex.instance = None
    _FakeMetadata.instance = None
    _FakeMetadata.projects = []
    _FakeMetadata.total = MIN_HISTORY_PROJECTS
    _FakeMetadata.features = MIN_HISTORY_WITH_FEATURES
    _FakeMetadata.raise_on_get = False
    yield


@pytest.mark.asyncio
async def test_semantic_hits_return_items(fake_modules, monkeypatch):
    original_init = _FakeVectorIndex.__init__

    def _init(self):
        original_init(self)
        self._count = MIN_VECTOR_RESULTS
        self._results = [
            ({"project_id": "p1", "feature_list": ["登录", "报表"]}, 0.7),
            ({"project_id": "p2", "feature_list": []}, 0.9),
        ]

    monkeypatch.setattr(_FakeVectorIndex, "__init__", _init)
    items = await l2.layer2_semantic_match("需要登录")
    assert [i.content for i in items] == ["登录", "报表"]
    assert all(i.sub_category == "semantic_match" for i in items)
    assert all(item.confidence == pytest.approx(0.8) for item in items)


@pytest.mark.asyncio
async def test_semantic_fills_features_from_metadata(fake_modules, monkeypatch):
    original_init = _FakeVectorIndex.__init__

    def _init(self):
        original_init(self)
        self._count = MIN_VECTOR_RESULTS
        self._results = [({"project_id": "p1", "feature_list": []}, 0.5)]

    monkeypatch.setattr(_FakeVectorIndex, "__init__", _init)
    _FakeMetadata.projects = [
        {"project_id": "p1", "feature_list": ["用户管理"], "feature_source": "llm"}
    ]
    items = await l2.layer2_semantic_match("用户管理")
    assert [i.content for i in items] == ["用户管理"]


@pytest.mark.asyncio
async def test_semantic_metadata_lookup_failure_is_debug(fake_modules, monkeypatch):
    original_init = _FakeVectorIndex.__init__

    def _init(self):
        original_init(self)
        self._count = MIN_VECTOR_RESULTS
        self._results = [({"project_id": "p1", "feature_list": []}, 0.5)]

    monkeypatch.setattr(_FakeVectorIndex, "__init__", _init)
    _FakeMetadata.raise_on_get = True
    debug_messages = []
    monkeypatch.setattr(l2.logger, "debug", lambda msg, *a, **k: debug_messages.append(msg))

    items = await l2.layer2_semantic_match("用户管理")
    assert items == []
    assert any("语义搜索失败" in m for m in debug_messages)


@pytest.mark.asyncio
async def test_semantic_file_fallback_features_are_dropped(fake_modules, monkeypatch):
    original_init = _FakeVectorIndex.__init__

    def _init(self):
        original_init(self)
        self._count = MIN_VECTOR_RESULTS
        self._results = [
            (
                {
                    "project_id": "p1",
                    "feature_list": ["index.js"],
                    "feature_source": "file_fallback",
                },
                0.6,
            )
        ]

    monkeypatch.setattr(_FakeVectorIndex, "__init__", _init)
    assert await l2.layer2_semantic_match("x") == []


@pytest.mark.asyncio
async def test_semantic_empty_results_and_low_count_fall_back(fake_modules, monkeypatch):
    original_init = _FakeVectorIndex.__init__

    def _init(self):
        original_init(self)
        self._count = MIN_VECTOR_RESULTS - 1

    monkeypatch.setattr(_FakeVectorIndex, "__init__", _init)
    _FakeMetadata.projects = [
        {"requirement": "登录 注册", "feature_list": ["用户管理"], "similarity": 0.5}
    ]
    items = await l2.layer2_semantic_match("登录")
    assert [i.sub_category for i in items] == ["keyword_match"]

    def _init_empty(self):
        original_init(self)
        self._count = MIN_VECTOR_RESULTS
        self._results = []

    monkeypatch.setattr(_FakeVectorIndex, "__init__", _init_empty)
    assert await l2.layer2_semantic_match("登录") != []


@pytest.mark.asyncio
async def test_semantic_exception_falls_back(fake_modules, monkeypatch):
    def _boom(self):
        raise RuntimeError("faiss down")

    monkeypatch.setattr(_FakeVectorIndex, "load_or_create", _boom)
    _FakeMetadata.projects = [
        {"requirement": "支付", "feature_list": ["支付"], "similarity": 0.7}
    ]
    warn_messages = []
    monkeypatch.setattr(l2.logger, "warning", lambda msg, *a, **k: warn_messages.append(msg))
    items = await l2.layer2_semantic_match("支付")
    assert [i.content for i in items] == ["支付"]
    assert any("FAISS 语义检索异常" in m for m in warn_messages)


@pytest.mark.asyncio
async def test_keyword_fallback_below_min_projects(fake_modules):
    _FakeMetadata.total = MIN_HISTORY_PROJECTS - 1
    assert await l2.layer2_keyword_fallback("x") == []


@pytest.mark.asyncio
async def test_keyword_fallback_metadata_exception(fake_modules):
    _FakeMetadata.raise_on_get = True
    assert await l2.layer2_keyword_fallback("x") == []


@pytest.mark.asyncio
async def test_keyword_fallback_skips_file_fallback_projects(fake_modules):
    _FakeMetadata.projects = [
        {
            "requirement": "安全 登录",
            "feature_list": ["审计"],
            "feature_source": "file_fallback",
        },
        {"requirement": "安全 登录", "feature_list": ["认证"], "similarity": 0.8},
    ]
    items = await l2.layer2_keyword_fallback("安全 登录")
    assert [i.content for i in items] == ["认证"]
    # keyword_match_history 用实际重叠度覆盖了项目自带的 similarity
    assert items[0].confidence == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_keyword_fallback_limits_projects(fake_modules):
    _FakeMetadata.projects = [
        {"requirement": "登录", "feature_list": [f"f{i}"], "similarity": 0.9}
        for i in range(8)
    ]
    items = await l2.layer2_keyword_fallback("登录")
    assert len(items) == 5


def test_check_history_data_available_true(fake_modules):
    assert l2.check_history_data_available() is True


def test_check_history_data_available_insufficient(fake_modules):
    _FakeMetadata.total = MIN_HISTORY_PROJECTS
    _FakeMetadata.features = MIN_HISTORY_WITH_FEATURES - 1
    assert l2.check_history_data_available() is False


def test_check_history_data_available_exception(fake_modules, monkeypatch):
    def _boom(self):
        raise RuntimeError("db down")

    monkeypatch.setattr(_FakeMetadata, "total_count", _boom)
    debug_messages = []
    monkeypatch.setattr(l2.logger, "debug", lambda msg, *a, **k: debug_messages.append(msg))
    assert l2.check_history_data_available() is False
    assert any("检查历史项目数据失败" in m for m in debug_messages)


def test_keyword_match_history_scores_and_sorts():
    projects = [
        {"requirement": "用户登录 注册", "id": "a"},
        {"requirement": "完全无关", "id": "b"},
        {"requirement": "", "id": "c"},
    ]
    matched = l2.keyword_match_history("用户登录", projects)
    assert matched[0]["id"] == "a"
    assert matched[0]["similarity"] > 0.15
    assert all(item["similarity"] > 0.15 for item in matched)
    assert len(matched) <= 10


def test_keyword_match_history_caps_at_ten():
    projects = [{"requirement": "login"} for _ in range(20)]
    assert len(l2.keyword_match_history("login", projects)) == 10
