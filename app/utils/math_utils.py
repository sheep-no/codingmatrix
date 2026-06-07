"""
共享数学工具函数
"""

import math
from typing import List


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """计算两个向量的余弦相似度

    Args:
        vec1: 第一个向量
        vec2: 第二个向量

    Returns:
        余弦相似度，范围 [-1, 1]。若任一向量模为零或维度不匹配则返回 0.0
    """
    if len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return dot / (norm1 * norm2)
