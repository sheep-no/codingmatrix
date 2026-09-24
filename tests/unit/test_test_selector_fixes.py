"""回归：test_selector TS1/TS2/TS4/TS5/TS6。"""

from pathlib import Path

from app.agent.impact_analyzer import ChangeSummary
from app.agent.project_profiler import ProjectProfile, RiskAreas, TestPatterns
from app.agent.test_selector import (
    TestSelector,
    _path_boundary_match,
    _test_source_stem,
)


def _make_project(root: Path, files):
    for rel in files:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")


def _profile(language="python", naming="test_*.py", risks=None) -> ProjectProfile:
    profile = ProjectProfile(language=language)
    profile.test_patterns = TestPatterns(test_location="tests/", naming_convention=naming)
    profile.risk_areas = RiskAreas(high_dependency=list(risks or []))
    return profile


class TestStemAndBoundaryHelpers:
    """TS1/TS2 辅助函数"""

    def test_test_source_stem_variants(self):
        assert _test_source_stem("test_foo.py") == "foo"
        assert _test_source_stem("foo_test.py") == "foo"
        assert _test_source_stem("foo.test.js") == "foo"
        assert _test_source_stem("foo.spec.ts") == "foo"
        assert _test_source_stem("foo_test.go") == "foo"
        assert _test_source_stem("FooTest.java") == "foo"
        assert _test_source_stem("FooIT.java") == "foo"

    def test_path_boundary_no_substring_false_positive(self):
        assert not _path_boundary_match("src/auth.py", "src/my_author.py")
        assert not _path_boundary_match("auth", "my_author")

    def test_path_boundary_matches_suffix(self):
        assert _path_boundary_match("src/auth.py", "src/auth.py")
        assert _path_boundary_match("auth.py", "src/auth.py")
        assert _path_boundary_match("src/pkg/bar.py", "src/pkg/bar.py")


class TestSameDirectoryLayer:
    """TS1: 同源文件关联测试不再恒空"""

    def test_flat_naming_prefix(self, tmp_path):
        _make_project(tmp_path, ["src/foo.py", "tests/test_foo.py", "tests/test_other.py"])
        selector = TestSelector(str(tmp_path))
        result = selector._select_same_directory_tests(["src/foo.py"], _profile())
        assert result == ["tests/test_foo.py"]

    def test_flat_naming_suffix(self, tmp_path):
        _make_project(tmp_path, ["src/foo.py", "tests/foo_test.py"])
        selector = TestSelector(str(tmp_path))
        result = selector._select_same_directory_tests(["src/foo.py"], _profile(naming="*_test.py"))
        assert result == ["tests/foo_test.py"]

    def test_mirrored_directory(self, tmp_path):
        _make_project(tmp_path, ["src/pkg/bar.py", "tests/pkg/test_bar.py"])
        selector = TestSelector(str(tmp_path))
        result = selector._select_same_directory_tests(["src/pkg/bar.py"], _profile())
        assert result == ["tests/pkg/test_bar.py"]

    def test_modified_test_file_selected_directly(self, tmp_path):
        _make_project(tmp_path, ["src/foo.py", "tests/test_foo.py"])
        selector = TestSelector(str(tmp_path))
        result = selector._select_same_directory_tests(["tests/test_foo.py"], _profile())
        assert result == ["tests/test_foo.py"]

    def test_unrelated_file_selects_nothing(self, tmp_path):
        _make_project(tmp_path, ["src/foo.py", "tests/test_other.py"])
        selector = TestSelector(str(tmp_path))
        result = selector._select_same_directory_tests(["src/foo.py"], _profile())
        assert result == []


class TestHighDependencyLayer:
    """TS2: 高风险命中按路径边界 + 只选相关测试"""

    def test_substring_false_positive_not_matched(self, tmp_path):
        _make_project(tmp_path, ["src/my_author.py", "tests/test_my_author.py"])
        selector = TestSelector(str(tmp_path))
        result = selector._select_high_dependency_tests(
            ChangeSummary(modified_files=["src/my_author.py"]),
            _profile(risks=["src/auth.py"]),
        )
        assert result == []

    def test_risk_match_selects_related_only(self, tmp_path):
        _make_project(
            tmp_path,
            ["src/auth.py", "tests/test_auth.py", "tests/test_unrelated.py"],
        )
        selector = TestSelector(str(tmp_path))
        result = selector._select_high_dependency_tests(
            ChangeSummary(modified_files=["src/auth.py"]),
            _profile(risks=["src/auth.py"]),
        )
        assert result == ["tests/test_auth.py"]

    def test_risk_match_expands_mirrored_subtree_only(self, tmp_path):
        _make_project(
            tmp_path,
            [
                "src/pkg/bar.py",
                "tests/pkg/test_bar.py",
                "tests/pkg/test_extra.py",
                "tests/test_top_level.py",
            ],
        )
        selector = TestSelector(str(tmp_path))
        result = selector._select_high_dependency_tests(
            ChangeSummary(modified_files=["src/pkg/bar.py"]),
            _profile(risks=["src/pkg/bar.py"]),
        )
        assert set(result) == {"tests/pkg/test_bar.py", "tests/pkg/test_extra.py"}
        assert "tests/test_top_level.py" not in result


class TestMultilanguageAndSmoke:
    """TS4/TS5/TS6"""

    def test_javascript_naming_recognized(self, tmp_path):
        _make_project(tmp_path, ["src/foo.js", "tests/foo.test.js"])
        selector = TestSelector(str(tmp_path))
        result = selector._select_same_directory_tests(
            ["src/foo.js"], _profile(language="javascript", naming="*.test.js")
        )
        assert result == ["tests/foo.test.js"]

    def test_go_naming_recognized(self, tmp_path):
        _make_project(tmp_path, ["src/foo.go", "tests/foo_test.go"])
        selector = TestSelector(str(tmp_path))
        result = selector._select_same_directory_tests(
            ["src/foo.go"], _profile(language="go", naming="*_test.go")
        )
        assert result == ["tests/foo_test.go"]

    def test_custom_smoke_keywords(self, tmp_path):
        _make_project(tmp_path, ["tests/test_smoke.py", "tests/test_happy_path.py"])
        selector = TestSelector(str(tmp_path), smoke_keywords=["happy"])
        result = selector._select_smoke_tests(_profile())
        assert result == ["tests/test_happy_path.py"]

    def test_smoke_layer_does_not_top_up(self, tmp_path):
        _make_project(tmp_path, ["tests/test_smoke.py", "tests/test_other.py"])
        selector = TestSelector(str(tmp_path))
        result = selector._select_smoke_tests(_profile())
        assert result == ["tests/test_smoke.py"]

    def test_select_tests_returns_minimal_subset(self, tmp_path):
        _make_project(
            tmp_path,
            [
                "src/foo.py",
                "tests/test_foo.py",
                "tests/test_smoke.py",
                "tests/test_unrelated.py",
            ],
        )
        selector = TestSelector(str(tmp_path))
        result = selector.select_tests(ChangeSummary(modified_files=["src/foo.py"]), _profile())
        assert set(result) == {"tests/test_foo.py", "tests/test_smoke.py"}
        assert "tests/test_unrelated.py" not in result

    def test_fallback_to_all_when_nothing_matched(self, tmp_path):
        _make_project(tmp_path, ["src/foo.py", "tests/test_other.py"])
        selector = TestSelector(str(tmp_path))
        result = selector.select_tests(ChangeSummary(modified_files=["src/foo.py"]), _profile())
        assert result == ["tests/test_other.py"]
