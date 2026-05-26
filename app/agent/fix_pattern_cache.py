"""
成功模式缓存 - 存储和复用已验证的修复策略

v4.7.0 增强：
- 反模式追踪：记录验证失败的修复，failed_count >= 3 且成功率 < 0.3 视为反模式
- 查找时自动排除反模式条目
- BM25 文本相似度：用于跨项目知识迁移（替代向量嵌入）
"""
import json
import time
import hashlib
import math
import logging
import threading
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict, field
from pathlib import Path

from app.agent.error_classifier import ErrorClassification

logger = logging.getLogger(__name__)


@dataclass
class FixPattern:
    """修复模式记录"""
    error_signature: str
    error_type: str
    error_subtype: str
    project_type: str
    file_type: str
    fix_strategy: str
    model_used: str
    fixed_code_snippet: str
    success_rate: float
    usage_count: int
    strategy_version: int = 1
    last_hit_time: Optional[float] = None
    hit_count: int = 0

    failed_count: int = 0
    last_failed_at: Optional[str] = None
    failure_reason: Optional[str] = None

    def is_anti_pattern(self, threshold: int = 3) -> bool:
        """判定是否为反模式"""
        return self.failed_count >= threshold and self.success_rate < 0.3


class FixPatternCache:
    """修复模式缓存管理器（含 LRU 淘汰机制）"""
    
    def __init__(self, cache_file: Path = None, max_size: int = 1000):
        self.cache_file = cache_file or Path("fix_patterns_cache.json")
        self.max_size = max_size  # 最大缓存条目数
        self.patterns: Dict[str, FixPattern] = {}
        self._load_cache()
        self._save_lock = threading.Lock()  # 异步保存锁
    
    def _load_cache(self):
        """从文件加载缓存"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, pattern_dict in data.items():
                        pattern_dict.setdefault("failed_count", 0)
                        pattern_dict.setdefault("last_failed_at", None)
                        pattern_dict.setdefault("failure_reason", None)
                        self.patterns[key] = FixPattern(**pattern_dict)
            except Exception as e:
                logger.warning(f"加载修复模式缓存失败: {e}")
    
    def _save_cache(self):
        """保存缓存到文件（线程安全）"""
        with self._save_lock:
            try:
                active_patterns = {k: v for k, v in self.patterns.items() if v.usage_count > 0}
                with open(self.cache_file, 'w', encoding='utf-8') as f:
                    json.dump({k: asdict(v) for k, v in active_patterns.items()}, f, indent=2)
            except Exception as e:
                logger.warning(f"保存修复模式缓存失败：{e}")
    
    def _save_cache_async(self):
        """异步保存缓存"""
        def save_thread():
            try:
                self._save_cache()
            except Exception as e:
                logger.warning(f"异步保存修复模式缓存失败：{e}")
        
        threading.Thread(target=save_thread, daemon=True).start()
    
    def _get_eviction_priority(self, signature: str, pattern: FixPattern) -> tuple:
        """获取淘汰优先级（返回值越小越优先淘汰）"""
        return (
            pattern.is_anti_pattern(),  # 反模式优先删除 (True=1 < False=0)
            pattern.success_rate,       # 成功率低优先
            pattern.last_hit_time or 0, # 时间久远优先（时间戳小优先）
            -pattern.usage_count        # 使用次数少优先（负数使小的在前）
        )
    
    def _generate_error_signature(self, classification: ErrorClassification, project_type: str, file_type: str) -> str:
        """生成错误特征签名"""
        signature_data = f"{classification.error_type}:{classification.error_subtype}:{project_type}:{file_type}"
        return hashlib.md5(signature_data.encode()).hexdigest()
    
    def find_pattern(self, classification: ErrorClassification, project_type: str, file_type: str) -> Optional[FixPattern]:
        """查找匹配的修复模式（自动排除反模式）"""
        signature = self._generate_error_signature(classification, project_type, file_type)
        pattern = self.patterns.get(signature)
        if pattern:
            if pattern.is_anti_pattern():
                logger.warning(f"修复模式 {signature} 为反模式，跳过 (失败{pattern.failed_count}次, 成功率{pattern.success_rate:.0%})")
                return None
            pattern.usage_count += 1
            self._save_cache_async()
            return pattern
        return None
    
    def add_pattern(self, classification: ErrorClassification, project_type: str, file_type: str, 
                   fix_strategy: str, model_used: str, fixed_code_snippet: str, strategy_version: int = 1):
        """添加新的修复模式"""
        signature = self._generate_error_signature(classification, project_type, file_type)
        
        new_pattern = FixPattern(
            error_signature=signature,
            error_type=classification.error_type,
            error_subtype=classification.error_subtype,
            project_type=project_type,
            file_type=file_type,
            fix_strategy=fix_strategy,
            model_used=model_used,
            fixed_code_snippet=fixed_code_snippet,
            success_rate=1.0,
            usage_count=1,
            strategy_version=strategy_version,
            last_hit_time=time.time(),
            hit_count=1
        )
        
        self.patterns[signature] = new_pattern
        self._apply_decay_and_cleanup()
        self._save_cache_async()
    
    def update_pattern_success(self, signature: str, success: bool, failure_reason: Optional[str] = None):
        """更新修复模式的成功率（含反模式追踪）"""
        if signature in self.patterns:
            pattern = self.patterns[signature]
            if success:
                pattern.success_rate = min(1.0, pattern.success_rate + 0.1)
            else:
                pattern.success_rate = max(0.0, pattern.success_rate - 0.2)
                pattern.failed_count += 1
                pattern.last_failed_at = time.strftime("%Y-%m-%dT%H:%M:%S")
                pattern.failure_reason = failure_reason

            pattern.last_hit_time = time.time()
            pattern.hit_count += 1

            self._save_cache_async()
            self._apply_decay_and_cleanup()
    
    def _apply_decay_and_cleanup(self):
        """应用缓存衰减和清理策略（含 LRU 淘汰机制）"""
        current_time = time.time()
        patterns_to_remove = []
        
        for signature, pattern in self.patterns.items():
            if pattern.last_hit_time is None:
                continue
                
            days_since_last_hit = (current_time - pattern.last_hit_time) / (24 * 3600)
            
            # 超过 30 天未命中 → 权重减半
            if days_since_last_hit > 30 and pattern.success_rate > 0.1:
                pattern.success_rate *= 0.5
                pattern.last_hit_time = current_time  # 重置时间以避免重复衰减
            
            # 超过 60 天未命中 → 自动归档（标记为不活跃）
            if days_since_last_hit > 60:
                patterns_to_remove.append(signature)
        
        # LRU 淘汰机制：当缓存超过容量上限时，按优先级淘汰
        if len(self.patterns) > self.max_size:
            # 计算需要删除的条目数
            excess_count = len(self.patterns) - self.max_size
            
            # 按淘汰优先级排序
            sorted_items = sorted(
                self.patterns.items(),
                key=lambda item: self._get_eviction_priority(item[0], item[1])
            )
            
            # 添加需要淘汰的条目到删除列表
            patterns_to_remove.extend([sig for sig, _ in sorted_items[:excess_count]])
            logger.info(f"缓存触发容量上限 ({len(self.patterns)} > {self.max_size})，计划淘汰 {excess_count} 个条目")
        
        # 执行删除
        for signature in patterns_to_remove:
            del self.patterns[signature]
        
        if patterns_to_remove:
            self._save_cache()
            logger.info(f"清理 {len(patterns_to_remove)} 个缓存条目，剩余 {len(self.patterns)} 个")
    
    def _tokenize(self, text: str) -> List[str]:
        tokens = text.lower().split()
        normalized = []
        for t in tokens:
            cleaned = "".join(c for c in t if c.isalnum() or c == "_")
            if cleaned:
                normalized.append(cleaned)
        return normalized

    def _bm25_score(
        self,
        query_tokens: List[str],
        doc_tokens: List[str],
        avg_dl: float,
        k1: float = 1.5,
        b: float = 0.75
    ) -> float:
        doc_len = len(doc_tokens)
        tf_map: Dict[str, int] = {}
        for t in doc_tokens:
            tf_map[t] = tf_map.get(t, 0) + 1
        total_docs = max(len(self.patterns), 1)
        score = 0.0
        for qt in query_tokens:
            n_qi = sum(1 for p in self.patterns.values() if qt in self._tokenize(p.fix_strategy))
            idf = math.log((total_docs - n_qi + 0.5) / (n_qi + 0.5) + 1.0)
            tf = tf_map.get(qt, 0)
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * doc_len / max(avg_dl, 1.0))
            score += idf * numerator / denominator
        return score

    def find_similar_patterns(self, classification: ErrorClassification, project_type: str,
                            file_type: str, similarity_threshold: float = 0.8) -> List[FixPattern]:
        query_text = f"{classification.error_type} {classification.error_subtype} {project_type} {file_type}"
        query_tokens = self._tokenize(query_text)
        if not query_tokens:
            return []

        all_token_lists = []
        for pattern in self.patterns.values():
            if not pattern.is_anti_pattern():
                doc_text = f"{pattern.error_type} {pattern.error_subtype} {pattern.project_type} {pattern.file_type} {pattern.fix_strategy}"
                all_token_lists.append((pattern, self._tokenize(doc_text)))

        if not all_token_lists:
            return []

        avg_dl = sum(len(tl) for _, tl in all_token_lists) / len(all_token_lists)
        scored: List[tuple] = []
        for pattern, doc_tokens in all_token_lists:
            score = self._bm25_score(query_tokens, doc_tokens, avg_dl)
            if score >= similarity_threshold:
                scored.append((score, pattern))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [p for _, p in scored]


# 全局修复模式缓存实例（带容量上限）
fix_pattern_cache = FixPatternCache(max_size=1000)