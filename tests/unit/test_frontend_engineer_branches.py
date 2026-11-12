"""FrontendEngineer 全分支回归：提示词加载、规格约束、生成与分析方法。"""

import pytest

from app.agent import frontend_engineer as fe


def _engineer():
    return object.__new__(fe.FrontendEngineer)


class _Heartbeat:
    def __init__(self):
        self.touches = 0

    def touch(self):
        self.touches += 1


@pytest.fixture
def stub_engineer(monkeypatch):
    engineer = _engineer()
    prompts = []

    async def _call_llm(prompt, system_prompt):
        prompts.append((prompt, system_prompt))
        return "generated"

    async def _call_llm_with_tools(prompt, system_prompt, **kwargs):
        prompts.append((prompt, system_prompt))
        prompts.append(kwargs)
        return "generated-with-tools"

    engineer.call_llm = _call_llm
    engineer.call_llm_with_tools = _call_llm_with_tools
    engineer._prompts = prompts
    return engineer


def test_system_prompt_prefers_registry(monkeypatch):
    engineer = _engineer()
    import app.services.skill_registry as registry

    monkeypatch.setattr(registry, "get_skill", lambda name: "custom prompt")
    assert engineer.SYSTEM_PROMPT == "custom prompt"


def test_system_prompt_registry_failure_falls_back_to_loader(monkeypatch):
    engineer = _engineer()
    import app.services.skill_registry as registry

    def _boom(name):
        raise RuntimeError("registry down")

    monkeypatch.setattr(registry, "get_skill", _boom)
    monkeypatch.setattr(fe, "load_frontend_engineer_prompt", lambda: "loaded prompt")
    assert engineer.SYSTEM_PROMPT == "loaded prompt"


def test_system_prompt_loader_none_uses_fallback(monkeypatch):
    engineer = _engineer()
    import app.services.skill_registry as registry

    monkeypatch.setattr(registry, "get_skill", lambda name: None)
    monkeypatch.setattr(fe, "load_frontend_engineer_prompt", lambda: None)
    assert "世界级前端工程师" in engineer.SYSTEM_PROMPT


@pytest.mark.parametrize(
    "path,expected",
    [
        ("public/index.html", "template"),
        ("legacy/page.htm", "template"),
        ("src/styles/theme.less", "frontend_style"),
        ("src\\pages\\home.tsx", "frontend_page"),
        ("src/styles/main.scss", "frontend_style"),
        ("src/tests/button.spec.ts", "test"),
        ("src/components/Button.vue", "frontend_component"),
        ("src/unknown/file.vue", "frontend_component"),
        ("README.md", "unknown"),
        ("src/utils/helper.ts", "frontend_component"),
    ],
)
def test_infer_file_type(path, expected):
    assert fe.FrontendEngineer._infer_file_type_from_path(path) == expected


def test_build_spec_constraints_empty_spec_returns_empty():
    assert fe.FrontendEngineer._build_spec_constraints("page", {}) == ""


def test_build_spec_constraints_storage_variants():
    local = fe.FrontendEngineer._build_spec_constraints(
        "page", {"storage": {"type": "localStorage"}}
    )
    assert "localStorage" in local

    backend = fe.FrontendEngineer._build_spec_constraints(
        "page", {"storage": {"type": "sqlite"}}
    )
    assert "后端存储方式" in backend

    defaulted = fe.FrontendEngineer._build_spec_constraints("page", {"storage": {}})
    assert defaulted == ""

    custom = fe.FrontendEngineer._build_spec_constraints(
        "page", {"storage": {"type": "indexedDB"}}
    )
    assert "indexedDB" in custom
    assert "禁止直接使用" not in custom


def test_build_spec_constraints_terminology():
    text = fe.FrontendEngineer._build_spec_constraints(
        "page", {"terminology": {"user": "成员"}}
    )
    assert "术语约束" in text
    assert "user -> 成员" in text


