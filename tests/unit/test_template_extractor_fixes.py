"""template_extractor 回归：TE5（prompt f-string）、TE3（贪婪 JSON）、TE1（覆盖手工模板）、TE4（截断无标记）。"""

import json

import pytest


def _project(features):
    return {"feature_list": features}


VALID_TEMPLATE = {
    "domain": "banking",
    "version": "auto_extracted",
    "core_modules": [{"name": "用户认证", "category": "core"}],
    "non_functional_requirements": [{"category": "security", "item": "鉴权"}],
    "common_pitfalls": ["a", "b", "c"],
    "key_decisions": [{"question": "q"}],
}


class TestPromptRendering:
    """TE5: prompt 内 JSON 示例的花括号不得被 f-string 当表达式"""

    async def test_extract_prompt_renders(self, tmp_path, monkeypatch):
        import app.utils as utils_mod
        from app.agent import template_extractor as te_mod

        monkeypatch.setattr(te_mod, "DOMAIN_TEMPLATES_DIR", tmp_path)
        prompts = []

        async def fake_call_llm(model=None, prompt=None, **kwargs):
            prompts.append(prompt)
            if "审核员" in prompt:
                return json.dumps({"approved": True, "reason": "ok"})
            return json.dumps(VALID_TEMPLATE)

        monkeypatch.setattr(utils_mod, "call_llm", fake_call_llm)

        te = te_mod.TemplateExtractor()
        projects = [_project(["用户登录认证", "订单创建管理"]) for _ in range(5)]
        result = await te.extract_template("banking", projects)

        assert result is not None
        assert len(prompts) == 2
        extract_prompt, review_prompt = prompts
        assert '"core_modules"' in extract_prompt
        assert '"approved": true' in review_prompt

    async def test_review_prompt_renders(self, monkeypatch):
        import app.utils as utils_mod
        from app.agent import template_extractor as te_mod

        async def fake_call_llm(model=None, prompt=None, **kwargs):
            assert '"reason"' in prompt
            return '审核完成 {"approved": true, "reason": "ok"}'

        monkeypatch.setattr(utils_mod, "call_llm", fake_call_llm)
        te = te_mod.TemplateExtractor()
        result = await te._review_template(VALID_TEMPLATE)
        assert result["approved"] is True


class TestGreedyJsonParsing:
    """TE3: 多 JSON 块与解释文本不得使解析失败"""

    def test_multi_block_first_object(self, tmp_path, monkeypatch):
        from app.agent import template_extractor as te_mod

        monkeypatch.setattr(te_mod, "DOMAIN_TEMPLATES_DIR", tmp_path)
        te = te_mod.TemplateExtractor()
        response = (
            f'分析：{json.dumps(VALID_TEMPLATE)} '
            '补充：{"core_modules": [{"name": "另一个"}]}'
        )
        parsed = te._parse_template_response(response, "banking")
        assert parsed is not None
        assert parsed["core_modules"][0]["name"] == "用户认证"
        assert parsed["version"] == "auto_extracted"

    def test_explanatory_prefix_and_suffix(self, tmp_path, monkeypatch):
        from app.agent import template_extractor as te_mod

        monkeypatch.setattr(te_mod, "DOMAIN_TEMPLATES_DIR", tmp_path)
        te = te_mod.TemplateExtractor()
        response = f"如下：\n{json.dumps(VALID_TEMPLATE)}\n完成"
        parsed = te._parse_template_response(response, "banking")
        assert parsed is not None
        assert parsed["domain"] == "banking"

    def test_non_json_returns_none(self, tmp_path, monkeypatch):
        from app.agent import template_extractor as te_mod

        monkeypatch.setattr(te_mod, "DOMAIN_TEMPLATES_DIR", tmp_path)
        te = te_mod.TemplateExtractor()
        assert te._parse_template_response("无法输出模板", "banking") is None


class TestManualTemplateProtection:
    """TE1: 存在手工模板时不得覆盖 {domain}.json"""

    def test_manual_template_not_overwritten(self, tmp_path, monkeypatch):
        from app.agent import template_extractor as te_mod

        monkeypatch.setattr(te_mod, "DOMAIN_TEMPLATES_DIR", tmp_path)
        manual = {"domain": "banking", "version": "1.0", "description": "手工模板"}
        (tmp_path / "banking.json").write_text(
            json.dumps(manual, ensure_ascii=False), encoding="utf-8"
        )

        te = te_mod.TemplateExtractor()
        te._save_template(dict(VALID_TEMPLATE), "banking")

        kept = json.loads((tmp_path / "banking.json").read_text(encoding="utf-8"))
        assert kept["description"] == "手工模板"
        assert kept["version"] == "1.0"
        auto = json.loads((tmp_path / "banking_auto.json").read_text(encoding="utf-8"))
        assert auto["version"] == "auto_extracted"

    def test_auto_template_overwritten(self, tmp_path, monkeypatch):
        from app.agent import template_extractor as te_mod

        monkeypatch.setattr(te_mod, "DOMAIN_TEMPLATES_DIR", tmp_path)
        (tmp_path / "banking.json").write_text(
            json.dumps({"version": "auto_extracted", "old": True}), encoding="utf-8"
        )

        te = te_mod.TemplateExtractor()
        te._save_template(dict(VALID_TEMPLATE), "banking")

        saved = json.loads((tmp_path / "banking.json").read_text(encoding="utf-8"))
        assert saved["core_modules"][0]["name"] == "用户认证"
        assert not (tmp_path / "banking_auto.json").exists()


class TestTruncationMarker:
    """TE4: 功能清单截断需带标记"""

    async def test_truncation_note_present(self, tmp_path, monkeypatch):
        import app.utils as utils_mod
        from app.agent import template_extractor as te_mod

        monkeypatch.setattr(te_mod, "DOMAIN_TEMPLATES_DIR", tmp_path)
        captured = {}

        async def fake_call_llm(model=None, prompt=None, **kwargs):
            captured.setdefault("prompts", []).append(prompt)
            if "审核员" in prompt:
                return json.dumps({"approved": True, "reason": "ok"})
            return json.dumps(VALID_TEMPLATE)

        monkeypatch.setattr(utils_mod, "call_llm", fake_call_llm)

        te = te_mod.TemplateExtractor()
        features = [f"功能模块编号{i}" for i in range(300)]
        projects = [_project(features) for _ in range(5)]
        await te.extract_template("banking", projects)

        extract_prompt = captured["prompts"][0]
        assert "共 1500 条" in extract_prompt
        assert f"仅展示前 {te_mod.MAX_PROMPT_FEATURES} 条" in extract_prompt

    async def test_no_note_when_under_limit(self, tmp_path, monkeypatch):
        import app.utils as utils_mod
        from app.agent import template_extractor as te_mod

        monkeypatch.setattr(te_mod, "DOMAIN_TEMPLATES_DIR", tmp_path)
        captured = {}

        async def fake_call_llm(model=None, prompt=None, **kwargs):
            captured.setdefault("prompts", []).append(prompt)
            if "审核员" in prompt:
                return json.dumps({"approved": True, "reason": "ok"})
            return json.dumps(VALID_TEMPLATE)

        monkeypatch.setattr(utils_mod, "call_llm", fake_call_llm)

        te = te_mod.TemplateExtractor()
        projects = [_project(["用户登录认证"]) for _ in range(5)]
        await te.extract_template("banking", projects)

        assert "仅展示前" not in captured["prompts"][0]
