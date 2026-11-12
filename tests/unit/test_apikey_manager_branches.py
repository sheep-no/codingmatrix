"""APIKeyManager 全分支回归。"""

import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import pytest

from app.services import apikey_manager as ak

TOKEN = "t" * 32
OTHER_TOKEN = "u" * 32


class FakeRedis:
    """最小 Redis 语义实现，覆盖 manager 使用到的命令。"""

    def __init__(self):
        self.values = {}
        self.sets = {}
        self.ttls = {}
        self.eval_result = None
        self.raise_on_get = False
        self.scan_error = None
        self.ttl_error = None
        self.scan_pages = []

    def get(self, key):
        if self.raise_on_get:
            raise RuntimeError("redis down")
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value
        self.ttls[key] = -1

    def setex(self, key, ttl, value):
        self.values[key] = value
        self.ttls[key] = ttl

    def delete(self, key):
        self.values.pop(key, None)
        self.sets.pop(key, None)
        self.ttls.pop(key, None)

    def smembers(self, key):
        return set(self.sets.get(key, set()))

    def sismember(self, key, member):
        return member in self.sets.get(key, set())

    def srem(self, key, member):
        self.sets.get(key, set()).discard(member)

    def scard(self, key):
        return len(self.sets.get(key, set()))

    def ttl(self, key):
        if self.ttl_error:
            raise self.ttl_error
        return self.ttls.get(key, -2)

    def scan(self, cursor, match=None, count=100):
        if self.scan_error:
            error, self.scan_error = self.scan_error, None
            raise error
        if self.scan_pages:
            return self.scan_pages.pop(0)
        if cursor != 0:
            return 0, []
        prefix = match.replace("*", "") if match else ""
        keys = [k for k in self.sets if k.startswith(prefix)]
        return 0, keys

    def eval(self, script, numkeys, index_key, max_keys, token, ttl):
        if self.eval_result is not None:
            return self.eval_result
        members = self.sets.setdefault(index_key, set())
        if len(members) >= int(max_keys):
            return -1
        existed = index_key in self.sets
        added = token not in members
        members.add(token)
        desired = int(ttl) + 86400
        current = self.ttls.get(index_key, -2)
        if not existed or current != -1:
            if desired > current:
                self.ttls[index_key] = desired
        return 1 if added else 0


@pytest.fixture
def redis():
    return FakeRedis()


@pytest.fixture
def manager(redis, monkeypatch):
    monkeypatch.setattr(ak, "encrypt_secret", lambda value, aad: f"enc({aad})::{value}")
    def _decrypt(value, aad):
        prefix = f"enc({aad})::"
        if not value.startswith(prefix):
            raise ValueError("bad aad")
        return value[len(prefix):]
    monkeypatch.setattr(ak, "decrypt_secret", _decrypt)
    return ak.APIKeyManager(redis_client=redis)


def _meta(**overrides):
    data = dict(
        token=TOKEN,
        provider="openai",
        remark="r",
        status="verified",
        created_at=datetime.now(timezone.utc).isoformat(),
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        ttl_seconds=3600,
        enabled=True,
        context_lengths={"m": 100},
        fallback_preference="custom",
        custom_fallback_chain=["a"],
    )
    data.update(overrides)
    return ak.KeyMetadata(**data)


def _seed(redis, user_id, token=TOKEN, meta=None, api_key="sk"):
    redis.values[f"apikey:{user_id}:{token}"] = ak._SECRET_PREFIX + ak.encrypt_secret(
        api_key, f"apikey:{user_id}:{token}"
    )
    redis.ttls[f"apikey:{user_id}:{token}"] = 3600
    redis.values[f"apikey_meta:{user_id}:{token}"] = json.dumps(asdict(meta or _meta(token=token)))
    redis.ttls[f"apikey_meta:{user_id}:{token}"] = 3600
    redis.sets.setdefault(f"apikey_index:{user_id}", set()).add(token)
    redis.values[f"apikey:token:{token}"] = user_id


class TestResolveTTL:
    @pytest.mark.parametrize("value,expected", [("1h", 3600), ("24h", 86400), ("never", 315360000), ("120", 120), (60, 60), (60.9, 60)])
    def test_valid(self, value, expected):
        assert ak.resolve_ttl(value) == expected

    @pytest.mark.parametrize("value", ["0", "-1", 0, -5, 315360001, "315360001"])
    def test_out_of_range(self, value):
        with pytest.raises(ValueError):
            ak.resolve_ttl(value)

    def test_invalid_string(self):
        with pytest.raises(ValueError) as exc:
            ak.resolve_ttl("abc")
        assert "无效的 TTL 选项" in str(exc.value)

    def test_invalid_type(self):
        with pytest.raises(ValueError) as exc:
            ak.resolve_ttl(None)
        assert "TTL 类型无效" in str(exc.value)


