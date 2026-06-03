"""
SpecCache - 规范缓存

支持：
1. 语义相似度匹配（BCE embedding 向量余弦相似度 + tech_stack 索引预过滤）
2. 批量余弦相似度计算（避免逐条线性遍历）
3. 相似需求检测（基于语义哈希）
4. 规范缓存（OpenAPI、类型定义、数据库 Schema）
5. 缓存命中率统计
6. 自动过期清理
"""

import json
import hashlib
import logging
import math
import re
import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime, timedelta


logger = logging.getLogger(__name__)

# 缓存存储目录
CACHE_DIR = Path("./cache/spec_cache")
# 缓存过期时间（7 天）
CACHE_TTL = timedelta(days=7)
# 缓存最大条目数（超出时按 LRU 淘汰）
MAX_CACHE_ENTRIES = 200
# 相似度阈值
SIMILARITY_THRESHOLD = 0.85
# Embedding 相似度阈值（余弦相似度）
EMBEDDING_SIMILARITY_THRESHOLD = 0.80


def batch_cosine_similarity(query: List[float], vectors: List[List[float]]) -> List[float]:
    """批量计算 query 向量与多个向量的余弦相似度"""
    if not vectors:
        return []
    query_norm = math.sqrt(sum(a * a for a in query))
    if query_norm == 0:
        return [0.0] * len(vectors)
    results = []
    for vec in vectors:
        vec_norm = math.sqrt(sum(b * b for b in vec))
        if vec_norm == 0:
            results.append(0.0)
        else:
            dot = sum(a * b for a, b in zip(query, vec))
            results.append(dot / (query_norm * vec_norm))
    return results


@dataclass
class CacheEntry:
    """缓存条目"""
    requirement_hash: str           # 需求哈希
    requirement_preview: str        # 需求预览（前 200 字符）
    created_at: str                 # 创建时间
    last_accessed: str              # 最后访问时间
    access_count: int = 0           # 访问次数

    # 语义向量（BCE embedding）
    requirement_vector: Optional[List[float]] = None

    # 缓存的规范
    specs: Dict[str, Any] = field(default_factory=dict)

    # 架构设计
    architecture: Dict[str, Any] = field(default_factory=dict)
    file_plan: List[Dict[str, Any]] = field(default_factory=list)

    # 元数据
    complexity: Dict[str, Any] = field(default_factory=dict)
    tech_stack: List[str] = field(default_factory=list)

    # 关键词索引（用于快速匹配 + embedding 缓存失败时的降级）
    keywords: List[str] = field(default_factory=list)

    def is_expired(self) -> bool:
        """检查是否过期"""
        created = datetime.fromisoformat(self.created_at)
        return datetime.now() - created > CACHE_TTL


