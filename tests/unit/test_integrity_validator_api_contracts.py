"""IntegrityValidator API 契约校验测试（IV3/IV4 回归防线）。"""

from app.agent.adapters import PythonLanguageAdapter
from app.agent.integrity_validator import IntegrityValidator


def _api_mismatches(files):
    validator = IntegrityValidator(
        project_type="python", language_adapter=PythonLanguageAdapter()
    )
    result = validator.validate(files)
    return [
        issue for issue in result.issues if issue.issue_type == "api_mismatch"
    ]


def _mixed(backend: str, frontend: str):
    return {"app/main.py": backend, "static/api.js": frontend}


def test_exact_path_and_method_matches() -> None:
    assert (
        _api_mismatches(
            _mixed('@app.get("/api/user")\ndef h():\n    pass\n', 'fetch("/api/user")')
        )
        == []
    )


def test_path_param_matches_single_segment() -> None:
    assert (
        _api_mismatches(
            _mixed(
                '@app.get("/api/user/{id}")\ndef h():\n    pass\n',
                'axios.get("/api/user/42")',
            )
        )
        == []
    )


def test_resource_name_prefix_is_not_treated_as_match() -> None:
    # IV3 回归：/api/users 不应因前缀而命中 /api/user
    issues = _api_mismatches(
        _mixed('@app.get("/api/user")\ndef h():\n    pass\n', 'fetch("/api/users")')
    )
    assert len(issues) == 1
    assert "GET /api/users" in issues[0].message


def test_extra_segment_no_longer_matches_parent_path() -> None:
    # IV3 回归：/api/user/123 不应命中 /api/user
    issues = _api_mismatches(
        _mixed('@app.get("/api/user")\ndef h():\n    pass\n', 'fetch("/api/user/123")')
    )
    assert len(issues) == 1


def test_method_mismatch_is_reported() -> None:
    # IV4 回归：后端只有 POST，前端 GET 调用应报
    issues = _api_mismatches(
        _mixed('@app.post("/api/todo")\ndef h():\n    pass\n', 'fetch("/api/todo")')
    )
    assert len(issues) == 1
    assert "GET /api/todo" in issues[0].message

    issues = _api_mismatches(
        _mixed('@app.get("/api/todo")\ndef h():\n    pass\n', 'axios.post("/api/todo")')
    )
    assert len(issues) == 1
    assert "POST /api/todo" in issues[0].message


def test_query_string_is_stripped_before_matching() -> None:
    assert (
        _api_mismatches(
            _mixed(
                '@app.get("/api/users")\ndef h():\n    pass\n',
                'fetch("/api/users?page=1")',
            )
        )
        == []
    )


def test_path_special_chars_are_escaped() -> None:
    # re.escape：`/api/v1.0` 的 `.` 是字面量，不应命中 /api/v1x0
    issues = _api_mismatches(
        _mixed('@app.get("/api/v1.0/ping")\ndef h():\n    pass\n', 'fetch("/api/v1x0/ping")')
    )
    assert len(issues) == 1
