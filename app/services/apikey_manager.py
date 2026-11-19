"""
API Key 管理器

将用户的 API Key 安全存储在 Redis 中：
- Key 不落库，仅存 Redis 内存
- Key 以 RSA 包裹的 AES-256-GCM 信封落 Redis，明文不出现在存储层
- TTL 到期自动删除
- 支持多供应商、多 Key 管理
"""
import json
import logging
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

import redis

from app.core.config import settings
from app.utils.crypto import decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)

# 加密信封标记：带此前缀的值经 encrypt_secret 加密；无前缀视为历史明文，读取时透传
_SECRET_PREFIX = "v1:"

# Redis Lua 脚本：原子性检查 Key 数量限制并添加 Token
# 避免并发请求绕过 max_keys 限制的竞态条件
_CHECK_AND_ADD_SCRIPT = """
local index_key = KEYS[1]
local max_keys = tonumber(ARGV[1])
local token = ARGV[2]
local ttl_seconds = tonumber(ARGV[3])

local token_count = redis.call('SCARD', index_key)
if token_count >= max_keys then
    return -1  -- 超过限制
end

local existed = redis.call('EXISTS', index_key)
local added = redis.call('SADD', index_key, token)

-- 索引过期时间取当前值与目标值的较大者。若每次都用新 key 的 TTL 覆盖，
-- 先存的长效 key 会因为后存的短效 key 缩短索引寿命，索引过期后彻底
-- 从 list_keys 消失（key 本体仍在 Redis，成为不可管理的幽灵）。
local desired_ttl = ttl_seconds + 86400
local current_ttl = redis.call('TTL', index_key)
-- current_ttl == -1 且索引此前已存在，说明索引被设为永久，不再附加过期
if existed == 0 or current_ttl ~= -1 then
    if desired_ttl > current_ttl then
        redis.call('EXPIRE', index_key, desired_ttl)
    end
end

if added == 1 then
    return 1  -- 添加成功
end
return 0  -- Token 已存在
"""


@dataclass
class KeyMetadata:
    """API Key 元数据"""
    token: str
    provider: str
    remark: str
    status: str  # unverified, verified, invalid, expired
    created_at: str
    expires_at: str
    ttl_seconds: int
    enabled: bool = True
    context_lengths: dict = None  # 用户自定义的模型 context_length 配置 {model_id: context_length}
    fallback_preference: str = "use_admin_default"  # use_admin_default | custom | disabled
    custom_fallback_chain: list = None  # 用户自定义降级链（仅 fallback_preference="custom" 时生效）
    
    def __post_init__(self):
        if self.context_lengths is None:
            self.context_lengths = {}
        if self.custom_fallback_chain is None:
            self.custom_fallback_chain = []


# 供应商列表
SUPPORTED_PROVIDERS = [
    "siliconflow",
    "openai",
    "anthropic",
    "bailian",      # 阿里百炼
    "glm",          # 智谱 GLM
    "deepseek",
]

# TTL 选项（秒）
# 支持预设选项和自定义秒数
# "never" 表示永久（使用一个非常大的值，约 10 年）
TTL_OPTIONS = {
    "1h": 3600,
    "24h": 86400,
    "7d": 604800,
    "30d": 2592000,
    "never": 315360000,  # 10 年，近似永久
}

# 最大自定义 TTL（秒）- 限制用户不能设置超过 10 年
MAX_CUSTOM_TTL = 315360000

