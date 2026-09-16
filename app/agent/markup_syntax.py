"""共享的 HTML/CSS 结构校验。

生成管线里 `code_validator`（项目级与单文件校验）和 `refinement_loop`
（逐文件修复）都要判断 HTML/CSS 结构是否成立。纯计数实现会把注释、字符串
以及原始文本元素（script/style）里的定界符当成结构符号，从而产生误报，
因此统一在这里实现一份。
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Dict, List

_STRUCTURE_TAGS = ("html", "head", "body")
_RAW_TEXT_TAGS = ("script", "style")


class RawTextTagBalance(HTMLParser):
    """统计标签的开始与结束数量。

    原始文本元素内部出现的 ``<script``/``<style``/``<body`` 是普通文本而非
    标签（如 JS 字符串里的 ``"<script src=x>"``），注释同样不算标签，用解析器
    计数可避免把这些内容误判为结构错误。
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.starts: Dict[str, int] = {}
        self.ends: Dict[str, int] = {}

    def handle_starttag(self, tag, attrs):
        self.starts[tag] = self.starts.get(tag, 0) + 1

    def handle_startendtag(self, tag, attrs):
        self.starts[tag] = self.starts.get(tag, 0) + 1
        self.ends[tag] = self.ends.get(tag, 0) + 1

    def handle_endtag(self, tag):
        self.ends[tag] = self.ends.get(tag, 0) + 1


def html_structure_errors(content: str) -> List[str]:
    """返回 HTML 结构问题列表（空列表表示通过）。

    HTML5 允许省略 ``</head>``、``</body>``、``</html>``。只要文档以
    ``</html>`` 正常结束，前面省略的闭合标签就是合法的；不含这些标签的
    HTML 片段同样不做要求。
    """
    errors: List[str] = []
    document_closed = bool(re.search(r"</html\s*>", content, re.IGNORECASE))

    parser = RawTextTagBalance()
    parser.feed(content)
    parser.close()

    for tag in _STRUCTURE_TAGS:
        if parser.starts.get(tag, 0) > parser.ends.get(tag, 0) and not document_closed:
            errors.append(f"HTML 结构: 缺少 </{tag}> 闭合标签")

    for tag in _RAW_TEXT_TAGS:
        if parser.starts.get(tag, 0) > parser.ends.get(tag, 0):
            errors.append(
                f"HTML 结构: 缺少 </{tag}> 闭合标签 "
                f"(开: {parser.starts.get(tag, 0)}, 关: {parser.ends.get(tag, 0)})"
            )

    return errors


def css_structure_errors(content: str, *, check_parentheses: bool = False) -> List[str]:
    """返回 CSS 结构问题列表（空列表表示通过）。

    注释和字符串里的 ``{ } ( )`` 不是结构字符（如 ``content: "}"`` 或
    ``/* } */``），先剥离再做配对检查。空声明（连续或孤立的分号）在 CSS 中
    合法，不作为错误。
    """
    errors: List[str] = []
    sanitized = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    sanitized = re.sub(r'"[^"\n]*"|\'[^\'\n]*\'', "", sanitized)

    open_braces = sanitized.count("{")
    close_braces = sanitized.count("}")
    if open_braces != close_braces:
        errors.append(f"CSS 语法: 大括号不匹配 (开: {open_braces}, 关: {close_braces})")

    if check_parentheses:
        open_parens = sanitized.count("(")
        close_parens = sanitized.count(")")
        if open_parens != close_parens:
            errors.append(f"CSS 语法: 小括号不匹配 (开: {open_parens}, 关: {close_parens})")

    return errors
