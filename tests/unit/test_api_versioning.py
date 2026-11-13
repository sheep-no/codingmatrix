"""app/api/__init__.py 的版本路由、废弃装饰器与版本中间件。

该模块此前零调用、零覆盖，但它是 v1/v2 共用的版本基建，回归价值在于
固定三条契约：

- `get_version_router` 按版本缓存，不同版本前缀互不串用；
- `deprecated` 必须覆盖「返回 Response」「返回 (Response, meta)」「返回普通值」
  三种 FastAPI 返回值形态，并写入 Deprecation/Sunset/Link 头；
- `VersionMiddleware` 只对旧版本路径追加升级提示，当前版本只加基础头。
"""

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api import (
    API_VERSION_PREFIX,
    LATEST_VERSION,
    VERSION_ROUTERS,
    VersionMiddleware,
    create_versioned_app_setup,
    deprecated,
    get_version_router,
    include_all_version_routers,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    """每个用例前清空进程级路由注册表，避免跨用例串扰。"""
    VERSION_ROUTERS.clear()
    yield
    VERSION_ROUTERS.clear()


class TestVersionRouter:
    def test_creates_router_with_version_prefix(self):
        router = get_version_router("v9")
        assert router.prefix == f"{API_VERSION_PREFIX}/v9"
        assert VERSION_ROUTERS["v9"] is router

    def test_same_version_reuses_router(self):
        first = get_version_router("v9")
        second = get_version_router("v9")
        assert first is second

    def test_different_versions_are_isolated(self):
        assert get_version_router("v8") is not get_version_router("v9")
        assert set(VERSION_ROUTERS) == {"v8", "v9"}

    def test_include_all_version_routers_registers_each_once(self):
        app = FastAPI()
        for version in ("v8", "v9"):
            router = get_version_router(version)

            @router.get(f"/ping-{version}")
            async def ping():
                return {"ok": True}

        include_all_version_routers(app)

        prefixes = [route.path for route in app.routes]
        assert f"{API_VERSION_PREFIX}/v8/ping-v8" in prefixes
        assert f"{API_VERSION_PREFIX}/v9/ping-v9" in prefixes


class TestDeprecatedDecorator:
    def _client(self, handler):
        app = FastAPI()
        app.add_api_route("/demo", handler, methods=["GET"])
        return TestClient(app)

    def test_plain_value_is_wrapped_in_json_response_with_headers(self):
        @deprecated("v1", removal_version="v3", alternative="/api/v2/demo")
        async def handler():
            return {"ok": True}

        response = self._client(handler).get("/demo")

        assert response.json() == {"ok": True}
        assert response.headers["Deprecation"] == "version=v1"
        assert response.headers["Sunset"] == "v3"
        assert response.headers["Link"] == '</api/v2/demo>; rel="successor-version"'

    def test_returned_response_is_reused_and_augmented(self):
        original = JSONResponse(content={"ok": True})

        @deprecated("v1")
        async def handler():
            return original

        response = self._client(handler).get("/demo")

        assert response.json() == {"ok": True}
        assert response.headers["Deprecation"] == "version=v1"
        assert "Sunset" not in response.headers
        assert "Link" not in response.headers

    def test_tuple_result_uses_first_response(self):
        @deprecated("v1", alternative="/api/v2/demo")
        async def handler():
            return JSONResponse(content={"ok": True}), 201, {"X-Trace": "t"}

        response = self._client(handler).get("/demo")

        assert response.status_code == 201
        assert response.headers["X-Trace"] == "t"
        assert response.headers["Deprecation"] == "version=v1"
        assert response.headers["Link"] == '</api/v2/demo>; rel="successor-version"'

    def test_plain_tuple_keeps_status_and_headers(self):
        @deprecated("v1", removal_version="v3")
        async def handler():
            return {"ok": True}, 202, {"X-Trace": "t"}

        response = self._client(handler).get("/demo")

        assert response.status_code == 202
        assert response.json() == {"ok": True}
        assert response.headers["X-Trace"] == "t"
        assert response.headers["Deprecation"] == "version=v1"
        assert response.headers["Sunset"] == "v3"

    def test_plain_tuple_without_metadata_defaults_to_200(self):
        @deprecated("v1")
        async def handler():
            return {"ok": True}, "not-a-status"

        response = self._client(handler).get("/demo")

        assert response.status_code == 200
        assert response.json() == {"ok": True}
        assert response.headers["Deprecation"] == "version=v1"

    def test_response_tuple_ignores_non_int_status(self):
        @deprecated("v1")
        async def handler():
            return JSONResponse(content={"ok": True}), "not-a-status"

        response = self._client(handler).get("/demo")

        assert response.status_code == 200
        assert response.json() == {"ok": True}
        assert response.headers["Deprecation"] == "version=v1"

    def test_response_tuple_ignores_non_dict_headers(self):
        @deprecated("v1")
        async def handler():
            return JSONResponse(content={"ok": True}), 201, ["not", "a", "dict"]

        response = self._client(handler).get("/demo")

        assert response.status_code == 201
        assert response.json() == {"ok": True}
        assert response.headers["Deprecation"] == "version=v1"

    def test_metadata_is_attached_to_wrapper(self):
        @deprecated("v1", removal_version="v3", alternative="/api/v2/demo", message="自定义")
        async def handler():
            return {"ok": True}

        assert handler.__deprecated__ is True
        assert handler.__deprecation_info__ == {
            "since_version": "v1",
            "removal_version": "v3",
            "alternative": "/api/v2/demo",
            "message": "自定义",
        }

    def test_default_message_mentions_since_version(self):
        @deprecated("v1")
        async def handler():
            return {"ok": True}

        assert handler.__deprecation_info__["message"] == "此接口已从 v1 版本开始废弃"


class TestVersionMiddleware:
    def _client(self, current_version=LATEST_VERSION):
        app = FastAPI()
        app.add_middleware(VersionMiddleware, current_version=current_version)

        @app.get("/api/v1/demo")
        async def old():
            return {"ok": True}

        @app.get("/api/v2/demo")
        async def current():
            return {"ok": True}

        @app.get("/health")
        async def health():
            return {"ok": True}

        return TestClient(app)

    def test_current_version_only_gets_basic_header(self):
        response = self._client().get("/api/v2/demo")
        assert response.headers["X-API-Version"] == LATEST_VERSION
        assert "X-API-Current-Version" not in response.headers
        assert "X-API-Deprecation-Notice" not in response.headers

    def test_older_version_gets_upgrade_notice(self):
        response = self._client().get("/api/v1/demo")
        assert response.headers["X-API-Version"] == LATEST_VERSION
        assert response.headers["X-API-Current-Version"] == LATEST_VERSION
        assert "v1 is deprecated" in response.headers["X-API-Deprecation-Notice"]

    def test_non_versioned_path_gets_basic_header_only(self):
        response = self._client().get("/health")
        assert response.headers["X-API-Version"] == LATEST_VERSION
        assert "X-API-Deprecation-Notice" not in response.headers

    def test_custom_current_version_marks_v2_as_deprecated(self):
        response = self._client(current_version="v3").get("/api/v2/demo")
        assert response.headers["X-API-Deprecation-Notice"].startswith(
            "API version v2 is deprecated"
        )


def test_create_versioned_app_setup_wires_middleware_and_routers():
    app = FastAPI()
    router = get_version_router("v9")

    @router.get("/ping")
    async def ping():
        return {"ok": True}

    create_versioned_app_setup(app)

    response = TestClient(app).get(f"{API_VERSION_PREFIX}/v9/ping")
    assert response.json() == {"ok": True}
    assert response.headers["X-API-Version"] == LATEST_VERSION
