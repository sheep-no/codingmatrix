"""
CloudLearningHub - 跨项目知识共享中心

支持：
1. 上传修复模式到中央知识库
2. 从中央知识库下载相似模式
3. 基于项目特征的模式过滤
4. 模式质量评估和投票
"""

import json
import logging
import hashlib
import asyncio
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field, asdict

from app.agent.feedback_learner import FixPattern

logger = logging.getLogger(__name__)

# 本地缓存目录
CLOUD_CACHE_DIR = Path("./data/cloud_learning")
# 本地知识库文件
CLOUD_KNOWLEDGE_FILE = CLOUD_CACHE_DIR / "cloud_knowledge.json"
# 最大缓存模式数
MAX_CACHED_PATTERNS = 5000


@dataclass
class CloudPattern:
    """云端模式（包含额外元数据）"""
    pattern: Dict[str, Any]  # FixPattern 的字典形式
    project_id: str  # 来源项目 ID
    project_type: str  # 项目类型（web/api/cli 等）
    tech_stack: List[str]  # 技术栈
    upload_time: str  # 上传时间
    download_count: int = 0  # 被下载次数
    success_votes: int = 0  # 成功票数
    failure_votes: int = 0  # 失败票数
    
    @property
    def quality_score(self) -> float:
        """计算模式质量分数"""
        total_votes = self.success_votes + self.failure_votes
        if total_votes == 0:
            return 0.5  # 无投票时默认中等质量
        
        success_rate = self.success_votes / total_votes
        download_weight = min(1.0, self.download_count / 100)  # 下载次数权重
        
        # 质量分数 = 成功率 * 0.7 + 下载热度 * 0.3
        return success_rate * 0.7 + download_weight * 0.3
    
    def is_high_quality(self, threshold: float = 0.7) -> bool:
        """是否是高质量模式"""
        return self.quality_score >= threshold


