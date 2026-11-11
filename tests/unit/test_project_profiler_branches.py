import json
import logging
import time

import pytest

from app.agent.project_profiler import (
    ArchitectureInfo,
    LANGUAGE_PROFILES,
    ProjectProfile,
    ProjectProfiler,
    RiskAreas,
    TestPatterns,
    _make_import_pattern,
    detect_project_language,
)


def _profiler(root, language="python"):
    return ProjectProfiler(str(root), language=language)


def _write(root, relative, content=""):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TestSourceEnumeration:
    def test_only_language_extensions_are_returned(self, tmp_path):
        _write(tmp_path, "app.py", "x = 1\n")
        _write(tmp_path, "notes.txt", "ignored\n")
        _write(tmp_path, "web.ts", "export const x = 1\n")
        profiler = _profiler(tmp_path)
        assert [path.name for path in profiler._iter_source_files(tmp_path)] == ["app.py"]

    def test_skip_dirs_and_hidden_dirs_are_pruned(self, tmp_path):
        _write(tmp_path, "keep.py", "x = 1\n")
        for name in ("node_modules", "__pycache__", "venv", ".git", ".hidden"):
            _write(tmp_path, f"{name}/skip.py", "x = 1\n")
        profiler = _profiler(tmp_path)
        assert [path.name for path in profiler._iter_source_files(tmp_path)] == ["keep.py"]

    def test_hidden_project_root_does_not_hide_all_files(self, tmp_path):
        project = tmp_path / ".hidden-root"
        _write(project, "app.py", "x = 1\n")
        profiler = _profiler(project)
        assert profiler._count_source_files(project) == 1

    def test_count_source_files(self, tmp_path):
        _write(tmp_path, "a.py")
        _write(tmp_path, "pkg/b.py")
        _write(tmp_path, "pkg/c.txt")
        assert _profiler(tmp_path)._count_source_files(tmp_path) == 2


class TestTestFileAndDirMatching:
    @pytest.mark.parametrize("name", ["test_a.py", "a_test.py"])
    def test_python_test_files(self, tmp_path, name):
        assert _profiler(tmp_path)._is_test_file(tmp_path / name) is True

    @pytest.mark.parametrize("name", ["contest.py", "testing.py", "a_test.pyc"])
    def test_non_test_files(self, tmp_path, name):
        assert _profiler(tmp_path)._is_test_file(tmp_path / name) is False

    @pytest.mark.parametrize("name", ["a.test.js", "a.spec.ts", "a.spec.tsx"])
    def test_javascript_test_files(self, tmp_path, name):
        assert _profiler(tmp_path, "javascript")._is_test_file(tmp_path / name) is True

    def test_go_and_java_test_files(self, tmp_path):
        assert _profiler(tmp_path, "go")._is_test_file(tmp_path / "a_test.go") is True
        assert _profiler(tmp_path, "java")._is_test_file(tmp_path / "FooTest.java") is True
        assert _profiler(tmp_path, "java")._is_test_file(tmp_path / "FooIT.java") is True

    @pytest.mark.parametrize(
        ("language", "dirname", "expected"),
        [
            ("python", "tests", True),
            ("python", "Test", True),
            ("python", "contest", False),
            ("javascript", "__tests__", True),
            ("javascript", "spec", True),
        ],
    )
    def test_test_dirs_use_exact_names(self, tmp_path, language, dirname, expected):
        assert _profiler(tmp_path, language)._is_test_dir(f"/x/{dirname}") is expected


