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
TTL_OPTIONS = {
    "1h": 3600,
    "24h": 86400,
    "7d": 604800,
    "30d": 2592000,
}

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
        
        ttl_seconds = TTL_OPTIONS.get(ttl)
        if ttl_seconds is None:
            raise ValueError(f"无效的 TTL 选项：{ttl}，可选：{list(TTL_OPTIONS.keys())}")
        
        # 检查用户 Key 数量限制
        token_count = self.redis.scard(self._key_index(user_id))
        if token_count >= self.max_keys:
            raise RuntimeError(f"已达到最大 Key 数量限制 ({self.max_keys})")
        
        # 生成 Token
        token = str(uuid.uuid4())
        
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
        
        # 添加到用户索引
        self.redis.sadd(self._key_index(user_id), token)
        # 设置索引的过期时间（比最长 TTL 多一天）
        self.redis.expire(self._key_index(user_id), ttl_seconds + 86400)
        
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
        tokens = self.redis.smembers(self._key_index(user_id))
        result = []
        
        for token in tokens:
            token_str = token.decode("utf-8") if isinstance(token, bytes) else token
            meta = self.get_metadata(user_id, token_str)
            if meta is not None:
                result.append(meta)
            else:
                # 清理无效 token
                self.redis.srem(self._key_index(user_id), token)
        
        # 按创建时间排序（最新的在前）
        result.sort(key=lambda m: m.created_at, reverse=True)
        return result
    
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
    
    def _cleanup_meta(self, user_id: str, token: str):
        """清理过期的元数据和索引"""
        meta_name = self._key_meta(user_id, token)
        self.redis.delete(meta_name)
        self.redis.srem(self._key_index(user_id), token)


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
