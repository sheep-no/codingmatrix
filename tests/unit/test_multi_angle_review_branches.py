"""多角度审查全分支回归。"""

from types import SimpleNamespace

import pytest

from app.agent import multi_angle_review as mr
from app.agent.orchestrator_requirements.data_models import AssociationItem


def _item(content="c", confidence=0.8, category="functional"):
    return AssociationItem(
        content=content,
        category=category,
        source="x",
        confidence=confidence,
    )


class _CallLLM:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    async def __call__(self, model, prompt):
        self.calls.append((model, prompt))
        if self.error:
            raise self.error
        return self.response


def _patch_llm(monkeypatch, response=None, error=None):
    fake = _CallLLM(response=response, error=error)
    import app.utils as utils

    monkeypatch.setattr(utils, "call_llm", fake)
    return fake


@pytest.mark.asyncio
async def test_multi_angle_requires_architect_and_items():
    assert await mr.multi_angle_review("req", [_item()]) == []


@pytest.mark.asyncio
async def test_multi_angle_requires_enough_items():
    items = [_item(), _item()]
    assert await mr.multi_angle_review("req", items, architect=object()) == []


@pytest.mark.asyncio
async def test_multi_angle_without_high_confidence_items():
    items = [_item(confidence=0.1) for _ in range(4)]
    assert await mr.multi_angle_review("req", items, architect=object()) == []


@pytest.mark.asyncio
async def test_multi_angle_light_skips_review(monkeypatch):
    called = []
    monkeypatch.setattr(
        mr, "devil_advocate_review", lambda *a, **k: called.append(1)
    )
    items = [_item() for _ in range(3)]
    result = await mr.multi_angle_review(
        "req", items, severity=mr.ReviewSeverity.LIGHT, architect=object()
    )
    assert result == []
    assert called == []


@pytest.mark.asyncio
async def test_multi_angle_standard_uses_devil(monkeypatch):
    async def _devil(requirement, items, architect):
        return [{"role": "devil_advocate"}]

    monkeypatch.setattr(mr, "devil_advocate_review", _devil)
    items = [_item() for _ in range(3)]
    result = await mr.multi_angle_review(
        "req", items, severity=mr.ReviewSeverity.STANDARD, architect=object()
    )
    assert result == [{"role": "devil_advocate"}]


@pytest.mark.asyncio
async def test_multi_angle_strict_uses_parallel(monkeypatch):
    async def _parallel(requirement, items):
        return [{"role": "performance"}]

    monkeypatch.setattr(mr, "parallel_multi_review", _parallel)
    items = [_item() for _ in range(3)]
    result = await mr.multi_angle_review(
        "req", items, severity=mr.ReviewSeverity.STRICT, architect=object()
    )
    assert result == [{"role": "performance"}]


@pytest.mark.asyncio
async def test_multi_angle_unknown_severity_returns_empty():
    items = [_item() for _ in range(3)]
    assert await mr.multi_angle_review("req", items, severity="other", architect=object()) == []


def test_load_prompt_reads_existing_file(tmp_path, monkeypatch):
    (tmp_path / "p.md").write_text("hello", encoding="utf-8")
    monkeypatch.setattr(mr, "_SKILLS_DIR", tmp_path)
    assert mr._load_prompt("p.md") == "hello"


def test_load_prompt_falls_back_to_default(tmp_path, monkeypatch):
    monkeypatch.setattr(mr, "_SKILLS_DIR", tmp_path)
    prompt = mr._load_prompt("performance_reviewer_prompt.md")
    assert "性能工程师" in prompt


def test_get_default_prompt_unknown_returns_empty():
    assert mr._get_default_prompt("missing.md") == ""


