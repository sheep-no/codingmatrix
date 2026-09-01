"""按错误类型选择修复路径并限制自动修复预算。"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=True)
class RepairRoute:
    """一次错误对应的修复决策。"""

    category: str
    repairer: str
    auto_apply: bool
    max_attempts: int = 3


@dataclass
class RepairBudget:
    """限制单类错误和任务级自动修复次数。"""

    per_category_limit: int = 3
    total_limit: int = 5
    used_by_category: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    total_used: int = 0

    def consume(self, category: str) -> bool:
        """消耗一次预算，超限时返回 False。"""
        if self.total_used >= self.total_limit:
            return False
        if self.used_by_category[category] >= self.per_category_limit:
            return False
        self.used_by_category[category] += 1
        self.total_used += 1
        return True

    def can_consume(self, category: str) -> bool:
        return (
            self.total_used < self.total_limit
            and self.used_by_category[category] < self.per_category_limit
        )


class RepairRouter:
    """将分类器输出映射为稳定、可审计的修复路径。"""

    _AUTO_CATEGORIES = {
        "syntax": "code_repair",
        "import": "dependency_repair",
        "name": "code_repair",
        "type": "code_repair",
    }

    @classmethod
    def route(cls, error_type: str = "", error_message: str = "") -> RepairRoute:
        normalized = f"{error_type} {error_message}".lower()
        if any(token in normalized for token in ("syntaxerror", "语法", "parse error")):
            return RepairRoute("syntax", "code_repair", True)
        if any(token in normalized for token in ("importerror", "modulenotfound", "no module", "导入")):
            return RepairRoute("import", "dependency_repair", True)
        if any(token in normalized for token in ("nameerror", "未定义", "undefined")):
            return RepairRoute("name", "code_repair", True)
        if any(token in normalized for token in ("typeerror", "类型错误", "type mismatch")):
            return RepairRoute("type", "code_repair", True)
        if any(token in normalized for token in ("test_failure", "assertionerror", "测试", "断言")):
            return RepairRoute("test", "user_confirmation", False)
        if any(token in normalized for token in ("logicerror", "业务", "逻辑")):
            return RepairRoute("business", "user_confirmation", False)
        return RepairRoute("unknown", "user_confirmation", False)