@pytest.mark.asyncio
async def test_generate_file_uses_scaffold(monkeypatch, stub_engineer):
    import app.agent.adapters as adapters

    captured = {}

    def _scaffold(file_path, planned_type, architecture):
        captured["args"] = (file_path, planned_type, architecture)
        return "// scaffold"

    monkeypatch.setattr(
        adapters.LanguageAdapterRegistry, "scaffold_file", classmethod(lambda cls, *a: _scaffold(*a))
    )
    monkeypatch.setattr(fe, "compact_project_context_for_file", lambda path, ctx: "ctx")

    context = {
        "architecture": {
            "language": "typescript",
            "file_plan": [{"path": "src/pages/Home.tsx", "file_type": "frontend_page"}],
        }
    }
    result = await stub_engineer.generate_file(
        "src\\pages\\Home.tsx", "home", context, is_existing_file=False
    )
    assert result == "// scaffold"
    assert captured["args"][0] == "src\\pages\\Home.tsx"
    assert captured["args"][1] == "frontend_page"
    assert stub_engineer._prompts == []


@pytest.mark.asyncio
async def test_generate_file_scaffold_skipped_for_existing_file(monkeypatch, stub_engineer):
    import app.agent.adapters as adapters

    called = []
    monkeypatch.setattr(
        adapters.LanguageAdapterRegistry,
        "scaffold_file",
        classmethod(lambda cls, *a: called.append(a) or "// scaffold"),
    )
    monkeypatch.setattr(fe, "compact_project_context_for_file", lambda path, ctx: "ctx")

    result = await stub_engineer.generate_file(
        "src/pages/Home.tsx",
        "home",
        {"architecture": {"language": "typescript"}},
        is_existing_file=True,
    )
    assert result == "generated"
    assert called == []


@pytest.mark.asyncio
async def test_generate_file_merges_requirement_into_architecture(
    monkeypatch, stub_engineer
):
    import app.agent.adapters as adapters

    captured = {}

    def _scaffold(file_path, planned_type, architecture):
        captured["architecture"] = architecture
        return None

    monkeypatch.setattr(
        adapters.LanguageAdapterRegistry,
        "scaffold_file",
        classmethod(lambda cls, *a: _scaffold(*a)),
    )
    monkeypatch.setattr(fe, "compact_project_context_for_file", lambda path, ctx: "ctx")
    await stub_engineer.generate_file(
        "src/App.tsx",
        "app",
        {"architecture": {"language": "typescript"}, "requirement": "用户需求"},
    )
    assert captured["architecture"]["requirement"] == "用户需求"


@pytest.mark.asyncio
async def test_generate_file_scaffold_none_falls_through(monkeypatch, stub_engineer):
    import app.agent.adapters as adapters

    monkeypatch.setattr(
        adapters.LanguageAdapterRegistry,
        "scaffold_file",
        classmethod(lambda cls, *a: None),
    )
    monkeypatch.setattr(fe, "compact_project_context_for_file", lambda path, ctx: "ctx")

    result = await stub_engineer.generate_file(
        "src/pages/Home.tsx", "home", {"architecture": {"language": "typescript"}}
    )
    assert result == "generated"


@pytest.mark.asyncio
async def test_generate_file_new_file_prompt_branches(monkeypatch, stub_engineer):
    import app.agent.adapters as adapters

    monkeypatch.setattr(
        adapters.LanguageAdapterRegistry,
        "scaffold_file",
        classmethod(lambda cls, *a: None),
    )
    monkeypatch.setattr(fe, "compact_project_context_for_file", lambda path, ctx: "ctx")

    await stub_engineer.generate_file(
        "src/pages/home.tsx",
        "home",
        {"architecture": {"language": "typescript"}},
        spec_context="spec",
        dep_context="dep",
    )
    prompt = stub_engineer._prompts[0][0]
    assert "本文件的契约" in prompt
    assert "相关规范" in prompt
    assert "已生成依赖文件" in prompt
    assert "请创建以下文件" in prompt

    stub_engineer._prompts.clear()
    await stub_engineer.generate_file(
        "src/__init__.py",
        "pkg",
        {"architecture": {"language": "python"}},
    )
    assert "这是一个包入口文件" in stub_engineer._prompts[0][0]


