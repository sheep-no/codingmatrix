"""template_extractor 剩余分支补测。"""

import json

from app.agent import template_extractor as te_mod


def _project(features):
    return {"feature_list": features}


VALID_TEMPLATE = {
    "domain": "banking",
    "version": "auto_extracted",
    "core_modules": [{"name": "用户认证", "category": "core"}],
}


async def test_extract_template_skips_when_too_few_projects():
    extractor = te_mod.TemplateExtractor()
    assert await extractor.extract_template("banking", [_project(["登录"])] * 4) is None


async def test_extract_template_ignores_empty_feature_lists(monkeypatch):
    import app.utils as utils_mod

    async def call_llm(model=None, prompt=None, **kwargs):
        if "审核员" in prompt:
            return json.dumps({"approved": True, "reason": "ok"})
        return json.dumps(VALID_TEMPLATE)

    monkeypatch.setattr(utils_mod, "call_llm", call_llm)

    extractor = te_mod.TemplateExtractor()
    projects = [_project([]) for _ in range(3)] + [_project(["登录"]) for _ in range(4)]

    assert await extractor.extract_template("banking", projects) is None


async def test_extract_template_returns_none_when_primary_model_fails(monkeypatch):
    import app.utils as utils_mod

    async def failing_call_llm(**kwargs):
        raise RuntimeError("model down")

    monkeypatch.setattr(utils_mod, "call_llm", failing_call_llm)

    extractor = te_mod.TemplateExtractor()
    assert await extractor.extract_template("banking", [_project(["登录"])] * 5) is None


async def test_extract_template_returns_none_for_unparsable_response(monkeypatch):
    import app.utils as utils_mod

    async def call_llm(**kwargs):
        return "not json at all"

    monkeypatch.setattr(utils_mod, "call_llm", call_llm)

    extractor = te_mod.TemplateExtractor()
    assert await extractor.extract_template("banking", [_project(["登录"])] * 5) is None


async def test_extract_template_returns_none_when_review_rejects(monkeypatch):
    import app.utils as utils_mod

    async def call_llm(model=None, prompt=None, **kwargs):
        if "审核员" in prompt:
            return json.dumps({"approved": False, "reason": "太低质量"})
        return json.dumps(VALID_TEMPLATE)

    monkeypatch.setattr(utils_mod, "call_llm", call_llm)

    extractor = te_mod.TemplateExtractor()
    assert await extractor.extract_template("banking", [_project(["登录"])] * 5) is None


def test_parse_template_requires_core_modules():
    extractor = te_mod.TemplateExtractor()
    response = json.dumps({"domain": "banking", "core_modules": []})
    assert extractor._parse_template_response(response, "banking") is None


async def test_review_template_returns_rejection_on_exception(monkeypatch):
    import app.utils as utils_mod

    async def failing_call_llm(**kwargs):
        raise RuntimeError("review down")

    monkeypatch.setattr(utils_mod, "call_llm", failing_call_llm)

    extractor = te_mod.TemplateExtractor()
    result = await extractor._review_template(VALID_TEMPLATE)

    assert result == {"approved": False, "reason": "审核过程异常"}


async def test_review_template_returns_rejection_for_non_json(monkeypatch):
    import app.utils as utils_mod

    async def call_llm(**kwargs):
        return "审核通过"

    monkeypatch.setattr(utils_mod, "call_llm", call_llm)

    extractor = te_mod.TemplateExtractor()
    result = await extractor._review_template(VALID_TEMPLATE)

    assert result["approved"] is False


async def test_extract_template_saves_new_template(tmp_path, monkeypatch):
    import app.utils as utils_mod

    monkeypatch.setattr(te_mod, "DOMAIN_TEMPLATES_DIR", tmp_path)

    async def call_llm(model=None, prompt=None, **kwargs):
        if "审核员" in prompt:
            return json.dumps({"approved": True, "reason": "ok"})
        return json.dumps(VALID_TEMPLATE)

    monkeypatch.setattr(utils_mod, "call_llm", call_llm)

    extractor = te_mod.TemplateExtractor()
    result = await extractor.extract_template("banking", [_project(["登录"])] * 5)

    assert result is not None
    saved = json.loads((tmp_path / "banking.json").read_text(encoding="utf-8"))
    assert saved["core_modules"][0]["name"] == "用户认证"
