"""
Agent 认知 Skill 注入

为 Agent 注入 5 个认知能力：
1. 关键词检测：检测用户输入中的关键词，自动触发规格书生成
2. 多角度审查：修改前从兼容性/安全/性能/测试/文档角度审查
3. 对比学习：对比修改前后的代码差异，学习最佳实践
4. 反面自查：修改后自动检查常见错误模式
5. 风险自评：评估修改的风险等级
"""

import json
import logging
import re
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)


# ==================== Skill 1: 关键词检测 ====================

class KeywordDetectionSkill:
    """关键词检测：检测用户输入中的关键词，自动触发规格书生成"""

    def __init__(self):
        self._load_triggers()

    def _load_triggers(self):
        config_path = Path(settings.KEYWORD_TRIGGERS_PATH)
        self.triggers = []
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                self.triggers = config.get("triggers", [])
            except Exception as e:
                logger.error(f"加载关键词触发配置失败: {e}")

    def detect(self, user_input: str) -> Optional[Dict]:
        """
        检测用户输入是否触发关键词

        Returns:
            触发结果字典，包含 type, questions, related_files 等
        """
        for trigger in self.triggers:
            for keyword in trigger.get("keywords", []):
                if keyword.lower() in user_input.lower():
                    return {
                        "skill": "keyword_detection",
                        "triggered": True,
                        "type": trigger.get("type", "unknown"),
                        "keyword": keyword,
                        "questions": trigger.get("questions", [])[:3],
                        "action": "generate_spec",
                    }
        return {"skill": "keyword_detection", "triggered": False}


# ==================== Skill 2: 多角度审查 ====================

