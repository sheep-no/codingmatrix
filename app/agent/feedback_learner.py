"""
FeedbackLearner - 模型反馈学习

支持：
1. 记录 RefinementLoop 的修复模式
2. 学习常见错误和修复方法
3. 优化生成 prompt（基于历史修复经验）
4. 错误模式匹配和预防（向量化匹配）
"""

import json
import logging
import math
import re
import asyncio
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime

from app.utils.math_utils import cosine_similarity

logger = logging.getLogger(__name__)

# 学习数据存储目录
LEARNING_DIR = Path("./data/learning_data")
# 会话记录最大数量（超出时自动裁剪最旧的记录）
MAX_SESSION_RECORDS = 1000


@dataclass
class FixPattern:
    """修复模式"""
    error_type: str               # 错误类型（语法、导入、依赖、逻辑等）
    error_message: str            # 错误信息（归一化）
    error_pattern: str            # 错误模式（正则表达式）
    fix_description: str          # 修复描述
    fix_example: str              # 修复示例
    file_types: List[str]         # 适用的文件类型
    frequency: int = 1            # 出现频率
    success_rate: float = 1.0     # 成功率
    last_seen: str = ""           # 最后出现时间

    failed_count: int = 0         # 累计验证失败次数（反模式追踪）
    last_failed_at: Optional[str] = None  # 最后失败时间
    failure_reason: Optional[str] = None  # 最近一次失败原因

    error_embedding: Optional[List[float]] = None

    def is_anti_pattern(self, threshold: int = 3) -> bool:
        """判定是否为反模式：失败次数超过阈值且成功率过低"""
        return self.failed_count >= threshold and self.success_rate < 0.3


@dataclass
class ErrorPattern:
    """错误模式（用于预防）"""
    pattern: str                  # 错误模式描述
    keyword: str                  # 触发关键词
    severity: str = "low"         # 严重程度（low, medium, high）
    prevention_prompt: str = ""   # 预防性提示
    occurrences: int = 0


