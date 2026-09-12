"""Requirement keyword matching with negation and ASCII word boundaries."""

from __future__ import annotations

import re
from typing import Iterable, List, Optional, Sequence, Tuple

_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_NEGATION_RE = re.compile(
    r"(?:不需要|不包含|不含|不要|无需|不用|不必|禁止|拒绝|没有|绝不|别用|别加|别|"
    r"无|非|do\s+not|don't|don’t|without|never|exclude|excluding|skip|omit|no|not)"
    r"(?:\s*(?:a|an|the|any|all|use|using|with|用|使用|任何|所有))*"
    r"\s*[,，、]?\s*$",
    re.IGNORECASE,
)


def _is_cjk(keyword: str) -> bool:
    return bool(_CJK_RE.search(keyword))


def find_keyword_spans(text: str, keyword: str) -> List[Tuple[int, int]]:
    """Return (start, end) spans for keyword hits in text."""
    if not text or not keyword:
        return []
    haystack = text.lower()
    needle = keyword.lower()
    if _is_cjk(keyword) or not needle.isascii():
        spans = []
        start = 0
        while True:
            idx = haystack.find(needle, start)
            if idx < 0:
                break
            spans.append((idx, idx + len(needle)))
            start = idx + len(needle)
        return spans
    pattern = r"(?<![A-Za-z0-9_])" + re.escape(needle) + r"(?![A-Za-z0-9_])"
    return [(match.start(), match.end()) for match in re.finditer(pattern, haystack)]


def is_span_negated(text: str, start: int, window: int = 16) -> bool:
    """True when a negation token immediately precedes the span."""
    if start <= 0:
        return False
    prefix = text[max(0, start - window):start]
    return bool(_NEGATION_RE.search(prefix))


def first_positive_span(text: str, keyword: str) -> Optional[Tuple[int, int]]:
    for start, end in find_keyword_spans(text, keyword):
        if not is_span_negated(text, start):
            return start, end
    return None


def has_positive_keyword(text: str, keywords: Sequence[str]) -> bool:
    return any(first_positive_span(text, keyword) for keyword in keywords)


def positive_keywords(text: str, keywords: Iterable[str]) -> List[str]:
    hits = []
    for keyword in keywords:
        if first_positive_span(text, keyword):
            hits.append(keyword)
    return hits
