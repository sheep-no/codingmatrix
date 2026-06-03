"""
多角度审查系统

将单一魔鬼代言人拆分为 3 个专业审查角色：
- 性能师：N+1 查询、大数据量表现、缓存策略
- 安全师：SQL 注入、XSS、越权、敏感数据泄露
- 可维护性师：代码清晰度、模块耦合、交接难度

审查严格度配置：
- 轻量：仅契约检查 + 交叉验证
- 标准：+ 单一魔鬼代言人
- 严格：+ 多视角审查（3 个角色）
"""
import json
import logging
import asyncio
import re
from pathlib import Path
from enum import Enum
from typing import List, Dict

from app.agent.orchestrator_requirements.constants import DEVILS_ADVOCATE_MODEL
from app.agent.orchestrator_requirements.data_models import AssociationItem

logger = logging.getLogger(__name__)

# --- 提示词目录 ---
_SKILLS_DIR = Path(__file__).parent.parent.parent / ".claude" / "skills" / "orchestrator"

# --- 审查严格度 ---

class ReviewSeverity(str, Enum):
    """审查严格度"""
    LIGHT = "light"       # 轻量：仅契约检查 + 交叉验证
    STANDARD = "standard" # 标准：+ 单一魔鬼代言人
    STRICT = "strict"     # 严格：+ 多视角审查


# --- 从文件加载 System Prompts ---

def _load_prompt(filename: str) -> str:
    """从 skills 目录加载审查提示词"""
    filepath = _SKILLS_DIR / filename
    if filepath.exists():
        return filepath.read_text(encoding="utf-8")
    else:
        logger.warning(f"审查提示词文件不存在：{filepath}，使用内置默认值")
        return _get_default_prompt(filename)


def _get_default_prompt(filename: str) -> str:
    """内置默认提示词"""
    defaults = {
        "performance_reviewer_prompt.md": """你是资深性能工程师，专注于系统性能瓶颈识别和优化。关注 N+1 查询、缓存策略、内存泄漏、I/O 瓶颈、并发问题。请输出审查结果，格式：{"reviews": [{"target": "...", "issue": "...", "severity": "critical/high/medium/low", "suggestion": "...", "category": "database/cache/memory/io/concurrency"}]}""",

        "security_reviewer_prompt.md": """你是资深安全工程师，专注于应用安全漏洞识别和防护。关注 SQL 注入、XSS、越权、敏感数据泄露、认证缺陷、输入验证。请输出审查结果，格式：{"reviews": [{"target": "...", "vulnerability": "...", "severity": "critical/high/medium/low", "suggestion": "..."}]}""",

        "maintainability_reviewer_prompt.md": """你是资深软件架构师，专注于代码可维护性评估。关注代码清晰度、模块耦合、代码重复、设计模式、测试友好性、交接难度、可扩展性。请输出审查结果，格式：{"reviews": [{"target": "...", "issue": "...", "severity": "critical/high/medium/low", "suggestion": "...", "category": "clarity/coupling/repetition/pattern/testing/handoff/extensibility"}]}"""
    }
    return defaults.get(filename, "")


# --- 缓存提示词 ---
PERFORMANCE_SYS_PROMPT = _load_prompt("performance_reviewer_prompt.md")
SECURITY_SYS_PROMPT = _load_prompt("security_reviewer_prompt.md")
MAINTAINABILITY_SYS_PROMPT = _load_prompt("maintainability_reviewer_prompt.md")


# --- 审查角色 ---

REVIEW_ROLES = {
    "performance": {
        "name": "性能师",
        "system_prompt": PERFORMANCE_SYS_PROMPT,
    },
    "security": {
        "name": "安全师",
        "system_prompt": SECURITY_SYS_PROMPT,
    },
    "maintainability": {
        "name": "可维护性师",
        "system_prompt": MAINTAINABILITY_SYS_PROMPT,
    },
}


# --- 核心审查逻辑 ---

async def multi_angle_review(
    requirement: str,
    items: List[AssociationItem],
    severity: ReviewSeverity = ReviewSeverity.STANDARD,
    architect: object = None,
) -> List[Dict]:
    """
    多角度审查入口

    Args:
        requirement: 用户需求
        items: 联想项列表
        severity: 审查严格度
        architect: 架构师对象

    Returns:
        审查结果列表
    """
    if not architect or len(items) < 3:
        return []

    high_conf_items = [i for i in items if i.confidence >= 0.5]
    if not high_conf_items:
        return []

    if severity == ReviewSeverity.LIGHT:
        # 轻量模式：仅契约检查 + 交叉验证
        logger.info("轻量模式：跳过魔鬼代言人审查")
        return []

    elif severity == ReviewSeverity.STANDARD:
        # 标准模式：单一魔鬼代言人
        return await devil_advocate_review(requirement, items, architect)

    elif severity == ReviewSeverity.STRICT:
        # 严格模式：多视角审查
        return await parallel_multi_review(requirement, items)

    return []


