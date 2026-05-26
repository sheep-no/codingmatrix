"""
API Key 使用审计日志服务

记录所有 API Key 的使用情况，包括：
- 成功调用
- 失败调用
- 降级事件
- Token 消耗统计
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from dataclasses import dataclass, asdict

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class AuditLogEntry:
    """审计日志条目"""
    timestamp: str
    user_id: str
    token: str
    provider: str
    model: str
    success: bool
    duration_ms: int
    input_tokens: int = 0
    output_tokens: int = 0
    error_message: str = ""
    is_fallback: bool = False


class AuditLogger:
    """API Key 使用审计日志记录器"""
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis = redis_client
        if not self.redis:
            if settings.REDIS_URL:
                self.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
            else:
                self.redis = redis.Redis(
                    host="localhost",
                    port=6379,
                    decode_responses=True
                )
        
        self.prefix = "audit_log"
    
    def log_usage(
        self,
        user_id: str,
        token: str,
        provider: str,
        model: str,
        success: bool,
        duration_ms: int,
        input_tokens: int = 0,
        output_tokens: int = 0,
        error_message: str = "",
        is_fallback: bool = False
    ):
        """记录一次 API Key 使用"""
        try:
            entry = AuditLogEntry(
                timestamp=datetime.utcnow().isoformat() + "Z",
                user_id=user_id,
                token=token,
                provider=provider,
                model=model,
                success=success,
                duration_ms=duration_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                error_message=error_message,
                is_fallback=is_fallback
            )
            
            # 存储到 Redis List（按用户 ID 分组）
            key = f"{self.prefix}:{user_id}"
            self.redis.lpush(key, json.dumps(asdict(entry)))
            
            # 设置过期时间（30 天）
            self.redis.expire(key, 30 * 24 * 60 * 60)
            
            # 存储索引（按日期）
            date_key = f"{self.prefix}:date:{user_id}:{datetime.utcnow().strftime('%Y-%m-%d')}"
            self.redis.lpush(date_key, json.dumps(asdict(entry)))
            self.redis.expire(date_key, 30 * 24 * 60 * 60)
            
            logger.debug(f"审计日志记录：user={user_id}, token={token[:8]}..., success={success}")
            
        except Exception as e:
            logger.error(f"审计日志记录失败：{e}")
    
    def get_usage_history(
        self,
        user_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        provider: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """获取使用历史"""
        try:
            if start_date and end_date:
                # 按日期范围查询
                all_logs = []
                current_date = datetime.strptime(start_date, "%Y-%m-%d")
                end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
                
                while current_date <= end_date_obj:
                    date_key = f"{self.prefix}:date:{user_id}:{current_date.strftime('%Y-%m-%d')}"
                    logs = self.redis.lrange(date_key, 0, -1)
                    all_logs.extend([json.loads(log) for log in logs])
                    current_date = current_date + timedelta(days=1)
                
                logs = all_logs
            else:
                # 获取最近的日志
                key = f"{self.prefix}:{user_id}"
                logs = self.redis.lrange(key, 0, limit - 1)
                logs = [json.loads(log) for log in logs]
            
            # 过滤供应商
            if provider:
                logs = [log for log in logs if log['provider'] == provider]
            
            return logs
            
        except Exception as e:
            logger.error(f"获取使用历史失败：{e}")
            return []
    
    def get_usage_statistics(
        self,
        user_id: str,
        days: int = 7
    ) -> Dict:
        """获取使用统计"""
        try:
            from datetime import timedelta
            
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            
            logs = self.get_usage_history(
                user_id,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d")
            )
            
            # 统计数据
            total_calls = len(logs)
            successful_calls = sum(1 for log in logs if log['success'])
            failed_calls = total_calls - successful_calls
            total_input_tokens = sum(log.get('input_tokens', 0) for log in logs)
            total_output_tokens = sum(log.get('output_tokens', 0) for log in logs)
            fallback_count = sum(1 for log in logs if log.get('is_fallback', False))
            
            # 按供应商统计
            provider_stats = {}
            for log in logs:
                provider = log['provider']
                if provider not in provider_stats:
                    provider_stats[provider] = {'total': 0, 'success': 0, 'failed': 0}
                provider_stats[provider]['total'] += 1
                if log['success']:
                    provider_stats[provider]['success'] += 1
                else:
                    provider_stats[provider]['failed'] += 1
            
            return {
                'total_calls': total_calls,
                'successful_calls': successful_calls,
                'failed_calls': failed_calls,
                'total_input_tokens': total_input_tokens,
                'total_output_tokens': total_output_tokens,
                'fallback_count': fallback_count,
                'provider_stats': provider_stats,
                'period_days': days
            }
            
        except Exception as e:
            logger.error(f"获取使用统计失败：{e}")
            return {}
    
    def clear_logs(self, user_id: str):
        """清除用户的审计日志"""
        try:
            # 清除所有日志
            key = f"{self.prefix}:{user_id}"
            self.redis.delete(key)
            
            # 清除日期索引（需要扫描）
            # 注意：这部分可能需要定期清理任务
            logger.info(f"已清除用户 {user_id} 的审计日志")
            
        except Exception as e:
            logger.error(f"清除审计日志失败：{e}")


# 单例模式
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """获取审计日志记录器实例"""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
