"""传统生成链功能清单提取回归：TG1（f-string 花括号）与 TG2（文件内容映射）。"""


class TestFeaturePromptRendering:
    """TG1: prompt 的 JSON 示例花括号必须转义，否则每次调用抛 ValueError"""

    async def test_prompt_renders_and_features_parsed(self, tmp_path, monkeypatch):
        from app.agent import project_metadata as pm_mod
        import app.utils as utils_mod

        monkeypatch.setattr(pm_mod, "METADATA_PATH", tmp_path / "meta.json")
        calls = []

        async def fake_call_llm(model=None, prompt=None, **kwargs):
            calls.append(prompt)
            return '{"features": ["用户登录", "订单管理"]}'

        # _extract_feature_list 内部 `from app.utils import call_llm`，须补丁真实来源
        monkeypatch.setattr(utils_mod, "call_llm", fake_call_llm)

        pm = pm_mod.ProjectMetadataManager()
        features, source = await pm._extract_feature_list(
            "电商系统", {"a.py": "print(1)"}
        )

        assert features == ["用户登录", "订单管理"]
        assert source == "llm"
        assert calls, "应调用一次 LLM"
        prompt = calls[0]
        # 示例 JSON 应渲染为单个花括号，且文件摘要来自传入内容
        assert '{\n  "features": [' in prompt
        assert "a.py" in prompt


class TestFeatureExtractorFileMapping:
    """TG2: 调用方传入 {路径: 内容} 映射，不能因键名不匹配而丢空"""

    async def test_mapping_is_forwarded(self, monkeypatch):
        from app.agent.orchestrator_generation import feature_extractor as fe

        captured = {}

        class FakeManager:
            async def extract_and_save(self, requirement, files_dict, domain=""):
                captured["files"] = files_dict
                captured["domain"] = domain
                return {"feature_list": ["x"]}

            async def trigger_template_extraction(self, domain, min_projects=15):
                return None

        monkeypatch.setattr(
            "app.agent.project_metadata.ProjectMetadataManager", FakeManager
        )

        result = await fe.extract_and_save_feature_list(
            "电商系统", {"a.py": "print(1)", "b.py": "print(2)"}, domain="ecommerce"
        )

        assert result == {"feature_list": ["x"]}
        assert captured["files"] == {"a.py": "print(1)", "b.py": "print(2)"}
        assert captured["domain"] == "ecommerce"
