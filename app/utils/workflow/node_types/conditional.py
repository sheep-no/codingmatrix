"""
Conditional Node - 条件分支节点

根据上下文数据执行条件判断，决定后续执行路径
"""

import ast
import logging
import operator
from typing import Any, Dict, List, Optional

from app.schema.workflow import TaskType
from app.utils.workflow.node_types.base import TaskNodeBase, NodeResult

logger = logging.getLogger(__name__)

# 支持的比较运算符
OPERATORS = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "in": lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
    "contains": lambda a, b: b in str(a),
    "is_empty": lambda a, b: not a if a else True,
    "is_not_empty": lambda a, b: bool(a),
    "starts_with": lambda a, b: str(a).startswith(str(b)),
    "ends_with": lambda a, b: str(a).endswith(str(b)),
}


class ConditionalNode(TaskNodeBase):
    """
    条件分支节点

    根据条件判断结果设置分支路径

    参数:
        variable: 上下文变量名（用于判断的值）
        operator: 比较运算符（==, !=, >, >=, <, <=, in, not_in, contains, is_empty, is_not_empty, starts_with, ends_with）
        value: 比较值
        true_branch: 条件为真时的下一个节点 ID 列表
        false_branch: 条件为假时的下一个节点 ID 列表
        expression: 自定义表达式（可选，优先级高于 variable/operator/value）
    """

    task_type = TaskType.CONDITIONAL

    def __init__(self, node_id: str, params: Dict[str, Any]):
        super().__init__(node_id, params)

    def get_required_params(self) -> List[str]:
        return []

    def get_optional_params(self) -> Dict[str, Any]:
        return {
            "variable": None,
            "operator": "==",
            "value": None,
            "true_branch": [],
            "false_branch": [],
            "expression": None,
        }

    def validate_params(self) -> List[str]:
        errors = []

        expression = self.params.get("expression")
        variable = self.params.get("variable")

        if not expression and not variable:
            errors.append("Either 'expression' or 'variable' must be provided")

        if variable:
            op = self.params.get("operator", "==")
            if op not in OPERATORS:
                errors.append(f"Unsupported operator: {op}. Supported: {list(OPERATORS.keys())}")

        if "true_branch" in self.params:
            tb = self.params["true_branch"]
            if not isinstance(tb, list):
                errors.append("Parameter 'true_branch' must be a list")

        if "false_branch" in self.params:
            fb = self.params["false_branch"]
            if not isinstance(fb, list):
                errors.append("Parameter 'false_branch' must be a list")

        return errors

    async def execute(self, context: Dict[str, Any]) -> NodeResult:
        """
        执行条件判断

        Args:
            context: 执行上下文

        Returns:
            NodeResult: 执行结果，包含 branch_path 字段
        """
        expression = self.params.get("expression")
        variable = self.params.get("variable")
        op = self.params.get("operator", "==")
        compare_value = self.params.get("value")
        true_branch = self.params.get("true_branch", [])
        false_branch = self.params.get("false_branch", [])

        try:
            if expression:
                # 自定义表达式模式（安全沙箱执行）
                result = self._evaluate_expression(expression, context)
            elif variable:
                # 变量比较模式
                var_value = context.get(variable)
                op_func = OPERATORS.get(op)
                if op_func is None:
                    return NodeResult.error_result(error=f"Unsupported operator: {op}")

                # 类型转换
                compare_value = self._coerce_value(var_value, compare_value)
                result = op_func(var_value, compare_value)
            else:
                return NodeResult.error_result(error="No condition specified")

            branch_path = true_branch if result else false_branch

            logger.info(
                f"[{self.node_id}] 条件判断 | variable={variable} | op={op} | "
                f"result={result} | branch={branch_path}"
            )

            return NodeResult.success_result(
                data={
                    "condition_result": result,
                    "branch_path": branch_path,
                    "variable": variable,
                    "operator": op,
                    "compare_value": compare_value,
                },
                metadata={"branch_path": branch_path}
            )

        except Exception as e:
            error_msg = f"Conditional evaluation failed: {str(e)}"
            logger.error(f"[{self.node_id}] {error_msg}")
            return NodeResult.error_result(error=error_msg)

    def _evaluate_expression(self, expression: str, context: Dict[str, Any]) -> bool:
        """
        安全执行表达式

        只支持简单的布尔表达式，禁止危险操作
        """
        # 替换上下文变量
        expr = expression
        for key, value in context.items():
            if isinstance(value, str):
                expr = expr.replace(f"{{{key}}}", f"'{value}'")
            elif isinstance(value, (int, float, bool)):
                expr = expr.replace(f"{{{key}}}", str(value))

        # 安全检查
        forbidden = ["import", "exec", "eval", "open", "os.", "sys.", "__", "subprocess"]
        for word in forbidden:
            if word in expr:
                raise ValueError(f"Forbidden keyword in expression: {word}")

        try:
            # 使用安全的 AST 求值替代 eval()
            result = self._safe_eval(expr)
            return bool(result)
        except Exception as e:
            raise ValueError(f"Expression evaluation failed: {str(e)}")

    def _safe_eval(self, expr: str) -> Any:
        """安全的表达式求值，仅允许比较和布尔操作"""
        ALLOWED_NODES = (
            ast.Expression, ast.Compare, ast.BoolOp, ast.UnaryOp,
            ast.Name, ast.Constant,
            ast.And, ast.Or, ast.Not,
            ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
            ast.In, ast.NotIn, ast.Is, ast.IsNot,
            ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow,
        )
        tree = ast.parse(expr, mode='eval')
        for node in ast.walk(tree):
            if not isinstance(node, ALLOWED_NODES):
                raise ValueError(f"不允许的表达式元素: {type(node).__name__}")
        return eval(compile(tree, '<expr>', 'eval'), {"__builtins__": {}}, {})

    def _coerce_value(self, var_value: Any, compare_value: Any) -> Any:
        """将比较值转换为与变量值相同的类型"""
        if var_value is None or compare_value is None:
            return compare_value

        try:
            if isinstance(var_value, int):
                return int(compare_value)
            elif isinstance(var_value, float):
                return float(compare_value)
            elif isinstance(var_value, bool):
                return str(compare_value).lower() in ("true", "1", "yes")
            elif isinstance(var_value, list):
                if isinstance(compare_value, str):
                    import json
                    return json.loads(compare_value)
        except (ValueError, TypeError):
            pass

        return compare_value
