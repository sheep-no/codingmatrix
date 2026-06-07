"""
Data Transform Node - 数据转换节点

对上下文数据进行映射、过滤、聚合等转换操作
"""

import ast
import logging
import json
from typing import Any, Dict, List, Optional

from app.schema.workflow import TaskType
from app.utils.workflow.node_types.base import TaskNodeBase, NodeResult

logger = logging.getLogger(__name__)


class DataTransformNode(TaskNodeBase):
    """
    数据转换节点

    对上下文数据进行转换操作

    参数:
        operation: 操作类型（必填）
            - map: 映射列表
            - filter: 过滤列表
            - reduce: 聚合列表
            - pick: 选取字段
            - rename: 重命名字段
            - merge: 合并多个对象
            - template: 模板替换
            - jsonpath: JSONPath 提取
            - sort: 排序
            - slice: 切片
            - flatten: 展平嵌套列表
            - unique: 去重
        input_variable: 输入变量名（必填）
        output_variable: 输出变量名（可选，默认 "transform_result"）
        config: 操作配置（根据 operation 不同而不同）
    """

    task_type = TaskType.DATA_TRANSFORM

    def __init__(self, node_id: str, params: Dict[str, Any]):
        super().__init__(node_id, params)

    def get_required_params(self) -> List[str]:
        return ["operation", "input_variable"]

    def get_optional_params(self) -> Dict[str, Any]:
        return {
            "output_variable": "transform_result",
            "config": {},
        }

    def validate_params(self) -> List[str]:
        errors = []

        supported_ops = [
            "map", "filter", "reduce", "pick", "rename", "merge",
            "template", "sort", "slice", "flatten", "unique", "jsonpath"
        ]

        if "operation" not in self.params:
            errors.append("Missing required parameter: operation")
        elif self.params["operation"] not in supported_ops:
            errors.append(f"Unsupported operation: {self.params['operation']}. Supported: {supported_ops}")

        if "input_variable" not in self.params:
            errors.append("Missing required parameter: input_variable")

        return errors

    async def execute(self, context: Dict[str, Any]) -> NodeResult:
        """
        执行数据转换

        Args:
            context: 执行上下文

        Returns:
            NodeResult: 转换结果
        """
        operation = self.params["operation"]
        input_variable = self.params["input_variable"]
        output_variable = self.params.get("output_variable", "transform_result")
        config = self.params.get("config", {})

        # 获取输入数据
        input_data = context.get(input_variable)
        if input_data is None:
            return NodeResult.error_result(
                error=f"Variable '{input_variable}' not found in context"
            )

        logger.info(f"[{self.node_id}] 数据转换 | op={operation} | input={input_variable}")

        try:
            result = self._apply_operation(operation, input_data, config)

            logger.info(
                f"[{self.node_id}] 转换完成 | result_type={type(result).__name__} | "
                f"result_len={len(result) if isinstance(result, (list, dict, str)) else 'N/A'}"
            )

            return NodeResult.success_result(
                data={
                    "result": result,
                    "output_variable": output_variable,
                    "operation": operation,
                },
                metadata={"operation": operation, "output_variable": output_variable}
            )

        except Exception as e:
            error_msg = f"Data transform failed: {str(e)}"
            logger.error(f"[{self.node_id}] {error_msg}")
            return NodeResult.error_result(error=error_msg)

    def _apply_operation(self, operation: str, data: Any, config: Dict) -> Any:
        """应用转换操作"""

        if operation == "map":
            # 映射：对列表每个元素应用表达式
            expression = config.get("expression", "item")
            if not isinstance(data, list):
                raise ValueError("map requires list input")
            return [self._eval_item_expr(expression, item, i) for i, item in enumerate(data)]

        elif operation == "filter":
            # 过滤：根据条件筛选列表
            condition = config.get("condition", "True")
            if not isinstance(data, list):
                raise ValueError("filter requires list input")
            return [item for i, item in enumerate(data) if self._eval_item_expr(condition, item, i)]

        elif operation == "reduce":
            # 聚合：将列表合并为单个值
            expression = config.get("expression", "acc + item")
            initial = config.get("initial", 0)
            if not isinstance(data, list):
                raise ValueError("reduce requires list input")
            acc = initial
            for item in data:
                acc = self._safe_eval_reduce(expression, {"acc": acc, "item": item})
            return acc

        elif operation == "pick":
            # 选取字段
            fields = config.get("fields", [])
            if isinstance(data, dict):
                return {k: data.get(k) for k in fields}
            elif isinstance(data, list):
                return [{k: item.get(k) for k in fields} for item in data if isinstance(item, dict)]
            raise ValueError("pick requires dict or list input")

        elif operation == "rename":
            # 重命名字段
            mapping = config.get("mapping", {})
            if isinstance(data, dict):
                result = dict(data)
                for old_key, new_key in mapping.items():
                    if old_key in result:
                        result[new_key] = result.pop(old_key)
                return result
            raise ValueError("rename requires dict input")

        elif operation == "merge":
            # 合并多个对象
            variables = config.get("variables", [])
            merged = dict(data) if isinstance(data, dict) else {}
            for var_name in variables:
                var_value = config.get(var_name)
                if isinstance(var_value, dict):
                    merged.update(var_value)
            return merged

        elif operation == "template":
            # 模板替换
            template = config.get("template", str(data))
            if isinstance(data, dict):
                for key, value in data.items():
                    template = template.replace(f"{{{key}}}", str(value))
            return template

        elif operation == "jsonpath":
            # JSONPath 简化版提取
            path = config.get("path", "")
            return self._extract_path(data, path)

        elif operation == "sort":
            # 排序
            key = config.get("key")
            reverse = config.get("reverse", False)
            if not isinstance(data, list):
                raise ValueError("sort requires list input")
            if key:
                return sorted(data, key=lambda x: x.get(key, 0) if isinstance(x, dict) else x, reverse=reverse)
            return sorted(data, reverse=reverse)

        elif operation == "slice":
            # 切片
            start = config.get("start", 0)
            end = config.get("end")
            if not isinstance(data, list):
                raise ValueError("slice requires list input")
            return data[start:end]

        elif operation == "flatten":
            # 展平嵌套列表
            if not isinstance(data, list):
                raise ValueError("flatten requires list input")
            result = []
            for item in data:
                if isinstance(item, list):
                    result.extend(item)
                else:
                    result.append(item)
            return result

        elif operation == "unique":
            # 去重
            if not isinstance(data, list):
                raise ValueError("unique requires list input")
            key = config.get("key")
            if key:
                seen = set()
                result = []
                for item in data:
                    val = item.get(key) if isinstance(item, dict) else item
                    if val not in seen:
                        seen.add(val)
                        result.append(item)
                return result
            return list(dict.fromkeys(data))

        else:
            raise ValueError(f"Unsupported operation: {operation}")

    def _eval_item_expr(self, expression: str, item: Any, index: int) -> Any:
        """安全执行表达式"""
        forbidden = ["import", "exec", "eval", "open", "os.", "sys.", "__", "subprocess"]
        for word in forbidden:
            if word in expression:
                raise ValueError(f"Forbidden keyword: {word}")

        try:
            return self._safe_eval(expression, {"item": item, "index": index, "i": index})
        except Exception as e:
            raise ValueError(f"Expression error: {str(e)}")

    def _safe_eval_reduce(self, expression: str, context: dict) -> Any:
        """安全的 reduce 表达式求值"""
        ALLOWED_NODES = (
            ast.Expression, ast.BinOp, ast.UnaryOp, ast.Name, ast.Constant,
            ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow,
            ast.FloorDiv, ast.USub, ast.UAdd,
        )
        tree = ast.parse(expression, mode='eval')
        for node in ast.walk(tree):
            if not isinstance(node, ALLOWED_NODES):
                raise ValueError(f"不允许的表达式元素: {type(node).__name__}")
        return eval(compile(tree, '<expr>', 'eval'), {"__builtins__": {}}, context)

    def _safe_eval(self, expression: str, context: dict) -> Any:
        """安全的表达式求值"""
        ALLOWED_NODES = (
            ast.Expression, ast.Compare, ast.BoolOp, ast.UnaryOp,
            ast.Name, ast.Constant, ast.Attribute,
            ast.And, ast.Or, ast.Not,
            ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
            ast.In, ast.NotIn, ast.Is, ast.IsNot,
            ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow,
            ast.FloorDiv, ast.USub, ast.UAdd,
        )
        tree = ast.parse(expression, mode='eval')
        for node in ast.walk(tree):
            if not isinstance(node, ALLOWED_NODES):
                raise ValueError(f"不允许的表达式元素: {type(node).__name__}")
        return eval(compile(tree, '<expr>', 'eval'), {"__builtins__": {}}, context)

    def _extract_path(self, data: Any, path: str) -> Any:
        """简化版 JSONPath 提取"""
        if not path:
            return data

        parts = path.strip(".").split(".")
        current = data

        for part in parts:
            if current is None:
                return None

            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list):
                try:
                    idx = int(part)
                    current = current[idx] if 0 <= idx < len(current) else None
                except ValueError:
                    # 对列表中的所有元素提取该字段
                    current = [item.get(part) if isinstance(item, dict) else None for item in current]
            else:
                return None

        return current