class TestArchitectureDetection:
    def test_layered_directories_are_detected(self, tmp_path):
        for name in ("api", "services", "repositories", "models"):
            _write(tmp_path, f"{name}/mod.py", "x = 1\n")
        arch = _profiler(tmp_path)._analyze_architecture(tmp_path)
        assert arch.pattern == "layered"
        assert set(arch.layers) == {"api", "service", "repository", "model"}

    def test_token_boundaries_avoid_substring_false_positives(self, tmp_path):
        for name in ("rapid", "capital", "metadata", "capitalize"):
            _write(tmp_path, f"{name}/mod.py", "x = 1\n")
        arch = _profiler(tmp_path)._analyze_architecture(tmp_path)
        assert arch.layers == {}
        assert arch.pattern == "unknown"

    def test_plural_and_singular_directory_names_match(self, tmp_path):
        _write(tmp_path, "controllers/mod.py", "x = 1\n")
        _write(tmp_path, "service/mod.py", "x = 1\n")
        layers = _profiler(tmp_path)._detect_layers(tmp_path)
        assert layers["api"] == ["controllers"]
        assert layers["service"] == ["service"]

    def test_python_mixins_are_collected_and_capped(self, tmp_path):
        for index in range(25):
            _write(
                tmp_path,
                f"mixin_{index}.py",
                f"class Feature{index}Mixin:\n    pass\n",
            )
        mixins = _profiler(tmp_path)._detect_python_mixins(tmp_path)
        assert len(mixins) == 20
        assert all("Mixin" in entry for entry in mixins)

    def test_invalid_python_file_is_skipped(self, tmp_path):
        _write(tmp_path, "broken.py", "class :\n")
        assert _profiler(tmp_path)._detect_python_mixins(tmp_path) == []

    def test_javascript_architecture_skips_mixin_scan(self, tmp_path):
        _write(tmp_path, "component.js", "class FooMixin {}\n")
        arch = _profiler(tmp_path, "javascript")._analyze_architecture(tmp_path)
        assert arch.aggregate_classes == []
        assert arch.language == "javascript"

    @pytest.mark.parametrize(
        ("language", "relative", "content", "expected"),
        [
            ("python", "pkg/__init__.py", "from .a import b\nimport os\n", True),
            ("python", "pkg/__init__.py", "from .a import b\nVALUE = 1\n", False),
            ("python", "pkg/__init__.py", "class Foo:\n    pass\n", False),
            ("python", "pkg/__init__.py", "not valid python !!\n", False),
            ("python", "pkg/__init__.py", "", False),
            ("javascript", "pkg/index.js", "import a from './a'\nexport { b } from './b'\n", True),
            ("javascript", "pkg/index.js", "// comment\nexport * from './a'\n", True),
            ("javascript", "pkg/index.js", "import a from './a'\nconst b = 1\n", False),
            ("javascript", "pkg/index.js", "", False),
            ("rust", "src/mod.rs", "pub mod a;\nmod b;\n", True),
            ("rust", "src/mod.rs", "fn main() {}\n", False),
        ],
    )
    def test_export_module_detection(self, tmp_path, language, relative, content, expected):
        _write(tmp_path, relative, content)
        modules = _profiler(tmp_path, language)._detect_export_modules(tmp_path)
        assert (relative in modules) is expected

    def test_go_and_java_have_no_export_modules(self, tmp_path):
        _write(tmp_path, "src/index.js", "export const x = 1\n")
        assert _profiler(tmp_path, "go")._detect_export_modules(tmp_path) == []
        assert _profiler(tmp_path, "java")._detect_export_modules(tmp_path) == []

    def test_mixin_plus_layered_keeps_layered_pattern(self, tmp_path):
        _write(tmp_path, "api/mod.py", "class ApiMixin:\n    pass\n")
        arch = _profiler(tmp_path)._analyze_architecture(tmp_path)
        assert arch.pattern == "layered"
        assert arch.aggregate_classes


