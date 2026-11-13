"""补齐 LanguageDetector 的边界分支（冲突提示、项目类型、中文模式、全栈后端、LLM 同步封装）。"""

import asyncio

import pytest

from app.agent.language_detector import LanguageDetector


class TestConflictEvidence:
    def test_keyword_conflict_appends_evidence(self):
        # "android" 命中 kotlin 关键词，同时出现 ruby 关键词 → 记录冲突但仍返回 kotlin
        result = LanguageDetector.detect("android 应用，以及 ruby gem")

        assert result.language == "kotlin"
        assert any("检测到冲突" in item for item in result.evidence)

    def test_conflict_with_other_framework(self):
        conflict = LanguageDetector._check_language_conflict("django 项目", "rust")

        assert conflict is not None
        assert "django" in conflict

    def test_conflict_with_other_keyword(self):
        conflict = LanguageDetector._check_language_conflict("使用 ruby 写脚本", "kotlin")

        assert conflict is not None
        assert "ruby" in conflict

    def test_no_conflict_returns_none(self):
        assert LanguageDetector._check_language_conflict("django 项目", "python") is None


class TestProjectTypeFallback:
    def test_project_type_default_language(self):
        result = LanguageDetector.detect("做一个好用的工具", project_type="cli")

        assert result.language == "python"
        assert result.confidence == 0.60
        assert any("项目类型默认" in item for item in result.evidence)

    def test_unknown_project_type_falls_through(self):
        result = LanguageDetector.detect("做一个好用的工具", project_type="unknown")

        assert result.confidence == 0.30


class TestChinesePatterns:
    def test_unknown_ascii_language_needs_clarification(self):
        result = LanguageDetector.detect("用 brainfuck 写")

        assert result.language == "brainfuck"
        assert result.adapter_name == "generic"
        assert result.needs_clarification is True
        assert result.confidence == 0.40

    def test_known_extension_language_no_clarification(self):
        # 强制「中文模式」命中：把已知语言从关键词表中移出，仍保留在扩展名表
        original = LanguageDetector.LANGUAGE_KEYWORDS
        LanguageDetector.LANGUAGE_KEYWORDS = {"zig": ["zig-lang"]}
        try:
            result = LanguageDetector.detect("用 nim 写")
        finally:
            LanguageDetector.LANGUAGE_KEYWORDS = original

        assert result.language == "nim"
        assert result.needs_clarification is False
        assert result.confidence == 0.70
        assert any("已知语言" in item for item in result.evidence)

    def test_known_language_via_chinese_pattern(self):
        # 语言名在关键词表键中，但关键词列表不含它 → 走中文模式的高置信分支
        original = LanguageDetector.LANGUAGE_KEYWORDS
        LanguageDetector.LANGUAGE_KEYWORDS = {"cobol": ["cobol-lang"]}
        try:
            result = LanguageDetector.detect("用 cobol 写")
        finally:
            LanguageDetector.LANGUAGE_KEYWORDS = original

        assert result.language == "cobol"
        assert result.confidence == 0.70
        assert any("中文模式推断" in item for item in result.evidence)

    def test_non_ascii_group_scans_next_pattern(self):
        result = LanguageDetector.detect("用 中文 写 一个 xyz 程序")

        assert result.language == "xyz"
        assert result.needs_clarification is True

    def test_no_pattern_uses_python_default(self):
        result = LanguageDetector.detect("帮我做个东西")

        assert result.language == "python"
        assert result.confidence == 0.30
        assert any("默认" in item for item in result.evidence)


