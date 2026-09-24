"""project_metadata 解析加固回归：PM1（null/dict 崩溃）与 PM2（回退污染）。"""

import json
import types

import pytest


@pytest.fixture
def pm(tmp_path, monkeypatch):
    from app.agent import project_metadata as pm_mod

    monkeypatch.setattr(pm_mod, "METADATA_PATH", tmp_path / "meta.json")
    return pm_mod.ProjectMetadataManager()


class TestParseJsonValidation:
    """PM1: features 非列表时不得抛 TypeError 或静默返回空"""

    def test_features_null_falls_back_to_text(self, pm):
        # 旧实现 parsed.get("features", []) 返回 None → for 迭代抛 TypeError
        assert pm._parse_feature_response('{"features": null}') == []

    def test_features_dict_falls_back_to_text(self, pm):
        # 旧实现迭代 dict 得到 keys，isinstance 过滤后静默返回 []
        assert pm._parse_feature_response('{"features": {"a": 1}}') == []

    def test_features_scalar_falls_back_to_text(self, pm):
        assert pm._parse_feature_response('{"features": "登录"}') == []

    def test_features_list_still_parsed(self, pm):
        response = json.dumps({"features": ["用户登录认证", "订单创建管理"]})
        assert pm._parse_feature_response(response) == ["用户登录认证", "订单创建管理"]

    def test_empty_features_list_is_valid(self, pm):
        features, source = pm._parse_features_with_source('{"features": []}')
        assert features == []
        assert source == "llm"


class TestMultiBlockExtraction:
    """PM2a: 多 JSON 块不得把整段原文当功能项"""

    def test_first_json_block_wins(self, pm):
        response = (
            '结果 {"features": ["用户登录认证"]} '
            '补充 {"features": ["订单创建管理"]}'
        )
        assert pm._parse_feature_response(response) == ["用户登录认证"]

    def test_json_original_not_emitted_as_feature(self, pm):
        # 无有效列表时，文本回退不得输出含花括号的 JSON 原文
        features = pm._parse_feature_response('{"features": null}')
        assert not any("{" in f or "[" in f for f in features)

    def test_leading_text_then_json(self, pm):
        response = '分析如下：\n{"features": ["用户登录认证", "商品浏览搜索"]}\n完成'
        assert pm._parse_feature_response(response) == ["用户登录认证", "商品浏览搜索"]


class TestFeatureSourceMarking:
    """PM2b: 降级伪功能需带来源标记，且不计入有效功能项目数"""

    def test_count_excludes_file_fallback(self, pm):
        pm._projects = [
            {"project_id": "p1", "feature_list": ["真实功能"], "feature_source": "llm"},
            {"project_id": "p2", "feature_list": ["auth 模块"], "feature_source": "file_fallback"},
            {"project_id": "p3", "feature_list": ["旧数据无来源"]},
        ]
        assert pm.count_with_features() == 2

    async def test_extract_and_save_records_source(self, pm, monkeypatch):
        import app.utils as utils_mod

        async def fake_call_llm(model=None, prompt=None, **kwargs):
            return '{"features": ["用户登录认证"]}'

        monkeypatch.setattr(utils_mod, "call_llm", fake_call_llm)
        monkeypatch.setattr(
            "app.agent.vector_index.VectorIndexManager", lambda: _NoopIndex()
        )

        result = await pm.extract_and_save("电商", {"a.py": "x"}, domain="ecommerce")
        assert result["feature_source"] == "llm"
        assert result["feature_list"] == ["用户登录认证"]

    async def test_extract_and_save_marks_file_fallback(self, pm, monkeypatch):
        import app.utils as utils_mod

        async def boom(*args, **kwargs):
            raise RuntimeError("模型不可用")

        monkeypatch.setattr(utils_mod, "call_llm", boom)
        monkeypatch.setattr(
            "app.agent.vector_index.VectorIndexManager", lambda: _NoopIndex()
        )

        result = await pm.extract_and_save(
            "电商", {"app/user_service.py": "x"}, domain="ecommerce"
        )
        assert result["feature_source"] == "file_fallback"
        assert result["feature_list"] == ["user_service 模块"]


class _NoopIndex:
    def load_or_create(self):
        return None

    async def add_project(self, project):
        return True


class TestSummarizeTruncation:
    """PM4: 截断需带标记"""

    def test_content_truncation_marked(self, pm):
        summary = pm._summarize_files({"a.py": "x" * 500})
        assert "a.py" in summary
        assert "内容已截断" in summary

    def test_short_content_not_marked(self, pm):
        summary = pm._summarize_files({"a.py": "print(1)"})
        assert "内容已截断" not in summary

    def test_many_files_marked(self, pm):
        files = {f"f{i}.py": "x" for i in range(60)}
        summary = pm._summarize_files(files)
        assert "共 60 个文件" in summary


