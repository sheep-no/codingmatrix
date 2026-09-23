"""project_metadata 解析加固回归：PM1（null/dict 崩溃）与 PM2（回退污染）。"""

import json

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
