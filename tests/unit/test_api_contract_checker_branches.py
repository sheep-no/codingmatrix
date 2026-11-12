"""Branch coverage for app/agent/api_contract_checker.py."""

import pytest

from app.agent.api_contract_checker import (
    APIContractChecker,
    APIEndpoint,
    ConsistencyIssue,
    EndpointMethod,
    check_api_consistency,
    generate_frontend_prompt_contract,
)


@pytest.fixture
def checker() -> APIContractChecker:
    return APIContractChecker()


# ---------------------------------------------------------------------------
# Frontend extraction edge cases
# ---------------------------------------------------------------------------


def test_fetch_object_without_url_is_skipped(checker) -> None:
    code = "fetch({ method: 'POST', body: data })"

    assert checker.extract_frontend_endpoints(code, "app.js") == []


def test_axios_config_without_url_is_skipped(checker) -> None:
    code = "axios({ method: 'post', data })"

    assert checker.extract_frontend_endpoints(code, "app.js") == []


def test_unquote_without_matching_quotes_returns_token(checker) -> None:
    assert checker._unquote("/api/plain") == "/api/plain"
    assert checker._unquote("'/api/quoted'") == "/api/quoted"
    assert checker._unquote('`/api/template`') == "/api/template"
    assert checker._unquote("'") == "'"


def test_enum_method_unknown_falls_back_to_get(checker) -> None:
    assert checker._enum_method("options") is EndpointMethod.GET
    assert checker._enum_method("post") is EndpointMethod.POST


def test_method_from_text_invalid_falls_back_to_get(checker) -> None:
    assert checker._method_from_text("{method: 'invalid'}") is EndpointMethod.GET
    assert checker._method_from_text("{method: 'patch'}") is EndpointMethod.PATCH
    assert checker._method_from_text(None) is EndpointMethod.GET
    assert checker._method_from_text("{body: data}") is EndpointMethod.GET


# ---------------------------------------------------------------------------
# Backend extraction edge cases
# ---------------------------------------------------------------------------


def test_backend_skips_unsupported_method_name(checker) -> None:
    code = (
        "@app.api_route('/x', methods=['GET', 'TRACE'])\n"
        "def handler():\n    pass\n"
    )

    endpoints = checker.extract_backend_endpoints(code, "main.py", framework="fastapi")

    assert [endpoint.method for endpoint in endpoints] == [EndpointMethod.GET]


def test_collect_prefixes_ignores_router_without_prefix(checker) -> None:
    code = "router = APIRouter()\n@router.get('/x')\ndef x():\n    pass\n"

    endpoints = checker.extract_backend_endpoints(code, "main.py", framework="fastapi")

    assert endpoints[0].path == "/x"


def test_django_skips_include_only_entries(checker) -> None:
    code = (
        "urlpatterns = [\n"
        "    path('included/', include('other.urls')),\n"
        "    path('direct/', views.Direct.as_view()),\n"
        "]\n"
    )

    endpoints = checker.extract_backend_endpoints(code, "urls.py", framework="django")

    assert [endpoint.path for endpoint in endpoints] == ["/direct"]


def test_backend_default_framework_detection_for_flask_and_django(checker) -> None:
    assert checker._detect_framework("from flask import Flask") == "flask"
    assert checker._detect_framework("from django.urls import path") == "django"
    assert checker._detect_framework("no framework here") == "fastapi"


# ---------------------------------------------------------------------------
# check_single_file_consistency
# ---------------------------------------------------------------------------


def test_single_file_backend_missing_frontend(checker) -> None:
    backend_code = "@router.get('/items')\ndef items():\n    return []\n"
    frontend_code = "console.log('nothing here')\n"

    issues = checker.check_single_file_consistency(
        "backend/routers.py", backend_code, is_frontend=False,
        counterpart_files={"frontend/app.js": frontend_code},
    )

    assert issues[0].issue_type == "missing_frontend"
    assert issues[0].severity == "warning"