class TestStoreKey:
    def test_unsupported_provider(self, manager):
        with pytest.raises(ValueError):
            manager.store_key("u", "bad", "sk", "1h")

    def test_limit_exceeded(self, manager, redis):
        redis.eval_result = -1
        with pytest.raises(RuntimeError) as exc:
            manager.store_key("u", "openai", "sk", "1h")
        assert "最大 Key" in str(exc.value)

    def test_success_persists_all_entries(self, manager, redis):
        token = manager.store_key("u", "openai", "sk-abc", "1h", "note")
        assert redis.values[f"apikey:u:{token}"].startswith(ak._SECRET_PREFIX)
        assert json.loads(redis.values[f"apikey_meta:u:{token}"])["remark"] == "note"
        assert redis.values[f"apikey:token:{token}"] == "u"
        assert token in redis.sets["apikey_index:u"]
        assert redis.ttls[f"apikey:token:{token}"] == 3600 + 86400
        assert manager.get_key("u", token) == "sk-abc"

    def test_index_ttl_keeps_longer_value(self, manager, redis):
        manager.store_key("u", "openai", "sk1", "24h")
        manager.store_key("u", "openai", "sk2", "1h")
        assert redis.ttls["apikey_index:u"] == 86400 + 86400


class TestGetKey:
    def test_missing_cleans_meta(self, manager, redis):
        redis.sets["apikey_index:u"] = {TOKEN}
        assert manager.get_key("u", TOKEN) is None
        assert TOKEN not in redis.sets["apikey_index:u"]

    def test_legacy_plaintext_passthrough(self, manager, redis):
        redis.values[f"apikey:u:{TOKEN}"] = "plain"
        assert manager.get_key("u", TOKEN) == "plain"

    def test_bytes_value(self, manager, redis):
        redis.values[f"apikey:u:{TOKEN}"] = b"legacy"
        assert manager.get_key("u", TOKEN) == "legacy"

    def test_decrypt_failure_returns_none(self, manager, redis, monkeypatch):
        redis.values[f"apikey:u:{TOKEN}"] = ak._SECRET_PREFIX + "garbage"
        assert manager.get_key("u", TOKEN) is None


class TestGetMetadata:
    def test_missing(self, manager):
        assert manager.get_metadata("u", TOKEN) is None

    def test_valid(self, manager, redis):
        _seed(redis, "u")
        assert manager.get_metadata("u", TOKEN).token == TOKEN

    def test_corrupted_json(self, manager, redis):
        redis.values[f"apikey_meta:u:{TOKEN}"] = "{broken"
        assert manager.get_metadata("u", TOKEN) is None

    def test_expired_cleans_index(self, manager, redis):
        expired = _meta(expires_at=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat())
        _seed(redis, "u", meta=expired)
        assert manager.get_metadata("u", TOKEN) is None
        assert TOKEN not in redis.sets["apikey_index:u"]
        assert f"apikey_meta:u:{TOKEN}" not in redis.values


class TestSaveMeta:
    def test_persistent_meta_uses_set(self, manager, redis):
        redis.values["apikey_meta:u:t"] = "{}"
        redis.ttls["apikey_meta:u:t"] = -1
        manager._save_meta("u", "t", _meta())
        assert "expires_at" in redis.values["apikey_meta:u:t"]

    def test_ttl_meta_uses_setex(self, manager, redis):
        redis.values["apikey_meta:u:t"] = "{}"
        redis.ttls["apikey_meta:u:t"] = 60
        manager._save_meta("u", "t", _meta())
        assert redis.ttls["apikey_meta:u:t"] == 60

    def test_missing_meta_is_skipped(self, manager, redis):
        manager._save_meta("u", "t", _meta())
        assert "apikey_meta:u:t" not in redis.values


