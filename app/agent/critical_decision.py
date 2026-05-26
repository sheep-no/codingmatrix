"""
CriticalDecisionExtractor - 关键决策提取器

核心理念：在需求分析完成后，提取 1-3 个关键架构假设，
以选择题形式向用户提问，让用户用 30 秒决策注入全局架构方向。

工作流程：
1. 分析需求分析结果（架构设计、技术栈选择等）
2. 魔鬼代言人（GLM-Z1）识别最不确定的决策点
3. 将决策点转换为选择题格式
4. 应用用户选择到后续生成 prompt
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class DecisionCategory(Enum):
    AUTH_STRATEGY = "auth_strategy"
    DATABASE_CHOICE = "database_choice"
    API_STYLE = "api_style"
    FRONTEND_FRAMEWORK = "frontend_framework"
    STATE_MANAGEMENT = "state_management"
    CACHING_STRATEGY = "caching_strategy"
    DEPLOYMENT_MODE = "deployment_mode"
    ARCHITECTURE_PATTERN = "architecture_pattern"


@dataclass
class CriticalDecision:
    """关键决策定义"""
    id: str
    category: DecisionCategory
    question: str
    context: str
    options: List[Dict[str, str]]
    default: str
    impact_files: List[str]
    selected: Optional[str] = None


class CriticalDecisionExtractor:
    """
    关键决策提取器
    
    与架构师的协作：
    - 架构师输出初始架构设计后，提取关键不确定点
    - 用户做出决策后，将决策注入架构师的后续 prompt
    
    决策点示例：
    - 认证策略：JWT vs Session vs OAuth
    - 数据库：PostgreSQL vs MySQL vs MongoDB
    - API 风格：REST vs GraphQL vs RPC
    - 前端框架：Vue vs React vs Svelte
    """

    DECISION_TEMPLATES: Dict[str, Dict] = {
        "auth_strategy": {
            "question": "认证模块策略选择",
            "context": "系统需要用户认证功能。JWT 方式无状态适合分布式，Session 方式状态化适合单机，OAuth 适合第三方集成。",
            "options": [
                {"label": "JWT", "description": "无状态，适合分布式部署"},
                {"label": "Session", "description": "状态化，适合单机部署"},
                {"label": "OAuth 2.0", "description": "第三方认证集成"}
            ],
            "default": "JWT"
        },
        "database_choice": {
            "question": "数据库选型",
            "context": "系统需要持久化存储。关系型数据库适合结构化数据和复杂查询，文档型数据库适合灵活 schema。",
            "options": [
                {"label": "PostgreSQL", "description": "关系型，适合复杂查询和事务"},
                {"label": "MySQL", "description": "关系型，适合读写密集场景"},
                {"label": "MongoDB", "description": "文档型，适合灵活 schema"},
                {"label": "Redis", "description": "缓存型，适合高并发读"}
            ],
            "default": "PostgreSQL"
        },
        "api_style": {
            "question": "API 设计风格",
            "context": "前后端通信方式。REST 简单通用，GraphQL 灵活查询，RPC 高性能内部调用。",
            "options": [
                {"label": "REST", "description": "简单通用，广泛支持"},
                {"label": "GraphQL", "description": "灵活查询，减少请求次数"},
                {"label": "RPC/gRPC", "description": "高性能，适合内部服务调用"}
            ],
            "default": "REST"
        },
        "frontend_framework": {
            "question": "前端框架选择",
            "context": "前端技术栈选择影响开发效率和性能。",
            "options": [
                {"label": "Vue 3", "description": "渐进式框架，易上手"},
                {"label": "React", "description": "组件化，生态丰富"},
                {"label": "Svelte", "description": "编译型，性能优秀"},
                {"label": "Next.js", "description": "React + SSR，适合 SEO"}
            ],
            "default": "Vue 3"
        },
        "state_management": {
            "question": "状态管理方案",
            "context": "复杂应用的状态管理方式。",
            "options": [
                {"label": "Pinia/Vuex", "description": "集中式状态管理"},
                {"label": "Redux", "description": "严格单向数据流"},
                {"label": "Zustand", "description": "轻量级，简洁 API"},
                {"label": "React Query", "description": "服务端状态管理"}
            ],
            "default": "Pinia"
        },
        "caching_strategy": {
            "question": "缓存策略",
            "context": "高并发场景的缓存方式。",
            "options": [
                {"label": "Redis", "description": "分布式缓存，多数据结构"},
                {"label": "Memcached", "description": "简单高效，纯缓存"},
                {"label": "本地缓存", "description": "进程内缓存，无网络开销"}
            ],
            "default": "Redis"
        },
        "architecture_pattern": {
            "question": "架构模式选择",
            "context": "系统整体架构模式影响扩展性和复杂度。",
            "options": [
                {"label": "单体架构", "description": "简单，适合小型项目"},
                {"label": "微服务", "description": "可扩展，适合大型项目"},
                {"label": "分层架构", "description": "清晰分层，适合中型项目"}
            ],
            "default": "分层架构"
        }
    }

    def __init__(self):
        self.decisions: List[CriticalDecision] = []
        self.user_choices: Dict[str, str] = {}

    def extract_from_architecture(
        self,
        architecture: Dict[str, Any],
        complexity_analysis: Optional[Dict] = None
    ) -> List[CriticalDecision]:
        """
        从架构设计中提取关键决策点
        
        Args:
            architecture: 架构师输出的架构设计
            complexity_analysis: 复杂度分析结果
        
        Returns:
            关键决策列表（最多 3 个）
        """
        self.decisions.clear()
        
        tech_stack = architecture.get("tech_stack", {})
        decisions_needed = self._analyze_uncertainty(architecture, complexity_analysis)
        
        for decision_id in decisions_needed[:3]:
            template = self.DECISION_TEMPLATES.get(decision_id)
            if template:
                impact_files = self._identify_impact_files(decision_id, architecture)
                decision = CriticalDecision(
                    id=decision_id,
                    category=DecisionCategory(decision_id),
                    question=template["question"],
                    context=template["context"],
                    options=template["options"],
                    default=template["default"],
                    impact_files=impact_files
                )
                self.decisions.append(decision)
        
        logger.info(f"提取关键决策点: {len(self.decisions)} 个")
        return self.decisions

    def _analyze_uncertainty(
        self,
        architecture: Dict[str, Any],
        complexity_analysis: Optional[Dict]
    ) -> List[str]:
        """分析架构设计中的不确定决策点"""
        decisions_needed = []
        
        tech_stack = architecture.get("tech_stack", {})
        
        # tech_stack 可能是 list（如 ["FastAPI", "Vue3"]）或 dict
        if isinstance(tech_stack, list):
            tech_stack_str = " ".join(str(t).lower() for t in tech_stack)
            if "auth" not in tech_stack_str and "jwt" not in tech_stack_str:
                decisions_needed.append("auth_strategy")
            if "sqlite" not in tech_stack_str and "mysql" not in tech_stack_str and "postgres" not in tech_stack_str:
                decisions_needed.append("database_choice")
            if complexity_analysis and complexity_analysis.get("has_frontend"):
                if "vue" not in tech_stack_str and "react" not in tech_stack_str and "angular" not in tech_stack_str:
                    decisions_needed.append("frontend_framework")
            if complexity_analysis and complexity_analysis.get("estimated_files", 0) > 20:
                if "microservice" not in tech_stack_str and "monolith" not in tech_stack_str:
                    decisions_needed.append("architecture_pattern")
            if complexity_analysis and complexity_analysis.get("has_backend"):
                if "rest" not in tech_stack_str and "graphql" not in tech_stack_str:
                    decisions_needed.append("api_style")
        else:
            if not tech_stack.get("auth_explicit"):
                decisions_needed.append("auth_strategy")
            if not tech_stack.get("database_explicit"):
                decisions_needed.append("database_choice")
            if complexity_analysis and complexity_analysis.get("has_frontend"):
                if not tech_stack.get("frontend_framework"):
                    decisions_needed.append("frontend_framework")
            if complexity_analysis and complexity_analysis.get("estimated_files", 0) > 20:
                if not tech_stack.get("architecture_pattern"):
                    decisions_needed.append("architecture_pattern")
            if complexity_analysis and complexity_analysis.get("has_backend"):
                if not tech_stack.get("api_style"):
                    decisions_needed.append("api_style")
        
        return decisions_needed

    def _identify_impact_files(
        self,
        decision_id: str,
        architecture: Dict[str, Any]
    ) -> List[str]:
        """识别决策影响的文件"""
        file_plan = architecture.get("file_plan", [])
        impact_files = []
        
        patterns = {
            "auth_strategy": ["auth", "middleware", "security", "config"],
            "database_choice": ["database", "model", "config"],
            "api_style": ["api", "router", "controller"],
            "frontend_framework": ["main", "app", "index"],
            "state_management": ["store", "state"],
            "caching_strategy": ["cache", "redis", "config"],
            "architecture_pattern": []
        }
        
        keywords = patterns.get(decision_id, [])
        for file_info in file_plan:
            path = file_info.get("path", "")
            for keyword in keywords:
                if keyword.lower() in path.lower():
                    impact_files.append(path)
                    break
        
        return impact_files

    def format_as_questions(self) -> List[Dict[str, Any]]:
        """将决策转换为选择题格式"""
        questions = []
        for decision in self.decisions:
            question = {
                "id": decision.id,
                "question": decision.question,
                "context": decision.context,
                "options": decision.options,
                "default": decision.default,
                "impact_files": decision.impact_files
            }
            questions.append(question)
        return questions

    def apply_user_choice(
        self,
        decision_id: str,
        choice: str
    ) -> Dict[str, Any]:
        """
        应用用户选择的决策
        
        Args:
            decision_id: 决策 ID
            choice: 用户选择的选项
        
        Returns:
            决策应用结果
        """
        self.user_choices[decision_id] = choice
        
        for decision in self.decisions:
            if decision.id == decision_id:
                decision.selected = choice
                break
        
        logger.info(f"用户决策: {decision_id} -> {choice}")
        
        return {
            "decision_id": decision_id,
            "choice": choice,
            "impact_files": self._get_impact_files(decision_id),
            "applied": True
        }

    def _get_impact_files(self, decision_id: str) -> List[str]:
        """获取决策影响的文件列表"""
        for decision in self.decisions:
            if decision.id == decision_id:
                return decision.impact_files
        return []

    def get_decision_context_for_prompt(self) -> str:
        """生成用于注入 prompt 的决策上下文"""
        if not self.user_choices:
            return ""
        
        parts = []
        for decision_id, choice in self.user_choices.items():
            template = self.DECISION_TEMPLATES.get(decision_id)
            if template:
                option_desc = next(
                    (opt["description"] for opt in template["options"] if opt["label"] == choice),
                    ""
                )
                parts.append(f"- {template['question']}: {choice} ({option_desc})")
        
        if parts:
            return "用户架构决策:\n" + "\n".join(parts)
        return ""

    def get_all_choices(self) -> Dict[str, str]:
        """获取所有用户决策"""
        return self.user_choices.copy()

    def skip_remaining_decisions(self) -> None:
        """跳过剩余决策，使用默认值"""
        for decision in self.decisions:
            if decision.selected is None:
                decision.selected = decision.default
                self.user_choices[decision.id] = decision.default
                logger.info(f"跳过决策 {decision.id}，使用默认值 {decision.default}")