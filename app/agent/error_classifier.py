"""
错误类型分类器 - 识别不同类型的代码错误并返回对应的修复策略
"""
import logging
import re
from collections import deque
from dataclasses import dataclass
from typing import Optional

from app.utils import call_llm
from app.agent.models import DEFAULT_CODE_MODEL
from app.agent.json_parser import extract_first_json_object

logger = logging.getLogger(__name__)


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
                r"name '(\w+)' is not defined",
                # 无引号变体：``name x is not defined``
                r"name (\w+) is not defined",
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
                # 数字键变体：``KeyError: 5``
                r"KeyError:\s*(\d+)",
                r"key '(\w+)' not found",
                r"KeyError:",
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
                r"预期结果与实际不符",
                # 英文错误消息此前永不命中中文规则，规则路径实际不可达
                r"logic error",
                r"business logic error",
            ],
            "description": "逻辑/业务错误",
            "fix_strategy": "深度分析错误信息，重新梳理并修正核心业务逻辑"
        }
    }

    # 模型分类结果必需字段（缺失即视为分类失败）
    _MODEL_REQUIRED_FIELDS = ("error_type", "description", "suggested_fix_strategy")
    # 历史记录上限，避免全局单例在长会话中无界增长
    HISTORY_MAXLEN = 200

    def __init__(self):
        self.classification_history = deque(maxlen=self.HISTORY_MAXLEN)

    async def classify_error(self, error_message: str, code_context: str = "") -> ErrorClassification:
        """分类错误类型并返回修复策略"""
        # 首先尝试基于规则的匹配
        rule_based_result = self._rule_based_classification(error_message)
        if rule_based_result:
            return rule_based_result

        # 如果规则匹配失败，使用轻量级模型进行分类
        return await self._model_based_classification(error_message, code_context)

    def _rule_based_classification(self, error_message: str) -> Optional[ErrorClassification]:
        """基于规则的错误分类。

        调用方传入的是多条错误的拼接串（``"; ".join(...)``）。原实现按
        ERROR_PATTERNS 的 dict 顺序返回第一个命中的类型，返回结果由字典遍历
        顺序决定，与实际首个错误无关。现改为取所有命中中位置最靠前（即文本中
        最先出现）的那条，与错误出现顺序一致。
        """
        best = None  # (start, error_type, config, match)
        for error_type, config in self.ERROR_PATTERNS.items():
            for pattern in config["patterns"]:
                match = re.search(pattern, error_message, re.IGNORECASE)
                if match is None:
                    continue
                if best is None or match.start() < best[0]:
                    best = (match.start(), error_type, config, match)

        if best is None:
            return None

        _, error_type, config, match = best
        return ErrorClassification(
            error_type=error_type,
            error_subtype=match.groups()[0] if match.groups() else "",
            description=config["description"],
            suggested_fix_strategy=config["fix_strategy"],
            confidence=0.95
        )

    @staticmethod
    def _unclassified_fallback() -> ErrorClassification:
        """规则未命中且模型分类不可用时的兜底。

        原实现把分类失败伪装成 LogicError（confidence=0.5）并给出误导性的
        修复策略，使上游把「未知错误」当作「业务逻辑错误」处理。现返回显式的
        Unknown + confidence=0.0，让上游走人工确认/通用策略。
        """
        return ErrorClassification(
            error_type="Unknown",
            error_subtype="unclassified",
            description="错误分类失败（规则未命中且模型分类不可用）",
            suggested_fix_strategy="人工检查错误信息，按实际错误类型定位并修复",
            confidence=0.0,
        )

    def _coerce_model_result(self, data) -> Optional[ErrorClassification]:
        """校验模型返回的字典，字段缺失/类型非法时返回 None（视为分类失败）。"""
        if not isinstance(data, dict):
            return None
        if not all(data.get(field) for field in self._MODEL_REQUIRED_FIELDS):
            return None
        error_type = data.get("error_type")
        if error_type not in self.ERROR_PATTERNS and error_type != "Unknown":
            return None

        try:
            confidence = float(data.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        # LLM 可能返回越界值（如 5.0），统一夹到 [0, 1]
        confidence = min(1.0, max(0.0, confidence))

        return ErrorClassification(
            error_type=error_type,
            error_subtype=str(data.get("error_subtype", "")),
            description=str(data["description"]),
            suggested_fix_strategy=str(data["suggested_fix_strategy"]),
            confidence=confidence,
        )

    async def _model_based_classification(self, error_message: str, code_context: str) -> ErrorClassification:
        """基于模型的错误分类（使用 DEFAULT_CODE_MODEL）"""
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

            # 逐 ``{`` 取首个 JSON 对象：贪婪正则 ``\{.*\}`` 在多 JSON 块或
            # 带解释文本时会跨块匹配导致 json.loads 抛 "Extra data"。
            result_dict = extract_first_json_object(content)
            classification = self._coerce_model_result(result_dict)
            if classification is not None:
                return classification
            logger.warning("模型分类返回结构非法，降级为 Unknown")

        except Exception as e:
            logger.warning("模型分类失败: %s", e)

        return self._unclassified_fallback()

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
