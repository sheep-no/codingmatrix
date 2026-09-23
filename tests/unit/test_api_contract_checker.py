import pytest

from app.agent.api_contract_checker import (
    APIContractChecker,
    EndpointMethod,
    check_api_consistency,
    generate_frontend_prompt_contract,
)


FASTAPI_BASE = "from fastapi import FastAPI\napp = FastAPI()\n"


class TestNormalizePath:
    @pytest.fixture
    def checker(self):
        return APIContractChecker()

    def test_backend_brace_param(self, checker):
        assert checker._normalize_path('/api/users/{user_id}') == '/api/users/:user_id'

    def test_frontend_template_literal_param(self, checker):
        """AC1：前端 ${id} 不再变成 $:id"""
        assert checker._normalize_path('/api/users/${userId}') == '/api/users/:userId'

    def test_concrete_tail_becomes_param(self, checker):
        """AC3：裸具体值归一为 :param（仅前端 dynamic_tail）"""
        assert checker._normalize_path('/api/users/123', dynamic_tail=True) == '/api/users/:param'
        assert checker._normalize_path(
            '/api/users/3f6c1e2a-1111-2222-3333-444455556666', dynamic_tail=True
        ) == '/api/users/:param'

    def test_static_tail_preserved_without_flag(self, checker):
        assert checker._normalize_path('/api/users/123') == '/api/users/123'

    def test_query_and_trailing_slash(self, checker):
        assert checker._normalize_path('/api/users/?page=1') == '/api/users'

    def test_canonical_path_folds_param_names(self, checker):
        assert checker._canonical_path('/api/users/:user_id') == '/api/users/:param'
        assert checker._canonical_path('/api/users/:param') == '/api/users/:param'


class TestBackendExtraction:
    @pytest.fixture
    def checker(self):
        return APIContractChecker()

    def test_fastapi_decorator(self, checker):
        code = FASTAPI_BASE + "@app.get('/api/users')\ndef f(): ..."
        eps = checker.extract_backend_endpoints(code, 'api.py')
        assert [(e.method.value, e.path) for e in eps] == [('GET', '/api/users')]

    def test_fastapi_router_prefix(self, checker):
        """AC2：APIRouter(prefix=...) 拼接"""
        code = (
            "from fastapi import APIRouter\n"
            "router = APIRouter(prefix='/api/v1')\n"
            "@router.get('/users')\ndef f(): ..."
        )
        eps = checker.extract_backend_endpoints(code, 'api.py')
        assert [e.path for e in eps] == ['/api/v1/users']

    def test_fastapi_api_route_multiple_methods(self, checker):
        code = (
            "from fastapi import APIRouter\n"
            "r = APIRouter(prefix='/api')\n"
            "@r.api_route('/y', methods=['GET', 'PUT'])\ndef f(): ..."
        )
        eps = checker.extract_backend_endpoints(code, 'api.py')
        assert {(e.method.value, e.path) for e in eps} == {('GET', '/api/y'), ('PUT', '/api/y')}

    def test_flask_blueprint_url_prefix(self, checker):
        code = (
            "from flask import Blueprint\n"
            "bp = Blueprint('x', __name__, url_prefix='/api/v1')\n"
            "@bp.route('/users', methods=['GET', 'POST'])\ndef f(): ..."
        )
        eps = checker.extract_backend_endpoints(code, 'b.py')
        assert {(e.method.value, e.path) for e in eps} == {
            ('GET', '/api/v1/users'), ('POST', '/api/v1/users')
        }

    def test_django_only_extracts_urlpatterns(self, checker):
        """AC8：view 内部 path("...") 与 include() 子路由不误报"""
        code = (
            "from django.urls import path, include\n"
            "urlpatterns = [\n"
            "    path('api/', include('app.urls')),\n"
            "    path('api/items/', views.items),\n"
            "]\n"
            "def view():\n"
            "    return path('static.txt')\n"
        )
        eps = checker.extract_backend_endpoints(code, 'urls.py', framework='django')
        assert [e.path for e in eps] == ['/api/items']
        assert eps[0].line_number == 4

    def test_unknown_framework_defaults_to_fastapi(self, checker):
        assert checker._detect_framework("import something\n") == 'fastapi'
        assert checker._detect_framework("from flask import Flask\n") == 'flask'
        assert checker._detect_framework("from django.urls import path\n") == 'django'


