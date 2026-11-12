"""Branch coverage for app/agent/consistency_checker.py."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import app.agent.consistency_checker as module
from app.agent.consistency_checker import ConsistencyChecker, SchemaDrift


@pytest.fixture
def dirs(tmp_path):
    original = tmp_path / "orig"
    new = tmp_path / "new"
    original.mkdir()
    new.mkdir()
    return original, new


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class TestCheckAll:
    def test_no_original_dir_returns_empty(self, dirs, monkeypatch):
        fake_logger = MagicMock()
        monkeypatch.setattr(module, "logger", fake_logger)
        _original, new = dirs

        assert ConsistencyChecker(new).check_all(None) == []
        assert fake_logger.info.called

    def test_logs_each_drift_when_found(self, dirs, monkeypatch):
        original, new = dirs
        _write(original / "app.py", "def foo(a): pass")
        fake_logger = MagicMock()
        monkeypatch.setattr(module, "logger", fake_logger)

        drifts = ConsistencyChecker(new).check_all(original)

        assert drifts
        assert fake_logger.warning.called

    def test_drift_records_reset_between_runs(self, dirs):
        original, new = dirs
        _write(original / "app.py", "def foo(a): pass")
        checker = ConsistencyChecker(new)
        checker.check_all(original)
        assert checker.drift_records

        checker.check_all(None)

        assert checker.drift_records == []


class TestSignatureDrift:
    def test_removed_function_is_error(self, dirs):
        original, new = dirs
        _write(original / "app.py", "def foo(a): pass")
        _write(new / "app.py", "def bar(a): pass")

        drifts = ConsistencyChecker(new).check_all(original)

        removed = [d for d in drifts if d.new_value == "[已删除]"]
        assert removed
        assert removed[0].severity == "error"
        assert removed[0].file_path == "app.py"

    def test_changed_function_is_warning(self, dirs):
        original, new = dirs
        _write(original / "app.py", "def foo(a): pass")
        _write(new / "app.py", "def foo(a, b): pass")

        drifts = ConsistencyChecker(new).check_all(original)

        assert drifts[0].severity == "warning"
        assert drifts[0].new_value == "foo(a, b)"

    def test_private_and_async_functions(self, dirs):
        original, new = dirs
        _write(original / "app.py", "def _hidden(): pass\nasync def work(a): pass")
        _write(new / "app.py", "def _hidden(x): pass\nasync def work(a): pass")

        drifts = ConsistencyChecker(new).check_all(original)

        assert drifts == []

    def test_syntax_error_is_skipped(self, dirs):
        original, new = dirs
        _write(original / "bad.py", "def (broken")
        _write(original / "good.py", "def foo(): pass")
        _write(new / "good.py", "def foo(): pass")

        assert ConsistencyChecker(new).check_all(original) == []

    def test_unexpected_error_logs_debug(self, dirs, monkeypatch):
        original, new = dirs
        _write(original / "a.py", "def foo(): pass")
        fake_logger = MagicMock()
        monkeypatch.setattr(module, "logger", fake_logger)

        def boom(_self):
            raise OSError("unreadable")

        checker = ConsistencyChecker(new)
        monkeypatch.setattr(Path, "read_text", boom)

        assert checker._extract_signatures(original) == {}
        assert fake_logger.debug.called


class TestConfigDrift:
    def test_removed_dependency_is_reported(self, dirs):
        original, new = dirs
        _write(original / "requirements.txt", "fastapi==1.0\nrequests>=2\n")
        _write(new / "requirements.txt", "fastapi==1.0\n")

        drifts = ConsistencyChecker(new).check_all(original)

        config = [d for d in drifts if d.drift_type == "config"]
        assert config
        assert "requests" in config[0].old_value
        assert config[0].severity == "error"

    def test_added_dependency_is_ignored(self, dirs):
        original, new = dirs
        _write(original / "requirements.txt", "fastapi\n")
        _write(new / "requirements.txt", "fastapi\nrequests\n")

        assert ConsistencyChecker(new).check_all(original) == []

    def test_missing_new_config_is_ignored(self, dirs):
        original, new = dirs
        _write(original / "requirements.txt", "fastapi\n")

        assert ConsistencyChecker(new).check_all(original) == []

    def test_read_error_logs_debug(self, dirs, monkeypatch):
        original, new = dirs
        _write(original / "requirements.txt", "fastapi\n")
        _write(new / "requirements.txt", "fastapi\n")
        fake_logger = MagicMock()
        monkeypatch.setattr(module, "logger", fake_logger)

        original_read = Path.read_text

        def selective_boom(self, *args, **kwargs):
            if self.name == "requirements.txt":
                raise OSError("denied")
            return original_read(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", selective_boom)

        ConsistencyChecker(new)._check_config_drift(original)

        assert fake_logger.debug.called

    def test_dependency_extraction_skips_blank_and_comments(self):
        deps = ConsistencyChecker(Path("."))._extract_dependencies(
            "# comment\n\nfastapi==1.0\nrequests\n"
        )
        assert deps == ["fastapi", "requests"]

    def test_dependency_extraction_skips_version_only_lines(self):
        deps = ConsistencyChecker(Path("."))._extract_dependencies("===\n>=2\n")
        assert deps == []

    def test_non_requirements_config_is_not_parsed(self, dirs):
        original, new = dirs
        _write(original / "package.json", '{"deps": ["a"]}')
        _write(new / "package.json", "{}")

        assert ConsistencyChecker(new).check_all(original) == []


class TestOpenApiDrift:
    def test_removed_path_is_reported(self, dirs):
        original, new = dirs
        _write(
            original / "openapi.json",
            json.dumps({"paths": {"/a": {}, "/b": {}}}),
        )
        _write(new / "openapi.json", json.dumps({"paths": {"/a": {}}}))

        drifts = ConsistencyChecker(new).check_all(original)

        schema = [d for d in drifts if d.drift_type == "schema"]
        assert schema
        assert schema[0].old_value == "端点: /b"
        assert schema[0].severity == "error"

    def test_added_path_is_ignored(self, dirs):
        original, new = dirs
        _write(original / "openapi.json", json.dumps({"paths": {"/a": {}}}))
        _write(new / "openapi.json", json.dumps({"paths": {"/a": {}, "/b": {}}}))

        assert ConsistencyChecker(new).check_all(original) == []

    def test_missing_new_file_is_ignored(self, dirs):
        original, new = dirs
        _write(original / "openapi.json", json.dumps({"paths": {"/a": {}}}))

        assert ConsistencyChecker(new).check_all(original) == []

    def test_invalid_json_logs_debug(self, dirs, monkeypatch):
        original, new = dirs
        _write(original / "openapi.json", "not json")
        _write(new / "openapi.json", json.dumps({"paths": {}}))
        fake_logger = MagicMock()
        monkeypatch.setattr(module, "logger", fake_logger)

        ConsistencyChecker(new)._check_openapi_drift(original)

        assert fake_logger.debug.called

    def test_yaml_schema_loaded(self, dirs):
        original, new = dirs
        _write(original / "openapi.yaml", "paths:\n  /a: {}\n  /b: {}\n")
        _write(new / "openapi.yaml", "paths:\n  /a: {}\n")

        drifts = ConsistencyChecker(new).check_all(original)

        assert any(d.drift_type == "schema" for d in drifts)

    def test_empty_schema_is_ignored(self, dirs):
        original, new = dirs
        _write(original / "openapi.json", "{}")
        _write(new / "openapi.json", "{}")

        assert ConsistencyChecker(new).check_all(original) == []

    def test_unexpected_error_logs_debug(self, dirs, monkeypatch):
        original, new = dirs
        _write(original / "openapi.json", "{}")
        _write(new / "openapi.json", "{}")
        fake_logger = MagicMock()
        monkeypatch.setattr(module, "logger", fake_logger)

        def boom(_path):
            raise RuntimeError("cannot load")

        checker = ConsistencyChecker(new)
        monkeypatch.setattr(checker, "_load_openapi", boom)

        checker._check_openapi_drift(original)

        assert fake_logger.debug.called

    def test_load_openapi_returns_none_on_error(self, dirs):
        original, _new = dirs
        bad = original / "openapi.json"
        bad.write_text("not-json", encoding="utf-8")

        assert ConsistencyChecker(original)._load_openapi(bad) is None


class TestReport:
    def test_report_without_drift(self, tmp_path):
        assert ConsistencyChecker(tmp_path).get_drift_report() == "一致性检查通过，未发现漂移"

    def test_report_with_drift(self, tmp_path):
        checker = ConsistencyChecker(tmp_path)
        checker.drift_records = [
            SchemaDrift("f.py", "signature", "old", "new", "error"),
            SchemaDrift("g.py", "config", "a", "b"),
        ]

        report = checker.get_drift_report()

        assert "2 处漂移" in report
        assert "[ERROR] signature" in report
        assert "[WARNING] config" in report
        assert "文件: f.py" in report