class TestAtomicSave:
    """PM3: 落盘需原子，且并发追加不能互相覆盖"""

    def test_save_leaves_no_temp_files(self, pm, tmp_path):
        pm._projects = [{"project_id": "p1", "feature_list": ["a"]}]
        pm._save()

        assert json.loads((tmp_path / "meta.json").read_text(encoding="utf-8")) == pm._projects
        assert list(tmp_path.glob(".project_metadata.*.tmp")) == []

    def test_concurrent_appends_keep_all_projects(self, pm, monkeypatch, tmp_path):
        import threading

        # 每个线程用独立 manager 实例模拟真实消费方各自 new 的场景
        from app.agent import project_metadata as pm_mod

        monkeypatch.setattr(pm_mod, "METADATA_PATH", tmp_path / "meta.json")

        def worker(index):
            manager = pm_mod.ProjectMetadataManager()
            manager._append_and_save({"project_id": f"p{index}", "feature_list": ["x"]})

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        saved = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
        assert {p["project_id"] for p in saved} == {f"p{i}" for i in range(20)}

    def test_failed_write_keeps_previous_file(self, pm, tmp_path, monkeypatch):
        pm._projects = [{"project_id": "p1"}]
        pm._save()
        original = (tmp_path / "meta.json").read_text(encoding="utf-8")

        def boom(*args, **kwargs):
            raise RuntimeError("dump failed")

        monkeypatch.setattr(json, "dump", boom)
        with pytest.raises(RuntimeError):
            pm._save()

        assert (tmp_path / "meta.json").read_text(encoding="utf-8") == original
        assert list(tmp_path.glob(".project_metadata.*.tmp")) == []


class TestVectorIndexFallbackFilter:
    """PM2 后续: file_fallback 伪功能不得进入向量索引被语义检索命中"""

    def _manager(self, monkeypatch, tmp_path):
        from app.agent import vector_index as vi_mod

        monkeypatch.setattr(vi_mod, "VECTOR_INDEX_DIR", tmp_path / "vi")
        return vi_mod.VectorIndexManager()

    async def test_add_project_skips_file_fallback(self, monkeypatch, tmp_path):
        manager = self._manager(monkeypatch, tmp_path)
        called = []

        async def fake_embedding(text):
            called.append(text)
            return [0.0] * 768

        monkeypatch.setattr("app.utils.AiCodeUtil.get_embedding", fake_embedding)
        project = {
            "project_id": "p1",
            "feature_list": ["user_service 模块"],
            "feature_source": "file_fallback",
        }
        assert await manager.add_project(project) is False
        # 短路发生在 embedding 之前，不得为伪功能计算向量
        assert called == []

    def test_should_index_only_blocks_file_fallback(self, monkeypatch, tmp_path):
        from app.agent.vector_index import VectorIndexManager

        assert VectorIndexManager._should_index({"feature_source": "file_fallback"}) is False
        assert VectorIndexManager._should_index({"feature_source": "llm"}) is True
        assert VectorIndexManager._should_index({}) is True

    async def test_build_from_metadata_skips_file_fallback(self, monkeypatch, tmp_path):
        from app.agent import vector_index as vi_mod

        monkeypatch.setattr(vi_mod, "VECTOR_INDEX_DIR", tmp_path / "vi")
        monkeypatch.setattr(vi_mod, "METADATA_PATH", tmp_path / "meta.json")
        (tmp_path / "meta.json").write_text(
            json.dumps([
                {"project_id": "real", "feature_list": ["真实"], "feature_source": "llm"},
                {"project_id": "fake", "feature_list": ["伪功能"], "feature_source": "file_fallback"},
            ]),
            encoding="utf-8",
        )

        manager = vi_mod.VectorIndexManager()
        indexed_ids = []

        async def fake_embedding(text):
            return [0.0] * vi_mod.EMBEDDING_DIM

        class _FakeIndex:
            ntotal = 0

            def add(self, vec):
                indexed_ids.append(len(indexed_ids))

        monkeypatch.setattr("app.utils.AiCodeUtil.get_embedding", fake_embedding)
        # CI 环境未安装 faiss，build_from_metadata 会调用 faiss.normalize_L2
        monkeypatch.setattr(vi_mod, "faiss", types.SimpleNamespace(normalize_L2=lambda v: v))
        manager._create_empty_index = lambda: None
        manager._index = _FakeIndex()
        manager._save_index = lambda: None

        await manager.build_from_metadata()
        assert [entry["project_id"] for entry in manager._id_map.values()] == ["real"]