def resolve_ttl(ttl_input) -> int:
    """
    解析 TTL 输入，支持预设选项或自定义秒数
    
    Args:
        ttl_input: 可以是预设选项字符串（如 "24h"）或自定义秒数（int）
    
    Returns:
        TTL 秒数
    
    Raises:
        ValueError: 输入无效
    """
    if isinstance(ttl_input, str):
        # 预设选项
        if ttl_input in TTL_OPTIONS:
            return TTL_OPTIONS[ttl_input]
        # 尝试解析为数字字符串（自定义秒数）
        try:
            custom_seconds = int(ttl_input)
            if custom_seconds <= 0:
                raise ValueError("TTL 必须大于 0")
            if custom_seconds > MAX_CUSTOM_TTL:
                raise ValueError(f"自定义 TTL 不能超过 {MAX_CUSTOM_TTL} 秒（约 10 年）")
            return custom_seconds
        except ValueError as e:
            if "invalid literal" in str(e):
                raise ValueError(f"无效的 TTL 选项：{ttl_input}，可选：{list(TTL_OPTIONS.keys())} 或自定义秒数")
            raise
    elif isinstance(ttl_input, (int, float)):
        custom_seconds = int(ttl_input)
        if custom_seconds <= 0:
            raise ValueError("TTL 必须大于 0")
        if custom_seconds > MAX_CUSTOM_TTL:
            raise ValueError(f"自定义 TTL 不能超过 {MAX_CUSTOM_TTL} 秒（约 10 年）")
        return custom_seconds
    else:
        raise ValueError("TTL 类型无效，必须是字符串或整数")

MAX_KEYS_PER_USER = 20


