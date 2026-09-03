"""Shared commercial narrative content for PPT outline and rendering flows."""

from typing import Any, Dict, List


NARRATIVE_ROLES = (
    "opportunity_map",
    "evidence_story",
    "strategic_choice",
    "execution_roadmap",
    "decision_close",
)


METADATA_LABELS = {
    "roi": "ROI",
    "priority": "优先级",
    "validation_period": "验证周期",
    "metric": "指标",
    "target": "目标",
    "cost": "成本",
    "timeframe": "周期",
    "risk": "风险",
    "rationale": "依据",
    "deliverable": "交付物",
    "gate": "门槛",
    "owner": "负责人",
    "deadline": "时限",
}


ROLE_METADATA_KEYS = {
    "opportunity_map": ("roi", "priority", "validation_period", "metric", "target"),
    "evidence_story": ("metric", "target", "validation_period"),
    "strategic_choice": ("cost", "timeframe", "risk", "rationale"),
    "execution_roadmap": ("deliverable", "metric", "target", "gate"),
    "decision_close": ("owner", "deadline", "priority", "metric", "target"),
}


def format_commercial_metadata(role: str, metadata: Dict[str, Any], limit: int = 3) -> str:
    """Format role-specific metadata into a compact presentation label."""
    details: List[str] = []
    for key in ROLE_METADATA_KEYS.get(role, tuple(METADATA_LABELS)):
        value = metadata.get(key)
        if value not in (None, "", []):
            details.append(f"{METADATA_LABELS[key]}：{value}")
        if len(details) >= limit:
            break
    return " · ".join(details)


