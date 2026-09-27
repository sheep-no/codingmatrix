"""vector_index 相关阻塞 I/O 回归：索引/元数据读写不得卡住事件循环。"""

import json
import threading
import types


class _FakeIndex:
    def __init__(self):
        self.ntotal = 0

    def add(self, vec):
        self.ntotal += 1


async def test_build_from_metadata_reads_off_event_loop(monkeypatch, tmp_path):
    from app.agent import vector_index as vi_mod

    monkeypatch.setattr(vi_mod, "VECTOR_INDEX_DIR", tmp_path / "vi")
    monkeypatch.setattr(vi_mod, "METADATA_PATH", tmp_path / "meta.json")
    (tmp_path / "meta.json").write_text(
        json.dumps(
            [{"project_id": "p1", "feature_list": ["a"], "feature_source": "llm"}]
        ),
        encoding="utf-8",
    )

    async def fake_embedding(text):
        return [0.0] * vi_mod.EMBEDDING_DIM

    monkeypatch.setattr("app.utils.AiCodeUtil.get_embedding", fake_embedding)
    monkeypatch.setattr(
        vi_mod, "faiss", types.SimpleNamespace(normalize_L2=lambda v: v)
    )

    loop_thread = threading.get_ident()
    seen = []
    real_load = json.load

    def spy_load(fp):
        seen.append(threading.get_ident())
        return real_load(fp)

    monkeypatch.setattr(vi_mod.json, "load", spy_load)

    manager = vi_mod.VectorIndexManager()
    manager._create_empty_index = lambda: None
    manager._index = _FakeIndex()
    manager._save_index = lambda: None

    await manager.build_from_metadata()

    assert seen, "json.load 应被调用"
    assert loop_thread not in seen, "元数据读取不得在事件循环线程执行"


async def test_add_project_saves_off_event_loop(monkeypatch, tmp_path):
    from app.agent import vector_index as vi_mod

    monkeypatch.setattr(vi_mod, "VECTOR_INDEX_DIR", tmp_path / "vi")

    async def fake_embedding(text):
        return [0.0] * vi_mod.EMBEDDING_DIM

    monkeypatch.setattr("app.utils.AiCodeUtil.get_embedding", fake_embedding)
    monkeypatch.setattr(
        vi_mod, "faiss", types.SimpleNamespace(normalize_L2=lambda v: v)
    )

    loop_thread = threading.get_ident()
    seen = []

    def spy_save():
        seen.append(threading.get_ident())

    manager = vi_mod.VectorIndexManager()
    manager._index = _FakeIndex()
    manager._loaded = True
    manager._save_index = spy_save

    ok = await manager.add_project(
        {"project_id": "p1", "feature_list": ["a"], "feature_source": "llm"}
    )

    assert ok is True
    assert seen, "_save_index 应被调用"
    assert loop_thread not in seen, "索引写入不得在事件循环线程执行"


async def test_layer2_load_or_create_off_event_loop(monkeypatch):
    from app.agent.orchestrator_requirements import layer2_semantic as l2

    loop_thread = threading.get_ident()
    seen = []

    class _Recorder:
        def load_or_create(self):
            seen.append(threading.get_ident())

        def total_count(self):
            return 0

    monkeypatch.setattr(
        "app.agent.vector_index.VectorIndexManager", lambda: _Recorder()
    )

    async def fake_fallback(requirement):
        return []

    monkeypatch.setattr(l2, "layer2_keyword_fallback", fake_fallback)

    await l2.layer2_semantic_match("实现登录")

    assert seen, "load_or_create 应被调用"
    assert loop_thread not in seen, "索引加载不得在事件循环线程执行"


async def test_extract_and_save_loads_index_off_event_loop(monkeypatch, tmp_path):
    import app.utils as utils_mod
    from app.agent import project_metadata as pm_mod

    monkeypatch.setattr(pm_mod, "METADATA_PATH", tmp_path / "meta.json")

    loop_thread = threading.get_ident()
    seen = []

    class _Recorder:
        def load_or_create(self):
            seen.append(threading.get_ident())

        async def add_project(self, project):
            return True

    monkeypatch.setattr(
        "app.agent.vector_index.VectorIndexManager", lambda: _Recorder()
    )

    async def fake_call_llm(model=None, prompt=None, **kwargs):
        return '{"features": ["用户登录认证"]}'

    monkeypatch.setattr(utils_mod, "call_llm", fake_call_llm)

    pm = pm_mod.ProjectMetadataManager()
    await pm.extract_and_save("电商", {"a.py": "x"}, domain="ecommerce")

    assert seen, "load_or_create 应被调用"
    assert loop_thread not in seen, "索引加载不得在事件循环线程执行"
