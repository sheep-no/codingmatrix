"""
CrossValidator - 交叉验证器

核心理念：对于关键文件（认证、核心业务逻辑），
使用两个不同的模型独立生成，然后用第三个模型作为裁判进行对比验证。

工作流程：
1. 使用 Model A 生成代码
2. 使用 Model B 生成代码
3. 使用 Model C（裁判）对比两份代码，选择更好的那个
4. 如果两份代码都有问题，要求裁判生成最终版本
"""

import json
import re
import logging
from typing import Optional, Dict, Any, List, Tuple

from app.utils.AiCodeUtil import call_siliconflow
from app.utils.json_parser import extract_json_from_llm
from app.agent.shared_context import SharedContext
from app.agent.refinement_loop import RefinementLoop, RefinementResult

logger = logging.getLogger(__name__)


class CrossValidator:
    """
    交叉验证器 - 对关键文件进行双模型生成 + 裁判选择

    适用于：
    - 认证/授权逻辑（auth, permission, middleware）
    - 核心业务逻辑（payment, order, user_management）
    - 安全相关代码（crypto, encryption, token）
    """

    # 需要交叉验证的文件类型关键词
    CRITICAL_FILE_PATTERNS = [
        "auth", "permission", "middleware", "guard",
        "payment", "order", "billing", "subscription",
        "crypto", "encrypt", "token", "jwt", "oauth",
        "security", "validation", "sanitizer",
        "admin", "role", "access",
    ]

    JUDGE_SYSTEM_PROMPT = """你是一位资深技术评审专家，擅长代码审查和质量评估。

你的任务：
1. 对比同一文件的两份独立实现
2. 从以下维度评估：
   - 安全性：是否有安全漏洞（SQL注入、XSS、命令注入等）
   - 正确性：逻辑是否正确，边界情况是否处理
   - 可读性：命名是否清晰，结构是否合理
   - 完整性：是否实现了所有必要功能
   - 最佳实践：是否遵循框架约定和设计模式
3. 选择更好的一份，或生成改进后的最终版本

输出格式（JSON）：
{
  "winner": "A" / "B" / "merged",
  "reason": "选择理由",
  "issues_A": ["版本A的问题"],
  "issues_B": ["版本B的问题"],
  "final_code": "最终选用的代码（仅当winner为merged时提供）"
}"""

    def __init__(self, context: SharedContext):
        self.context = context

    def is_critical_file(self, file_path: str, file_type: str) -> bool:
        """判断文件是否需要交叉验证"""
        path_lower = file_path.lower()
        type_lower = file_type.lower()

        for pattern in self.CRITICAL_FILE_PATTERNS:
            if pattern in path_lower or pattern in type_lower:
                return True

        return False

    async def validate_and_select(
        self,
        file_path: str,
        file_type: str,
        description: str,
        version_a: str,
        model_a: str,
        version_b: str,
        model_b: str,
        judge_model: str,
        project_context: Optional[Dict] = None,
        callback=None
    ) -> Tuple[str, str]:
        """
        交叉验证并选择最佳版本

        Returns:
            (最终代码, 获胜模型)
        """
        prompt = f"""请对比以下两份代码实现，选择更好的版本。

文件路径: {file_path}
文件描述: {description}

## 版本 A (由 {model_a} 生成)
```
{version_a}
```

## 版本 B (由 {model_b} 生成)
```
{version_b}
```

请从安全性、正确性、可读性、完整性、最佳实践五个维度评估，
并选择更好的版本或生成改进后的最终版本。"""

        try:
            response = await call_siliconflow(
                prompt=f"【SYSTEM】\n{self.JUDGE_SYSTEM_PROMPT}\n\n【USER】\n{prompt}",
                model=judge_model,
                stream=False,
                max_tokens=8192,
                thinking_budget=4096,
                temperature=0.3  # 裁判需要确定性输出
            )

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                logger.warning(f"交叉验证裁判返回空内容，默认使用版本 A")
                return version_a, model_a

            result = self._extract_json(content)
            if not result:
                logger.warning(f"交叉验证结果解析失败，默认使用版本 A")
                return version_a, model_a

            winner = result.get("winner", "A")
            reason = result.get("reason", "")

            if winner == "A":
                logger.info(f"交叉验证选择版本 A ({model_a}): {reason}")
                return version_a, model_a
            elif winner == "B":
                logger.info(f"交叉验证选择版本 B ({model_b}): {reason}")
                return version_b, model_b
            elif winner == "merged":
                final_code = result.get("final_code", version_a)
                logger.info(f"交叉验证选择合并版本: {reason}")
                return final_code, f"{model_a}+{model_b}"
            else:
                return version_a, model_a

        except Exception as e:
            logger.error(f"交叉验证失败: {e}，默认使用版本 A")
            return version_a, model_a

    async def cross_validate_with_refinement(
        self,
        file_path: str,
        file_type: str,
        description: str,
        content_a: str,
        model_a: str,
        content_b: str,
        model_b: str,
        judge_model: str,
        refinement_loop: RefinementLoop,
        project_context: Optional[Dict] = None,
        callback=None
    ) -> RefinementResult:
        """
        完整的交叉验证流程：生成 -> 对比 -> 修复

        Returns:
            RefinementResult
        """
        # Step 1: 裁判选择最佳版本
        selected_code, winner_model = await self.validate_and_select(
            file_path=file_path,
            file_type=file_type,
            description=description,
            version_a=content_a,
            model_a=model_a,
            version_b=content_b,
            model_b=model_b,
            judge_model=judge_model,
            project_context=project_context,
            callback=callback
        )

        # Step 2: 对选中版本进行迭代修复
        result = await refinement_loop.refine(
            file_path=file_path,
            file_type=file_type,
            description=description,
            initial_content=selected_code,
            model_name=winner_model,
            project_context=project_context,
            callback=callback
        )

        return result

    def _extract_json(self, text: str) -> Optional[Dict]:
        """从文本中提取 JSON"""
        return extract_json_from_llm(text)
