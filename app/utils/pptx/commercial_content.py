"""Shared commercial narrative content for PPT outline and rendering flows."""

import hashlib
from typing import Any, Dict, List


NARRATIVE_ROLES = (
    "opportunity_map",
    "evidence_story",
    "strategic_choice",
    "execution_roadmap",
    "decision_close",
)


TOPIC_TEMPLATE_SIGNALS = {
    "reflection": ("谦虚", "成长", "自我", "反思", "习惯", "沟通", "领导力", "心理"),
    "civic": ("爱国", "社会", "公共", "社区", "公益", "责任", "文化", "传统"),
    "learning": ("课程", "教学", "学习", "培训", "教育", "课堂", "知识"),
    "technology": ("科技", "技术", "系统", "工程", "数据", "算法", "平台", "研发"),
    "business": ("增长", "业务", "市场", "销售", "产品", "商业", "运营", "战略"),
}

TOPIC_TEMPLATE_BY_PROFILE = {
    "reflection": "minimal",
    "civic": "academic",
    "learning": "education",
    "technology": "tech",
    "business": "modern",
}


def resolve_topic_template(topic: str, requested_template: str) -> str:
    """Resolve the default template from topic semantics while honoring explicit choices."""
    if isinstance(requested_template, str) and requested_template not in {"", "auto"}:
        return requested_template

    topic_text = topic.lower() if isinstance(topic, str) else ""
    scores = {
        profile: sum(topic_text.count(signal.lower()) for signal in signals)
        for profile, signals in TOPIC_TEMPLATE_SIGNALS.items()
    }
    best_score = max(scores.values(), default=0)
    if best_score:
        profile = max(scores, key=scores.get)
        return TOPIC_TEMPLATE_BY_PROFILE[profile]

    templates = ("modern", "minimal", "elegant", "education", "academic")
    digest = hashlib.sha256(topic_text.encode("utf-8")).digest()
    return templates[digest[0] % len(templates)]


def build_expanded_commercial_page_blueprint(topic: str, count: int) -> List[Dict[str, Any]]:
    """Build a domain-aware fallback sequence for any deck length."""
    topic_text = str(topic or "")
    if "游戏" in topic_text and any(signal in topic_text.lower() for signal in ("ai", "人工智能", "智能")):
        return build_game_ai_page_blueprint(topic_text, count)

    base = build_commercial_page_blueprint(topic)
    angles = ("现状", "证据", "关键选择", "推进路径", "阶段结论", "用户价值", "资源约束", "协作机制", "风险边界", "落地复盘", "下一步")
    pages = []
    for index in range(count):
        page = base[index % len(base)]
        cycle = index // len(base)
        if cycle == 0:
            pages.append({**page, "title": f"{topic}：{angles[index]}"})
            continue
        angle = angles[index % len(angles)]
        pages.append({
            **page,
            "title": f"{topic}：{angle}（阶段 {cycle + 1}）",
            "key_message": f"{page['key_message']} 当前聚焦{angle}，形成可验证的阶段结论。",
            "blocks": [
                {**block, "content": f"{block['content']} 当前聚焦{angle}，补充第 {cycle + 1} 阶段的验证结果。"}
                for block in page["blocks"]
            ],
        })
    return pages


def _game_ai_page(topic: str, title: str, key_message: str, role: str, slide_type: str, blocks: List[Dict[str, Any]], asset_type: str = "diagram") -> Dict[str, Any]:
    return {
        "title": f"{topic}：{title}",
        "key_message": key_message,
        "role": role,
        "slide_type": slide_type,
        "blocks": blocks,
        "asset_intent": {
            "description": f"{topic}{title}主题图",
            "keywords": ["game", "ai", "interactive", "future"],
            "asset_type": asset_type,
        },
    }