class APIKeyManager:
    """API Key 管理器"""
    
    def __init__(
        self,
        redis_client: redis.Redis,
        max_keys_per_user: int = MAX_KEYS_PER_USER,
        legacy_redis_client: Optional[redis.Redis] = None,
    ):
        self.redis = redis_client
        # 迁移期只读回退：新实例缺少的条目从旧共享 Redis 读取并回填，
        # 避免切换存储后用户的 Key 突然“消失”。
        self.legacy_redis = legacy_redis_client
        self.max_keys = max_keys_per_user

    def _stores(self) -> List[redis.Redis]:
        stores = [self.redis]
        if self.legacy_redis is not None:
            stores.append(self.legacy_redis)
        return stores

    def _read_key(self, key: str):
        value = self.redis.get(key)
        legacy = self.legacy_redis
        if value is None and legacy is not None:
            value = legacy.get(key)
            if value is not None:
                self._backfill(legacy, key, value)
        return value

    def _backfill(self, legacy: redis.Redis, key: str, value) -> None:
        try:
            ttl = legacy.ttl(key)
            if ttl == -1:
                self.redis.set(key, value)
            elif ttl > 0:
                self.redis.setex(key, ttl, value)
        except Exception as e:
            logger.warning(f"API Key 迁移回填失败（读取仍可用）: {e}")

    def _delete_everywhere(self, *keys: str) -> None:
        for store in self._stores():
            store.delete(*keys)

    def _tokens_for_index(self, index_key: str) -> set[str]:
        tokens: set[str] = set()
        for store in self._stores():
            tokens.update(
                item.decode("utf-8") if isinstance(item, bytes) else item
                for item in store.smembers(index_key)
            )
        return tokens

    def _scan_index_keys(self):
        seen: set[str] = set()
        for store in self._stores():
            cursor = 0
            while True:
                cursor, keys = store.scan(cursor, match="apikey_index:*", count=100)
                for key in keys:
                    key_str = key.decode("utf-8") if isinstance(key, bytes) else key
                    if key_str not in seen:
                        seen.add(key_str)
                        yield key_str
                if cursor == 0:
                    break
    
    def _key_token(self, user_id: str, token: str) -> str:
        """Redis 键：存储 API Key"""
        return f"apikey:{user_id}:{token}"

    def _secret_aad(self, user_id: str, token: str) -> str:
        """API Key 信封的附加认证数据，绑定用户与 Token，防止跨条目重放。"""
        return f"apikey:{user_id}:{token}"
    
    def _key_meta(self, user_id: str, token: str) -> str:
        """Redis 键：存储元数据"""
        return f"apikey_meta:{user_id}:{token}"
    
    def _key_index(self, user_id: str) -> str:
        """Redis 键：用户索引"""
        return f"apikey_index:{user_id}"

    def _key_token_reverse(self, token: str) -> str:
        """Redis 键：token → user_id 反向索引（O(1) 查找）"""
        return f"apikey:token:{token}"
    
    def store_key(
        self,
        user_id: str,
        provider: str,
        api_key: str,
        ttl: str,
        remark: str = ""
    ) -> str:
        """
        存储 API Key 到 Redis
        
        Args:
            user_id: 用户 ID
            provider: 供应商名称
            api_key: 解密后的 API Key
            ttl: TTL 选项 ("1h", "24h", "7d", "30d")
            remark: 备注
            
        Returns:
            生成的 Token
            
        Raises:
            ValueError: 参数无效
            RuntimeError: 超过 Key 数量限制
        """
        # 验证参数
        if provider not in SUPPORTED_PROVIDERS:
            raise ValueError(f"不支持的供应商：{provider}")
        
        ttl_seconds = resolve_ttl(ttl)
        
        # 生成 Token（提前生成，因为 Lua 脚本需要它）
        token = str(uuid.uuid4())
        
        # 原子性检查用户 Key 数量限制并添加 Token（使用 Lua 脚本避免竞态条件）
        index_key = self._key_index(user_id)
        result = self.redis.eval(
            _CHECK_AND_ADD_SCRIPT,
            1,  # 1 个 key 参数
            index_key,
            str(self.max_keys),
            token,
            str(ttl_seconds)
        )
        
        if result == -1:
            raise RuntimeError(f"已达到最大 Key 数量限制 ({self.max_keys})")
        
        # 计算过期时间
        now = datetime.now(timezone.utc)
        expires_at = now.timestamp() + ttl_seconds
        expires_at_str = datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat()
        
        # 存储 API Key
        key_name = self._key_token(user_id, token)
        self.redis.setex(
            key_name,
            ttl_seconds,
            _SECRET_PREFIX + encrypt_secret(api_key, self._secret_aad(user_id, token)),
        )
        
        # 存储元数据
        meta = KeyMetadata(
            token=token,
            provider=provider,
            remark=remark,
            status="unverified",
            created_at=now.isoformat(),
            expires_at=expires_at_str,
            ttl_seconds=ttl_seconds,
            enabled=True,
        )
        meta_name = self._key_meta(user_id, token)
        self.redis.setex(meta_name, ttl_seconds, json.dumps(asdict(meta)))

        # 写反向索引：token → user_id（O(1) 查找，避免 SCAN 全表扫）
        # TTL 比最长 TTL 多 1 天，保证 Key 过期后仍能找到 user_id 用于清理
        reverse_ttl = ttl_seconds + 86400
        self.redis.setex(self._key_token_reverse(token), reverse_ttl, user_id)

        # 注意：Token 已通过 Lua 脚本原子性地添加到用户索引，无需重复 sadd
        # Lua 脚本已设置索引的过期时间（比最长 TTL 多一天）
        logger.info(f"用户 {user_id} 存储 {provider} Key，Token: {token[:8]}...")
        return token
    
    def get_key(self, user_id: str, token: str) -> Optional[str]:
        """
        从 Redis 获取 API Key
        
        Args:
            user_id: 用户 ID
            token: Token
            
        Returns:
            API Key 或 None
        """
        key_name = self._key_token(user_id, token)
        api_key = self._read_key(key_name)
        
        if api_key is None:
            # Key 不存在或已过期
            self._cleanup_meta(user_id, token)
            return None
        
        stored = api_key.decode("utf-8") if isinstance(api_key, bytes) else api_key
        if not stored.startswith(_SECRET_PREFIX):
            # 历史明文条目：缓存写入前遗留，直接返回，随其 TTL 自然淘汰
            return stored
        try:
            return decrypt_secret(
                stored[len(_SECRET_PREFIX):], self._secret_aad(user_id, token)
            )
        except Exception as e:
            logger.error(f"用户 {user_id} 的 API Key 解密失败: {e}")
            return None
    
    def get_metadata(self, user_id: str, token: str) -> Optional[KeyMetadata]:
        """
        获取 API Key 元数据
        
        Args:
            user_id: 用户 ID
            token: Token
            
        Returns:
            KeyMetadata 或 None
        """
        meta_name = self._key_meta(user_id, token)
        meta_json = self._read_key(meta_name)
        
        if meta_json is None:
            return None
        
        try:
            meta_dict = json.loads(meta_json)
        except (ValueError, TypeError, KeyError) as e:
            # 单个损坏的元数据不应拖垮 list_keys/get_metadata 整体
            logger.warning(f"API Key 元数据损坏，已跳过: {e}")
            return None
        
        # 检查是否过期
        expires_at = datetime.fromisoformat(meta_dict["expires_at"])
        if expires_at < datetime.now(timezone.utc):
            meta_dict["status"] = "expired"
            self._cleanup_meta(user_id, token)
            return None
        
        return KeyMetadata(**meta_dict)

    def _save_meta(self, user_id: str, token: str, meta: KeyMetadata) -> None:
        """持久化元数据，保留原 TTL。

        `ttl == -1` 表示该元数据被设为无过期时间，此时必须用 SET 而非跳过，
        否则更新会被静默丢弃（`ttl > 0` 的旧逻辑只覆盖有过期时间的键）。
        """
        meta_name = self._key_meta(user_id, token)
        ttl = self.redis.ttl(meta_name)
        if ttl == -1:
            self.redis.set(meta_name, json.dumps(asdict(meta)))
        elif ttl > 0:
            self.redis.setex(meta_name, ttl, json.dumps(asdict(meta)))
    
    def list_keys(self, user_id: str) -> List[KeyMetadata]:
        """
        获取用户所有 API Key 的元数据列表
        
        Args:
            user_id: 用户 ID
            
        Returns:
            KeyMetadata 列表
        """
        index_key = self._key_index(user_id)

        tokens = self._tokens_for_index(index_key)
        if self.legacy_redis is not None and tokens:
            # 把旧索引成员补到新实例，避免旧实例过期后列表丢 Key
            self.redis.sadd(index_key, *tokens)
            legacy_ttl = self.legacy_redis.ttl(index_key)
            current_ttl = self.redis.ttl(index_key)
            if legacy_ttl > 0 and (current_ttl == -1 or legacy_ttl > current_ttl):
                self.redis.expire(index_key, legacy_ttl)

        result = []
        for token in tokens:
            meta = self.get_metadata(user_id, token)
            if meta is not None:
                result.append(meta)
        
        result.sort(key=lambda m: m.created_at, reverse=True)
        return result
    
    def get_context_lengths_by_token(self, token: str) -> dict:
        """根据 token 获取 context_lengths 配置（O(1) 反向索引查找）

        Args:
            token: API Key Token

        Returns:
            context_lengths dict 或 None
        """
        if not token or len(token) < 30:
            return None

        try:
            # 快速路径：反向索引
            reverse_key = self._key_token_reverse(token)
            user_id_bytes = self._read_key(reverse_key)
            if user_id_bytes is not None:
                user_id = user_id_bytes.decode("utf-8") if isinstance(user_id_bytes, bytes) else user_id_bytes
                meta = self.get_metadata(user_id, token)
                if meta and meta.context_lengths:
                    return meta.context_lengths
                return None
        except Exception as e:
            logger.warning(f"反向索引查询 context_lengths 失败: {e}")

        # 慢速路径：SCAN（兼容老数据）
        for index_key in self._scan_index_keys():
            user_id = index_key.replace("apikey_index:", "")
            if token in self._tokens_for_index(index_key):
                meta = self.get_metadata(user_id, token)
                if meta and meta.context_lengths:
                    return meta.context_lengths
                return None
        return None
    
    def get_key_by_token(self, token: str) -> Optional[str]:
        """根据 token 获取 API Key（O(1) 反向索引查找）

        优化：使用 apikey:token:{token} → user_id 反向索引，避免 SCAN apikey_index:*
        仅在反向索引缺失（老数据/异常清理）时回退到 SCAN。

        Args:
            token: API Key Token

        Returns:
            API Key 或 None
        """
        if not token or len(token) < 30:
            return None

        try:
            # 1. 快速路径：反向索引
            reverse_key = self._key_token_reverse(token)
            user_id_bytes = self._read_key(reverse_key)
            if user_id_bytes is not None:
                user_id = user_id_bytes.decode("utf-8") if isinstance(user_id_bytes, bytes) else user_id_bytes
                return self.get_key(user_id, token)
        except Exception as e:
            logger.warning(f"反向索引查询失败，回退到 SCAN: {e}")

        # 2. 慢速路径：SCAN 全表扫（兼容老数据）
        for index_key in self._scan_index_keys():
            user_id = index_key.replace("apikey_index:", "")
            if token in self._tokens_for_index(index_key):
                # 回填反向索引，加速下次查询
                try:
                    key_ttl = self.redis.ttl(self._key_token(user_id, token))
                    if key_ttl > 0:
                        self.redis.setex(self._key_token_reverse(token), key_ttl + 86400, user_id)
                except Exception:
                    pass
                return self.get_key(user_id, token)
        return None
    
    def delete_key(self, user_id: str, token: str) -> bool:
        """
        删除 API Key
        
        Args:
            user_id: 用户 ID
            token: Token
            
        Returns:
            是否成功删除
        """
        # 删除 Key
        key_name = self._key_token(user_id, token)
        self._delete_everywhere(key_name)
        
        # 删除元数据
        meta_name = self._key_meta(user_id, token)
        self._delete_everywhere(meta_name)
        
        # 从索引中移除
        for store in self._stores():
            store.srem(self._key_index(user_id), token)

        # 清理反向索引
        self._delete_everywhere(self._key_token_reverse(token))

        logger.info(f"用户 {user_id} 删除 Key，Token: {token[:8]}...")
        return True
    
    def update_status(self, user_id: str, token: str, status: str) -> bool:
        """
        更新 API Key 状态
        
        Args:
            user_id: 用户 ID
            token: Token
            status: 新状态 (verified, invalid)
            
        Returns:
            是否成功更新
        """
        meta = self.get_metadata(user_id, token)
        if meta is None:
            return False
        
        meta.status = status
        self._save_meta(user_id, token, meta)
        return True
    
    def update_enabled(self, user_id: str, token: str, enabled: bool) -> bool:
        """
        更新 API Key 启用状态
        
        Args:
            user_id: 用户 ID
            token: Token
            enabled: 是否启用
            
        Returns:
            是否成功更新
        """
        meta = self.get_metadata(user_id, token)
        if meta is None:
            return False
        
        meta.enabled = enabled
        self._save_meta(user_id, token, meta)
        return True
    
    def update_context_lengths(self, user_id: str, token: str, context_lengths: dict) -> bool:
        """更新 API Key 的 context_length 配置
        
        Args:
            user_id: 用户 ID
            token: Token
            context_lengths: 模型 context_length 配置 {model_id: context_length}
            
        Returns:
            是否成功更新
        """
        meta = self.get_metadata(user_id, token)
        if meta is None:
            return False
        
        meta.context_lengths = context_lengths or {}
        self._save_meta(user_id, token, meta)

        logger.info(
            f"用户 {user_id} 更新 Key {token[:8]}... "
            f"context_lengths: {list(meta.context_lengths.keys())}"
        )
        return True

    def update_fallback_preference(
        self, user_id: str, token: str,
        preference: str, custom_chain: list = None
    ) -> bool:
        """更新 API Key 的降级链偏好

        Args:
            user_id: 用户 ID
            token: Token
            preference: 偏好模式 (use_admin_default | custom | disabled)
            custom_chain: 自定义降级链模型列表（仅 preference="custom" 时生效）

        Returns:
            是否成功更新
        """
        valid_preferences = ("use_admin_default", "custom", "disabled")
        if preference not in valid_preferences:
            raise ValueError(f"无效的偏好: {preference}，可选: {valid_preferences}")

        meta = self.get_metadata(user_id, token)
        if meta is None:
            return False

        meta.fallback_preference = preference
        if preference == "custom" and custom_chain is not None:
            meta.custom_fallback_chain = custom_chain
        elif preference != "custom":
            meta.custom_fallback_chain = []

        self._save_meta(user_id, token, meta)

        logger.info(f"用户 {user_id} 更新 Key {token[:8]}... fallback_preference: {preference}")
        return True

    def get_fallback_preference_by_token(self, token: str) -> Optional[Dict]:
        """根据 token 获取降级链偏好（O(1) 反向索引查找）

        Returns:
            {"fallback_preference": str, "custom_fallback_chain": list} 或 None
        """
        if not token or len(token) < 30:
            return None

        try:
            reverse_key = self._key_token_reverse(token)
            user_id_bytes = self._read_key(reverse_key)
            if user_id_bytes is not None:
                user_id = user_id_bytes.decode("utf-8") if isinstance(user_id_bytes, bytes) else user_id_bytes
                meta = self.get_metadata(user_id, token)
                if meta:
                    return {
                        "fallback_preference": meta.fallback_preference,
                        "custom_fallback_chain": meta.custom_fallback_chain,
                    }
        except Exception as e:
            logger.warning(f"获取降级链偏好失败: {e}")

        return None

    def _cleanup_meta(self, user_id: str, token: str):
        """清理过期的元数据和索引"""
        meta_name = self._key_meta(user_id, token)
        self._delete_everywhere(meta_name)
        for store in self._stores():
            store.srem(self._key_index(user_id), token)
    
    def get_all_enabled_keys(self) -> list:
        """获取所有用户的已启用 Key 元数据（用于重启恢复）
        
        Returns:
            list of (user_id, token, provider, api_key) tuples
        """
        result = []
        # 扫描所有用户索引
        for index_key in self._scan_index_keys():
            user_id = index_key.replace("apikey_index:", "")
            for token in self._tokens_for_index(index_key):
                meta = self.get_metadata(user_id, token)
                if meta and meta.enabled and meta.status in ("verified", "unverified"):
                    api_key = self.get_key(user_id, token)
                    if api_key:
                        result.append((user_id, token, meta.provider, api_key))
        return result