@pytest.mark.asyncio
async def test_parallel_multi_review_merges_and_limits(monkeypatch):
    responses = {
        "performance": '{"reviews": [{"target": "t", "issue": "i"}]}',
        "security": '{"reviews": [{"target": "t", "vulnerability": "v"}]}',
        "maintainability": RuntimeError("down"),
    }
    calls = []

    async def _fake_role(role_name, system_prompt, requirement, items_summary):
        calls.append(role_name)
        value = responses[role_name]
        if isinstance(value, Exception):
            raise value
        return mr.parse_multi_review_response(value, role_name)

    monkeypatch.setattr(mr, "_review_with_role", _fake_role)
    items = [_item(content=f"c{i}") for i in range(20)]
    result = await mr.parallel_multi_review("req", items)
    assert len(result) == 2
    assert {r["role"] for r in result} == {"性能师", "安全师"}
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_parallel_multi_review_exception_result_skipped(monkeypatch):
    async def _fake_role(role_name, **kwargs):
        if role_name == "performance":
            raise RuntimeError("boom")
        return []

    monkeypatch.setattr(mr, "_review_with_role", _fake_role)
    result = await mr.parallel_multi_review("req", [_item() for _ in range(3)])
    assert result == []


@pytest.mark.asyncio
async def test_review_with_role_success(monkeypatch):
    fake = _patch_llm(
        monkeypatch, '{"reviews": [{"target": "t", "issue": "i"}]}'
    )
    result = await mr._review_with_role("performance", "sys", "req", "summary")
    assert result[0]["role"] == "性能师"
    assert fake.calls[0][0] == mr.DEVILS_ADVOCATE_MODEL


@pytest.mark.asyncio
async def test_review_with_role_error(monkeypatch):
    _patch_llm(monkeypatch, error=RuntimeError("down"))
    assert await mr._review_with_role("security", "sys", "req", "s") == []


@pytest.mark.parametrize(
    "response,expected",
    [
        ("no json", 0),
        ('{"reviews": []}', 0),
        ("not json at all", 0),
        (
            '{"reviews": [{"target": "t"}, {"target": "t2", "issue": "i"}]}',
            1,
        ),
    ],
)
def test_parse_multi_review_response_variants(response, expected):
    assert len(mr.parse_multi_review_response(response, "security")) == expected


def test_parse_multi_review_response_caps_ten():
    reviews = ",".join(
        '{"target": "t", "issue": "i"}' for _ in range(15)
    )
    result = mr.parse_multi_review_response(f'{{"reviews": [{reviews}]}}', "security")
    assert len(result) == 10


def test_parse_multi_review_response_invalid_json():
    assert mr.parse_multi_review_response("{not: valid}", "security") == []


@pytest.mark.asyncio
async def test_devil_advocate_review_success(monkeypatch):
    fake = _patch_llm(
        monkeypatch, '{"reviews": [{"target": "t", "issue": "i"}]}'
    )
    result = await mr.devil_advocate_review("req", [_item() for _ in range(3)])
    assert result[0]["role"] == "devil_advocate"
    assert fake.calls


@pytest.mark.asyncio
async def test_devil_advocate_review_no_low_confidence_summary():
    items = [_item(confidence=0.1)]
    assert await mr.devil_advocate_review("req", items) == []


@pytest.mark.asyncio
async def test_devil_advocate_review_llm_error(monkeypatch):
    _patch_llm(monkeypatch, error=RuntimeError("down"))
    assert await mr.devil_advocate_review("req", [_item()]) == []


@pytest.mark.parametrize(
    "response,expected",
    [
        ("no json", 0),
        ('{"reviews": [{"target": "t"}]}', 0),
        ('{"reviews": [{"target": "t", "issue": "i"}]}', 1),
        ("{bad json}", 0),
    ],
)
def test_parse_devil_response_variants(response, expected):
    assert len(mr.parse_devil_response(response)) == expected


def test_parse_devil_response_caps_ten():
    reviews = ",".join('{"target": "t", "issue": "i"}' for _ in range(12))
    assert len(mr.parse_devil_response(f'{{"reviews": [{reviews}]}}')) == 10


def test_reload_prompts(tmp_path, monkeypatch):
    (tmp_path / "performance_reviewer_prompt.md").write_text("perf")
    (tmp_path / "security_reviewer_prompt.md").write_text("sec")
    (tmp_path / "maintainability_reviewer_prompt.md").write_text("maint")
    monkeypatch.setattr(mr, "_SKILLS_DIR", tmp_path)
    mr.reload_prompts()
    assert mr.PERFORMANCE_SYS_PROMPT == "perf"
    assert mr.SECURITY_SYS_PROMPT == "sec"
    assert mr.MAINTAINABILITY_SYS_PROMPT == "maint"
