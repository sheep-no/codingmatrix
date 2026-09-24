"""回归：language_detector LD2/LD4/LD5/LD8（扩展名规则、中文边界、TS 归一）。"""

import pytest

from app.agent.language_detector import LanguageDetector


class TestLanguageExtensionMap:
    """LD5: 一等语言不应因扩展名表缺项而要求澄清"""

    @pytest.mark.parametrize(
        ("language", "extension"),
        [("csharp", ".cs"), ("typescript", ".ts")],
    )
    def test_first_class_language_has_extension(self, language, extension):
        rules = LanguageDetector.get_language_specific_rules(language)

        assert rules["file_extension"] == extension
        assert not rules.get("needs_clarification")

    def test_unknown_language_still_requests_clarification(self):
        rules = LanguageDetector.get_language_specific_rules("brainfuck")

        assert rules["file_extension"] is None
        assert rules["needs_clarification"] is True


class TestExtensionStrategyChineseBoundary:
    """LD2: 扩展名紧贴中文时不应被 \\w 贪婪吞掉"""

    def test_extension_followed_by_chinese_is_recognized(self):
        # 'rs' 不是语言关键词，只可能由扩展名策略识出
        result = LanguageDetector.detect("处理 data.csv 和 main.rs文件")

        assert result.language == "rust"
        assert result.confidence == 0.85

    def test_extension_with_space_still_recognized(self):
        result = LanguageDetector.detect("please edit main.rs")

        assert result.language == "rust"


class TestLLMTypescriptNormalization:
    """LD4/LD8: LLM 返回 typescript 时归一为 javascript，而非被 valid 校验拒绝"""

    @pytest.mark.asyncio
    async def test_typescript_is_normalized_to_javascript(self, monkeypatch):
        async def fake_call_llm(prompt, system_prompt=None):
            return '{"primary_language": "typescript", "reasoning": "TS frontend"}'

        monkeypatch.setattr("app.utils.call_llm", fake_call_llm)

        result = await LanguageDetector._detect_with_llm("...", [])

        assert result is not None
        assert result.language == "javascript"
        assert result.adapter_name == "javascript"
        assert result.detection_method == "llm"

    @pytest.mark.asyncio
    async def test_ts_alias_is_normalized_to_javascript(self, monkeypatch):
        async def fake_call_llm(prompt, system_prompt=None):
            return '{"primary_language": "ts"}'

        monkeypatch.setattr("app.utils.call_llm", fake_call_llm)

        result = await LanguageDetector._detect_with_llm("...", [])

        assert result is not None
        assert result.language == "javascript"

    @pytest.mark.asyncio
    async def test_unknown_language_is_rejected(self, monkeypatch):
        async def fake_call_llm(prompt, system_prompt=None):
            return '{"primary_language": "cobol"}'

        monkeypatch.setattr("app.utils.call_llm", fake_call_llm)

        assert await LanguageDetector._detect_with_llm("...", []) is None