class SpecCache:
    """规范缓存管理器（带向量索引优化）"""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, CacheEntry] = {}

        # 向量索引优化
        self._tech_index: Dict[str, List[str]] = {}  # tech_stack -&gt; [req_hash]
        self._vector_cache: Dict[str, List[float]] = {}  # req_hash -&gt; vector (内存)

        # 异步懒加载索引（不阻塞初始化）
        self._index_loaded = False
        self._index_lock = asyncio.Lock()
        self._index_load_task: Optional[asyncio.Task] = None

        self._stats = {"hits": 0, "misses": 0, "total_requests": 0}

    async def _ensure_index_loaded(self):
        """确保索引已加载（异步懒加载，带锁保护）"""
        if self._index_loaded:
            return
        async with self._index_lock:
            if self._index_loaded:
                return
            if self._index_load_task is None:
                self._index_load_task = asyncio.create_task(self._async_load_index())
            await self._index_load_task

    async def _async_load_index(self):
        """异步加载索引（不阻塞事件循环）"""
        await asyncio.to_thread(self._load_index_sync)
        await asyncio.to_thread(self._build_indices)
        self._index_loaded = True

    def _load_index_sync(self):
        """同步加载缓存索引"""
        index_file = self.cache_dir / "index.json"
        if index_file.exists():
            try:
                with open(index_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for req_hash, entry_data in data.items():
                    self._cache[req_hash] = CacheEntry(**entry_data)
            except Exception as e:
                logger.error(f"加载缓存索引失败: {e}")

    def _load_index(self):
        """同步加载索引（兼容旧调用）"""
        self._load_index_sync()
        self._build_indices()
        self._index_loaded = True

    def _build_indices(self):
        """构建技术栈索引和向量缓存"""
        self._tech_index.clear()
        self._vector_cache.clear()

        for req_hash, entry in self._cache.items():
            if entry.is_expired():
                continue

            # 技术栈索引
            for tech in entry.tech_stack:
                if tech not in self._tech_index:
                    self._tech_index[tech] = []
                self._tech_index[tech].append(req_hash)

            # 向量缓存（加载有向量的条目）
            if entry.requirement_vector is not None:
                self._vector_cache[req_hash] = entry.requirement_vector

        logger.info(f"索引构建完成: {len(self._tech_index)} 个技术栈, {len(self._vector_cache)} 个向量")

    def _save_index(self):
        """保存缓存索引"""
        index_file = self.cache_dir / "index.json"
        try:
            data = {
                k: {
                    "requirement_hash": v.requirement_hash,
                    "requirement_preview": v.requirement_preview,
                    "created_at": v.created_at,
                    "last_accessed": v.last_accessed,
                    "access_count": v.access_count,
                    "requirement_vector": v.requirement_vector,
                    "keywords": v.keywords,
                    "specs": {},
                    "architecture": {},
                    "file_plan": [],
                    "complexity": {},
                    "tech_stack": v.tech_stack
                }
                for k, v in self._cache.items()
                if not v.is_expired()
            }
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存缓存索引失败: {e}")

    def _compute_requirement_hash(self, requirement: str) -> str:
        """计算需求哈希（归一化后）"""
        normalized = self._normalize_requirement(requirement)
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]

    @staticmethod
    def _normalize_requirement(requirement: str) -> str:
        """归一化需求文本"""
        text = requirement.lower()
        text = re.sub(r'\s+', ' ', text).strip()
        text = re.sub(r'[^\w\s\u4e00-\u9fff]', '', text)
        return text

    def extract_keywords(self, requirement: str) -> List[str]:
        """提取需求关键词"""
        text = requirement.lower()
        keywords = []

        tech_keywords = [
            'vue', 'react', 'angular', 'html', 'css', 'javascript', 'typescript',
            'python', 'fastapi', 'django', 'flask', 'spring', 'express', 'node',
            'mysql', 'postgres', 'sqlite', 'mongo', 'redis', 'database',
            'jwt', 'oauth', 'auth', 'login', 'register',
            'api', 'rest', 'graphql',
            'docker', 'k8s', 'deploy',
            '游戏', 'chess', 'game',
            '商城', 'shop', 'ecommerce',
            '聊天', 'chat', 'im',
            '博客', 'blog', 'cms',
            '管理', 'admin', 'dashboard',
        ]

        for kw in tech_keywords:
            if kw in text:
                keywords.append(kw)

        action_patterns = [
            r'(\w+)(?:系统|平台|应用|app|app)',
            r'(?:实现|开发|创建|制作)(\w+)',
        ]

        for pattern in action_patterns:
            matches = re.findall(pattern, text)
            keywords.extend(matches)

        return list(set(keywords))

    def compute_similarity(self, req1: str, req2: str) -> float:
        """计算两个需求的相似度（基于 Jaccard 相似度）"""
        kw1 = set(self.extract_keywords(req1))
        kw2 = set(self.extract_keywords(req2))

        if not kw1 and not kw2:
            norm1 = set(self._normalize_requirement(req1).split())
            norm2 = set(self._normalize_requirement(req2).split())
            if not norm1 and not norm2:
                return 1.0
            intersection = norm1 & norm2
            union = norm1 | norm2
            return len(intersection) / len(union) if union else 0.0

        if not kw1 or not kw2:
            return 0.0

        intersection = kw1 & kw2
        union = kw1 | kw2
        return len(intersection) / len(union)

    def _extract_tech_keywords(self, requirement: str) -> List[str]:
        """从需求中提取技术栈关键词（用于索引预过滤）"""
        text = requirement.lower()
        tech_keywords = [
            'vue', 'react', 'angular', 'html', 'css', 'javascript', 'typescript',
            'python', 'fastapi', 'django', 'flask', 'spring', 'express', 'node',
            'mysql', 'postgres', 'sqlite', 'mongo', 'redis', 'database',
            'jwt', 'oauth', 'auth', 'login', 'register',
            'api', 'rest', 'graphql',
            'docker', 'k8s', 'deploy',
            '游戏', 'chess', 'game',
            '商城', 'shop', 'ecommerce',
            '聊天', 'chat', 'im',
            '博客', 'blog', 'cms',
            '管理', 'admin', 'dashboard',
        ]
        return [kw for kw in tech_keywords if kw in text]

    def lookup(
        self,
        requirement: str,
        min_similarity: float = SIMILARITY_THRESHOLD,
        requirement_vector: Optional[List[float]] = None
    ) -> Optional[CacheEntry]:
        """
        查找相似需求的缓存（带索引优化）

        优化策略：
        1. tech_stack 预过滤 — 只搜索技术栈匹配的条目
        2. 批量余弦相似度计算 — 一次性计算所有候选项
        3. 内存向量缓存 — 避免重复加载磁盘文件
        """
        self._stats["total_requests"] += 1

        # 1. 精确匹配
        req_hash = self._compute_requirement_hash(requirement)
        if req_hash in self._cache:
            entry = self._cache[req_hash]
            if not entry.is_expired():
                entry.access_count += 1
                entry.last_accessed = datetime.now().isoformat()
                self._stats["hits"] += 1
                return self._load_full_entry(entry)
            else:
                del self._cache[req_hash]
                self._remove_cache_file(req_hash)
                if req_hash in self._vector_cache:
                    del self._vector_cache[req_hash]

        # 2. 模糊匹配 — 带索引优化
        use_embedding = requirement_vector is not None
        threshold = EMBEDDING_SIMILARITY_THRESHOLD if use_embedding else min_similarity

        # 技术栈预过滤
        tech_keywords = self._extract_tech_keywords(requirement)
        candidate_hashes = set()

        if tech_keywords:
            for tech in tech_keywords:
                if tech in self._tech_index:
                    candidate_hashes.update(self._tech_index[tech])

        # 如果没有匹配的技术栈，使用全部缓存
        if not candidate_hashes:
            candidate_hashes = set(self._cache.keys())

        # 清理过期条目并过滤候选
        valid_candidates = []
        for h in candidate_hashes:
            if h not in self._cache:
                continue
            entry = self._cache[h]
            if entry.is_expired():
                del self._cache[h]
                self._remove_cache_file(h)
                if h in self._vector_cache:
                    del self._vector_cache[h]
                continue
            valid_candidates.append(h)

        if not valid_candidates:
            self._stats["misses"] += 1
            return None

        # 3. 批量计算相似度
        if use_embedding:
            # 收集候选向量（从内存缓存或磁盘加载）
            candidate_vectors = []
            candidate_entries = []

            for h in valid_candidates:
                # 优先用内存缓存
                if h in self._vector_cache:
                    vec = self._vector_cache[h]
                else:
                    full_entry = self._load_full_entry(self._cache[h])
                    vec = full_entry.requirement_vector
                    if vec is not None:
                        self._vector_cache[h] = vec

                if vec is not None:
                    candidate_vectors.append(vec)
                    candidate_entries.append(self._cache[h])

            # 批量计算余弦相似度
            if candidate_vectors:
                similarities = batch_cosine_similarity(requirement_vector, candidate_vectors)

                best_idx = -1
                best_sim = 0.0
                for i, sim in enumerate(similarities):
                    if sim >= threshold and sim > best_sim:
                        best_sim = sim
                        best_idx = i

                if best_idx >= 0:
                    best_entry = candidate_entries[best_idx]
                    full_entry = self._load_full_entry(best_entry)
                    full_entry.access_count += 1
                    full_entry.last_accessed = datetime.now().isoformat()
                    self._stats["hits"] += 1
                    return full_entry

        # 4. 降级：Jaccard 关键词相似度
        best_match = None
        best_similarity = 0.0

        for h in valid_candidates:
            entry = self._cache[h]
            full_entry = self._load_full_entry(entry)
            similarity = self.compute_similarity(requirement, full_entry.requirement_preview)

            if similarity >= threshold and similarity > best_similarity:
                best_similarity = similarity
                best_match = full_entry

        if best_match:
            best_match.access_count += 1
            best_match.last_accessed = datetime.now().isoformat()
            self._stats["hits"] += 1
            return best_match

        self._stats["misses"] += 1
        return None

    def save(
        self,
        requirement: str,
        specs: Dict[str, Any],
        architecture: Dict[str, Any],
        file_plan: List[Dict],
        complexity: Dict[str, Any],
        tech_stack: List[str],
        requirement_vector: Optional[List[float]] = None
    ) -> str:
        """缓存规范"""
        req_hash = self._compute_requirement_hash(requirement)
        keywords = self.extract_keywords(requirement)

        entry = CacheEntry(
            requirement_hash=req_hash,
            requirement_preview=requirement[:200],
            created_at=datetime.now().isoformat(),
            last_accessed=datetime.now().isoformat(),
            requirement_vector=requirement_vector,
            specs=specs,
            architecture=architecture,
            file_plan=file_plan,
            complexity=complexity,
            tech_stack=tech_stack,
            keywords=keywords
        )

        self._cache[req_hash] = entry

        # LRU 淘汰：超出上限时移除最久未访问的条目
        if len(self._cache) > MAX_CACHE_ENTRIES:
            oldest_hash = min(self._cache.keys(), key=lambda k: self._cache[k].last_accessed)
            if oldest_hash != req_hash:  # 不要刚添加的就移除
                self._cache.pop(oldest_hash)
                self._remove_cache_file(oldest_hash)
                self._vector_cache.pop(oldest_hash, None)
                for tech in list(self._tech_index.keys()):
                    if oldest_hash in self._tech_index[tech]:
                        self._tech_index[tech].remove(oldest_hash)
                    if not self._tech_index[tech]:
                        del self._tech_index[tech]
                logger.info(f"缓存已满，LRU 淘汰: {oldest_hash}")

        # 更新索引
        if requirement_vector is not None:
            self._vector_cache[req_hash] = requirement_vector
        for tech in tech_stack:
            if tech not in self._tech_index:
                self._tech_index[tech] = []
            if req_hash not in self._tech_index[tech]:
                self._tech_index[tech].append(req_hash)

        self._save_entry(entry)
        self._save_index()

        logger.info(f"缓存规范: {req_hash} ({len(specs)} 个规范, {len(tech_stack)} 个技术栈, {'有' if requirement_vector else '无'} embedding)")
        return req_hash

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        total = self._stats["total_requests"]
        hits = self._stats["hits"]
        return {
            "total_requests": total,
            "cache_hits": hits,
            "cache_misses": self._stats["misses"],
            "hit_rate": hits / total if total > 0 else 0.0,
            "cached_entries": len(self._cache),
            "cache_size_mb": self._get_cache_size_mb(),
            "vector_index_size": len(self._vector_cache),
            "tech_index_groups": len(self._tech_index)
        }

    def clear_expired(self, min_age: Optional[timedelta] = None) -> int:
        """清理过期缓存（或指定最小年龄的缓存）"""
        now = datetime.now()
        expired = []
        for k, v in self._cache.items():
            if min_age is not None:
                # 按指定年龄清理
                created = datetime.fromisoformat(v.created_at)
                if now - created > min_age:
                    expired.append(k)
            elif v.is_expired():
                expired.append(k)
        for k in expired:
            del self._cache[k]
            self._remove_cache_file(k)
            if k in self._vector_cache:
                del self._vector_cache[k]
            # 清理技术栈索引
            for tech in list(self._tech_index.keys()):
                if k in self._tech_index[tech]:
                    self._tech_index[tech].remove(k)
                if not self._tech_index[tech]:
                    del self._tech_index[tech]
        self._save_index()
        logger.info(f"清理 {len(expired)} 个缓存")
        return len(expired)

    def clear_all(self) -> int:
        """清理所有缓存"""
        count = len(self._cache)
        for k in list(self._cache.keys()):
            del self._cache[k]
            self._remove_cache_file(k)
        self._vector_cache.clear()
        self._tech_index.clear()
        self._save_index()
        logger.info(f"清理所有缓存: {count} 个")
        return count

    def _load_full_entry(self, entry: CacheEntry) -> CacheEntry:
        """从磁盘加载完整的缓存条目"""
        cache_file = self.cache_dir / f"{entry.requirement_hash}.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return CacheEntry(**data)
            except Exception as e:
                logger.error(f"加载缓存文件失败: {e}")
        return entry

    def _save_entry(self, entry: CacheEntry):
        """保存缓存条目到磁盘"""
        cache_file = self.cache_dir / f"{entry.requirement_hash}.json"
        try:
            data = {
                "requirement_hash": entry.requirement_hash,
                "requirement_preview": entry.requirement_preview,
                "created_at": entry.created_at,
                "last_accessed": entry.last_accessed,
                "access_count": entry.access_count,
                "requirement_vector": entry.requirement_vector,
                "specs": entry.specs,
                "architecture": entry.architecture,
                "file_plan": entry.file_plan,
                "complexity": entry.complexity,
                "tech_stack": entry.tech_stack,
                "keywords": entry.keywords
            }
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存缓存文件失败: {e}")

    def _remove_cache_file(self, req_hash: str):
        """删除缓存文件"""
        cache_file = self.cache_dir / f"{req_hash}.json"
        if cache_file.exists():
            try:
                cache_file.unlink()
            except Exception as e:
                logger.error(f"删除缓存文件失败: {e}")

    def _get_cache_size_mb(self) -> float:
        """获取缓存大小（MB）"""
        total_size = 0
        for f in self.cache_dir.glob("*.json"):
            total_size += f.stat().st_size
        return total_size / (1024 * 1024)

    # ===== 异步包装方法（供 async 上下文调用，避免阻塞事件循环） =====

    async def async_save(
        self,
        requirement: str,
        specs: Dict[str, Any],
        architecture: Dict[str, Any],
        file_plan: List[Dict],
        complexity: Dict[str, Any],
        tech_stack: List[str],
        requirement_vector: Optional[List[float]] = None
    ) -> str:
        """异步缓存规范（非阻塞事件循环）"""
        await self._ensure_index_loaded()
        return await asyncio.to_thread(
            self.save, requirement, specs, architecture, file_plan,
            complexity, tech_stack, requirement_vector
        )

    async def async_clear_expired(self, min_age: Optional[timedelta] = None) -> int:
        """异步清理过期缓存"""
        await self._ensure_index_loaded()
        return await asyncio.to_thread(self.clear_expired, min_age)

    async def async_clear_all(self) -> int:
        """异步清理所有缓存"""
        await self._ensure_index_loaded()
        return await asyncio.to_thread(self.clear_all)

    async def async_lookup(self, requirement: str, **kwargs) -> Optional["CacheEntry"]:
        """异步查找缓存"""
        await self._ensure_index_loaded()
        return await asyncio.to_thread(self.lookup, requirement, **kwargs)