class TestFrontendExtraction:
    @pytest.fixture
    def checker(self):
        return APIContractChecker()

    def test_fetch_crossline_method(self, checker):
        """AC4：跨行 fetch options 的 method 不再漏判为 GET"""
        code = "fetch('/api/orders', {\n  method: 'POST',\n  body: JSON.stringify(x)\n})"
        eps = checker.extract_frontend_endpoints(code, 'a.js')
        assert [(e.method.value, e.path) for e in eps] == [('POST', '/api/orders')]

    def test_fetch_template_literal(self, checker):
        eps = checker.extract_frontend_endpoints("fetch(`/api/users/${userId}`)", 'a.js')
        assert [(e.method.value, e.path) for e in eps] == [('GET', '/api/users/:userId')]

    def test_fetch_concat_marks_dynamic_tail(self, checker):
        eps = checker.extract_frontend_endpoints("fetch('/api/users/' + userId)", 'a.js')
        assert [e.path for e in eps] == ['/api/users/:param']

    def test_fetch_object_url_form(self, checker):
        code = "fetch({\n  url: '/api/a/3',\n  method: 'delete'\n})"
        eps = checker.extract_frontend_endpoints(code, 'a.js')
        assert [(e.method.value, e.path) for e in eps] == [('DELETE', '/api/a/:param')]

    def test_axios_method_and_config_form(self, checker):
        eps = checker.extract_frontend_endpoints("axios.get('/api/a/1')", 'a.js')
        assert [(e.method.value, e.path) for e in eps] == [('GET', '/api/a/:param')]

        eps = checker.extract_frontend_endpoints(
            "axios({\n  method: 'put',\n  url: '/api/a/2'\n})", 'a.js'
        )
        assert [(e.method.value, e.path) for e in eps] == [('PUT', '/api/a/:param')]

    def test_plain_object_get_not_treated_as_endpoint(self, checker):
        """AC5：移除死模式后，dict.get('k') 之类不被当作 API 调用"""
        eps = checker.extract_frontend_endpoints("const v = data.get('name')", 'a.js')
        assert eps == []

    def test_axios_config_with_nested_options(self, checker):
        code = "axios({\n  method: 'post',\n  url: '/api/a',\n  headers: { 'X-Token': '1' }\n})"
        eps = checker.extract_frontend_endpoints(code, 'a.js')
        assert [(e.method.value, e.path) for e in eps] == [('POST', '/api/a')]

    def test_invalid_method_falls_back_to_get(self, checker):
        eps = checker.extract_frontend_endpoints("fetch('/api/x', {method: 'FOO'})", 'a.js')
        assert [e.method.value for e in eps] == ['GET']

    def test_line_numbers(self, checker):
        code = "const a = 1;\n\nfetch('/api/x');\n"
        eps = checker.extract_frontend_endpoints(code, 'a.js')
        assert eps[0].line_number == 3