class TestListKeys:
    def test_sorted_and_skips_missing(self, manager, redis):
        _seed(redis, "u", TOKEN, _meta(token=TOKEN, created_at="2026-01-01T00:00:00+00:00"))
        _seed(redis, "u", OTHER_TOKEN, _meta(token=OTHER_TOKEN, created_at="2026-02-01T00:00:00+00:00"))
        redis.sets["apikey_index:u"].add(b"x" * 32)
        result = manager.list_keys("u")
        assert [m.token for m in result] == [OTHER_TOKEN, TOKEN]

    def test_bytes_tokens(self, manager, redis):
        _seed(redis, "u")
        redis.sets["apikey_index:u"] = {TOKEN.encode()}
        assert manager.list_keys("u")[0].token == TOKEN


class TestReverseLookups:
    def test_context_lengths_short_token(self, manager):
        assert manager.get_context_lengths_by_token("short") is None
        assert manager.get_context_lengths_by_token(None) is None

    def test_context_lengths_fast_path(self, manager, redis):
        _seed(redis, "u")
        assert manager.get_context_lengths_by_token(TOKEN) == {"m": 100}

    def test_context_lengths_fast_path_empty(self, manager, redis):
        _seed(redis, "u", meta=_meta(context_lengths={}))
        assert manager.get_context_lengths_by_token(TOKEN) is None

    def test_context_lengths_scan_path(self, manager, redis):
        _seed(redis, "u")
        redis.values.pop(f"apikey:token:{TOKEN}")
        assert manager.get_context_lengths_by_token(TOKEN) == {"m": 100}

    def test_context_lengths_scan_bytes_index_and_no_match(self, manager, redis):
        redis.sets["apikey_index:u"] = {OTHER_TOKEN.encode()}
        assert manager.get_context_lengths_by_token(TOKEN) is None

    def test_context_lengths_scan_multiple_pages(self, manager, redis):
        _seed(redis, "u")
        redis.values.pop(f"apikey:token:{TOKEN}")
        redis.scan_pages = [(5, []), (0, ["apikey_index:u"])]
        assert manager.get_context_lengths_by_token(TOKEN) == {"m": 100}

    def test_context_lengths_scan_match_without_config(self, manager, redis):
        _seed(redis, "u", meta=_meta(context_lengths={}))
        redis.values.pop(f"apikey:token:{TOKEN}")
        assert manager.get_context_lengths_by_token(TOKEN) is None

    def test_context_lengths_reverse_error_falls_back(self, manager, redis, monkeypatch):
        def _boom(*args):
            raise RuntimeError("down")

        monkeypatch.setattr(redis, "get", _boom)
        assert manager.get_context_lengths_by_token(TOKEN) is None

    def test_get_key_by_token_short(self, manager):
        assert manager.get_key_by_token("short") is None
        assert manager.get_key_by_token("") is None

    def test_get_key_by_token_fast(self, manager, redis):
        _seed(redis, "u", api_key="sk-fast")
        assert manager.get_key_by_token(TOKEN) == "sk-fast"

    def test_get_key_by_token_scan_backfills(self, manager, redis):
        _seed(redis, "u", api_key="sk-scan")
        redis.values.pop(f"apikey:token:{TOKEN}")
        assert manager.get_key_by_token(TOKEN) == "sk-scan"
        assert redis.values[f"apikey:token:{TOKEN}"] == "u"

    def test_get_key_by_token_scan_no_ttl(self, manager, redis):
        _seed(redis, "u", api_key="sk")
        redis.values.pop(f"apikey:token:{TOKEN}")
        redis.ttls[f"apikey:u:{TOKEN}"] = -1
        assert manager.get_key_by_token(TOKEN) == "sk"
        assert f"apikey:token:{TOKEN}" not in redis.values

    def test_get_key_by_token_scan_ttl_error(self, manager, redis):
        _seed(redis, "u", api_key="sk")
        redis.values.pop(f"apikey:token:{TOKEN}")
        redis.ttl_error = RuntimeError("ttl down")
        assert manager.get_key_by_token(TOKEN) == "sk"

    def test_get_key_by_token_reverse_error(self, manager, redis, monkeypatch):
        def _boom(*args):
            raise RuntimeError("down")

        monkeypatch.setattr(redis, "get", _boom)
        assert manager.get_key_by_token(TOKEN) is None

    def test_get_key_by_token_no_match(self, manager, redis):
        redis.sets["apikey_index:u"] = {OTHER_TOKEN}
        assert manager.get_key_by_token(TOKEN) is None

    def test_get_key_by_token_scan_multiple_pages(self, manager, redis):
        _seed(redis, "u", api_key="sk-page")
        redis.values.pop(f"apikey:token:{TOKEN}")
        redis.scan_pages = [(5, []), (0, ["apikey_index:u"])]
        assert manager.get_key_by_token(TOKEN) == "sk-page"

    def test_fallback_preference_short(self, manager):
        assert manager.get_fallback_preference_by_token("short") is None

    def test_fallback_preference_fast(self, manager, redis):
        _seed(redis, "u")
        assert manager.get_fallback_preference_by_token(TOKEN) == {
            "fallback_preference": "custom",
            "custom_fallback_chain": ["a"],
        }

    def test_fallback_preference_missing_meta(self, manager, redis):
        redis.values[f"apikey:token:{TOKEN}"] = "u"
        assert manager.get_fallback_preference_by_token(TOKEN) is None

    def test_fallback_preference_without_reverse_index(self, manager):
        assert manager.get_fallback_preference_by_token(TOKEN) is None

    def test_fallback_preference_no_meta(self, manager, redis):
        _seed(redis, "u")
        redis.values.pop(f"apikey_meta:u:{TOKEN}")
        assert manager.get_fallback_preference_by_token(TOKEN) is None

    def test_fallback_preference_error(self, manager, redis, monkeypatch):
        def _boom(*args):
            raise RuntimeError("down")

        monkeypatch.setattr(redis, "get", _boom)
        assert manager.get_fallback_preference_by_token(TOKEN) is None