class TestImportCounting:
    def test_python_imports_are_counted_for_project_modules(self, tmp_path):
        _write(tmp_path, "helpers.py", "x = 1\n")
        for index in range(6):
            _write(tmp_path, f"use_{index}.py", "import helpers\nfrom helpers import x\n")
        counts = _profiler(tmp_path)._count_imports(tmp_path)
        assert counts["helpers"] == 12

    def test_external_and_stdlib_imports_are_ignored(self, tmp_path):
        _write(tmp_path, "use.py", "import os\nimport flask\nfrom json import loads\n")
        assert _profiler(tmp_path)._count_imports(tmp_path) == {}

    def test_relative_imports_resolve_to_package_paths(self, tmp_path):
        _write(tmp_path, "pkg/__init__.py", "")
        _write(tmp_path, "pkg/helpers.py", "x = 1\n")
        for index in range(6):
            _write(
                tmp_path,
                f"pkg/use_{index}.py",
                "from .helpers import x\nfrom . import sibling\n",
            )
        counts = _profiler(tmp_path)._count_imports(tmp_path)
        assert counts["pkg.helpers"] == 6
        assert "pkg" not in counts

    def test_relative_import_outside_root_is_ignored(self, tmp_path):
        nested = tmp_path / "a"
        _write(nested, "mod.py", "from ...outside import x\n")
        assert _profiler(nested)._count_imports(nested) == {}

    def test_relative_import_non_python_keeps_module(self, tmp_path):
        profiler = _profiler(tmp_path, "javascript")
        assert profiler._resolve_relative_module("./a", tmp_path / "b.js", tmp_path) == "./a"

    @pytest.mark.parametrize(
        ("language", "line", "expected_group"),
        [
            ("javascript", "import x from 'mod-a'", "mod-a"),
            ("javascript", "const x = require('mod-b')", "mod-b"),
            ("go", '\t"example.com/pkg"', "example.com/pkg"),
            ("rust", "use crate::thing;", "crate::thing"),
            ("java", "import com.example.Foo;", "com.example.Foo"),
            ("unknown", 'import "fallback-mod"', "fallback-mod"),
        ],
    )
    def test_import_patterns_by_language(self, language, line, expected_group):
        match = _make_import_pattern(language).match(line)
        assert match
        assert expected_group in match.groups()

    def test_high_dependency_threshold_and_cap(self, tmp_path):
        modules = [f"mod_{index}" for index in range(25)]
        for module in modules:
            _write(tmp_path, f"{module}.py", "x = 1\n")
        files = []
        for index in range(6):
            files.append("\n".join(f"import {module}" for module in modules))
        for index, content in enumerate(files):
            _write(tmp_path, f"consumer_{index}.py", content + "\n")
        risks = _profiler(tmp_path)._analyze_risk_areas(tmp_path)
        assert len(risks.high_dependency) == 20
        assert risks.high_dependency[0] == "mod_0.py"

    @pytest.mark.parametrize(
        ("language", "module", "expected"),
        [
            ("python", "", False),
            ("python", "/abs/path", True),
            ("python", "./relative", True),
            ("python", "os.path", False),
            ("python", None, False),
            ("javascript", "node:fs", False),
            ("javascript", "fs/promises", False),
            ("go", "net/http", False),
            ("rust", "std::io", False),
            ("java", "org.springframework.web", False),
            ("java", "com.example.Service", True),
        ],
    )
    def test_project_module_detection(self, tmp_path, language, module, expected):
        assert _profiler(tmp_path, language)._is_project_module(module, tmp_path) is expected

    def test_python_project_module_without_root_trusts_name(self, tmp_path):
        assert _profiler(tmp_path)._is_project_module("anything") is True

    @pytest.mark.parametrize(
        ("language", "module", "expected"),
        [
            ("python", "app.utils", "app/utils.py"),
            ("javascript", "src/app", "src/app.js"),
            ("go", "example.com/pkg", "example.com/pkg"),
            ("rust", "crate::a", "src/crate/a.rs"),
            ("java", "com.example.Foo", "com/example/Foo.java"),
            ("python", "raw", "raw.py"),
        ],
    )
    def test_module_to_filename(self, tmp_path, language, module, expected):
        profiler = _profiler(tmp_path, language)
        assert profiler._module_to_filename(module) == expected