class TestConsistency:
    @pytest.fixture
    def checker(self):
        return APIContractChecker()

    def test_match_no_issues(self, checker):
        issues = checker.check_consistency(
            {"main.js": "fetch('/api/users')"},
            {"api.py": FASTAPI_BASE + "@app.get('/api/users')\ndef f(): ..."},
        )
        assert issues == []

    def test_template_param_matches_backend(self, checker):
        """AC1：`${userId}` 与后端 `{user_id}` 参数名不同也应匹配"""
        issues = checker.check_consistency(
            {"a.js": "fetch(`/api/users/${userId}`)"},
            {"api.py": FASTAPI_BASE + "@app.get('/api/users/{user_id}')\ndef f(): ..."},
        )
        assert issues == []

    def test_router_prefix_matches(self, checker):
        """AC2：prefix 拼接后不再双误报"""
        issues = checker.check_consistency(
            {"a.js": "fetch('/api/v1/users')"},
            {"api.py": "from fastapi import APIRouter\nrouter = APIRouter(prefix='/api/v1')\n@router.get('/users')\ndef f(): ..."},
        )
        assert issues == []

    def test_concrete_and_concat_match_backend_param(self, checker):
        """AC3：具体值/拼接路径与后端参数化端点对齐"""
        be = {"api.py": FASTAPI_BASE + "@app.get('/api/users/{id}')\ndef f(): ..."}
        for fe in ("fetch('/api/users/123')", "fetch('/api/users/' + userId)"):
            assert checker.check_consistency({"a.js": fe}, be) == []
    def test_crossline_post_matches(self, checker):
        """AC4：跨行 POST 不再误报"""
        issues = checker.check_consistency(
            {"a.js": "fetch('/api/orders', {\n  method: 'POST',\n  body: b\n})"},
            {"api.py": FASTAPI_BASE + "@app.post('/api/orders')\ndef f(): ..."},
        )
        assert issues == []

    def test_missing_backend(self, checker):
        issues = checker.check_consistency(
            {"a.js": "fetch('/api/none')"},
            {"api.py": FASTAPI_BASE + "@app.get('/api/x')\ndef f(): ..."},
        )
        types = {(i.issue_type, i.severity) for i in issues}
        assert ('missing_backend', 'error') in types
        assert ('missing_frontend', 'warning') in types

    def test_method_mismatch_frontend_extra(self, checker):
        """AC7：路径存在但方法不同 → method_mismatch（原为死代码）"""
        issues = checker.check_consistency(
            {"a.js": "fetch('/api/x', {method: 'DELETE'})"},
            {"api.py": FASTAPI_BASE + "@app.get('/api/x')\ndef f(): ..."},
        )
        mm = [i for i in issues if i.issue_type == 'method_mismatch']
        assert any(i.severity == 'error' and 'DELETE' in i.message for i in mm)

    def test_method_mismatch_backend_extra(self, checker):
        issues = checker.check_consistency(
            {"a.js": "fetch('/api/x', {method: 'GET'})"},
            {"api.py": FASTAPI_BASE + "@app.get('/api/x')\ndef f(): ...\n@app.post('/api/x')\ndef g(): ..."},
        )
        mm = [i for i in issues if i.issue_type == 'method_mismatch']
        assert any(i.severity == 'warning' and 'POST' in i.message for i in mm)
        assert not [i for i in issues if i.issue_type == 'missing_backend']

    def test_no_method_mismatch_when_methods_equal(self, checker):
        issues = checker.check_consistency(
            {"a.js": "fetch('/api/x')"},
            {"api.py": FASTAPI_BASE + "@app.get('/api/x')\ndef f(): ..."},
        )
        assert issues == []

    def test_single_file_method_mismatch(self, checker):
        issues = checker.check_single_file_consistency(
            file_path='a.js',
            code="fetch('/api/x', {method: 'PUT'})",
            is_frontend=True,
            counterpart_files={"api.py": FASTAPI_BASE + "@app.get('/api/x')\ndef f(): ..."},
        )
        assert [i.issue_type for i in issues] == ['method_mismatch']
        assert issues[0].severity == 'error'

    def test_single_file_param_name_folded(self, checker):
        issues = checker.check_single_file_consistency(
            file_path='a.js',
            code="fetch('/api/users/${userId}')",
            is_frontend=True,
            counterpart_files={"api.py": FASTAPI_BASE + "@app.get('/api/users/{user_id}')\ndef f(): ..."},
        )
        assert issues == []

    def test_convenience_function(self, checker):
        passed, issues = check_api_consistency(
            {"a.js": "fetch('/api/users')"},
            {"api.py": FASTAPI_BASE + "@app.get('/api/users')\ndef f(): ..."},
        )
        assert passed is True and issues == []

        passed, issues = check_api_consistency({"a.js": "fetch('/api/none')"}, {})
        assert passed is False and issues


class TestContractGeneration:
    @pytest.fixture
    def checker(self):
        return APIContractChecker()

    def test_generate_api_contract_groups_by_module(self, checker):
        contract = checker.generate_api_contract({
            "api.py": FASTAPI_BASE + "@app.get('/api/v1/users')\ndef f(): ...",
        })
        assert 'api' in contract
        assert contract['api'][0]['path'] == '/api/v1/users'

    def test_generate_frontend_prompt_contract_lists_routes(self, checker):
        text = generate_frontend_prompt_contract({
            "api.py": FASTAPI_BASE + "@app.get('/api/users')\ndef f(): ...",
        })
        assert '`/api/users`' in text
        assert '`GET`' in text
