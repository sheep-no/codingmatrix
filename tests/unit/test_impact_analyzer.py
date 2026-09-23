"""ImpactAnalyzer 缺陷修复回归（IA1 / IA4 / IA5 / IA7）与消费方 OT16。

IA1: 新旧同名符号同时出现在 new_symbols 与 modified_symbols。
IA4: _has_dynamic_imports 用子串匹配（getattr( / 注释）产生假阳性。
IA5: ast.AsyncFunctionDef 未纳入符号提取。
IA7: 无 old_versions 时把既有符号当作「新增」。
OT16: orchestrator_testing._select_tests 无参构造 ImpactAnalyzer/TestSelector，
      TypeError 被 except 吞掉，智能测试选择恒回退全量。
"""
from pathlib import Path

import pytest

from app.agent.impact_analyzer import ChangeSummary, ImpactAnalyzer
from app.agent.orchestrator_testing import TestingMixin


def _write(root: Path, name: str, content: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestSymbolDiff:
    def test_modified_symbol_not_duplicated_in_new(self, tmp_path):
        """IA1: 新旧同名符号只应出现在 modified，不应同时算作 new。"""
        _write(tmp_path, "util.py", "def helper():\n    pass\n\nclass Foo:\n    pass\n")
        analyzer = ImpactAnalyzer(str(tmp_path))

        summary = analyzer.analyze(
            ["util.py"],
            old_versions={"util.py": "def helper():\n    pass\n"},
        )

        assert summary.modified_symbols == ["helper"]
        assert "helper" not in summary.new_symbols
        assert summary.new_symbols == ["Foo"]
        assert summary.removed_symbols == []

    def test_without_baseline_no_new_symbol_claims(self, tmp_path):
        """IA7: 没有旧版本时不应声称「新增」。"""
        _write(tmp_path, "util.py", "class Foo:\n    pass\n")
        analyzer = ImpactAnalyzer(str(tmp_path))

        summary = analyzer.analyze(["util.py"])

        assert summary.new_symbols == []
        assert summary.modified_symbols == []
        assert summary.modified_files == ["util.py"]

    def test_async_function_extracted(self, tmp_path):
        """IA5: async def 也应被提取为函数符号。"""
        _write(tmp_path, "svc.py", "async def fetch():\n    pass\n")
        analyzer = ImpactAnalyzer(str(tmp_path))

        summary = analyzer.analyze(
            ["svc.py"], old_versions={"svc.py": "# empty\n"}
        )

        assert summary.new_symbols == ["fetch"]


class TestDynamicImports:
    def test_dynamic_import_detected(self):
        analyzer = ImpactAnalyzer(".")
        assert analyzer._has_dynamic_imports("import importlib\nimportlib.import_module('x')\n")
        assert analyzer._has_dynamic_imports("mod = __import__('os')\n")

    def test_getattr_reflection_not_flagged(self):
        """IA4: 普通 getattr 反射不应算动态导入。"""
        analyzer = ImpactAnalyzer(".")
        assert not analyzer._has_dynamic_imports("x = getattr(obj, 'y')\n")

    def test_comment_mention_not_flagged(self):
        analyzer = ImpactAnalyzer(".")
        assert not analyzer._has_dynamic_imports("# __import__ is dangerous\n")

    def test_non_python_content_not_flagged(self):
        analyzer = ImpactAnalyzer(".")
        assert not analyzer._has_dynamic_imports("body { color: red; }\n")


class _Stub(TestingMixin):
    def __init__(self, output_dir):
        self.output_dir = Path(output_dir)


class _Patterns:
    test_location = "tests"
    naming_convention = "test_*.py"


class _Risk:
    high_dependency = []
    security_critical = []


class _Profile:
    test_patterns = _Patterns()
    risk_areas = _Risk()


class TestSelectTestsWiring:
    @pytest.mark.asyncio
    async def test_select_tests_runs_with_real_collaborators(self, tmp_path):
        """OT16: 无参构造会让 ImpactAnalyzer/TestSelector 抛 TypeError 被吞，
        智能测试选择恒回退全量。用真实协作对象跑通，选中同目录测试。"""
        _write(tmp_path, "a.py", "def run():\n    pass\n")
        _write(tmp_path, "tests/test_a.py", "def test_a():\n    pass\n")

        stub = _Stub(tmp_path)
        result = await stub._select_tests(["a.py"], project_profile=_Profile())

        assert "tests/test_a.py" in result