class CloudLearningHub:
    """
    跨项目知识共享中心
    
    使用场景：
    1. 项目 A 学到了一个修复模式
    2. 上传到 CloudLearningHub
    3. 项目 B 遇到类似问题时，从 CloudLearningHub 下载模式
    4. 项目 B 应用模式后，可以投票反馈效果
    """

    def __init__(
        self, 
        project_id: str = "default",
        project_type: str = "web",
        tech_stack: Optional[List[str]] = None,
        enable_cloud: bool = True,
        cache_dir: Optional[Path] = None
    ):
        self.project_id = project_id
        self.project_type = project_type
        self.tech_stack = tech_stack or []
        self.enable_cloud = enable_cloud
        self.cache_dir = cache_dir or CLOUD_CACHE_DIR
        
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self._local_patterns: Dict[str, CloudPattern] = {}
        self._cloud_patterns: Dict[str, CloudPattern] = {}
        
        self._load_local_cache()

    def _compute_pattern_hash(self, pattern: FixPattern) -> str:
        """计算模式的唯一哈希"""
        key = f"{pattern.error_type}:{pattern.error_message}:{pattern.fix_description}"
        return hashlib.md5(key.encode()).hexdigest()[:16]

    def _load_local_cache(self):
        """加载本地缓存"""
        if CLOUD_KNOWLEDGE_FILE.exists():
            try:
                with open(CLOUD_KNOWLEDGE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                for pattern_hash, pattern_data in data.get("patterns", {}).items():
                    self._local_patterns[pattern_hash] = CloudPattern(**pattern_data)
                
                logger.info(f"CloudLearningHub: 加载了 {len(self._local_patterns)} 个本地模式")
            except Exception as e:
                logger.error(f"CloudLearningHub: 加载本地缓存失败 {e}")

    def _save_local_cache(self):
        """保存到本地缓存"""
        try:
            # 限制缓存大小
            if len(self._local_patterns) > MAX_CACHED_PATTERNS:
                # 删除质量最低的模式
                sorted_patterns = sorted(
                    self._local_patterns.items(),
                    key=lambda x: x[1].quality_score,
                    reverse=True
                )
                self._local_patterns = dict(sorted_patterns[:MAX_CACHED_PATTERNS])
            
            data = {"patterns": {}}
            for pattern_hash, pattern in self._local_patterns.items():
                data["patterns"][pattern_hash] = asdict(pattern)
            
            with open(CLOUD_KNOWLEDGE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
            logger.info(f"CloudLearningHub: 保存了 {len(self._local_patterns)} 个模式到本地缓存")
        except Exception as e:
            logger.error(f"CloudLearningHub: 保存本地缓存失败 {e}")

    def upload_pattern(
        self, 
        pattern: FixPattern,
        success: bool = True
    ) -> str:
        """
        上传修复模式到云端
        
        Args:
            pattern: 修复模式
            success: 是否成功修复
            
        Returns:
            模式哈希 ID
        """
        pattern_hash = self._compute_pattern_hash(pattern)
        
        cloud_pattern = CloudPattern(
            pattern=asdict(pattern),
            project_id=self.project_id,
            project_type=self.project_type,
            tech_stack=self.tech_stack,
            upload_time=datetime.now().isoformat(),
            download_count=0,
            success_votes=1 if success else 0,
            failure_votes=0 if success else 1
        )
        
        # 添加到本地缓存
        if pattern_hash in self._local_patterns:
            existing = self._local_patterns[pattern_hash]
            if success:
                existing.success_votes += 1
            else:
                existing.failure_votes += 1
            existing.download_count += 1
        else:
            self._local_patterns[pattern_hash] = cloud_pattern
        
        self._save_local_cache()
        
        logger.info(
            f"CloudLearningHub: 上传模式 {pattern_hash} "
            f"(错误类型：{pattern.error_type}, 项目：{self.project_id})"
        )
        
        return pattern_hash

    def download_similar_patterns(
        self, 
        query_error_type: str,
        query_keywords: Optional[List[str]] = None,
        max_results: int = 10
    ) -> List[CloudPattern]:
        """
        下载相似的修复模式
        
        Args:
            query_error_type: 查询的错误类型
            query_keywords: 查询关键词
            max_results: 最大返回数量
            
        Returns:
            高质量修复模式列表
        """
        results = []
        
        # 1. 先从本地缓存查找
        for pattern_hash, cloud_pattern in self._local_patterns.items():
            pattern = FixPattern(**cloud_pattern.pattern)
            
            # 错误类型匹配
            if pattern.error_type != query_error_type:
                continue
            
            # 关键词匹配
            if query_keywords:
                matched = False
                for keyword in query_keywords:
                    if keyword.lower() in pattern.error_message.lower():
                        matched = True
                        break
                if not matched:
                    continue
            
            # 只返回高质量模式
            if cloud_pattern.is_high_quality() and not pattern.is_anti_pattern():
                results.append(cloud_pattern)
        
        # 2. 按质量分数排序
        results.sort(key=lambda x: x.quality_score, reverse=True)
        
        # 3. 增加下载计数
        for result in results[:max_results]:
            result.download_count += 1
        
        self._save_local_cache()
        
        logger.info(
            f"CloudLearningHub: 找到 {len(results)} 个相似模式 "
            f"(错误类型：{query_error_type})"
        )
        
        return results[:max_results]

    def vote_pattern(self, pattern_hash: str, success: bool):
        """
        对模式投票反馈效果
        
        Args:
            pattern_hash: 模式哈希 ID
            success: 是否成功应用
        """
        if pattern_hash not in self._local_patterns:
            logger.warning(f"CloudLearningHub: 模式 {pattern_hash} 不存在，无法投票")
            return
        
        pattern = self._local_patterns[pattern_hash]
        if success:
            pattern.success_votes += 1
            logger.info(f"CloudLearningHub: 模式 {pattern_hash} 获得 1 张成功票")
        else:
            pattern.failure_votes += 1
            logger.warning(f"CloudLearningHub: 模式 {pattern_hash} 获得 1 张失败票")
        
        self._save_local_cache()

    def get_project_knowledge_stats(self) -> Dict[str, Any]:
        """获取项目知识统计"""
        total_patterns = len(self._local_patterns)
        high_quality_patterns = sum(
            1 for p in self._local_patterns.values() 
            if p.is_high_quality()
        )
        total_downloads = sum(p.download_count for p in self._local_patterns.values())
        total_votes = sum(
            p.success_votes + p.failure_votes 
            for p in self._local_patterns.values()
        )
        total_success_votes = sum(
            p.success_votes for p in self._local_patterns.values()
        )
        
        # 按项目类型统计
        project_type_counts: Dict[str, int] = {}
        for pattern in self._local_patterns.values():
            ptype = pattern.project_type
            project_type_counts[ptype] = project_type_counts.get(ptype, 0) + 1
        
        return {
            "total_patterns": total_patterns,
            "high_quality_patterns": high_quality_patterns,
            "total_downloads": total_downloads,
            "total_votes": total_votes,
            "overall_success_rate": total_success_votes / total_votes if total_votes > 0 else 0,
            "project_type_distribution": project_type_counts,
            "top_patterns": [
                {
                    "hash": h,
                    "error_type": p.pattern["error_type"],
                    "quality_score": p.quality_score,
                    "download_count": p.download_count
                }
                for h, p in sorted(
                    self._local_patterns.items(),
                    key=lambda x: x[1].quality_score,
                    reverse=True
                )[:5]
            ]
        }

    def clear_cache(self):
        """清空本地缓存"""
        self._local_patterns.clear()
        if CLOUD_KNOWLEDGE_FILE.exists():
            CLOUD_KNOWLEDGE_FILE.unlink()
        logger.info("CloudLearningHub: 已清空本地缓存")


# 全局单例
_cloud_hub: Optional[CloudLearningHub] = None
_hub_lock = asyncio.Lock()


async def get_cloud_learning_hub(
    project_id: str = "default",
    project_type: str = "web",
    tech_stack: Optional[List[str]] = None
) -> CloudLearningHub:
    """获取 CloudLearningHub 单例"""
    global _cloud_hub
    if _cloud_hub is None:
        async with _hub_lock:
            if _cloud_hub is None:
                _cloud_hub = CloudLearningHub(
                    project_id=project_id,
                    project_type=project_type,
                    tech_stack=tech_stack
                )
    return _cloud_hub