class FeedbackLearner:
    """模型反馈学习器（支持向量化匹配）"""

    def __init__(self, learning_dir: Optional[Path] = None):
        self.learning_dir = learning_dir or LEARNING_DIR
        self.learning_dir.mkdir(parents=True, exist_ok=True)
        self._fix_patterns: Dict[str, FixPattern] = {}
        self._error_patterns: Dict[str, ErrorPattern] = {}
        self._session_records: List[Dict[str, Any]] = []

        # 向量索引
        self._error_vectors: Dict[str, List[float]] = {}  # pattern_key → embedding

        self._load_patterns()

    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        return cosine_similarity(vec1, vec2)

    def record_fix(
        self,
        file_path: str,
        file_type: str,
        original_content: str,
        fixed_content: str,
        errors: Dict[str, Any],
        model_name: str,
        success: bool,
        error_embeddings: Optional[Dict[str, List[float]]] = None
    ):
        """记录一次修复"""
        for error_type, error_list in errors.items():
            if not error_list:
                continue

            for error_msg in error_list:
                pattern_key = self._normalize_error(error_msg)
                pattern_key = f"{error_type}:{pattern_key}"

                if pattern_key in self._fix_patterns:
                    pattern = self._fix_patterns[pattern_key]
                    pattern.frequency += 1
                    pattern.last_seen = datetime.now().isoformat()
                    if success:
                        pattern.success_rate = (
                            pattern.success_rate * (pattern.frequency - 1) + 1.0
                        ) / pattern.frequency
                    else:
                        pattern.failed_count += 1
                        pattern.last_failed_at = datetime.now().isoformat()
                        pattern.failure_reason = error_msg[:200]
                        pattern.success_rate = (
                            pattern.success_rate * (pattern.frequency - 1) + 0.0
                        ) / pattern.frequency
                else:
                    fix_description = self._extract_fix_description(
                        original_content, fixed_content, error_msg
                    )

                    # 获取 embedding（如果有）
                    embedding = None
                    if error_embeddings and error_msg in error_embeddings:
                        embedding = error_embeddings[error_msg]
                    elif error_embeddings is None and pattern_key in self._error_vectors:
                        embedding = self._error_vectors[pattern_key]

                    self._fix_patterns[pattern_key] = FixPattern(
                        error_type=error_type,
                        error_message=error_msg,
                        error_pattern=self._build_error_regex(error_msg),
                        fix_description=fix_description,
                        fix_example=self._extract_code_diff(
                            original_content, fixed_content
                        ),
                        file_types=[file_type],
                        frequency=1,
                        success_rate=1.0 if success else 0.0,
                        last_seen=datetime.now().isoformat(),
                        failed_count=0 if success else 1,
                        last_failed_at=None if success else datetime.now().isoformat(),
                        failure_reason=None if success else error_msg[:200],
                        error_embedding=embedding
                    )

                    if embedding is not None:
                        self._error_vectors[pattern_key] = embedding

        record = {
            "file_path": file_path,
            "file_type": file_type,
            "model_name": model_name,
            "errors": errors,
            "success": success,
            "timestamp": datetime.now().isoformat()
        }
        self._session_records.append(record)
        # 防止内存泄漏：裁剪超出上限的旧记录
        if len(self._session_records) > MAX_SESSION_RECORDS:
            self._session_records = self._session_records[-MAX_SESSION_RECORDS:]

        self._save_patterns()

    async def get_prevention_prompt(
        self,
        file_path: str,
        file_type: str,
        project_context: Dict[str, Any],
        error_context: Optional[str] = None
    ) -> str:
        """
        生成预防性 prompt（基于历史修复经验）
        
        优化：
        - 如果有 error_context，计算 embedding 后用向量匹配
        """
        query_embedding = None
        if error_context:
            from app.utils.AiCodeUtil import get_embedding
            try:
                query_embedding = await get_embedding(f"error context: {error_context}")
            except Exception as e:
                logger.warning(f"预防 prompt embedding 失败: {e}")

        relevant_patterns = await self._find_relevant_patterns_async(
            file_path, file_type, query_embedding
        )

        if not relevant_patterns:
            return ""

        parts = [
            "\n## 历史修复经验（重要提示）",
            "根据历史修复记录，生成以下代码时请特别注意：",
            ""
        ]

        for pattern in relevant_patterns[:5]:
            parts.append(f"- {pattern.fix_description}")
            if pattern.fix_example:
                parts.append(f"  示例: {pattern.fix_example[:100]}...")

        return "\n".join(parts)

    async def _find_relevant_patterns_async(
        self,
        file_path: str,
        file_type: str,
        query_embedding: Optional[List[float]] = None
    ) -> List[FixPattern]:
        """异步版本的模式查找（支持向量化）"""
        relevant = []

        if query_embedding is not None:
            scored_patterns = []
            for pattern_key, pattern in self._fix_patterns.items():
                if pattern.error_embedding is not None and pattern.success_rate > 0.3 and not pattern.is_anti_pattern():
                    similarity = self._cosine_similarity(query_embedding, pattern.error_embedding)
                    if similarity > 0.7:
                        scored_patterns.append((similarity, pattern))

            scored_patterns.sort(key=lambda x: x[0], reverse=True)
            relevant = [p for _, p in scored_patterns[:10]]
        else:
            for pattern in self._fix_patterns.values():
                if pattern.frequency > 1 and pattern.success_rate > 0.5 and not pattern.is_anti_pattern():
                    if file_type in pattern.file_types or file_type == "unknown":
                        relevant.append(pattern)
            relevant.sort(key=lambda x: x.frequency, reverse=True)

        return relevant

    def get_common_errors(self, file_type: str) -> List[Dict[str, Any]]:
        """获取指定文件类型的常见错误"""
        common = []
        for pattern_key, pattern in self._fix_patterns.items():
            if file_type in pattern.file_types or file_type == "unknown":
                common.append({
                    "error_type": pattern.error_type,
                    "error_message": pattern.error_message,
                    "frequency": pattern.frequency,
                    "success_rate": pattern.success_rate,
                    "fix_description": pattern.fix_description
                })

        # 按频率排序
        common.sort(key=lambda x: x["frequency"], reverse=True)
        return common[:10]

    def get_learning_stats(self) -> Dict[str, Any]:
        """获取学习统计"""
        total_fixes = sum(p.frequency for p in self._fix_patterns.values())
        total_records = len(self._session_records)
        success_records = sum(
            1 for r in self._session_records if r.get("success")
        )

        return {
            "learned_patterns": len(self._fix_patterns),
            "total_fixes_recorded": total_fixes,
            "total_sessions": total_records,
            "overall_success_rate": success_records / total_records if total_records > 0 else 0.0,
            "top_errors": self.get_common_errors("unknown")[:5]
        }

    def _normalize_error(self, error_msg: str) -> str:
        """归一化错误信息"""
        text = error_msg.lower().strip()
        # 移除行号等变化部分
        text = re.sub(r'第?\d+行?', 'LINE', text)
        text = re.sub(r'line \d+', 'line X', text)
        text = re.sub(r'position \d+', 'position X', text)
        return text[:100]

    def _build_error_regex(self, error_msg: str) -> str:
        """构建错误模式的正则表达式"""
        # 简单实现：提取关键词
        keywords = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z_]+', error_msg)
        return "|".join(keywords[:5])

    def _extract_fix_description(
        self,
        original: str,
        fixed: str,
        error_msg: str
    ) -> str:
        """提取修复描述"""
        # 基于错误类型生成描述
        if "语法" in error_msg or "syntax" in error_msg.lower():
            return "修复语法错误（检查括号、缩进、关键字拼写）"
        elif "导入" in error_msg or "import" in error_msg.lower():
            return "修复导入错误（确保模块存在且路径正确）"
        elif "依赖" in error_msg or "dependency" in error_msg.lower():
            return "修复依赖错误（添加缺失的包到 requirements.txt）"
        elif "类型" in error_msg or "type" in error_msg.lower():
            return "修复类型错误（检查变量类型和注解）"
        else:
            return f"修复: {error_msg[:50]}"

    def _extract_code_diff(self, original: str, fixed: str) -> str:
        """提取代码差异（简化版）"""
        orig_lines = original.split('\n')
        fixed_lines = fixed.split('\n')

        # 找到第一个不同的行
        diff_start = 0
        for i in range(min(len(orig_lines), len(fixed_lines))):
            if orig_lines[i] != fixed_lines[i]:
                diff_start = i
                break

        # 提取差异区域（前后各 2 行）
        start = max(0, diff_start - 2)
        end = min(len(fixed_lines), diff_start + 5)

        diff_lines = fixed_lines[start:end]
        return '\n'.join(diff_lines)[:100]

    async def compute_error_embeddings(self, errors: List[str]) -> Dict[str, List[float]]:
        """
        批量计算错误信息的 embedding
        
        Returns:
            {error_msg: embedding}
        """
        from app.utils.AiCodeUtil import get_embedding

        result = {}
        for error_msg in errors:
            try:
                embedding = await get_embedding(f"error: {error_msg}")
                result[error_msg] = embedding
            except Exception as e:
                logger.warning(f"错误 embedding 失败: {error_msg[:50]}, {e}")
        return result

    def _find_relevant_patterns(
        self,
        file_path: str,
        file_type: str,
        query_embedding: Optional[List[float]] = None
    ) -> List[FixPattern]:
        """
        查找相关的修复模式（向量化匹配优化）
        
        优化：
        - 如果有 query_embedding，用余弦相似度匹配
        - 否则用传统的文件类型匹配
        """
        relevant = []
        ext = Path(file_path).suffix.lower()

        if query_embedding is not None:
            # 向量化匹配
            scored_patterns = []
            for pattern_key, pattern in self._fix_patterns.items():
                if pattern.error_embedding is not None and pattern.success_rate > 0.3:
                    similarity = self._cosine_similarity(query_embedding, pattern.error_embedding)
                    if similarity > 0.7:  # 相似度阈值
                        scored_patterns.append((similarity, pattern))

            # 按相似度排序
            scored_patterns.sort(key=lambda x: x[0], reverse=True)
            relevant = [p for _, p in scored_patterns[:10]]
        else:
            # 传统匹配：频率 > 1 且成功率 > 0.5
            for pattern in self._fix_patterns.values():
                if pattern.frequency > 1 and pattern.success_rate > 0.5:
                    if file_type in pattern.file_types or file_type == "unknown":
                        relevant.append(pattern)

            relevant.sort(key=lambda x: x.frequency, reverse=True)

        return relevant

    def _load_patterns(self):
        """加载修复模式"""
        patterns_file = self.learning_dir / "fix_patterns.json"
        if patterns_file.exists():
            try:
                with open(patterns_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for key, p_data in data.items():
                    self._fix_patterns[key] = FixPattern(**p_data)
                    # 加载向量索引
                    if p_data.get("error_embedding") is not None:
                        self._error_vectors[key] = p_data["error_embedding"]
            except Exception as e:
                logger.error(f"加载修复模式失败: {e}")

    def _save_patterns(self):
        """保存修复模式"""
        patterns_file = self.learning_dir / "fix_patterns.json"
        try:
            data = {
                k: {
                    "error_type": v.error_type,
                    "error_message": v.error_message,
                    "error_pattern": v.error_pattern,
                    "fix_description": v.fix_description,
                    "fix_example": v.fix_example,
                    "file_types": v.file_types,
                    "frequency": v.frequency,
                    "success_rate": v.success_rate,
                    "last_seen": v.last_seen,
                    "failed_count": v.failed_count,
                    "last_failed_at": v.last_failed_at,
                    "failure_reason": v.failure_reason,
                    "error_embedding": v.error_embedding
                }
                for k, v in self._fix_patterns.items()
            }
            with open(patterns_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存修复模式失败: {e}")

    # ===== 异步包装方法 =====

    async def async_record_fix(self, *args, **kwargs):
        """异步记录修复（非阻塞事件循环）"""
        return await asyncio.to_thread(self.record_fix, *args, **kwargs)

    async def async_save_patterns(self):
        """异步保存修复模式"""
        return await asyncio.to_thread(self._save_patterns)

    async def async_learn_patterns(self, file_path, file_type, error_msg, error_type, fix_content, success=True):
        """异步学习修复模式"""
        return await asyncio.to_thread(
            self.learn_fix_patterns, file_path, file_type, error_msg, error_type, fix_content, success
        )