@pytest.mark.asyncio
async def test_generate_file_frozen_contract_and_exploration(monkeypatch, stub_engineer):
    import app.agent.adapters as adapters

    monkeypatch.setattr(
        adapters.LanguageAdapterRegistry,
        "scaffold_file",
        classmethod(lambda cls, *a: None),
    )
    monkeypatch.setattr(fe, "compact_project_context_for_file", lambda path, ctx: "ctx")

    context = {
        "architecture": {"language": "typescript", "requirement": "req"},
        "requirement": "outer",
        "generation_contract": {"files": []},
    }
    await stub_engineer.generate_file("src/App.tsx", "app", context)
    prompt = stub_engineer._prompts[0][0]
    assert "冻结生成契约" in prompt
    assert "冻结文件集合" in prompt


@pytest.mark.asyncio
async def test_generate_file_modification_prompt_variants(monkeypatch, stub_engineer):
    import app.agent.adapters as adapters

    monkeypatch.setattr(
        adapters.LanguageAdapterRegistry,
        "scaffold_file",
        classmethod(lambda cls, *a: None),
    )
    monkeypatch.setattr(fe, "compact_project_context_for_file", lambda path, ctx: "ctx")

    context = {
        "architecture": {"language": "javascript"},
        "original_content": "const a = 1;",
        "modification_reason": "修复",
    }
    await stub_engineer.generate_file(
        "src/app.js", "app", context, is_existing_file=True
    )
    prompt = stub_engineer._prompts[0][0]
    assert "请修改以下已有文件" in prompt
    assert "修复" in prompt
    assert "partial_update" in prompt

    stub_engineer._prompts.clear()
    context["generation_contract"] = {}
    await stub_engineer.generate_file(
        "src/app.js", "app", context, is_existing_file=True
    )
    assert "直接返回修改后的" in stub_engineer._prompts[0][0]


@pytest.mark.asyncio
async def test_generate_file_existing_without_reason_uses_description(
    monkeypatch, stub_engineer
):
    import app.agent.adapters as adapters

    monkeypatch.setattr(
        adapters.LanguageAdapterRegistry,
        "scaffold_file",
        classmethod(lambda cls, *a: None),
    )
    monkeypatch.setattr(fe, "compact_project_context_for_file", lambda path, ctx: "ctx")

    await stub_engineer.generate_file(
        "src/app.js",
        "补充登录",
        {"architecture": {"language": "javascript"}},
        is_existing_file=True,
    )
    assert "本文件修改原因：补充登录" in stub_engineer._prompts[0][0]


@pytest.mark.asyncio
async def test_generate_file_with_project_path_uses_tools(monkeypatch, stub_engineer):
    import app.agent.adapters as adapters

    monkeypatch.setattr(
        adapters.LanguageAdapterRegistry,
        "scaffold_file",
        classmethod(lambda cls, *a: None),
    )
    monkeypatch.setattr(fe, "compact_project_context_for_file", lambda path, ctx: "ctx")
    heartbeat = _Heartbeat()

    result = await stub_engineer.generate_file(
        "src/App.tsx",
        "app",
        {"architecture": {"language": "typescript"}},
        project_path="/tmp/project",
        heartbeat_tracker=heartbeat,
    )
    assert result == "generated-with-tools"
    kwargs = stub_engineer._prompts[1]
    assert set(kwargs["tools"]) <= {
        "read_file",
        "list_files",
        "read_symbols",
        "read_imports",
        "summarize_file",
        "search_files",
    }
    assert heartbeat.touches == 2