# 全局单例
_apikey_manager: Optional[APIKeyManager] = None
_apikey_manager_lock = threading.Lock()


def get_apikey_manager(redis_client: Optional[redis.Redis] = None) -> APIKeyManager:
    """获取全局 APIKeyManager 实例"""
    global _apikey_manager
    if _apikey_manager is None:
        with _apikey_manager_lock:
            if _apikey_manager is None:
                if redis_client is None:
                    redis_client = _build_default_redis_client()
                    legacy_client = _build_legacy_redis_client()
                else:
                    legacy_client = None
                _apikey_manager = APIKeyManager(redis_client, legacy_redis_client=legacy_client)
    return _apikey_manager


def _build_default_redis_client() -> redis.Redis:
    """按配置构建默认 Redis 连接。

    未显式注入 client 时，优先使用 ``APIKEY_REDIS_URL``。生产环境应把它指向
    独立的 noeviction 实例，避免用户 Key 与缓存共用 allkeys-lru 时被淘汰。
    未配置时回退 ``REDIS_URL``，保持本地开发和单实例部署可用。
    """
    url = (
        getattr(settings, "APIKEY_REDIS_URL", "")
        or getattr(settings, "REDIS_URL", "")
        or ""
    ).strip()
    if url:
        return redis.from_url(url, decode_responses=False)
    return redis.Redis(host="localhost", port=6379, db=0, decode_responses=False)