class MultiAngleReviewSkill:
    """多角度审查：修改前从多个角度审查变更"""

    def __init__(self):
        self._load_checklist()

    def _load_checklist(self):
        checklist_path = Path(settings.REVIEW_CHECKLIST_PATH)
        self.checklist = {}
        if checklist_path.exists():
            try:
                with open(checklist_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                self.checklist = config.get("checklists", {})
            except Exception as e:
                logger.error(f"加载审查清单失败: {e}")

    def review(self, file_path: str, change_description: str) -> Dict:
        """
        从多角度审查变更

        Returns:
            审查结果，包含各角度的检查项和建议
        """
        result = {
            "skill": "multi_angle_review",
            "file": file_path,
            "description": change_description,
            "reviews": {},
        }

        for category, items in self.checklist.items():
            result["reviews"][category] = {
                "items": items,
                "status": "pending_review",
                "notes": [],
            }

        return result

    def get_review_prompt(self, file_path: str, change_description: str) -> str:
        """生成审查提示词，供 Agent 使用"""
        lines = [
            f"请对以下变更进行多角度审查：",
            f"",
            f"文件: {file_path}",
            f"变更描述: {change_description}",
            f"",
            f"请从以下角度逐一审查：",
        ]

        for category, items in self.checklist.items():
            lines.append(f"")
            lines.append(f"### {self._get_category_name(category)}")
            for item in items:
                lines.append(f"- [ ] {item}")

        lines.append(f"")
        lines.append(f"请逐项检查并给出审查结论。")

        return "\n".join(lines)

    def _get_category_name(self, category: str) -> str:
        names = {
            "compatibility": "兼容性审查",
            "security": "安全审查",
            "performance": "性能审查",
            "testing": "测试审查",
            "documentation": "文档审查",
            "operations": "运维审查",
        }
        return names.get(category, category)


# ==================== Skill 3: 对比学习 ====================

class ComparativeLearningSkill:
    """对比学习：对比修改前后的代码差异，学习最佳实践"""

    def detect_patterns(self, before: str, after: str) -> Dict:
        """
        对比修改前后的代码，检测变更模式

        Returns:
            变更模式分析结果
        """
        before_lines = before.split('\n')
        after_lines = after.split('\n')

        # 简单差异分析
        added_lines = [line for line in after_lines if line not in before_lines]
        removed_lines = [line for line in before_lines if line not in after_lines]

        patterns = []
        if any("import" in line for line in added_lines):
            patterns.append("新增依赖")
        if any("def " in line for line in added_lines):
            patterns.append("新增函数")
        if any("class " in line for line in added_lines):
            patterns.append("新增类")
        if any("@router" in line for line in added_lines):
            patterns.append("新增路由")
        if any("async def" in line for line in added_lines):
            patterns.append("异步化改造")

        return {
            "skill": "comparative_learning",
            "lines_added": len(added_lines),
            "lines_removed": len(removed_lines),
            "patterns_detected": patterns,
            "suggestion": self._get_suggestion(patterns),
        }

    def _get_suggestion(self, patterns: List[str]) -> str:
        suggestions = {
            "新增依赖": "请确保依赖已添加到 requirements.txt",
            "新增函数": "请为新函数添加测试用例和文档字符串",
            "新增类": "请为新类添加测试用例和类型注解",
            "新增路由": "请确保路由有正确的认证和参数验证",
            "异步化改造": "请确保所有 I/O 操作都是异步的，避免阻塞",
        }
        return "; ".join(suggestions.get(p, "") for p in patterns if p in suggestions)


# ==================== Skill 4: 反面自查 ====================

class AntiPatternSelfCheckSkill:
    """反面自查：修改后自动检查常见错误模式"""

    def __init__(self):
        self._load_patterns()

    def _load_patterns(self):
        patterns_path = Path(settings.ANTI_PATTERNS_PATH)
        self.patterns = []
        if patterns_path.exists():
            try:
                with open(patterns_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                self.patterns = config.get("patterns", [])
            except Exception as e:
                logger.error(f"加载错误模式库失败: {e}")

    def check(self, code: str) -> List[Dict]:
        """
        检查代码是否存在常见错误模式

        Returns:
            检测到的错误模式列表
        """
        findings = []

        for pattern_info in self.patterns:
            pattern = pattern_info.get("pattern", "")
            if not pattern:
                continue

            try:
                matches = re.findall(pattern, code, re.MULTILINE | re.IGNORECASE)
                if matches:
                    findings.append({
                        "id": pattern_info.get("id", "unknown"),
                        "category": pattern_info.get("category", "unknown"),
                        "name": pattern_info.get("name", "未知模式"),
                        "severity": pattern_info.get("severity", "notice"),
                        "description": pattern_info.get("description", ""),
                        "suggestion": pattern_info.get("suggestion", ""),
                        "match_count": len(matches),
                    })
            except re.error:
                logger.warning(f"正则表达式错误: {pattern}")

        return findings

    def get_check_prompt(self) -> str:
        """生成自查提示词"""
        lines = [
            "请对照以下常见错误模式进行自查：",
            ""
        ]
        for p in self.patterns:
            lines.append(f"- **[{p.get('severity', 'notice').upper()}] {p.get('name', '未知')}**: {p.get('description', '')}")
        lines.append("")
        lines.append("请逐项检查你的修改是否存在上述问题。")
        return "\n".join(lines)


# ==================== Skill 5: 风险自评 ====================

class RiskSelfAssessmentSkill:
    """风险自评：评估修改的风险等级"""

    def assess(self, file_path: str, change_type: str, dep_graph: Optional[Dict] = None) -> Dict:
        """
        评估修改的风险等级

        Args:
            file_path: 修改的文件路径
            change_type: 变更类型 (add/modify/delete)
            dep_graph: 依赖图谱

        Returns:
            风险评估结果
        """
        risk_score = 0
        risk_factors = []

        # 因素1: 文件类型
        if "auth" in file_path.lower() or "security" in file_path.lower():
            risk_score += 30
            risk_factors.append("涉及认证/安全核心模块")
        elif "middleware" in file_path.lower():
            risk_score += 25
            risk_factors.append("涉及中间件层")
        elif "model" in file_path.lower() or "db" in file_path.lower():
            risk_score += 20
            risk_factors.append("涉及数据库模型")
        elif "api" in file_path.lower():
            risk_score += 15
            risk_factors.append("涉及 API 接口")

        # 因素2: 变更类型
        if change_type == "delete":
            risk_score += 20
            risk_factors.append("删除操作")
        elif change_type == "modify":
            risk_score += 10
            risk_factors.append("修改操作")

        # 因素3: 依赖数量
        if dep_graph:
            reverse_index = dep_graph.get("reverse_index", {})
            dependent_count = 0
            for target, sources in reverse_index.items():
                if target in file_path:
                    dependent_count += len(sources)

            if dependent_count > 5:
                risk_score += 20
                risk_factors.append(f"被 {dependent_count} 个其他文件依赖")
            elif dependent_count > 0:
                risk_score += 10
                risk_factors.append(f"被 {dependent_count} 个文件依赖")

        # 确定风险等级
        if risk_score >= 60:
            level = "high"
            action = "需要详细审查和用户确认"
        elif risk_score >= 30:
            level = "medium"
            action = "需要审查，建议运行关联测试"
        else:
            level = "low"
            action = "常规修改，注意基本测试"

        return {
            "skill": "risk_self_assessment",
            "file": file_path,
            "change_type": change_type,
            "risk_score": risk_score,
            "risk_level": level,
            "risk_factors": risk_factors,
            "recommended_action": action,
        }


# ==================== Skill 管理器 ====================

class AgentSkillsManager:
    """Agent 认知技能管理器"""

    def __init__(self):
        self.keyword_detection = KeywordDetectionSkill()
        self.multi_angle_review = MultiAngleReviewSkill()
        self.comparative_learning = ComparativeLearningSkill()
        self.anti_pattern_check = AntiPatternSelfCheckSkill()
        self.risk_assessment = RiskSelfAssessmentSkill()

    def get_all_skills_context(self) -> Dict:
        """获取所有技能的上下文（供 Agent 加载到知识库）"""
        return {
            "skills": {
                "keyword_detection": {
                    "description": "关键词检测，自动触发规格书生成",
                    "trigger_count": len(self.keyword_detection.triggers),
                },
                "multi_angle_review": {
                    "description": "多角度审查，从兼容性/安全/性能/测试/文档角度审查",
                    "checklist_categories": list(self.multi_angle_review.checklist.keys()),
                },
                "comparative_learning": {
                    "description": "对比学习，分析代码变更模式",
                    "known_patterns": ["新增依赖", "新增函数", "新增类", "新增路由", "异步化改造"],
                },
                "anti_pattern_check": {
                    "description": "反面自查，检查常见错误模式",
                    "pattern_count": len(self.anti_pattern_check.patterns),
                },
                "risk_assessment": {
                    "description": "风险自评，评估修改的风险等级",
                    "levels": ["low", "medium", "high"],
                },
            }
        }

    def process_user_input(self, user_input: str) -> Dict:
        """
        处理用户输入，应用所有相关技能

        Returns:
            综合处理结果
        """
        result = {
            "input": user_input,
            "skills_triggered": [],
        }

        # Skill 1: 关键词检测
        keyword_result = self.keyword_detection.detect(user_input)
        if keyword_result.get("triggered"):
            result["skills_triggered"].append("keyword_detection")
            result["keyword_detection"] = keyword_result

        return result

    def pre_modify_review(self, file_path: str, change_description: str) -> Dict:
        """修改前审查"""
        return {
            "multi_angle_review": self.multi_angle_review.review(file_path, change_description),
            "risk_assessment": self.risk_assessment.assess(file_path, "modify"),
        }

    def post_modify_check(self, code: str, file_path: str) -> Dict:
        """修改后自查"""
        return {
            "anti_pattern_check": self.anti_pattern_check.check(code),
            "comparative_learning": self.comparative_learning.detect_patterns("", code),
        }


# 全局单例
_skills_manager: Optional[AgentSkillsManager] = None


def get_skills_manager() -> AgentSkillsManager:
    """获取技能管理器单例"""
    global _skills_manager
    if _skills_manager is None:
        _skills_manager = AgentSkillsManager()
    return _skills_manager
