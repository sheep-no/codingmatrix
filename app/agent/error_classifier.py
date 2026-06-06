"""
错误类型分类器 - 识别不同类型的代码错误并返回对应的修复策略
"""
import re
import json
from dataclasses import dataclass

from app.utils import call_llm
from app.agent.models import DEFAULT_CODE_MODEL


@dataclass
class ErrorClassification:
    """错误分类结果"""
    error_type: str
    error_subtype: str
    description: str
    suggested_fix_strategy: str
    confidence: float


class ErrorClassifier:
    """错误分类器 - 使用轻量级模型进行错误类型识别"""

    # 错误模式匹配规则
    ERROR_PATTERNS = {
        "NameError": {
            "patterns": [
                r"NameError: name '(\w+)' is not defined",
                r"name '(\w+)' is not defined"
            ],
            "description": "变量或函数未定义",
            "fix_strategy": "检查变量声明和导入语句，确保所有使用的变量都已正确定义或导入"
        },
        "AttributeError": {
            "patterns": [
                r"AttributeError: '(\w+)' object has no attribute '(\w+)'",
                r"'(\w+)' object has no attribute '(\w+)'"
            ],
            "description": "对象属性访问错误",
            "fix_strategy": "区分 Pydantic 模型和普通 dict 的访问方式，检查对象类型和可用属性"
        },
        "ImportError": {
            "patterns": [
                r"ImportError: cannot import name '(\w+)'",
                r"cannot import name '(\w+)' from '(\w+)'",
                r"No module named '(\w+)'"
            ],
            "description": "导入错误",
            "fix_strategy": "检查实际存在的导出名称，修正引用路径，确认模块是否已安装"
        },
        "SyntaxError": {
            "patterns": [
                r"SyntaxError:",
                r"invalid syntax",
                r"unexpected EOF while parsing"
            ],
            "description": "语法错误",
            "fix_strategy": "检查括号匹配、缩进、冒号、引号闭合等基本语法问题"
        },
        "TypeError": {
            "patterns": [
                r"TypeError:",
                r"unsupported operand type",
                r"takes \d+ positional arguments but \d+ were given"
            ],
            "description": "类型错误",
            "fix_strategy": "检查函数参数类型和数量，确保类型兼容性"
        },
        "KeyError": {
            "patterns": [
                r"KeyError: '(\w+)'",
                r"key '(\w+)' not found"
            ],
            "description": "字典键错误",
            "fix_strategy": "使用 .get() 方法安全访问字典键，或先检查键是否存在"
        },
        "IndexError": {
            "patterns": [
                r"IndexError:",
                r"list index out of range"
            ],
            "description": "索引越界错误",
            "fix_strategy": "检查列表/数组边界，确保索引在有效范围内"
        },
        "LogicError": {
            "patterns": [
                r"逻辑错误",
                r"业务逻辑错误",
                r"预期结果与实际不符"
            ],
            "description": "逻辑/业务错误",
            "fix_strategy": "使用 deepseek-r1 深度分析错误信息，重新生成核心逻辑"
        }
    }

    def __init__(self):
        self.classification_history = []

    async def classify_error(self, error_message: str, code_context: str = "") -> ErrorClassification:
        """分类错误类型并返回修复策略"""
        # 首先尝试基于规则的匹配
        rule_based_result = self._rule_based_classification(error_message)
        if rule_based_result:
            return rule_based_result

        # 如果规则匹配失败，使用轻量级模型进行分类
        return await self._model_based_classification(error_message, code_context)

    def _rule_based_classification(self, error_message: str) -> ErrorClassification:
        """基于规则的错误分类"""
        for error_type, config in self.ERROR_PATTERNS.items():
            for pattern in config["patterns"]:
                match = re.search(pattern, error_message, re.IGNORECASE)
                if match:
                    return ErrorClassification(
                        error_type=error_type,
                        error_subtype=match.groups()[0] if match.groups() else "",
                        description=config["description"],
                        suggested_fix_strategy=config["fix_strategy"],
                        confidence=0.95
                    )

        return None

    async def _model_based_classification(self, error_message: str, code_context: str) -> ErrorClassification:
        """基于模型的错误分类（使用 qwen3.5-4b）"""
        system_prompt = """你是一位资深的错误分类专家。你的任务是分析错误信息并将其分类到预定义的错误类型中。
只返回 JSON 格式的结果，不要包含其他文本。"""

        prompt = f"""请将以下错误信息分类到最合适的错误类型：

【错误信息】
{error_message}

【代码上下文】
{code_context[:500] if code_context else "无"}

【可用错误类型】
1. NameError - 变量或函数未定义
2. AttributeError - 对象属性访问错误
3. ImportError - 导入错误
4. SyntaxError - 语法错误
5. TypeError - 类型错误
6. KeyError - 字典键错误
7. IndexError - 索引越界错误
8. LogicError - 逻辑/业务错误

【返回格式】
{{"error_type": "错误类型", "error_subtype": "具体子类型", "description": "错误描述", "suggested_fix_strategy": "修复策略", "confidence": 0.0}}

请只返回 JSON，不要包含其他文本。"""

        try:
            response = await call_llm(
                model=DEFAULT_CODE_MODEL,
                prompt=f"【USER】\n{prompt}",
                stream=False,
                max_tokens=500,
                temperature=0.1,
                system_prompt=system_prompt
            )

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

            # 提取 JSON
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                result_dict = json.loads(json_match.group())
                return ErrorClassification(**result_dict)

        except Exception as e:
            print(f"模型分类失败: {e}")

        # 默认返回 LogicError
        return ErrorClassification(
            error_type="LogicError",
            error_subtype="unknown",
            description="未知逻辑错误",
            suggested_fix_strategy="使用 deepseek-r1 深度分析错误信息，重新生成核心逻辑",
            confidence=0.5
        )

    def get_fix_strategy_by_type(self, error_type: str) -> str:
        """根据错误类型获取修复策略"""
        if error_type in self.ERROR_PATTERNS:
            return self.ERROR_PATTERNS[error_type]["fix_strategy"]
        return "通用修复策略：仔细分析错误信息，逐步调试代码逻辑"

    def add_to_history(self, classification: ErrorClassification):
        """添加分类结果到历史记录"""
        self.classification_history.append(classification)


# 全局错误分类器实例
error_classifier = ErrorClassifier()