@pytest.mark.asyncio
async def test_generate_file_unknown_language_falls_back_to_project_language(
    monkeypatch, stub_engineer
):
    import app.agent.adapters as adapters
    import app.agent.utils as agent_utils

    monkeypatch.setattr(
        adapters.LanguageAdapterRegistry,
        "scaffold_file",
        classmethod(lambda cls, *a: None),
    )
    monkeypatch.setattr(fe, "compact_project_context_for_file", lambda path, ctx: "ctx")
    monkeypatch.setattr(
        agent_utils, "get_expected_language_for_file", lambda path, lang: None
    )
    await stub_engineer.generate_file(
        "src/App.tsx", "app", {"architecture": {"language": "typescript"}}
    )
    assert "此文件的语言：typescript" in stub_engineer._prompts[0][0]


@pytest.mark.asyncio
async def test_analyze_with_context_and_files(stub_engineer):
    heartbeat = _Heartbeat()
    result = await stub_engineer.analyze(
        "如何改进？",
        "/tmp/project",
        project_context={"architecture": {"language": "vue"}},
        heartbeat_tracker=heartbeat,
    )
    assert result == "generated"
    prompt = stub_engineer._prompts[0][0]
    assert "项目主语言: vue" in prompt
    assert heartbeat.touches == 2


@pytest.mark.asyncio
async def test_analyze_without_project_path_or_context(stub_engineer):
    result = await stub_engineer.analyze("问题", "")
    assert result == "generated"
    prompt = stub_engineer._prompts[0][0]
    assert "项目主语言" not in prompt
    assert "\n项目文件结构:\n" not in prompt


@pytest.mark.asyncio
async def test_analyze_file_listing_failure_is_logged(stub_engineer, monkeypatch):
    import app.agent.tools as tools

    async def _noop():
        return None

    monkeypatch.setitem(
        tools.SPECIALIST_TOOLS,
        "list_files",
        {"fn": lambda **kwargs: (_ for _ in ()).throw(RuntimeError("list down"))},
    )
    warnings = []
    monkeypatch.setattr(
        fe.logger, "warning", lambda msg, *a, **k: warnings.append(msg)
    )

    result = await stub_engineer.analyze("问题", "/tmp/project")
    assert result == "generated"
    assert any("获取文件列表失败" in w for w in warnings)


@pytest.mark.asyncio
async def test_analyze_without_list_files_tool(stub_engineer, monkeypatch):
    import app.agent.tools as tools

    monkeypatch.delitem(tools.SPECIALIST_TOOLS, "list_files", raising=False)
    result = await stub_engineer.analyze("问题", "/tmp/project")
    assert result == "generated"
    assert "\n项目文件结构:\n" not in stub_engineer._prompts[0][0]


@pytest.mark.asyncio
async def test_analyze_empty_file_listing(stub_engineer, monkeypatch):
    import app.agent.tools as tools

    monkeypatch.setitem(
        tools.SPECIALIST_TOOLS, "list_files", {"fn": lambda **kwargs: {"entries": []}}
    )
    result = await stub_engineer.analyze("问题", "/tmp/project")
    assert result == "generated"
    assert "\n项目文件结构:\n" not in stub_engineer._prompts[0][0]


@pytest.mark.asyncio
async def test_analyze_none_listing_and_populated_listing(stub_engineer, monkeypatch):
    import app.agent.tools as tools

    monkeypatch.setitem(tools.SPECIALIST_TOOLS, "list_files", {"fn": lambda **kwargs: None})
    await stub_engineer.analyze("问题", "/tmp/project")
    assert "\n项目文件结构:\n" not in stub_engineer._prompts[0][0]

    stub_engineer._prompts.clear()
    monkeypatch.setitem(
        tools.SPECIALIST_TOOLS,
        "list_files",
        {"fn": lambda **kwargs: {"entries": [{"path": "src/App.vue"}]}},
    )
    await stub_engineer.analyze("问题", "/tmp/project")
    assert "src/App.vue" in stub_engineer._prompts[0][0]
