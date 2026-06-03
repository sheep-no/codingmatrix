"""
API Key 管理器

将用户的 API Key 安全存储在 Redis 中：
- Key 不落库，仅存 Redis 内存
- TTL 到期自动删除
- 支持多供应商、多 Key 管理
"""
import json
import uuid
import time
import logging
from typing import Optional, List, Dict
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

import redis

logger = logging.getLogger(__name__)

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

local added = redis.call('SADD', index_key, token)
if added == 1 then
    -- 设置索引的过期时间（比最长 TTL 多一天）
    redis.call('EXPIRE', index_key, ttl_seconds + 86400)
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
    
    def __post_init__(self):
        if self.context_lengths is None:
            self.context_lengths = {}


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
        raise ValueError(f"TTL 类型无效，必须是字符串或整数")

MAX_KEYS_PER_USER = 20


class APIKeyManager:
    """API Key 管理器"""
    
    def __init__(self, redis_client: redis.Redis, max_keys_per_user: int = MAX_KEYS_PER_USER):
        self.redis = redis_client
        self.max_keys = max_keys_per_user
    
    def _key_token(self, user_id: str, token: str) -> str:
        """Redis 键：存储 API Key"""
        return f"apikey:{user_id}:{token}"
    
    def _key_meta(self, user_id: str, token: str) -> str:
        """Redis 键：存储元数据"""
        return f"apikey_meta:{user_id}:{token}"
    
    def _key_index(self, user_id: str) -> str:
        """Redis 键：用户索引"""
        return f"apikey_index:{user_id}"
    
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
        self.redis.setex(key_name, ttl_seconds, api_key)
        
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
        api_key = self.redis.get(key_name)
        
        if api_key is None:
            # Key 不存在或已过期
            self._cleanup_meta(user_id, token)
            return None
        
        return api_key.decode("utf-8") if isinstance(api_key, bytes) else api_key
    
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
        meta_json = self.redis.get(meta_name)
        
        if meta_json is None:
            return None
        
        meta_dict = json.loads(meta_json)
        
        # 检查是否过期
        expires_at = datetime.fromisoformat(meta_dict["expires_at"])
        if expires_at < datetime.now(timezone.utc):
            meta_dict["status"] = "expired"
            self._cleanup_meta(user_id, token)
            return None
        
        return KeyMetadata(**meta_dict)
    
    def list_keys(self, user_id: str) -> List[KeyMetadata]:
        """
        获取用户所有 API Key 的元数据列表
        
        Args:
            user_id: 用户 ID
            
        Returns:
            KeyMetadata 列表
        """
        index_key = self._key_index(user_id)
        
        tokens = self.redis.smembers(index_key)
        
        result = []
        for token in tokens:
            token_str = token.decode("utf-8") if isinstance(token, bytes) else token
            meta = self.get_metadata(user_id, token_str)
            if meta is not None:
                result.append(meta)
        
        result.sort(key=lambda m: m.created_at, reverse=True)
        return result
    
    def get_context_lengths_by_token(self, token: str) -> dict:
        """根据 token 获取 context_lengths 配置（扫描所有用户）
        
        注意：这是一个低效操作，仅用于 token -> context_lengths 的查找
        
        Args:
            token: API Key Token
            
        Returns:
            context_lengths dict 或 None
        """
        # 扫描所有用户索引
        cursor = 0
        while True:
            cursor, keys = self.redis.scan(cursor, match="apikey_index:*", count=100)
            for index_key in keys:
                user_id = index_key.decode("utf-8").replace("apikey_index:") if isinstance(index_key, bytes) else index_key.replace("apikey_index:", "")
                
                # 检查这个 token 是否属于该用户
                if self.redis.sismember(index_key, token):
                    meta = self.get_metadata(user_id, token)
                    if meta and meta.context_lengths:
                        return meta.context_lengths
                    return None
            
            if cursor == 0:
                break
        return None
    
    def get_key_by_token(self, token: str) -> Optional[str]:
        """根据 token 获取 API Key（扫描所有用户）
        
        注意：这是一个低效操作，仅用于 token -> api_key 的查找
        
        Args:
            token: API Key Token
            
        Returns:
            API Key 或 None
        """
        if not token or len(token) < 30:
            return None
        
        cursor = 0
        while True:
            cursor, keys = self.redis.scan(cursor, match="apikey_index:*", count=100)
            for index_key in keys:
                user_id = index_key.decode("utf-8").replace("apikey_index:") if isinstance(index_key, bytes) else index_key.replace("apikey_index:", "")
                
                if self.redis.sismember(index_key, token):
                    return self.get_key(user_id, token)
            
            if cursor == 0:
                break
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
        self.redis.delete(key_name)
        
        # 删除元数据
        meta_name = self._key_meta(user_id, token)
        self.redis.delete(meta_name)
        
        # 从索引中移除
        self.redis.srem(self._key_index(user_id), token)
        
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
        
        # 更新元数据
        meta_name = self._key_meta(user_id, token)
        ttl = self.redis.ttl(meta_name)
        if ttl > 0:
            self.redis.setex(meta_name, ttl, json.dumps(asdict(meta)))
        
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
        
        meta_name = self._key_meta(user_id, token)
        ttl = self.redis.ttl(meta_name)
        if ttl > 0:
            self.redis.setex(meta_name, ttl, json.dumps(asdict(meta)))
        
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
        
        meta_name = self._key_meta(user_id, token)
        ttl = self.redis.ttl(meta_name)
        if ttl > 0:
            self.redis.setex(meta_name, ttl, json.dumps(asdict(meta)))
        
        logger.info(f"用户 {user_id} 更新 Key {token[:8]}... context_lengths: {list(context_lengths.keys())}")
        return True
    
    def _cleanup_meta(self, user_id: str, token: str):
        """清理过期的元数据和索引"""
        meta_name = self._key_meta(user_id, token)
        self.redis.delete(meta_name)
        self.redis.srem(self._key_index(user_id), token)
    
    def get_all_enabled_keys(self) -> list:
        """获取所有用户的已启用 Key 元数据（用于重启恢复）
        
        Returns:
            list of (user_id, token, provider, api_key) tuples
        """
        result = []
        # 扫描所有用户索引
        cursor = 0
        while True:
            cursor, keys = self.redis.scan(cursor, match="apikey_index:*", count=100)
            for index_key in keys:
                # 提取 user_id
                key_str = index_key.decode("utf-8") if isinstance(index_key, bytes) else index_key
                user_id = key_str.replace("apikey_index:", "")
                
                # 获取该用户的所有 token
                tokens = self.redis.smembers(index_key)
                for token in tokens:
                    token_str = token.decode("utf-8") if isinstance(token, bytes) else token
                    meta = self.get_metadata(user_id, token_str)
                    if meta and meta.enabled and meta.status in ("verified", "unverified"):
                        api_key = self.get_key(user_id, token_str)
                        if api_key:
                            result.append((user_id, token_str, meta.provider, api_key))
            
            if cursor == 0:
                break
        return result


# 全局单例
_apikey_manager: Optional[APIKeyManager] = None


def get_apikey_manager(redis_client: Optional[redis.Redis] = None) -> APIKeyManager:
    """获取全局 APIKeyManager 实例"""
    global _apikey_manager
    if _apikey_manager is None:
        if redis_client is None:
            # 默认 Redis 连接
            redis_client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=False)
        _apikey_manager = APIKeyManager(redis_client)
    return _apikey_manager


def init_apikey_manager(redis_client: redis.Redis) -> APIKeyManager:
    """初始化全局 APIKeyManager 实例（应用启动时调用）"""
    global _apikey_manager
    _apikey_manager = APIKeyManager(redis_client)
    return _apikey_manager
