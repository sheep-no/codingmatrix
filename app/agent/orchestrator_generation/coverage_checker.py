import re
from pathlib import Path
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

# 需求中显式点名的可创建文件；只覆盖常见源码/文档/配置扩展名。
_ARTIFACT_RE = re.compile(
    r"(?<![\w/.-])((?:[\w.-]+/)*[\w.-]+"
    r"\.(?:html?|md|json|ya?ml|toml|txt|py|js|jsx|ts|tsx|vue|css|scss|java|go|rs|sh))"
)
_SENTENCE_SPLIT_RE = re.compile(r"[。；;！!\n]")
_CLAUSE_SPLIT_RE = re.compile(r"[，,]")
_ROOT_HINTS = (
    "根级", "根目录", "项目根", "根路径", "仓库根",
    "root-level", "project root", "repository root",
)
_CREATE_HINTS = (
    "生成", "创建", "包含", "输出", "提供", "需要", "必须", "放在", "写入", "添加",
    "create", "generate", "include", "provide", "output", "add", "write", "must",
)


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


def extract_required_artifacts(requirement: str) -> list[dict[str, Any]]:
    """Extract files the requirement explicitly asks to create.

    A path becomes a hard requirement only when the same sentence names it in a
    clause carrying a creation verb. Root-level hints apply to the whole
    sentence, so "根级 index.html 与 README.md" marks both as root files.
    """
    if not requirement:
        return []
    requirement = _strip_internal_context(requirement)
    found: dict[str, bool] = {}
    order: list[str] = []
    for sentence in _SENTENCE_SPLIT_RE.split(requirement):
        if not sentence.strip():
            continue
        lowered = sentence.lower()
        root_scoped = any(hint in lowered for hint in _ROOT_HINTS)
        for clause in _CLAUSE_SPLIT_RE.split(sentence):
            clause_lower = clause.lower()
            if not any(hint in clause_lower for hint in _CREATE_HINTS):
                continue
            for match in _ARTIFACT_RE.finditer(clause):
                path = match.group(1).strip("./")
                if not path or path.startswith(("http", "www.")):
                    continue
                if path not in found:
                    found[path] = root_scoped
                    order.append(path)
                elif root_scoped:
                    found[path] = True
    return [{"path": path, "root": found[path]} for path in order]


def _strip_internal_context(text: str) -> str:
    """Keep only the user requirement; ignore pipeline banners and Skill text."""
    text = re.sub(r"^\[Pipeline Mode\]\n.*?\n\n", "", text, count=1, flags=re.DOTALL)
    return text.split("\n\n[Available Skills]\n", 1)[0]


def check_required_artifacts(
    requirement: str,
    generated_paths: list[str],
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Verify requirement-named artifacts exist in the generated paths.

    Root-scoped artifacts must sit at the project root; other artifacts may be
    nested (``README.md`` under ``docs/`` counts unless root was requested).
    """
    required = extract_required_artifacts(requirement)
    if not required:
        return {
            "checked": False,
            "required": [],
            "missing": [],
            "passed": True,
        }
    existing = {str(path).replace("\\", "/").strip("./") for path in generated_paths if path}
    missing = []
    for item in required:
        path = item["path"]
        if item["root"]:
            satisfied = path in existing
        else:
            satisfied = any(
                candidate == path or candidate.endswith("/" + path)
                for candidate in existing
            )
        if not satisfied and output_dir is not None:
            satisfied = _artifact_exists_on_disk(output_dir, path, item["root"])
        if not satisfied:
            missing.append(path)
    return {
        "checked": True,
        "required": required,
        "missing": missing,
        "passed": not missing,
    }


def _artifact_exists_on_disk(
    output_dir: str | Path,
    path: str,
    root_scoped: bool,
) -> bool:
    root_dir = Path(output_dir)
    relative = Path(path)
    if not root_dir.is_dir() or relative.is_absolute() or ".." in relative.parts:
        return False
    if (root_dir / relative).is_file():
        return True
    if root_scoped:
        return False
    return any(candidate.is_file() for candidate in root_dir.glob(f"**/{path}"))


def materialize_scaffold_artifacts(
    required: list[dict[str, Any]],
    output_dir: str | Path,
    language: str,
    architecture: dict[str, Any],
) -> list[dict[str, str]]:
    """Create deterministic README/manifest files that the requirement names."""
    from app.agent.adapters.boilerplate import (
        MANIFEST_NAMES,
        README_NAMES,
        scaffold_for_language,
    )
    from app.agent.utils import write_file_atomic

    root_dir = Path(output_dir)
    created: list[dict[str, str]] = []
    for item in required:
        path = str(item.get("path") or "")
        relative = Path(path)
        if (
            not path
            or relative.is_absolute()
            or ".." in relative.parts
            or relative.name.lower() not in README_NAMES | MANIFEST_NAMES
        ):
            continue
        content = scaffold_for_language(language, path, "", architecture)
        if not content:
            continue
        write_file_atomic(
            root_dir,
            path,
            content,
            skip_placeholder_check=True,
        )
        created.append({"path": path, "content": content})
    return created
