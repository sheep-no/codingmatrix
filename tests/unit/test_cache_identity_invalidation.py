"""按用户失效缓存必须真的命中目标用户的条目。

回归的缺陷：缓存键把用户身份藏在 md5 摘要里，而 invalidate_user_cache 用
``user:{id}:*`` / ``profile:{id}:*`` 做模式匹配，永远不会命中任何键，
是恒为空的无效调用；且调用方传入的是 email，与键身份（用户 id）不一致。
"""

import pytest

from app.utils import cache as cache_module
from app.utils import cache_decorator
from app.utils.cache import MemoryCache, RedisCacheManager, invalidate_user_cache


def _key_for(prefix: str, identity: str, func_name: str = "get_user_profile") -> str:
    return cache_decorator._generate_cache_key(
        prefix, func_name, (), {"token": {"sub": identity}}
    )


def test_cache_key_exposes_identity_as_matchable_segment():
    key = _key_for("profile", "42")

    assert key.startswith("profile:u=42:")
    # 身份段可被按用户失效的模式命中
    assert MemoryCache._match_pattern(key, "profile:u=42:*")
    assert not MemoryCache._match_pattern(key, "profile:u=43:*")


def test_anonymous_cache_key_has_no_identity_segment():
    key = cache_decorator._generate_cache_key("public", "get_public", (), {})

    assert key.startswith("public:")
    assert ":u=" not in key


@pytest.mark.asyncio
async def test_invalidate_user_cache_removes_only_target_user(monkeypatch):
    manager = RedisCacheManager(redis_url=None)

    async def fake_manager():
        return manager

    monkeypatch.setattr(cache_module, "get_cache_manager", fake_manager)

    alice_profile = _key_for("profile", "1")
    alice_other = _key_for("profile", "1", func_name="get_other")
    bob_profile = _key_for("profile", "2")
    for key in (alice_profile, alice_other, bob_profile):
        await manager.set(key, {"ok": True}, ttl=60)

    removed = await invalidate_user_cache("1")

    assert removed == 2
    assert await manager.get(alice_profile) is None
    assert await manager.get(alice_other) is None
    assert await manager.get(bob_profile) == {"ok": True}


@pytest.mark.asyncio
async def test_prefix_invalidation_still_covers_identity_keys():
    manager = RedisCacheManager(redis_url=None)
    for user_id in ("1", "2"):
        await manager.set(_key_for("profile", user_id), {"id": user_id}, ttl=60)

    removed = await manager.invalidate_pattern("profile:*")

    assert removed == 2
    assert await manager.get(_key_for("profile", "1")) is None