class TestRiskScanning:
    def test_security_and_database_keywords_split_files(self, tmp_path):
        _write(tmp_path, "auth.py", "def login(token):\n    return token\n")
        _write(tmp_path, "store.py", "query = 'select 1'\n")
        _write(tmp_path, "plain.py", "value = 1\n")
        risks = _profiler(tmp_path)._analyze_risk_areas(tmp_path)
        assert risks.security_critical == ["auth.py"]
        assert risks.data_critical == ["store.py"]

    def test_unreadable_file_is_skipped(self, tmp_path, monkeypatch):
        _write(tmp_path, "a.py", "x = 1\n")
        profiler = _profiler(tmp_path)

        real_open = open

        def fake_open(path, *args, **kwargs):
            if str(path).endswith("a.py"):
                raise OSError("boom")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", fake_open)
        assert profiler._analyze_risk_areas(tmp_path).high_dependency == []


class TestTestPatterns:
    def test_python_prefix_wins_naming_convention(self, tmp_path):
        _write(tmp_path, "tests/test_one.py", "def test():\n    pass\n")
        _write(tmp_path, "tests/test_two.py", "def test():\n    pass\n")
        _write(tmp_path, "tests/three_test.py", "def test():\n    pass\n")
        patterns = _profiler(tmp_path)._analyze_test_patterns(tmp_path)
        assert patterns.test_location == "tests"
        assert patterns.naming_convention == "test_*.py"
        assert patterns.fixture_usage is False

    def test_python_suffix_wins_when_more_common(self, tmp_path):
        _write(tmp_path, "tests/a_test.py", "")
        _write(tmp_path, "tests/b_test.py", "")
        _write(tmp_path, "tests/test_c.py", "")
        patterns = _profiler(tmp_path)._analyze_test_patterns(tmp_path)
        assert patterns.naming_convention == "*_test.py"

    def test_javascript_spec_and_test_naming(self, tmp_path):
        _write(tmp_path, "a.spec.js", "")
        _write(tmp_path, "b.spec.js", "")
        _write(tmp_path, "c.test.js", "")
        patterns = _profiler(tmp_path, "javascript")._analyze_test_patterns(tmp_path)
        assert patterns.naming_convention == "*.spec.js"
        assert patterns.test_location == "tests/"

    @pytest.mark.parametrize(
        ("language", "filename", "expected"),
        [
            ("go", "a_test.go", "*_test.go"),
            ("rust", "a_test.rs", "*_test.rs"),
            ("java", "FooTest.java", "*Test.java"),
            ("java", "FooIT.java", "*IT.java"),
        ],
    )
    def test_language_specific_naming(self, tmp_path, language, filename, expected):
        _write(tmp_path, filename, "")
        patterns = _profiler(tmp_path, language)._analyze_test_patterns(tmp_path)
        assert patterns.naming_convention == expected

    def test_python_fixture_config_detected(self, tmp_path):
        _write(tmp_path, "tests/conftest.py", "")
        patterns = _profiler(tmp_path)._analyze_test_patterns(tmp_path)
        assert patterns.fixture_usage is True

    def test_python_fixture_marker_detected_in_test_file(self, tmp_path):
        _write(tmp_path, "tests/test_a.py", "@pytest.fixture\ndef f():\n    pass\n")
        assert _profiler(tmp_path)._detect_fixture_usage(tmp_path, [tmp_path / "tests/test_a.py"])

    def test_fixture_marker_absent_returns_false(self, tmp_path):
        _write(tmp_path, "tests/test_a.py", "def test_a():\n    assert True\n")
        assert not _profiler(tmp_path)._detect_fixture_usage(tmp_path, [tmp_path / "tests/test_a.py"])

    def test_language_without_fixture_marker_returns_false(self, tmp_path):
        profiler = _profiler(tmp_path)
        markerless = type(profiler.profile_rules)(
            **{**profiler.profile_rules.__dict__, "test_fixture_marker": ""}
        )
        profiler.profile_rules = markerless
        assert profiler._detect_fixture_usage(tmp_path, []) is False

    def test_fixture_read_error_is_ignored(self, tmp_path, monkeypatch):
        test_file = _write(tmp_path, "tests/test_a.py", "@pytest.fixture\n")
        profiler = _profiler(tmp_path)

        real_open = open

        def fake_open(path, *args, **kwargs):
            if str(path).endswith("test_a.py"):
                raise OSError("boom")
            return real_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", fake_open)
        assert profiler._detect_fixture_usage(tmp_path, [test_file]) is False

    def test_fallback_naming_for_unmapped_language(self, tmp_path):
        profiler = _profiler(tmp_path)
        profiler.language = "unknown"
        profiler.profile_rules = LANGUAGE_PROFILES["python"]
        assert profiler._detect_naming_convention([]) == "test_*.py"


