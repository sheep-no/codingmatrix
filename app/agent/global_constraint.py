"""
GlobalConstraintParser - 全局约束解析器

核心理念：从用户需求中提取全局约束（如"必须用 FastAPI"、"需兼容 IE11"），
注入到所有后续生成器 prompt，避免全局性约束在个体生成环节遗漏。

工作流程：
1. 解析需求文本，识别全局性关键词（"必须"、"所有"、"统一"等）
2. 分类约束（技术栈约束、兼容性约束、安全约束、性能约束）
3. 生成全局约束 prompt 片段
4. 在文件生成时自动注入
"""

import re
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ConstraintCategory(Enum):
    TECH_STACK = "tech_stack"
    COMPATIBILITY = "compatibility"
    SECURITY = "security"
    PERFORMANCE = "performance"
    ARCHITECTURE = "architecture"
    STYLE = "style"
    NAMING = "naming"
    TESTING = "testing"


@dataclass
class GlobalConstraint:
    """全局约束定义"""
    id: str
    category: ConstraintCategory
    description: str
    original_text: str
    applies_to: List[str]
    priority: str


class GlobalConstraintParser:
    """
    全局约束解析器
    
    与需求分析和架构师的协作：
    - 需求分析完成后，提取全局约束
    - 约束注入架构师和工程师的所有 prompt
    
    约束示例：
    - 技术栈："必须用 FastAPI"
    - 兼容性："需兼容 IE11"
    - 安全："所有接口必须有权限校验"
    - 性能："响应时间不超过 200ms"
    """

    GLOBAL_KEYWORDS = [
        "必须", "务必", "一定", "强制", "统一", "全局",
        "所有", "全部", "任何", "每个", "各个",
        "禁止", "不得", "不许", "严禁",
        "兼容", "支持", "适配",
        "必须用", "必须使用", "必须采用"
    ]

    CONSTRAINT_PATTERNS: Dict[str, Dict] = {
        "tech_stack": {
            "patterns": [
                r"必须\s*用\s*([\w\-\.]+)",
                r"必须\s*使用\s*([\w\-\.]+)",
                r"采用\s*([\w\-\.]+)\s*框架",
                r"使用\s*([\w\-\.]+)\s*作为\s*.*框架",
                r"技术栈\s*为\s*([\w\-\.]+)",
            ],
            "applies_to": ["backend", "frontend", "all"]
        },
        "compatibility": {
            "patterns": [
                r"兼容\s*([\w\-\.]+)",
                r"支持\s*([\w\-\.]+)\s*浏览器",
                r"适配\s*([\w\-\.]+)",
                r"需要\s*兼容\s*([\w\-\.]+)",
            ],
            "applies_to": ["frontend"]
        },
        "security": {
            "patterns": [
                r"所有\s*接口\s*必须.*权限",
                r"任何\s*操作\s*必须.*认证",
                r"禁止.*未授权",
                r"必须\s*有\s*权限校验",
                r"必须.*加密",
            ],
            "applies_to": ["backend", "api"]
        },
        "performance": {
            "patterns": [
                r"响应\s*时间\s*(?:不超过|少于)\s*(\d+)",
                r"加载\s*时间\s*(?:不超过|少于)\s*(\d+)",
                r"延迟\s*(?:不超过|少于)\s*(\d+)",
                r"必须.*优化",
            ],
            "applies_to": ["all"]
        },
        "architecture": {
            "patterns": [
                r"统一\s*使用\s*([\w\-\.]+)",
                r"全局\s*配置",
                r"所有\s*模块\s*统一",
                r"架构\s*(?:采用|使用)\s*([\w\-\.]+)",
            ],
            "applies_to": ["all"]
        },
        "style": {
            "patterns": [
                r"统一\s*代码\s*风格",
                r"遵循\s*([\w\-\.]+)\s*规范",
                r"使用\s*([\w\-\.]+)\s*风格",
            ],
            "applies_to": ["all"]
        },
        "naming": {
            "patterns": [
                r"统一\s*命名\s*规范",
                r"命名\s*规则\s*为",
                r"所有\s*文件\s*命名",
                r"命名\s*统一\s*使用",
            ],
            "applies_to": ["all"]
        },
        "testing": {
            "patterns": [
                r"必须\s*有\s*单元测试",
                r"所有\s*模块\s*必须\s*测试",
                r"测试\s*覆盖率\s*(?:不低于|至少)\s*(\d+)",
            ],
            "applies_to": ["all"]
        }
    }

    def __init__(self):
        self.constraints: List[GlobalConstraint] = []
        self.raw_text: str = ""

    def parse_requirement(self, requirement: str) -> List[GlobalConstraint]:
        """
        解析需求文本，提取全局约束
        
        Args:
            requirement: 用户需求文本
        
        Returns:
            全局约束列表
        """
        self.constraints.clear()
        self.raw_text = requirement
        
        global_statements = self._extract_global_statements(requirement)
        
        for statement in global_statements:
            constraint = self._classify_constraint(statement)
            if constraint:
                self.constraints.append(constraint)
        
        logger.info(f"解析全局约束: {len(self.constraints)} 个")
        return self.constraints

    def _extract_global_statements(self, text: str) -> List[str]:
        """提取包含全局关键词的语句"""
        statements = []
        
        sentences = re.split(r'[。\n;]', text)
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            
            for keyword in self.GLOBAL_KEYWORDS:
                if keyword in sentence:
                    statements.append(sentence)
                    break
        
        return statements

    def _classify_constraint(self, statement: str) -> Optional[GlobalConstraint]:
        """分类约束"""
        for category, config in self.CONSTRAINT_PATTERNS.items():
            for pattern in config["patterns"]:
                match = re.search(pattern, statement)
                if match:
                    constraint_id = f"{category}_{len(self.constraints)}"
                    return GlobalConstraint(
                        id=constraint_id,
                        category=ConstraintCategory(category),
                        description=self._generate_description(category, match, statement),
                        original_text=statement,
                        applies_to=config["applies_to"],
                        priority="high"
                    )
        
        return GlobalConstraint(
            id=f"general_{len(self.constraints)}",
            category=ConstraintCategory.ARCHITECTURE,
            description=statement,
            original_text=statement,
            applies_to=["all"],
            priority="medium"
        )

    def _generate_description(
        self,
        category: str,
        match: re.Match,
        statement: str
    ) -> str:
        """生成约束描述"""
        if match.groups():
            value = match.group(1)
            category_names = {
                "tech_stack": "技术栈约束",
                "compatibility": "兼容性约束",
                "security": "安全约束",
                "performance": "性能约束",
                "architecture": "架构约束",
                "style": "代码风格约束",
                "naming": "命名规范约束",
                "testing": "测试约束"
            }
            return f"{category_names.get(category, '约束')}: {value}"
        return statement

    def get_constraints_for_file(
        self,
        file_path: str,
        file_type: str
    ) -> List[GlobalConstraint]:
        """
        获取适用于特定文件的约束
        
        Args:
            file_path: 文件路径
            file_type: 文件类型
        
        Returns:
            适用的约束列表
        """
        applicable = []
        
        for constraint in self.constraints:
            if "all" in constraint.applies_to:
                applicable.append(constraint)
            elif file_type in constraint.applies_to:
                applicable.append(constraint)
            elif self._file_matches_category(file_path, constraint.category):
                applicable.append(constraint)
        
        return applicable

    def _file_matches_category(
        self,
        file_path: str,
        category: ConstraintCategory
    ) -> bool:
        """判断文件是否匹配约束类别"""
        path_lower = file_path.lower()
        
        category_paths = {
            ConstraintCategory.TECH_STACK: True,
            ConstraintCategory.COMPATIBILITY: "frontend" in path_lower or "view" in path_lower,
            ConstraintCategory.SECURITY: "api" in path_lower or "router" in path_lower or "controller" in path_lower,
            ConstraintCategory.PERFORMANCE: True,
            ConstraintCategory.ARCHITECTURE: True,
            ConstraintCategory.STYLE: True,
            ConstraintCategory.NAMING: True,
            ConstraintCategory.TESTING: "test" in path_lower,
        }
        
        return category_paths.get(category, True)

    def generate_prompt_fragment(
        self,
        file_path: str,
        file_type: str
    ) -> str:
        """
        生成用于注入 prompt 的约束片段
        
        Args:
            file_path: 文件路径
            file_type: 文件类型
        
        Returns:
            约束 prompt 片段
        """
        applicable = self.get_constraints_for_file(file_path, file_type)
        
        if not applicable:
            return ""
        
        lines = ["全局约束要求:"]
        for constraint in applicable:
            lines.append(f"- {constraint.description}")
        
        return "\n".join(lines)

    def get_all_constraints(self) -> List[GlobalConstraint]:
        """获取所有约束"""
        return self.constraints.copy()

    def get_constraints_summary(self) -> Dict[str, Any]:
        """获取约束摘要"""
        summary = {
            "total": len(self.constraints),
            "by_category": {},
            "high_priority": [],
            "original_texts": []
        }
        
        for constraint in self.constraints:
            cat = constraint.category.value
            if cat not in summary["by_category"]:
                summary["by_category"][cat] = 0
            summary["by_category"][cat] += 1
            
            if constraint.priority == "high":
                summary["high_priority"].append(constraint.description)
            
            summary["original_texts"].append(constraint.original_text)
        
        return summary

    def merge_with_decisions(
        self,
        decisions: Dict[str, str]
    ) -> str:
        """
        将用户决策合并到约束 prompt
        
        Args:
            decisions: 用户决策字典
        
        Returns:
            合后的约束 prompt
        """
        parts = []
        
        if self.constraints:
            parts.append(self.generate_prompt_fragment("all", "all"))
        
        if decisions:
            decision_lines = ["用户架构决策:"]
            for decision_id, choice in decisions.items():
                decision_lines.append(f"- {decision_id}: {choice}")
            parts.append("\n".join(decision_lines))
        
        return "\n\n".join(parts)