def _build_legacy_redis_client() -> Optional[redis.Redis]:
    """迁移期回退连接：专用实例启用后，从原共享 Redis 惰性读取旧 Key。"""
    dedicated = (getattr(settings, "APIKEY_REDIS_URL", "") or "").strip()
    shared = (getattr(settings, "REDIS_URL", "") or "").strip()
    if dedicated and shared and dedicated != shared:
        return redis.from_url(shared, decode_responses=False)
    return None


def init_apikey_manager(
    redis_client: redis.Redis,
    legacy_redis_client: Optional[redis.Redis] = None,
) -> APIKeyManager:
    """初始化全局 APIKeyManager 实例（应用启动时调用）"""
    global _apikey_manager
    _apikey_manager = APIKeyManager(
        redis_client, legacy_redis_client=legacy_redis_client
    )
    return _apikey_manager


def get_key_by_token(token: str) -> Optional[str]:
    """模块级便捷函数：根据 token 获取 API Key"""
    return get_apikey_manager().get_key_by_token(token)


def get_metadata_by_token(token: str) -> Optional[Dict]:
    """模块级便捷函数：根据 token 获取完整元数据（含 provider、fallback_preference 等）

    Returns:
        KeyMetadata 字典 或 None
    """
    manager = get_apikey_manager()
    # 反向索引找 user_id
    reverse_key = manager._key_token_reverse(token)
    user_id_bytes = manager.redis.get(reverse_key)
    if user_id_bytes is None:
        return None
    user_id = user_id_bytes.decode("utf-8") if isinstance(user_id_bytes, bytes) else user_id_bytes
    meta = manager.get_metadata(user_id, token)
    if meta is None:
        return None
    return asdict(meta)