class TestCaching:
    def test_cache_round_trip(self, tmp_path):
        profiler = _profiler(tmp_path)
        profile = ProjectProfile(
            architecture=ArchitectureInfo(pattern="layered", layers={"api": ["api"]}, language="python"),
            risk_areas=RiskAreas(high_dependency=["a.py"]),
            test_patterns=TestPatterns(fixture_usage=True, framework="pytest"),
            generated_at="2026-01-01 00:00:00",
            cache_key="abc123",
            language="python",
        )
        profiler._save_cache(profile)
        loaded = profiler._load_cache("abc123")
        assert loaded == profile

    def test_cache_miss_returns_none(self, tmp_path):
        assert _profiler(tmp_path)._load_cache("missing") is None

    def test_corrupt_cache_returns_none(self, tmp_path):
        profiler = _profiler(tmp_path)
        (profiler.cache_dir / "bad.json").write_text("{not json", encoding="utf-8")
        assert profiler._load_cache("bad") is None

    def test_cache_key_changes_with_content_and_language(self, tmp_path):
        path = _write(tmp_path, "a.py", "x = 1\n")
        python_key = _profiler(tmp_path, "python")._generate_cache_key(tmp_path)
        javascript_key = _profiler(tmp_path, "javascript")._generate_cache_key(tmp_path)
        assert python_key != javascript_key
        stat = path.stat()
        path.write_text("x = 2\n", encoding="utf-8")
        updated = path.stat().st_mtime + 10
        import os

        os.utime(path, (updated, updated))
        assert _profiler(tmp_path, "python")._generate_cache_key(tmp_path) != python_key

    def test_cache_key_skips_unreadable_stat(self, tmp_path, monkeypatch):
        _write(tmp_path, "a.py", "x = 1\n")
        profiler = _profiler(tmp_path)

        class UnreadableFile:
            def __str__(self):
                return "unreadable.py"

            def stat(self):
                raise OSError("boom")

        monkeypatch.setattr(profiler, "_iter_source_files", lambda root: iter([UnreadableFile()]))
        assert isinstance(profiler._generate_cache_key(tmp_path), str)

    def test_save_cache_failure_is_logged(self, tmp_path, caplog):
        profiler = _profiler(tmp_path)
        profiler.cache_dir = tmp_path / "no-such-dir" / "nested"
        # app.main 导入时 setup_logging() 把 app 日志器设为 propagate=False，
        # 全量运行下 caplog 挂在 root 上收不到记录，直接挂到目标日志器。
        target = logging.getLogger("app.agent.project_profiler")
        with caplog.at_level(logging.WARNING, logger=target.name):
            target.addHandler(caplog.handler)
            try:
                profiler._save_cache(
                    ProjectProfile(cache_key="key", language="python", generated_at="now")
                )
            finally:
                target.removeHandler(caplog.handler)
        assert "保存缓存失败" in caplog.text


