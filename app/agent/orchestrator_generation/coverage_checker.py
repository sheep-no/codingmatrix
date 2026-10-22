import re
from typing import Any

# 覆盖率检查可调参数（模块级常量，调优入口；与 memory.py 阈值常量风格一致）
# 功能项进入检查的最低关联置信度
COVERAGE_CONFIDENCE_THRESHOLD = 0.7
# 显著关键词命中率低于该比例时判为未覆盖
COVERAGE_MATCH_RATIO = 0.3
# 从架构信息中提取语料的字段名
COVERAGE_ARCH_FIELDS = ("project_type", "tech_stack", "database", "api_endpoints")

_ASCII_WORD_RE = re.compile(r"[a-zA-Z0-9_]+")
_CJK_SEG_RE = re.compile(r"[\u4e00-\u9fff]+")


def _tokenize(text: str) -> list[str]:
    """切分出可匹配的检索单元。

    英文/数字按词提取；中文无空格边界，按字符 bigram 切分
    （单字段落退化为单字），使中文需求能以词粒度命中语料。
    """
    tokens = _ASCII_WORD_RE.findall(text)
    for seg in _CJK_SEG_RE.findall(text):
        if len(seg) == 1:
            tokens.append(seg)
        else:
            tokens.extend(seg[i:i + 2] for i in range(len(seg) - 1))
    return tokens


def _is_significant(token: str) -> bool:
    """判定 token 是否计入命中率分母：过滤英文停用短词与中文单字。"""
    if _CJK_SEG_RE.fullmatch(token):
        return len(token) >= 2
    return len(token) > 2


def _unchecked() -> dict[str, Any]:
    """未执行检查的统一返回：coverage_rate 用 None 与真实满分区分。"""
    return {"checked": False, "total_items": 0, "uncovered": [], "coverage_rate": None}


def check_requirement_coverage(
    requirement: str,
    architecture: dict,
    file_plan: list[dict],
    association_result: Any | None = None,
) -> dict[str, Any]:
    if not association_result:
        return _unchecked()

    association_items = association_result.items
    if not association_items or association_result.skipped:
        return _unchecked()

    confirmed_items = [
        i for i in association_items
        if i.confidence >= COVERAGE_CONFIDENCE_THRESHOLD and i.category == "functional"
    ]
    if not confirmed_items:
        return {"checked": True, "total_items": 0, "uncovered": [], "coverage_rate": 1.0}

    all_content = []
    for file_info in file_plan:
        path = file_info.get("path", "")
        desc = file_info.get("description", "")
        all_content.append(path.lower())
        all_content.append(desc.lower())

    arch_content = []
    for key in COVERAGE_ARCH_FIELDS:
        val = architecture.get(key, "")
        if isinstance(val, str):
            arch_content.append(val.lower())
        elif isinstance(val, list):
            arch_content.extend(str(v).lower() for v in val)

    combined_text = " ".join(all_content + arch_content)
    corpus_tokens = set(_tokenize(combined_text))

    uncovered = []
    for item in confirmed_items:
        keywords = [kw for kw in _tokenize(item.content.lower()) if _is_significant(kw)]
        # 词级集合求交替代子串包含，避免 'api' 命中 'rapid' 类虚增覆盖
        matched_kw = sum(1 for kw in keywords if kw in corpus_tokens)
        if keywords and matched_kw < len(keywords) * COVERAGE_MATCH_RATIO:
            uncovered.append({
                "item": item.content,
                "category": item.category,
                "source": item.source,
                "confidence": item.confidence,
            })

    coverage_rate = 1.0 - (len(uncovered) / max(len(confirmed_items), 1))

    return {
        "checked": True,
        "total_items": len(confirmed_items),
        "uncovered": uncovered,
        "coverage_rate": coverage_rate,
    }