class TestMutations:
    def test_delete_key(self, manager, redis):
        _seed(redis, "u")
        assert manager.delete_key("u", TOKEN) is True
        assert f"apikey:u:{TOKEN}" not in redis.values
        assert f"apikey_meta:u:{TOKEN}" not in redis.values
        assert TOKEN not in redis.sets["apikey_index:u"]
        assert f"apikey:token:{TOKEN}" not in redis.values

    def test_update_status(self, manager, redis):
        _seed(redis, "u")
        assert manager.update_status("u", TOKEN, "invalid") is True
        assert manager.get_metadata("u", TOKEN).status == "invalid"

    def test_update_status_missing(self, manager):
        assert manager.update_status("u", TOKEN, "invalid") is False

    def test_update_enabled(self, manager, redis):
        _seed(redis, "u")
        assert manager.update_enabled("u", TOKEN, False) is True
        assert manager.get_metadata("u", TOKEN).enabled is False

    def test_update_enabled_missing(self, manager):
        assert manager.update_enabled("u", TOKEN, False) is False

    def test_update_context_lengths(self, manager, redis):
        _seed(redis, "u")
        assert manager.update_context_lengths("u", TOKEN, {"x": 1}) is True
        assert manager.get_metadata("u", TOKEN).context_lengths == {"x": 1}

    def test_update_context_lengths_none(self, manager, redis):
        _seed(redis, "u")
        assert manager.update_context_lengths("u", TOKEN, None) is True
        assert manager.get_metadata("u", TOKEN).context_lengths == {}

    def test_update_context_lengths_missing(self, manager):
        assert manager.update_context_lengths("u", TOKEN, {}) is False

    def test_update_fallback_invalid(self, manager):
        with pytest.raises(ValueError):
            manager.update_fallback_preference("u", TOKEN, "bad")

    def test_update_fallback_custom(self, manager, redis):
        _seed(redis, "u")
        assert manager.update_fallback_preference("u", TOKEN, "custom", ["b"]) is True
        meta = manager.get_metadata("u", TOKEN)
        assert meta.fallback_preference == "custom"
        assert meta.custom_fallback_chain == ["b"]

    def test_update_fallback_custom_without_chain_keeps_old(self, manager, redis):
        _seed(redis, "u")
        assert manager.update_fallback_preference("u", TOKEN, "custom") is True
        assert manager.get_metadata("u", TOKEN).custom_fallback_chain == ["a"]

    def test_update_fallback_non_custom_clears_chain(self, manager, redis):
        _seed(redis, "u")
        assert manager.update_fallback_preference("u", TOKEN, "disabled") is True
        meta = manager.get_metadata("u", TOKEN)
        assert meta.fallback_preference == "disabled"
        assert meta.custom_fallback_chain == []

    def test_update_fallback_missing(self, manager):
        assert manager.update_fallback_preference("u", TOKEN, "custom", ["a"]) is False