class TestProfileEndToEnd:
    def test_profile_returns_complete_fingerprint(self, tmp_path):
        _write(tmp_path, "api/mod.py", "import helpers\n")
        _write(tmp_path, "helpers.py", "x = 1\n")
        _write(tmp_path, "tests/test_mod.py", "@pytest.fixture\ndef f():\n    pass\n")
        profile = _profiler(tmp_path).profile()
        assert profile.language == "python"
        assert profile.architecture.pattern == "layered"
        assert profile.architecture.language == "python"
        assert profile.test_patterns.framework == "pytest"
        assert profile.test_patterns.fixture_usage is True
        assert profile.generated_at
        assert profile.cache_key

    def test_profile_uses_cache_on_second_call(self, tmp_path):
        _write(tmp_path, "a.py", "x = 1\n")
        profiler = _profiler(tmp_path)
        first = profiler.profile()
        second = profiler.profile()
        assert second == first
        assert second.cache_key == first.cache_key

    def test_profile_accepts_explicit_root(self, tmp_path):
        root = tmp_path / "project"
        _write(root, "a.py", "x = 1\n")
        profiler = _profiler(tmp_path)
        profile = profiler.profile(project_root=str(root))
        assert profile.language == "python"

    def test_profile_ignores_cache_for_different_language(self, tmp_path):
        _write(tmp_path, "a.py", "x = 1\n")
        python_profile = _profiler(tmp_path, "python").profile()
        cache_key = python_profile.cache_key
        javascript_profiler = _profiler(tmp_path, "javascript")
        javascript_profiler._save_cache(python_profile)
        loaded = javascript_profiler._load_cache(cache_key)
        assert loaded is not None
        profile = javascript_profiler.profile()
        assert profile.language == "javascript"

    @pytest.mark.parametrize(
        ("language", "filename", "content", "framework"),
        [
            ("javascript", "a.test.js", "describe('x', () => {})\n", "jest/vitest"),
            ("go", "a_test.go", "func TestA(t *testing.T) {}\n", "go test"),
            ("rust", "a_test.rs", "#[test]\nfn a() {}\n", "cargo test"),
            ("java", "FooTest.java", "@Test\nvoid a() {}\n", "junit"),
        ],
    )
    def test_profile_frameworks_per_language(self, tmp_path, language, filename, content, framework):
        _write(tmp_path, filename, content)
        profile = _profiler(tmp_path, language).profile()
        assert profile.test_patterns.framework == framework


class TestLanguageDetection:
    def test_missing_root_defaults_to_python(self, tmp_path):
        assert detect_project_language(str(tmp_path / "nope")) == "python"

    def test_empty_project_defaults_to_python(self, tmp_path):
        assert detect_project_language(str(tmp_path)) == "python"

    @pytest.mark.parametrize(
        ("manifest", "language"),
        [
            ("go.mod", "go"),
            ("Cargo.toml", "rust"),
            ("package.json", "javascript"),
            ("pyproject.toml", "python"),
            ("pom.xml", "java"),
        ],
    )
    def test_manifest_hints_win(self, tmp_path, manifest, language):
        _write(tmp_path, manifest, "")
        _write(tmp_path, "a.py", "x = 1\n")
        assert detect_project_language(str(tmp_path)) == language

    def test_extension_counts_choose_dominant_language(self, tmp_path):
        for index in range(3):
            _write(tmp_path, f"m{index}.go", "package main\n")
        _write(tmp_path, "a.py", "x = 1\n")
        assert detect_project_language(str(tmp_path)) == "go"

    @pytest.mark.parametrize(
        ("filename", "language"),
        [
            ("a.rs", "rust"),
            ("A.java", "java"),
            ("a.tsx", "javascript"),
            ("a.cjs", "javascript"),
        ],
    )
    def test_extension_detection(self, tmp_path, filename, language):
        _write(tmp_path, filename, "")
        assert detect_project_language(str(tmp_path)) == language

    def test_hidden_directories_are_skipped(self, tmp_path):
        for index in range(5):
            _write(tmp_path, f".cache/m{index}.go", "package main\n")
        _write(tmp_path, "a.py", "x = 1\n")
        assert detect_project_language(str(tmp_path)) == "python"