def test_single_file_backend_method_mismatch(checker) -> None:
    backend_code = "@router.post('/items')\ndef create():\n    return {}\n"
    frontend_code = "fetch('/items', {method: 'GET'})\n"

    issues = checker.check_single_file_consistency(
        "backend/routers.py", backend_code, is_frontend=False,
        counterpart_files={"frontend/app.js": frontend_code},
    )

    assert issues[0].issue_type == "method_mismatch"
    assert issues[0].severity == "warning"


def test_single_file_frontend_missing_method(checker) -> None:
    frontend_code = "fetch('/items', {method: 'POST'})\n"
    backend_code = "@router.get('/items')\ndef items():\n    return []\n"

    issues = checker.check_single_file_consistency(
        "frontend/app.js", frontend_code, is_frontend=True,
        counterpart_files={"backend/routers.py": backend_code},
    )

    assert issues[0].issue_type == "method_mismatch"
    assert issues[0].severity == "error"


def test_single_file_frontend_missing_backend(checker) -> None:
    frontend_code = "fetch('/missing')\n"

    issues = checker.check_single_file_consistency(
        "frontend/app.js", frontend_code, is_frontend=True, counterpart_files={}
    )

    assert issues[0].issue_type == "missing_backend"
    assert issues[0].severity == "error"


def test_single_file_frontend_no_issues(checker) -> None:
    frontend_code = "fetch('/items', {method: 'GET'})\n"
    backend_code = "@router.get('/items')\ndef items():\n    return []\n"

    issues = checker.check_single_file_consistency(
        "frontend/app.js", frontend_code, is_frontend=True,
        counterpart_files={"backend/routers.py": backend_code},
    )

    assert issues == []


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def test_consistency_report_without_issues(checker) -> None:
    assert "通过" in checker.get_consistency_report()


def test_consistency_report_lists_enabled_sections(checker) -> None:
    checker.issues = [
        ConsistencyIssue("error", "missing_backend", "err", suggestion="fix"),
        ConsistencyIssue("warning", "missing_frontend", "warn", suggestion="less"),
    ]

    report = checker.get_consistency_report()

    assert "错误 (1)" in report
    assert "警告 (1)" in report
    assert "总计: 2 个问题 (1 错误, 1 警告)" in report


def test_consistency_report_skips_empty_sections(checker) -> None:
    checker.issues = [ConsistencyIssue("info", "other", "note")]

    report = checker.get_consistency_report()

    assert "错误 (" not in report
    assert "警告 (" not in report
    assert "总计: 1 个问题 (0 错误, 0 警告)" in report


# ---------------------------------------------------------------------------
# API contract generation
# ---------------------------------------------------------------------------


def test_normalize_path_force_leading_slash() -> None:
    assert APIContractChecker()._normalize_path("api/items") == "/api/items"


def test_normalize_path_uuid_tail_becomes_param() -> None:
    path = "/api/items/123e4567-e89b-12d3-a456-426614174000"

    assert APIContractChecker()._normalize_path(path, dynamic_tail=True) == (
        "/api/items/:param"
    )


def test_generate_api_contract_root_path_uses_empty_module_key() -> None:
    code = "@app.get('/')\ndef root():\n    return {}\n"

    contract = APIContractChecker().generate_api_contract({"main.py": code})

    # strip('/').split('/') always yields at least [""], so the documented
    # "default" fallback is unreachable; root paths group under "".
    assert list(contract) == [""]


def test_generate_frontend_prompt_contract_for_empty_backend() -> None:
    prompt = generate_frontend_prompt_contract({})

    assert "## API 契约（必须遵守）" in prompt
    assert "### 模块:" not in prompt


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def test_check_api_consistency_passes_without_errors() -> None:
    frontend = {"app.js": "fetch('/items', {method: 'GET'})\n"}
    backend = {"main.py": "@app.get('/items')\ndef items():\n    return []\n"}

    passed, issues = check_api_consistency(frontend, backend)

    assert passed is True
    assert issues == []


def test_check_api_consistency_fails_with_error() -> None:
    frontend = {"app.js": "fetch('/missing')\n"}

    passed, issues = check_api_consistency(frontend, {})

    assert passed is False
    assert issues[0].issue_type == "missing_backend"
