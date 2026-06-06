"""
AI 审查器

从 multi_model_agent.py 拆分而来，保持向后兼容。
"""

import json
import logging
from typing import List, Dict, Any, Optional

from pydantic import ValidationError

from app.utils import call_llm
from app.agent.json_parser import safe_parse_json
from app.agent.models import ModelRegistry
from app.agent.file_contract import FileContract, ReviewResult

logger = logging.getLogger(__name__)


class AIReviewer:
    """
    AI 审查器 - 验证执行结果的质量和安全性
    """

    def __init__(self, model_key: str = "deepseek-r1-qwen3-8b", api_key_token: Optional[str] = None):
        self.model = ModelRegistry.get(model_key)
        self.api_key_token = api_key_token
        pass  # JSON parsing uses unified json_parser module

    async def review_code(self, code: str, context: str = "") -> ReviewResult:
        """
        审查代码

        Args:
            code: 待审查的代码
            context: 上下文信息

        Returns:
            审查结果
        """
        prompt = f"""审查以下代码，检查：
1. 安全性（SQL注入、XSS、命令注入等）
2. 正确性（逻辑错误、边界情况）
3. 性能问题
4. 代码质量

代码：
```{code}```

上下文：{context}

请以JSON格式返回：
{{
  "approved": true/false,
  "issues": ["问题列表"],
  "suggestions": ["改进建议"],
  "risk_level": "low/medium/high"
}}"""

        try:
            response = await call_llm(
                model=self.model.name,
                prompt=prompt,
                stream=False,
                max_tokens=self.model.max_tokens,
                temperature=self.model.temperature,
                api_key_token=self.api_key_token
            )

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")

            parsed = safe_parse_json(content)
            if not isinstance(parsed, dict):
                return ReviewResult(
                    approved=False,
                    issues=[f"审查输出不是 dict（实际: {type(parsed).__name__}）"],
                    risk_level="medium"
                )

            return ReviewResult.model_validate(parsed)
        except ValidationError as e:
            logger.warning(f"代码审查输出 schema 校验失败: {e}")
            err_msg = e.errors()[0]["msg"] if e.errors() else str(e)
            return ReviewResult(
                approved=False,
                issues=[f"审查输出 schema 校验失败: {err_msg}"],
                risk_level="medium"
            )
        except ValueError as e:
            logger.warning(f"代码审查输出无法解析: {e}")
            return ReviewResult(
                approved=False,
                issues=[f"审查输出无法解析: {str(e)[:200]}"],
                risk_level="medium"
            )
        except Exception as e:
            logger.error(f"代码审查失败: {e}")
            return ReviewResult(
                approved=False,
                issues=[f"审查过程出错: {str(e)}"],
                risk_level="medium"
            )

    async def review_file_operation(
        self,
        operation: str,
        file_path: str,
        content: str = None
    ) -> ReviewResult:
        """
        审查文件操作

        Args:
            operation: 操作类型
            file_path: 文件路径
            content: 文件内容（如果是写入操作）

        Returns:
            审查结果
        """
        contract = FileContract(
            operation=operation,
            file_path=file_path,
            expected_content=content
        )

        if not contract.validate_path():
            return ReviewResult(
                approved=False,
                issues=["路径验证失败：路径不安全或扩展名不允许"],
                risk_level="high"
            )

        if content and not contract.validate_content(content):
            return ReviewResult(
                approved=False,
                issues=["内容验证失败：内容过大或包含危险模式"],
                risk_level="high"
            )

        return ReviewResult(approved=True, risk_level="low")

    async def review_plan(self, plan: List[Dict]) -> ReviewResult:
        """
        审查执行计划

        Args:
            plan: 执行计划列表

        Returns:
            审查结果
        """
        prompt = f"""审查以下执行计划，判断是否合理和安全：

计划：
{json.dumps(plan, indent=2, ensure_ascii=False)}

请以JSON格式返回：
{{
  "approved": true/false,
  "issues": ["问题列表"],
  "suggestions": ["改进建议"],
  "risk_level": "low/medium/high"
}}"""

        try:
            response = await call_llm(
                model=self.model.name,
                prompt=prompt,
                stream=False,
                max_tokens=self.model.max_tokens,
                temperature=self.model.temperature,
                api_key_token=self.api_key_token
            )

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")

            parsed = safe_parse_json(content)
            if not isinstance(parsed, dict):
                logger.warning(f"无法从审查响应中提取 dict，拒绝放行计划: {content[:200]}")
                return ReviewResult(
                    approved=False,
                    issues=["审查响应格式异常，已拒绝放行"],
                    suggestions=["检查 LLM 输出格式或重试"],
                    risk_level="high"
                )

            has_degraded = any(
                isinstance(s, dict) and s.get("degraded") for s in plan
            )
            result = ReviewResult.model_validate(parsed)
            if has_degraded and (result.approved or result.risk_level != "high"):
                result = result.model_copy(update={
                    "approved": False,
                    "risk_level": "high",
                    "issues": result.issues + ["计划中包含降级步骤，需人工审查"],
                })
            return result
        except ValidationError as e:
            logger.warning(f"计划审查输出 schema 校验失败: {e}")
            err_msg = e.errors()[0]["msg"] if e.errors() else str(e)
            return ReviewResult(
                approved=False,
                issues=[f"审查输出 schema 校验失败: {err_msg}"],
                suggestions=["检查 LLM 输出格式或重试"],
                risk_level="high"
            )
        except ValueError as e:
            logger.warning(f"计划审查输出无法解析: {e}")
            return ReviewResult(
                approved=False,
                issues=[f"审查输出无法解析: {str(e)[:200]}"],
                suggestions=["检查 LLM 输出格式或重试"],
                risk_level="high"
            )
        except Exception as e:
            logger.error(f"计划审查失败: {e}")
            return ReviewResult(
                approved=False,
                issues=[f"审查异常: {str(e)}"],
                risk_level="high"
            )
