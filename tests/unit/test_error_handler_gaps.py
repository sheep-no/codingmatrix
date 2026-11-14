"""error_handler 各异常处理器响应格式补测。"""

import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.utils import error_handler as module
from app.utils.aicloud.llm_caller import (
    LLMCallError,
    ProviderAPIKeyNotConfiguredError,
    UserAPIKeyNotFoundError,
)


class _Request:
    url = type("URL", (), {"path": "/api/test"})()
    method = "POST"


class _Body(BaseModel):
    age: int


class _App:
    def __init__(self):
        self.handlers = {}

    def add_exception_handler(self, exc_type, handler):
        self.handlers[exc_type] = handler


async def test_validation_exception_handler():
    exc = RequestValidationError([
        {"loc": ("body", "age"), "msg": "bad", "type": "int_parsing"},
    ])
    response = await module.validation_exception_handler(_Request(), exc)
    body = response.body.decode()

    assert response.status_code == 422
    assert '"VALIDATION_ERROR"' in body
    assert "body.age" in body


async def test_pydantic_validation_handler():
    with pytest.raises(ValidationError) as info:
        _Body(age="not-int")
    response = await module.pydantic_validation_exception_handler(_Request(), info.value)

    assert response.status_code == 422
    assert '"数据验证失败"' in response.body.decode()


@pytest.mark.parametrize("status_code,expected", [
    (400, "BAD_REQUEST"),
    (401, "UNAUTHORIZED"),
    (403, "FORBIDDEN"),
    (404, "NOT_FOUND"),
    (405, "METHOD_NOT_ALLOWED"),
    (409, "CONFLICT"),
    (422, "VALIDATION_ERROR"),
    (429, "RATE_LIMITED"),
    (500, "INTERNAL_ERROR"),
    (502, "BAD_GATEWAY"),
    (503, "SERVICE_UNAVAILABLE"),
    (418, "HTTP_ERROR"),
])
async def test_http_exception_handler_code_map(status_code, expected):
    response = await module.http_exception_handler(
        _Request(), HTTPException(status_code=status_code, detail="detail")
    )
    assert response.status_code == status_code
    assert expected in response.body.decode()


async def test_http_exception_handler_non_str_detail():
    response = await module.http_exception_handler(
        _Request(), HTTPException(status_code=400, detail={"a": 1})
    )
    assert "{'a': 1}" in response.body.decode()


async def test_http_429_uses_header_retry_after():
    exc = HTTPException(status_code=429, detail="slow down", headers={"Retry-After": "12"})
    response = await module.http_exception_handler(_Request(), exc)
    assert response.headers["Retry-After"] == "12"


async def test_http_429_lowercase_header():
    exc = HTTPException(status_code=429, detail="slow down", headers={"retry-after": "7"})
    response = await module.http_exception_handler(_Request(), exc)
    assert response.headers["Retry-After"] == "7"


async def test_http_429_default_retry_after():
    response = await module.http_exception_handler(
        _Request(), HTTPException(status_code=429, detail="slow")
    )
    assert response.headers["Retry-After"] == str(module.DEFAULT_RETRY_AFTER_SECONDS)


async def test_http_429_empty_header_value_uses_default():
    exc = HTTPException(status_code=429, detail="slow", headers={"Retry-After": ""})
    response = await module.http_exception_handler(_Request(), exc)
    assert response.headers["Retry-After"] == str(module.DEFAULT_RETRY_AFTER_SECONDS)


async def test_non_429_has_no_retry_header():
    response = await module.http_exception_handler(
        _Request(), HTTPException(status_code=404, detail="missing")
    )
    assert "Retry-After" not in response.headers


async def test_starlette_http_exception_handler():
    response = await module.starlette_http_exception_handler(
        _Request(), StarletteHTTPException(status_code=404, detail="nope")
    )
    assert response.status_code == 404
    assert '"HTTP_ERROR"' in response.body.decode()


async def test_integrity_error_handler():
    exc = IntegrityError("INSERT", {}, Exception("duplicate"))
    response = await module.integrity_error_handler(_Request(), exc)
    assert response.status_code == 409
    assert '"DATABASE_INTEGRITY_ERROR"' in response.body.decode()


async def test_operational_error_handler():
    exc = OperationalError("SELECT 1", {}, Exception("timeout"))
    response = await module.operational_error_handler(_Request(), exc)
    assert response.status_code == 500
    assert '"DATABASE_ERROR"' in response.body.decode()


async def test_sqlalchemy_error_handler():
    response = await module.sqlalchemy_error_handler(_Request(), SQLAlchemyError("boom"))
    assert response.status_code == 500


@pytest.mark.parametrize("exc_type,expected", [
    (UserAPIKeyNotFoundError, "USER_API_KEY_NOT_FOUND"),
    (ProviderAPIKeyNotConfiguredError, "PROVIDER_API_KEY_NOT_CONFIGURED"),
    (LLMCallError, "LLM_CALL_ERROR"),
])
async def test_llm_call_error_handler(exc_type, expected):
    exc = exc_type("failed")
    response = await module.llm_call_error_handler(_Request(), exc)
    assert expected in response.body.decode()
    assert response.status_code == getattr(exc, "status_code", 500)


async def test_generic_exception_handler():
    response = await module.generic_exception_handler(_Request(), RuntimeError("boom"))
    assert response.status_code == 500
    assert '"INTERNAL_ERROR"' in response.body.decode()


def test_error_response_details_and_headers():
    response = module._error_response(
        "X", "msg", 418, details={"k": 1}, headers={"H": "v"}
    )
    assert response.headers["H"] == "v"
    assert '"k":1' in response.body.decode()


def test_register_exception_handlers_registers_all():
    app = _App()
    module.register_exception_handlers(app)
    assert Exception in app.handlers
    assert RequestValidationError in app.handlers
    assert HTTPException in app.handlers
    assert StarletteHTTPException in app.handlers
    assert IntegrityError in app.handlers
    assert OperationalError in app.handlers
    assert SQLAlchemyError in app.handlers
    assert LLMCallError in app.handlers


def test_register_exception_handlers_skips_missing_llm_error(monkeypatch):
    import builtins

    app = _App()
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "app.utils.aicloud.llm_caller":
            raise ImportError("gone")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    module.register_exception_handlers(app)

    assert LLMCallError not in app.handlers
    assert Exception in app.handlers