def build_game_ai_page_blueprint(topic: str, count: int) -> List[Dict[str, Any]]:
    """Return a game-industry-specific fallback narrative for AI-era strategy decks."""
    pages = [
        _game_ai_page(topic, "核心判断", "AI 会重写游戏的生产方式、交互方式和内容供给，竞争焦点转向可持续的玩家体验。", "opportunity_map", "key_points", [
            {"type": "signal", "content": "游戏从预设内容产品演化为能感知、能回应、能持续变化的互动世界。", "metadata": {"priority": "P0", "metric": "玩家有效互动时长", "target": "持续提升"}},
            {"type": "signal", "content": "模型能力会快速普及，真正的壁垒来自世界观、数据闭环和体验设计。", "metadata": {"priority": "P0", "metric": "内容复用率", "target": "持续提升"}},
            {"type": "signal", "content": "优先从高频、可验证的研发和运营环节切入，再进入核心玩法。", "metadata": {"priority": "P1", "validation_period": "一个版本周期", "target": "完成闭环"}},
            {"type": "metric", "content": "战略目标是让 AI 同时提升内容供给效率和玩家留存质量。", "metadata": {"roi": "研发效率与留存双提升", "priority": "P0"}},
        ]),
        _game_ai_page(topic, "产业链变化", "AI 正在同时改造研发、内容、分发和运营四个环节。", "evidence_story", "data", [
            {"type": "evidence", "content": "美术、文本、配音和关卡草案进入可批量生成阶段，制作瓶颈向筛选与整合移动。", "metadata": {"metric": "内容生产周期", "target": "缩短"}},
            {"type": "evidence", "content": "玩家与 NPC 的每次互动都可以成为动态内容和体验优化的反馈信号。", "metadata": {"metric": "互动反馈利用率", "target": "提升"}},
            {"type": "case", "content": "同一套世界规则可以支持不同玩家的任务、对话和挑战组合。", "metadata": {"metric": "内容组合数", "target": "扩大"}},
            {"type": "implication", "content": "游戏公司需要把模型接入生产系统，而非停留在单点工具试用。", "metadata": {"metric": "AI 能力接入率", "target": "覆盖关键流程"}},
        ]),
        _game_ai_page(topic, "玩家体验重心", "玩家购买的是有意义的选择和情绪反馈，AI 的价值在于扩大体验空间。", "opportunity_map", "key_points", [
            {"type": "signal", "content": "NPC 需要记住关系、理解上下文，并对玩家行为做出一致回应。", "metadata": {"priority": "P0", "metric": "互动连贯性", "target": "可感知提升"}},
            {"type": "signal", "content": "动态任务应服务于玩家目标和节奏，避免随机内容稀释叙事。", "metadata": {"priority": "P0", "metric": "任务完成满意度", "target": "提升"}},
            {"type": "signal", "content": "个性化难度和反馈可以扩大不同能力玩家的可玩空间。", "metadata": {"priority": "P1", "metric": "分层留存", "target": "改善"}},
            {"type": "metric", "content": "体验指标应从内容数量转向选择质量、情绪峰值和长期留存。", "metadata": {"metric": "D30 留存", "target": "持续改善"}},
        ]),
        _game_ai_page(topic, "AI 原生玩法", "下一代游戏的差异化来自 AI 参与规则和玩法，而非给旧玩法外挂聊天框。", "strategic_choice", "comparison", [
            {"type": "option", "content": "把 AI 仅用于客服、文案和资产草图，风险低但玩家感知有限。", "metadata": {"cost": "低", "timeframe": "短", "risk": "体验同质化"}},
            {"type": "option", "content": "让 AI 进入 NPC、任务和世界状态，体验创新强但需要新的测试体系。", "metadata": {"cost": "中高", "timeframe": "中期", "risk": "可控性"}},
            {"type": "recommendation", "content": "优先设计一个 AI 直接改变玩家决策的核心场景。", "metadata": {"rationale": "玩家可感知、可验证、可形成长期壁垒", "priority": "P0"}},
            {"type": "criteria", "content": "以玩家主动使用率、重复体验率和异常内容率评估 AI 玩法。", "metadata": {"metric": "主动使用率", "target": "持续提升"}},
        ]),
        _game_ai_page(topic, "NPC 与游戏智能体", "NPC 将从台词容器升级为拥有记忆、目标和关系网络的游戏角色。", "evidence_story", "data", [
            {"type": "evidence", "content": "短期记忆负责对话上下文，长期记忆负责关系变化和任务历史。", "metadata": {"metric": "关系一致性", "target": "稳定"}},
            {"type": "evidence", "content": "智能体需要遵守世界规则、阵营目标和信息边界，避免自由生成破坏设定。", "metadata": {"metric": "规则遵循率", "target": "高"}},
            {"type": "case", "content": "NPC 可以根据玩家选择改变态度、资源分配和后续任务，而非只切换台词。", "metadata": {"metric": "状态变化数", "target": "可追踪"}},
            {"type": "implication", "content": "角色设计、系统设计和模型编排必须共同定义智能体行为边界。", "metadata": {"metric": "异常行为率", "target": "可控"}},
        ]),
        _game_ai_page(topic, "程序化内容与世界生成", "生成式 AI 让内容规模扩大，设计价值转向规则、审美和筛选。", "opportunity_map", "key_points", [
            {"type": "signal", "content": "地图、任务、道具和环境叙事可以按照规则组合，提升内容更新频率。", "metadata": {"priority": "P0", "metric": "版本内容供给", "target": "提升"}},
            {"type": "signal", "content": "生成结果必须经过风格、难度、叙事和安全性校验。", "metadata": {"priority": "P0", "metric": "可上线内容比例", "target": "提升"}},
            {"type": "signal", "content": "高质量世界观资产和规则库会成为模型输出质量的关键来源。", "metadata": {"priority": "P1", "metric": "规则资产复用率", "target": "提升"}},
            {"type": "metric", "content": "核心指标是单位研发成本下可交付且被玩家接受的内容量。", "metadata": {"metric": "有效内容产出", "target": "提升"}},
        ]),
        _game_ai_page(topic, "研发管线重构", "AI 会压缩重复劳动，但游戏研发仍需要人负责方向、品味和最终体验。", "execution_roadmap", "timeline", [
            {"type": "stage", "content": "概念阶段：用 AI 快速生成世界观、玩法草案和视觉方向，保留设计师决策。", "metadata": {"deliverable": "概念样片", "metric": "验证周期", "gate": "可玩"}},
            {"type": "stage", "content": "制作阶段：接入资产、脚本、测试和本地化工具，建立统一素材规范。", "metadata": {"deliverable": "生产工具链", "metric": "返工率", "gate": "下降"}},
            {"type": "stage", "content": "运营阶段：根据玩家行为生成内容候选，经过人工与自动审核再上线。", "metadata": {"deliverable": "动态运营闭环", "metric": "内容响应速度", "gate": "稳定"}},
            {"type": "gate", "content": "每个环节都要同时满足效率、质量、安全和玩家接受度门槛。", "metadata": {"deliverable": "评估机制", "metric": "上线通过率", "target": "提升"}},
        ]),
        _game_ai_page(topic, "UGC 与玩家共创", "AI 会降低创作门槛，游戏平台将从内容分发者转为创作基础设施。", "opportunity_map", "key_points", [
            {"type": "signal", "content": "玩家可以用自然语言创建角色、任务、地图和剧情分支。", "metadata": {"priority": "P0", "metric": "玩家创作参与率", "target": "提升"}},
            {"type": "signal", "content": "优秀作品需要被发现、 remix、评价和持续运营，分发机制决定生态质量。", "metadata": {"priority": "P0", "metric": "优质作品留存", "target": "提升"}},
            {"type": "signal", "content": "创作权限、素材归属和收益分配必须在产品设计阶段明确。", "metadata": {"priority": "P1", "metric": "创作者活跃率", "target": "稳定"}},
            {"type": "metric", "content": "UGC 的长期价值取决于玩家创作与消费之间形成正循环。", "metadata": {"metric": "创作消费转化率", "target": "提升"}},
        ]),
        _game_ai_page(topic, "实时运营与个性化", "AI 让运营从固定活动排期转向对玩家群体和状态的动态响应。", "evidence_story", "data", [
            {"type": "evidence", "content": "玩家行为可以驱动任务推荐、难度调节和回流内容的差异化组合。", "metadata": {"metric": "分群命中率", "target": "提升"}},
            {"type": "evidence", "content": "运营团队可以用模型发现流失信号，并在玩家离开前提供合适的体验修复。", "metadata": {"metric": "流失预警准确率", "target": "提升"}},
            {"type": "case", "content": "同一活动根据玩家进度提供不同目标，减少重复劳动并提高参与意愿。", "metadata": {"metric": "活动参与率", "target": "提升"}},
            {"type": "implication", "content": "个性化必须以玩家授权和体验尊重为前提，避免操纵式运营。", "metadata": {"metric": "投诉率", "target": "可控"}},
        ]),
        _game_ai_page(topic, "商业模式变化", "AI 的商业价值来自更丰富的体验和更高效的内容供给，单纯降低成本不足以形成增长。", "strategic_choice", "comparison", [
            {"type": "option", "content": "把 AI 作为内部降本工具，短期财务收益清晰，玩家侧差异有限。", "metadata": {"cost": "低", "timeframe": "短", "risk": "体验不变"}},
            {"type": "option", "content": "把 AI 能力包装成创作、陪伴和动态世界体验，增长空间大，治理要求更高。", "metadata": {"cost": "中高", "timeframe": "中长期", "risk": "内容治理"}},
            {"type": "recommendation", "content": "优先围绕可感知体验建立付费点，再将效率收益反哺内容投资。", "metadata": {"rationale": "价值可见、长期可持续", "priority": "P0"}},
            {"type": "criteria", "content": "同时评估付费转化、体验满意度、内容成本和社区健康度。", "metadata": {"metric": "单位玩家价值", "target": "提升"}},
        ]),
        _game_ai_page(topic, "风险与治理边界", "AI 游戏的核心竞争力必须建立在可解释、可控和可追责的内容系统上。", "evidence_story", "data", [
            {"type": "evidence", "content": "开放生成可能带来暴力、歧视、色情、诈骗和未成年人不适内容。", "metadata": {"metric": "高风险内容率", "target": "降低"}},
            {"type": "evidence", "content": "训练数据、角色形象和玩家创作涉及版权、肖像和收益归属问题。", "metadata": {"metric": "版权争议数", "target": "可控"}},
            {"type": "case", "content": "关键剧情、交易和社交行为需要日志、审核和人工申诉机制共同保护。", "metadata": {"metric": "申诉处理时效", "target": "缩短"}},
            {"type": "implication", "content": "安全规则、模型评估和运营处置应当成为游戏基础设施。", "metadata": {"metric": "风险闭环覆盖率", "target": "100%"}},
        ]),
        _game_ai_page(topic, "组织与人才变化", "未来团队需要把游戏设计、模型工程、数据治理和社区运营协同起来。", "opportunity_map", "key_points", [
            {"type": "signal", "content": "设计师负责定义体验目标、规则和边界，模型负责扩大方案空间。", "metadata": {"priority": "P0", "metric": "方案验证速度", "target": "提升"}},
            {"type": "signal", "content": "技术美术、数据工程和提示词设计会成为连接创意与生产的新岗位。", "metadata": {"priority": "P1", "metric": "跨职能协作效率", "target": "提升"}},
            {"type": "signal", "content": "玩家社区需要参与测试和反馈，帮助团队判断 AI 内容是否真正有趣。", "metadata": {"priority": "P1", "metric": "社区反馈采纳率", "target": "提升"}},
            {"type": "metric", "content": "组织升级的结果是更快产出可玩原型，而非单纯增加 AI 工具数量。", "metadata": {"metric": "可玩原型周期", "target": "缩短"}},
        ]),
        _game_ai_page(topic, "平台型还是场景型", "游戏公司应先选择一个能被玩家感知的 AI 场景，再逐步沉淀平台能力。", "strategic_choice", "comparison", [
            {"type": "option", "content": "先建设通用 AI 平台，能力完整但容易陷入基础设施竞争。", "metadata": {"cost": "高", "timeframe": "长", "risk": "价值延后"}},
            {"type": "option", "content": "先做一个 NPC、动态任务或 UGC 场景，反馈快但需要控制技术债。", "metadata": {"cost": "中", "timeframe": "短中期", "risk": "局部最优"}},
            {"type": "recommendation", "content": "采用场景牵引平台的路径，让真实玩家反馈决定能力优先级。", "metadata": {"rationale": "价值先行、能力沉淀", "priority": "P0"}},
            {"type": "criteria", "content": "用玩家使用率、内容质量、系统稳定性和复用成本判断是否平台化。", "metadata": {"metric": "场景复用率", "target": "提升"}},
        ]),
        _game_ai_page(topic, "三阶段路线图", "AI 游戏能力应沿着辅助生产、增强体验、重构玩法逐步推进。", "execution_roadmap", "timeline", [
            {"type": "stage", "content": "第一阶段：覆盖美术、文本、测试和运营辅助，建立数据与审核基础。", "metadata": {"deliverable": "生产辅助工具", "metric": "研发周期", "gate": "缩短"}},
            {"type": "stage", "content": "第二阶段：上线有边界的智能 NPC、个性化任务和动态内容。", "metadata": {"deliverable": "增强体验版本", "metric": "玩家参与率", "gate": "提升"}},
            {"type": "stage", "content": "第三阶段：探索 AI 原生世界、玩家共创和持续演化的游戏规则。", "metadata": {"deliverable": "AI 原生玩法", "metric": "长期留存", "gate": "改善"}},
            {"type": "gate", "content": "每一阶段都要完成玩家价值、安全治理和商业回报的联合验证。", "metadata": {"deliverable": "阶段评审", "metric": "综合达标率", "target": "100%"}},
        ]),
        _game_ai_page(topic, "最终结论", "游戏公司的 AI 战略应从玩家体验出发，用真实场景验证，再把能力沉淀为长期壁垒。", "decision_close", "summary", [
            {"type": "decision", "content": "把 AI 放进玩家真正能感知的互动、内容和世界状态中。", "metadata": {"owner": "产品与研发负责人", "deadline": "本季度", "priority": "P0"}},
            {"type": "action", "content": "选择一个 NPC、动态任务或 UGC 场景，完成可玩原型和小规模测试。", "metadata": {"owner": "游戏项目组", "deadline": "一个版本周期", "priority": "P0"}},
            {"type": "request", "content": "同步建立数据、版权、安全审核和玩家反馈机制。", "metadata": {"owner": "管理与平台团队", "deadline": "首个版本前", "priority": "P0"}},
            {"type": "success_metric", "content": "以玩家主动使用、体验满意度、内容质量和长期留存验证方向。", "metadata": {"metric": "玩家长期价值", "target": "持续提升", "deadline": "持续"}},
        ]),
    ]
    return [pages[index % len(pages)] for index in range(max(0, count))]


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