class TestFullstackBackendDetection:
    @pytest.mark.parametrize(
        ("requirement", "backend", "expected_fullstack"),
        [
            ("react 前端 加上 django", "python", True),
            ("react 前端 加上 express", "javascript", False),
            ("react 前端 加上 spring", "java", True),
            ("react 前端 加上 gin", "go", True),
        ],
    )
    def test_backend_framework_language(self, requirement, backend, expected_fullstack):
        fullstack, frontend_lang, backend_lang = LanguageDetector._detect_fullstack_languages(requirement)

        assert frontend_lang == "javascript"
        assert backend_lang == backend
        assert fullstack is expected_fullstack

    def test_backend_alias_js(self):
        _, _, backend = LanguageDetector._detect_fullstack_languages("前端 vue，后端用 js")

        assert backend == "javascript"

    def test_backend_alias_golang(self):
        _, _, backend = LanguageDetector._detect_fullstack_languages("前端 vue，后端用 golang")

        assert backend == "go"

    def test_chinese_backend_marker_with_language_suffix(self):
        _, _, backend = LanguageDetector._detect_fullstack_languages("后端是 python")

        assert backend == "python"

    def test_backend_marker_for_frontend_only_does_not_set_backend(self):
        _, _, backend = LanguageDetector._detect_fullstack_languages("前端用 react")

        assert backend is None

    def test_fullstack_different_languages(self):
        fullstack, frontend, backend = LanguageDetector._detect_fullstack_languages(
            "react 前端 + 后端用 python"
        )

        assert fullstack is True
        assert frontend == "javascript"
        assert backend == "python"


class TestSyncLLMWrapper:
    def test_without_running_loop(self, monkeypatch):
        async def fake_detect(requirement, evidence):
            return "ok"

        monkeypatch.setattr(LanguageDetector, "_detect_with_llm", fake_detect)

        assert LanguageDetector._detect_with_llm_sync("req", []) == "ok"

    def test_with_running_loop_uses_thread(self, monkeypatch):
        async def fake_detect(requirement, evidence):
            return "threaded"

        monkeypatch.setattr(LanguageDetector, "_detect_with_llm", fake_detect)

        async def caller():
            return LanguageDetector._detect_with_llm_sync("req", [])

        assert asyncio.run(caller()) == "threaded"

    def test_exception_returns_none(self, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("loop unavailable")

        monkeypatch.setattr("asyncio.get_event_loop", boom)

        assert LanguageDetector._detect_with_llm_sync("req", []) is None


class TestLLMResponseParsing:
    async def test_empty_response_returns_none(self, monkeypatch):
        async def fake_call_llm(prompt, system_prompt=None):
            return "   "

        monkeypatch.setattr("app.utils.call_llm", fake_call_llm)

        assert await LanguageDetector._detect_with_llm("req", []) is None

    async def test_invalid_json_returns_none(self, monkeypatch):
        async def fake_call_llm(prompt, system_prompt=None):
            return "not a json payload"

        monkeypatch.setattr("app.utils.call_llm", fake_call_llm)

        assert await LanguageDetector._detect_with_llm("req", []) is None

    async def test_json_without_braces_parsed(self, monkeypatch):
        async def fake_call_llm(prompt, system_prompt=None):
            return '{"primary_language": "python", "reasoning": "default"}'

        monkeypatch.setattr("app.utils.call_llm", fake_call_llm)

        result = await LanguageDetector._detect_with_llm("req", [])

        assert result is not None
        assert result.language == "python"

    async def test_alias_js_maps_to_javascript(self, monkeypatch):
        async def fake_call_llm(prompt, system_prompt=None):
            return '{"primary_language": "nodejs", "reasoning": "web"}'

        monkeypatch.setattr("app.utils.call_llm", fake_call_llm)

        result = await LanguageDetector._detect_with_llm("req", [])

        assert result is not None
        assert result.language == "javascript"

    async def test_unknown_language_returns_none(self, monkeypatch):
        async def fake_call_llm(prompt, system_prompt=None):
            return '{"primary_language": "cobol", "reasoning": "legacy"}'

        monkeypatch.setattr("app.utils.call_llm", fake_call_llm)

        assert await LanguageDetector._detect_with_llm("req", []) is None

    async def test_parsing_exception_returns_none(self, monkeypatch):
        async def fake_call_llm(prompt, system_prompt=None):
            return "[1, 2, 3]"

        monkeypatch.setattr("app.utils.call_llm", fake_call_llm)

        assert await LanguageDetector._detect_with_llm("req", []) is None
