"""GZip 中间件必须跳过 NDJSON 流式响应（B2 回归）。"""

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.testclient import TestClient
from starlette.responses import StreamingResponse

import app.main  # noqa: F401  导入即注册 NDJSON 排除项


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(GZipMiddleware, minimum_size=500)

    @app.get("/ndjson")
    async def ndjson():
        async def generate():
            for _ in range(3):
                yield ("{" + ("x" * 400) + "}\n").encode()

        return StreamingResponse(generate(), media_type="application/x-ndjson")

    @app.get("/json")
    async def json_route():
        return {"data": "x" * 2000}

    return app


def test_ndjson_stream_is_not_gzipped():
    response = TestClient(_build_app()).get(
        "/ndjson", headers={"Accept-Encoding": "gzip"}
    )

    assert response.status_code == 200
    assert "content-encoding" not in response.headers
    assert response.text.count("\n") == 3


def test_regular_json_response_still_gzipped():
    response = TestClient(_build_app()).get(
        "/json", headers={"Accept-Encoding": "gzip"}
    )

    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"