class TestGetAllEnabledKeys:
    def test_filters_disabled_invalid_and_missing_key(self, manager, redis):
        _seed(redis, "u1", TOKEN, _meta(token=TOKEN, status="verified"))
        _seed(redis, "u2", OTHER_TOKEN, _meta(token=OTHER_TOKEN, status="invalid"))
        redis.sets["apikey_index:u1"].add("missing" * 6)
        result = manager.get_all_enabled_keys()
        assert result == [("u1", TOKEN, "openai", "sk")]

    def test_skips_falsy_api_key(self, manager, redis):
        _seed(redis, "u", meta=_meta(status="unverified"))
        redis.values[f"apikey:u:{TOKEN}"] = "plain-empty"
        redis.values[f"apikey:u:{TOKEN}"] = ""
        assert manager.get_all_enabled_keys() == []

    def test_bytes_index_and_token(self, manager, redis):
        _seed(redis, "u")
        redis.sets["apikey_index:u"] = {TOKEN.encode()}
        redis.sets["apikey_index:u"] = {TOKEN.encode()}
        result = manager.get_all_enabled_keys()
        assert result and result[0][1] == TOKEN

    def test_scan_multiple_pages(self, manager, redis):
        _seed(redis, "u")
        redis.scan_pages = [(5, []), (0, ["apikey_index:u"])]
        result = manager.get_all_enabled_keys()
        assert result == [("u", TOKEN, "openai", "sk")]


class TestModuleHelpers:
    def test_get_apikey_manager_cached(self, redis):
        original = ak._apikey_manager
        try:
            ak._apikey_manager = None
            first = ak.get_apikey_manager(redis)
            second = ak.get_apikey_manager(redis)
            assert first is second
        finally:
            ak._apikey_manager = original

    def test_get_apikey_manager_double_checked_lock(self, redis):
        original = ak._apikey_manager

        class _Lock:
            def __enter__(self):
                ak._apikey_manager = "already-set"

            def __exit__(self, *args):
                return False

        try:
            ak._apikey_manager = None
            original_lock = ak._apikey_manager_lock
            ak._apikey_manager_lock = _Lock()
            assert ak.get_apikey_manager(redis) == "already-set"
        finally:
            ak._apikey_manager_lock = original_lock
            ak._apikey_manager = original

    def test_get_apikey_manager_builds_default_client(self, redis, monkeypatch):
        original = ak._apikey_manager
        monkeypatch.setattr(ak, "_build_default_redis_client", lambda: redis)
        try:
            ak._apikey_manager = None
            assert ak.get_apikey_manager() is not None
            assert ak._apikey_manager.redis is redis
        finally:
            ak._apikey_manager = original

    def test_build_default_redis_client_with_url(self, monkeypatch):
        monkeypatch.setattr(ak.settings, "REDIS_URL", "redis://example:6379/0")
        called = {}

        def _from_url(url, decode_responses=False):
            called["url"] = url
            return "client"

        monkeypatch.setattr(ak.redis, "from_url", _from_url)
        assert ak._build_default_redis_client() == "client"
        assert called["url"] == "redis://example:6379/0"

    def test_build_default_redis_client_without_url(self, monkeypatch):
        monkeypatch.setattr(ak.settings, "REDIS_URL", "")
        called = {}

        def _redis(**kwargs):
            called.update(kwargs)
            return "client"

        monkeypatch.setattr(ak.redis, "Redis", _redis)
        assert ak._build_default_redis_client() == "client"
        assert called["host"] == "localhost"

    def test_init_and_module_get_key(self, redis):
        original = ak._apikey_manager
        try:
            ak.init_apikey_manager(redis)
            _seed(redis, "u", api_key="sk-module")
            assert ak.get_key_by_token(TOKEN) == "sk-module"
        finally:
            ak._apikey_manager = original

    def test_module_get_metadata_by_token(self, redis):
        original = ak._apikey_manager
        try:
            ak.init_apikey_manager(redis)
            _seed(redis, "u")
            assert ak.get_metadata_by_token(TOKEN)["provider"] == "openai"
            assert ak.get_metadata_by_token(OTHER_TOKEN) is None
        finally:
            ak._apikey_manager = original

    def test_module_get_metadata_by_token_missing_meta(self, redis):
        original = ak._apikey_manager
        try:
            ak.init_apikey_manager(redis)
            redis.values[f"apikey:token:{TOKEN}"] = "u"
            assert ak.get_metadata_by_token(TOKEN) is None
        finally:
            ak._apikey_manager = original