async def parallel_multi_review(
    requirement: str,
    items: List[AssociationItem],
) -> List[Dict]:
    """
    并行执行 3 个角色的审查

    Args:
        requirement: 用户需求
        items: 联想项列表

    Returns:
        合并后的审查结果
    """
    items_summary = "\n".join(
        f"  [{i.category}] {i.content} (置信度: {i.confidence:.1f})"
        for i in items[:15]
    )

    # 准备 3 个角色的审查任务
    tasks = []
    for role_name, role_config in REVIEW_ROLES.items():
        task = _review_with_role(
            role_name=role_name,
            system_prompt=role_config["system_prompt"],
            requirement=requirement,
            items_summary=items_summary,
        )
        tasks.append(task)

    # 并行执行（最多 3 个并发）
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 合并结果
    all_reviews = []
    for i, result in enumerate(results):
        role_name = list(REVIEW_ROLES.keys())[i]
        if isinstance(result, Exception):
            logger.warning(f"{role_name} 审查失败: {result}")
        else:
            all_reviews.extend(result)

    logger.info(f"多角度审查完成：共 {len(all_reviews)} 条意见")
    return all_reviews[:30]  # 最多返回 30 条


async def _review_with_role(
    role_name: str,
    system_prompt: str,
    requirement: str,
    items_summary: str,
) -> List[Dict]:
    """使用特定角色进行审查"""
    prompt = f"""{system_prompt}

---

用户需求：{requirement}

需审查的联想项：
{items_summary}

请开始审查并输出 JSON 结果。"""

    try:
        from app.utils import call_llm
        response = await call_llm(
            model=DEVILS_ADVOCATE_MODEL,
            prompt=prompt,
        )

        return parse_multi_review_response(response, role_name)
    except Exception as e:
        logger.warning(f"{role_name} 审查失败: {e}")
        return []


def parse_multi_review_response(response: str, role_name: str) -> List[Dict]:
    """解析多角度审查响应"""
    try:
        json_match = re.search(r'\{[\s\S]*\}', response)
        if not json_match:
            return []

        parsed = json.loads(json_match.group())
        reviews = parsed.get("reviews", [])

        valid = []
        for r in reviews:
            if "target" in r and ("issue" in r or "vulnerability" in r):
                valid.append({
                    "role": REVIEW_ROLES[role_name]["name"],
                    "target": r.get("target", ""),
                    "issue": r.get("issue", r.get("vulnerability", "")),
                    "severity": r.get("severity", "medium"),
                    "suggestion": r.get("suggestion", ""),
                    "category": r.get("category", "general"),
                })

        return valid[:10]  # 每个角色最多 10 条

    except json.JSONDecodeError:
        logger.warning(f"{role_name} 返回格式无效")
        return []


# --- 兼容旧 API ---

async def devil_advocate_review(
    requirement: str,
    items: List[AssociationItem],
    architect: object = None
) -> List[Dict]:
    """
    保持向后兼容的魔鬼代言人函数

    现在调用标准模式（单一魔鬼代言人）
    """
    items_summary = "\n".join(
        f"  [{i.category}] {i.content} (置信度: {i.confidence:.1f})"
        for i in items if i.confidence >= 0.5
    )[:15]

    if not items_summary:
        return []

    prompt = f"""你是"魔鬼代言人"，职责是对已确认的需求联想项进行质疑和风险审视。

用户需求：{requirement}

已确认的联想项：
{items_summary}

请从以下角度逐一审视这些联想项：
1. 是否有遗漏的前置条件或依赖关系？
2. 是否有表面合理但实际会产生连锁风险的功能？
3. 是否有需要额外补充但联想项中未提到的环节？

请严格按照以下 JSON 格式输出，不要输出任何其他内容：
```json
{{
  "reviews": [
    {{
      "target": "被质疑的联想项内容",
      "issue": "质疑内容 - 为什么这个项可能有问题或遗漏了什么",
      "severity": "critical/high/medium/low",
      "suggestion": "补充建议",
      "role": "devil_advocate"
    }}
  ]
}}
```"""

    try:
        from app.utils import call_llm
        response = await call_llm(
            model=DEVILS_ADVOCATE_MODEL,
            prompt=prompt,
        )

        return parse_devil_response(response)
    except Exception as e:
        logger.warning(f"魔鬼代言人审视失败: {e}")
        return []


def parse_devil_response(response: str) -> List[Dict]:
    """解析魔鬼代言人响应"""
    try:
        json_match = re.search(r'\{[\s\S]*\}', response)
        if not json_match:
            return []

        parsed = json.loads(json_match.group())
        reviews = parsed.get("reviews", [])

        valid = []
        for r in reviews:
            if r.get("issue") and r.get("target"):
                valid.append({
                    "role": "devil_advocate",
                    "target": r.get("target", ""),
                    "issue": r.get("issue", ""),
                    "severity": r.get("severity", "medium"),
                    "suggestion": r.get("suggestion", ""),
                    "category": "risk",
                })

        return valid[:10]
    except json.JSONDecodeError:
        pass
    return []


def reload_prompts():
    """重新加载提示词（用于开发调试）"""
    global PERFORMANCE_SYS_PROMPT, SECURITY_SYS_PROMPT, MAINTAINABILITY_SYS_PROMPT
    PERFORMANCE_SYS_PROMPT = _load_prompt("performance_reviewer_prompt.md")
    SECURITY_SYS_PROMPT = _load_prompt("security_reviewer_prompt.md")
    MAINTAINABILITY_SYS_PROMPT = _load_prompt("maintainability_reviewer_prompt.md")
    logger.info("审查提示词已重新加载")