def build_commercial_page_blueprint(topic: str) -> List[Dict[str, Any]]:
    """Return five differentiated commercial narrative pages for a topic."""
    return [
        {
            "title": topic,
            "key_message": f"围绕{topic}明确汇报目标、核心判断与行动方向。",
            "role": "opportunity_map",
            "slide_type": "key_points",
            "blocks": [
                {
                    "type": "signal",
                    "content": "用户期待从单点工具升级为端到端结果。",
                    "metadata": {"priority": "P0", "metric": "高频痛点占比", "target": "≥40%"},
                },
                {
                    "type": "signal",
                    "content": "高频、重复、可量化的环节形成首个机会窗口。",
                    "metadata": {"priority": "P1", "metric": "可触达用户数", "target": "≥100"},
                },
                {
                    "type": "signal",
                    "content": "先验证付费意愿，再扩大产品和运营投入。",
                    "metadata": {"priority": "P0", "validation_period": "2 周", "target": "5 位目标用户"},
                },
                {
                    "type": "metric",
                    "content": "以结果改善幅度和投入产出比决定是否进入下一阶段。",
                    "metadata": {"roi": "≥3.0", "priority": "P0", "validation_period": "2 周"},
                },
            ],
            "asset_intent": {"description": f"{topic}战略主题概念图", "keywords": ["strategy", "business", "technology"], "asset_type": "illustration"},
        },
        {
            "title": "现状与机会",
            "key_message": f"梳理{topic}当前背景、关键变化与主要机会。",
            "role": "evidence_story",
            "slide_type": "data",
            "blocks": [
                {
                    "type": "evidence",
                    "content": "等待、交接和重复录入构成体验损耗的主要来源。",
                    "metadata": {"metric": "无效耗时占比", "target": "降低 30%"},
                },
                {
                    "type": "evidence",
                    "content": "高价值用户更关注结果确定性，功能数量的边际价值下降。",
                    "metadata": {"metric": "任务完成率", "target": "提升 20%"},
                },
                {
                    "type": "case",
                    "content": "把一次完整任务从 6 个步骤压缩为 3 个可追踪节点。",
                    "metadata": {"metric": "流程节点", "target": "6 降至 3", "validation_period": "首轮试点"},
                },
                {
                    "type": "implication",
                    "content": "优先解决流程断点，能够更快完成商业价值验证。",
                    "metadata": {"metric": "价值验证周期", "target": "≤4 周"},
                },
            ],
            "asset_intent": {"description": f"{topic}现状与机会分析插画", "keywords": ["market", "growth", "analysis"], "asset_type": "diagram"},
        },
        {
            "title": "核心策略",
            "key_message": f"围绕{topic}聚焦重点策略，形成可执行的优先级安排。",
            "role": "strategic_choice",
            "slide_type": "comparison",
            "blocks": [
                {
                    "type": "option",
                    "content": "先做完整平台，覆盖面广，具备统一能力底座。",
                    "metadata": {"cost": "高", "timeframe": "12-16 周", "risk": "需求扩散"},
                },
                {
                    "type": "option",
                    "content": "先做关键场景闭环，快速形成可复用样板。",
                    "metadata": {"cost": "中", "timeframe": "4-6 周", "risk": "场景选择"},
                },
                {
                    "type": "recommendation",
                    "content": "推荐关键场景闭环，以结果验证换取后续扩展空间。",
                    "metadata": {"rationale": "周期短、反馈快、投入可控", "priority": "P0"},
                },
                {
                    "type": "criteria",
                    "content": "以首个结果周期、用户完成率、复用成本和扩展潜力评估路径。",
                    "metadata": {"metric": "首个结果周期", "target": "≤6 周"},
                },
            ],
            "asset_intent": {"description": f"{topic}核心策略路线图", "keywords": ["roadmap", "strategy", "workflow"], "asset_type": "diagram"},
        },
        {
            "title": "落地路径",
            "key_message": f"为{topic}建立阶段性计划、关键指标和责任分工。",
            "role": "execution_roadmap",
            "slide_type": "timeline",
            "blocks": [
                {
                    "type": "stage",
                    "content": "试点：交付一个端到端场景，完成首批用户验证。",
                    "metadata": {"deliverable": "试点闭环", "metric": "完成率", "gate": "≥70%"},
                },
                {
                    "type": "stage",
                    "content": "扩展：沉淀可复用能力，覆盖相邻用户和流程。",
                    "metadata": {"deliverable": "能力组件", "metric": "复用率", "gate": "≥50%"},
                },
                {
                    "type": "stage",
                    "content": "规模化：建立运营机制，让结果稳定复制。",
                    "metadata": {"deliverable": "运营机制", "metric": "单位成本", "gate": "降低 25%"},
                },
                {
                    "type": "gate",
                    "content": "完成率、复用率、交付周期和单位成本达标后扩大投入。",
                    "metadata": {"deliverable": "阶段复盘", "metric": "关键指标达标率", "target": "100%"},
                },
            ],
            "asset_intent": {"description": f"{topic}分阶段落地路线图", "keywords": ["timeline", "execution", "milestone"], "asset_type": "diagram"},
        },
        {
            "title": "总结与下一步",
            "key_message": f"总结{topic}的核心结论，并明确下一阶段的行动事项。",
            "role": "decision_close",
            "slide_type": "summary",
            "blocks": [
                {
                    "type": "decision",
                    "content": "先证明一个高价值闭环，再扩展能力边界。",
                    "metadata": {"owner": "业务负责人", "deadline": "本周", "priority": "P0"},
                },
                {
                    "type": "action",
                    "content": "确认试点场景、负责人、用户名单和首个交付日期。",
                    "metadata": {"owner": "项目负责人", "deadline": "3 个工作日", "priority": "P0"},
                },
                {
                    "type": "request",
                    "content": "批准试点资源，并锁定两周后的结果评审窗口。",
                    "metadata": {"owner": "决策委员会", "deadline": "今日", "priority": "P0"},
                },
                {
                    "type": "success_metric",
                    "content": "以用户完成率、结果改善幅度和复用意愿判断成效。",
                    "metadata": {"metric": "用户完成率", "target": "≥70%", "deadline": "2 周"},
                },
            ],
            "asset_intent": {"description": f"{topic}成果与下一步行动概念图", "keywords": ["success", "teamwork", "next steps"], "asset_type": "illustration"},
        },
    ]
