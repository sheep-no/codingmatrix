"""补齐 cache_decorator 的身份提取、参数序列化与响应缓存分支。"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse

from app.utils import cache_decorator


class _FakeCache:
    def __init__(self, store=None):
        self.store = dict(store or {})
        self.written = []
        self.invalidated = []

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ttl=None):
        self.written.append((key, value, ttl))
        self.store[key] = value
        return True

    async def invalidate_pattern(self, pattern):
        self.invalidated.append(pattern)
        return 0


class _ModelDump:
    def model_dump(self):
        return {"a": 1}


class _ModelDumpError:
    def model_dump(self):
        raise RuntimeError("dump failed")


class _LegacyDict:
    def dict(self):
        return {"b": 2}


class _LegacyDictError:
    def dict(self):
        raise RuntimeError("dict failed")


class _BadRepr:
    def __str__(self):
        raise TypeError("cannot stringify")

    __repr__ = __str__


def _request(path="/x", query=b""):
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": query,
        "headers": [],
    }
    return Request(scope)


class TestUserIdentity:
    def test_token_subject(self):
        assert cache_decorator._extract_user_identity({"token": {"sub": "alice"}}) == "alice"

    def test_token_user_id_fallback(self):
        assert cache_decorator._extract_user_identity({"token": {"user_id": 7}}) == "7"

    def test_token_without_subject_falls_through(self):
        assert cache_decorator._extract_user_identity({"token": {}, "user_id": 3}) == "3"

    def test_bool_user_id_ignored(self):
        assert cache_decorator._extract_user_identity({"user_id": True}) is None

    def test_current_user_attributes(self):
        class _User:
            id = 11

        assert cache_decorator._extract_user_identity({"current_user": _User()}) == "11"

    def test_current_user_username(self):
        class _User:
            username = "bob"

        assert cache_decorator._extract_user_identity({"current_user": _User()}) == "bob"

    def test_current_user_without_usable_attr(self):
        class _User:
            id = None
            user_id = True
            username = False

        assert cache_decorator._extract_user_identity({"current_user": _User()}) is None

    def test_no_identity(self):
        assert cache_decorator._extract_user_identity({}) is None


class TestSerializeParam:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (True, "bool:True"),
            (False, "bool:False"),
            (5, "5"),
            (1.5, "1.5"),
            ("text", "text"),
        ],
    )
    def test_scalars(self, value, expected):
        assert cache_decorator._serialize_cache_param(value) == expected

    def test_set_sorted(self):
        assert cache_decorator._serialize_cache_param({"b", "a"}) == '["a", "b"]'

    def test_set_serialization_failure(self):
        assert cache_decorator._serialize_cache_param({_BadRepr()}) is None

    def test_dict_serialized(self):
        assert cache_decorator._serialize_cache_param({"a": 1}) == '{"a": 1}'

    def test_list_serialization_failure(self):
        assert cache_decorator._serialize_cache_param([_BadRepr()]) is None

    def test_model_dump(self):
        assert cache_decorator._serialize_cache_param(_ModelDump()) == '{"a": 1}'

    def test_model_dump_failure(self):
        assert cache_decorator._serialize_cache_param(_ModelDumpError()) is None

    def test_legacy_dict(self):
        assert cache_decorator._serialize_cache_param(_LegacyDict()) == '{"b": 2}'

    def test_legacy_dict_failure(self):
        assert cache_decorator._serialize_cache_param(_LegacyDictError()) is None

    def test_unknown_object(self):
        assert cache_decorator._serialize_cache_param(object()) is None


class TestGenerateKey:
    def test_request_with_query_params(self):
        key = cache_decorator._generate_cache_key(
            "p", "f", (), {}, _request("/api/items", b"limit=10")
        )

        assert key.startswith("p:")

    def test_request_in_args_skipped(self):
        req = _request("/api/items")
        with_req = cache_decorator._generate_cache_key("p", "f", (req,), {})
        without = cache_decorator._generate_cache_key("p", "f", (), {})

        assert with_req == without

    def test_request_in_kwargs_skipped(self):
        with_req = cache_decorator._generate_cache_key("p", "f", (), {"request": _request("/x")})
        without = cache_decorator._generate_cache_key("p", "f", (), {})

        assert with_req == without

    def test_identity_segment_present(self):
        key = cache_decorator._generate_cache_key("p", "f", (), {"token": {"sub": "u1"}})

        assert ":u=u1:" in key

    def test_unserializable_arg_skipped(self):
        key = cache_decorator._generate_cache_key("p", "f", (object(),), {})

        assert key == cache_decorator._generate_cache_key("p", "f", (), {})

    def test_unserializable_kwarg_skipped(self):
        key = cache_decorator._generate_cache_key("p", "f", (), {"payload": object()})

        assert key == cache_decorator._generate_cache_key("p", "f", (), {})


class TestShouldCacheResponse:
    def test_non_2xx_not_cached(self):
        assert cache_decorator._should_cache_response(404) is False

    def test_condition_true(self):
        assert cache_decorator._should_cache_response(200, lambda: True) is True

    def test_condition_false(self):
        assert cache_decorator._should_cache_response(200, lambda: False) is False


class TestCacheResponseWrapper:
    @pytest.fixture
    def fake_cache(self):
        cache = _FakeCache()

        async def manager():
            return cache

        return cache, manager

    async def test_request_from_positional_arg(self, fake_cache):
        cache, manager = fake_cache
        calls = []

        @cache_decorator.cache_response(ttl=10)
        async def handler(request: Request):
            calls.append(1)
            return {"ok": True}

        with patch.object(cache_decorator, "get_cache_manager", manager):
            req = _request("/h")
            await handler(req)
            await handler(req)

        assert calls == [1]

    async def test_request_from_kwargs(self, fake_cache):
        cache, manager = fake_cache
        calls = []

        @cache_decorator.cache_response(ttl=10)
        async def handler(request=None):
            calls.append(1)
            return {"ok": True}

        with patch.object(cache_decorator, "get_cache_manager", manager):
            await handler(request=_request("/h"))
            await handler(request=_request("/h"))

        assert calls == [1]

    async def test_non_request_kwarg_ignored(self, fake_cache):
        cache, manager = fake_cache
        calls = []

        @cache_decorator.cache_response(ttl=10)
        async def handler(request=None):
            calls.append(1)
            return {"ok": True}

        with patch.object(cache_decorator, "get_cache_manager", manager):
            await handler(request={"not": "a request"})
            await handler(request={"not": "a request"})

        # 非 Request 值按普通参数参与键，同参数仍命中缓存
        assert calls == [1]

    async def test_invalidate_on_true(self, fake_cache):
        cache, manager = fake_cache

        @cache_decorator.cache_response(ttl=10, key_prefix="conv", invalidate_on=lambda *a, **k: True)
        async def handler():
            return {"ok": True}

        with patch.object(cache_decorator, "get_cache_manager", manager):
            await handler()

        assert cache.invalidated == ["conv:*"]

    async def test_cached_response_payload_unwrapped(self, fake_cache):
        cache, manager = fake_cache
        key = cache_decorator._generate_cache_key("api", "handler", (), {})
        cache.store[key] = {"_cached_response": {"cached": True}}

        @cache_decorator.cache_response(ttl=10)
        async def handler():
            raise AssertionError("缓存命中不应执行函数")

        with patch.object(cache_decorator, "get_cache_manager", manager):
            assert await handler() == {"cached": True}

    async def test_plain_cached_value_returned(self, fake_cache):
        cache, manager = fake_cache
        key = cache_decorator._generate_cache_key("api", "handler", (), {})
        cache.store[key] = [1, 2, 3]

        @cache_decorator.cache_response(ttl=10)
        async def handler():
            raise AssertionError("缓存命中不应执行函数")

        with patch.object(cache_decorator, "get_cache_manager", manager):
            assert await handler() == [1, 2, 3]

    async def test_exception_propagates(self, fake_cache):
        cache, manager = fake_cache

        @cache_decorator.cache_response(ttl=10)
        async def handler():
            raise RuntimeError("boom")

        with patch.object(cache_decorator, "get_cache_manager", manager):
            with pytest.raises(RuntimeError, match="boom"):
                await handler()

    async def test_response_status_used(self, fake_cache):
        cache, manager = fake_cache
        calls = []

        @cache_decorator.cache_response(ttl=10)
        async def handler():
            calls.append(len(calls) + 1)
            return JSONResponse({"n": calls[-1]}, status_code=201)

        with patch.object(cache_decorator, "get_cache_manager", manager):
            await handler()
            await handler()

        # Response 对象不写入缓存
        assert cache.written == []
        assert calls == [1, 2]

    async def test_dict_status_code_controls_caching(self, fake_cache):
        cache, manager = fake_cache
        calls = []

        @cache_decorator.cache_response(ttl=10)
        async def handler():
            calls.append(len(calls) + 1)
            return {"status_code": 404}

        with patch.object(cache_decorator, "get_cache_manager", manager):
            await handler()
            await handler()

        assert cache.written == []
        assert calls == [1, 2]

    async def test_condition_blocks_write(self, fake_cache):
        cache, manager = fake_cache

        @cache_decorator.cache_response(ttl=10, condition=lambda: False)
        async def handler():
            return {"ok": True}

        with patch.object(cache_decorator, "get_cache_manager", manager):
            await handler()

        assert cache.written == []

    async def test_none_not_cached_when_disabled(self, fake_cache):
        cache, manager = fake_cache

        @cache_decorator.cache_response(ttl=10, cache_none=False)
        async def handler():
            return None

        with patch.object(cache_decorator, "get_cache_manager", manager):
            assert await handler() is None

        assert cache.written == []

    async def test_none_cached_by_default(self, fake_cache):
        cache, manager = fake_cache

        @cache_decorator.cache_response(ttl=10)
        async def handler():
            return None

        with patch.object(cache_decorator, "get_cache_manager", manager):
            await handler()

        assert len(cache.written) == 1


class TestInvalidateDecorators:
    async def test_invalidate_cache_runs_finally_on_error(self, monkeypatch):
        cache = _FakeCache()

        async def manager():
            return cache

        monkeypatch.setattr(cache_decorator, "get_cache_manager", manager)

        @cache_decorator.invalidate_cache(key_prefix="conv")
        async def handler():
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError):
            await handler()

        assert cache.invalidated == ["conv:*"]

    async def test_invalidate_cache_custom_pattern(self, monkeypatch):
        cache = _FakeCache()

        async def manager():
            return cache

        monkeypatch.setattr(cache_decorator, "get_cache_manager", manager)

        @cache_decorator.invalidate_cache(key_prefix="conv", pattern="conv:u=1:*")
        async def handler():
            return "ok"

        assert await handler() == "ok"
        assert cache.invalidated == ["conv:u=1:*"]

    async def test_invalidate_by_prefix_default_pattern(self, monkeypatch):
        cache = _FakeCache()

        async def manager():
            return cache

        monkeypatch.setattr(cache_decorator, "get_cache_manager", manager)

        assert await cache_decorator.invalidate_cache_by_prefix("conv") == 0
        assert cache.invalidated == ["conv:*"]

    async def test_invalidate_by_prefix_custom_pattern(self, monkeypatch):
        cache = _FakeCache()

        async def manager():
            return cache

        monkeypatch.setattr(cache_decorator, "get_cache_manager", manager)

        await cache_decorator.invalidate_cache_by_prefix("conv", "conv:special:*")

        assert cache.invalidated == ["conv:special:*"]
