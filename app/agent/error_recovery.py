"""
错误恢复循环 - 智能自我修正（验证-修复-重试 + 模型降级）
"""

import re
import json
import time
import logging
from typing import Optional, Dict, List, Callable, Tuple, Any
from dataclasses import dataclass
from pathlib import Path

from app.utils import call_llm
from app.agent.code_validator import CodeValidator
from app.agent.specialists import CodeReviewer
from app.agent.dynamic_model_router import LayeredModelRouter
from app.agent.test_runner import TestRunner
from app.agent.error_classifier import error_classifier, ErrorClassification
from app.agent.strategy_evaluator import strategy_evaluator, StrategyEvaluationResult
from app.agent.specialist_base import get_global_llm_semaphore


logger = logging.getLogger(__name__)


@dataclass
class FixAttempt:
    """修复尝试记录"""
    file_path: str
    error_type: str
    error_message: str
    fix_applied: bool
    attempts: int
    model_used: Optional[str] = None


class ErrorRecoveryLoop:
    """错误恢复循环 - 智能自我修正（验证-修复-重试 + 模型降级）"""

    MAX_FIX_ATTEMPTS = 3  # 智能修正循环最多尝试 3 次（捕获深层问题）

    # 默认模型降级链（硬编码兜底）
    DEFAULT_FALLBACK_CHAIN = [
        "Qwen/Qwen3-8B",             # 代码修复首选
        "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",  # 通用修复
        "Qwen/Qwen3.5-4B",           # 快速降级
    ]

    def __init__(self, validator: CodeValidator, reviewer: CodeReviewer):
        self.validator = validator
        self.reviewer = reviewer
        self.fix_history: List[FixAttempt] = []
        self._semaphore = get_global_llm_semaphore()
        self.MODEL_FALLBACK_CHAIN = self._load_fallback_chain("error_recovery")

    def _load_fallback_chain(self, chain_name: str = "error_recovery") -> List[str]:
        """从配置文件加载降级链"""
        from app.agent.dynamic_model_router import load_agent_model_config, resolve_model_key
        config = load_agent_model_config()
        if config and "fallback_chains" in config:
            chain = config["fallback_chains"].get(chain_name, [])
            if chain:
                resolved = [resolve_model_key(m) for m in chain]
                return resolved
        return self.DEFAULT_FALLBACK_CHAIN.copy()

    async def validate_and_fix(
        self,
        file_path: Path,
        content: str,
        file_description: str,
        backend_model: str,
        callback: Optional[Callable] = None
    ) -> Tuple[bool, str]:
        """验证并智能修复文件内容"""
        project_path = file_path.parent

        # 创建临时文件进行验证
        temp_file = project_path / f".temp_{file_path.name}"
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(content)

            # 运行完整验证
            validation = await self.validator.run_full_validation()

            if validation["is_valid"]:
                if temp_file.exists():
                    temp_file.unlink()
                return True, content

            # 验证失败，进入智能修正循环
            fix_result = await self._smart_fix_loop(
                file_path=file_path,
                content=content,
                errors=validation,
                backend_model=backend_model,
                callback=callback
            )

            if temp_file.exists():
                temp_file.unlink()
            return fix_result["success"], fix_result["fixed_content"]

        except Exception as e:
            logger.error(f"验证修复异常: {e}")
            if temp_file.exists():
                temp_file.unlink()
            return False, content

    async def _smart_fix_loop(
        self,
        file_path: Path,
        content: str,
        errors: Dict,
        backend_model: str,
        callback: Optional[Callable] = None
    ) -> Dict:
        """智能修正循环：带模型降级策略、错误分类和 A/B 测试策略"""
        # 确定修复模型链：主模型 + 配置文件中的降级链
        models_to_try = [backend_model] + self.MODEL_FALLBACK_CHAIN
        # 去重并保持顺序
        seen = set()
        unique_models = []
        for m in models_to_try:
            if m not in seen:
                seen.add(m)
                unique_models.append(m)
        models_to_try = unique_models

        # 分析错误类型以选择最佳修复策略
        error_messages = "; ".join(self._extract_error_messages(errors))
        classification = await error_classifier.classify_error(error_messages, content)
        error_classifier.add_to_history(classification)

        # 通过策略评估器获取修复模板
        fix_template, strategy_id = strategy_evaluator.get_strategy_template(classification.error_type)

        # 如果没有预定义策略，使用默认模板
        if fix_template is None:
            fix_template = self._build_default_fix_template()

        for attempt in range(self.MAX_FIX_ATTEMPTS):
            # 根据错误类型选择合适的修复模型
            fix_model = self._select_fix_model_by_error_type(classification.error_type, models_to_try, attempt)
            fix_model_config = LayeredModelRouter.get_model_config(fix_model, task_type="fix")

            # 构建针对性的修复提示（使用策略模板）
            error_context = self._build_targeted_error_context_with_template(
                errors, content, attempt, classification, fix_template
            )

            system_prompt = f"""你是一位资深代码修复专家。你的任务是修复代码中的{classification.description}。
请遵循以下原则：
1. 仅修复指出的问题，不要修改其他代码
2. 保持原有代码结构和风格
3. 确保修复后的代码语法正确、导入完整
4. 返回完整代码，不要省略任何部分

【修复策略】
{fix_template}"""

            fix_prompt = f"""请修复以下代码中的错误。

【当前代码】
```
{content}
```

【发现的错误】
{error_context}

【修复要求】
1. {classification.suggested_fix_strategy}
2. 仅修复指出的问题，保持其他代码不变
3. 确保修复后的代码能通过语法、导入和依赖验证
4. 返回完整修复后的代码，不要省略任何部分
5. {"（这是最后一次尝试，请使用不同的修复策略）" if attempt == self.MAX_FIX_ATTEMPTS - 1 else ""}
"""

            async with self._semaphore:
                try:
                    start_time = time.time()
                    response = await call_llm(
                        model=fix_model,
                        prompt=fix_prompt,
                        stream=False,
                        max_tokens=fix_model_config["max_tokens"],
                        thinking_budget=fix_model_config["thinking_budget"],
                        temperature=fix_model_config["temperature"],
                        system_prompt=system_prompt
                    )
                    fix_time = time.time() - start_time

                    fixed_content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
                    code_match = re.search(r'```(?:\w+)?\s*(.*?)\s*```', fixed_content, re.DOTALL)
                    if code_match:
                        fixed_content = code_match.group(1).strip()

                    if not fixed_content:
                        logger.warning(f"修复尝试 {attempt + 1} 返回空内容 (模型: {fix_model})")
                        # 记录失败评估结果
                        if strategy_id:
                            strategy_evaluator.record_evaluation_result(
                                StrategyEvaluationResult(
                                    strategy_id=strategy_id,
                                    success=False,
                                    fix_time=fix_time,
                                    code_quality_score=0.0,
                                    timestamp=time.time()
                                )
                            )
                        continue

                    # 验证修复后的代码（只验证单个文件）
                    temp_file = file_path.parent / f".temp_fix_{file_path.name}"
                    with open(temp_file, 'w', encoding='utf-8') as f:
                        f.write(fixed_content)

                    validation = await self.validator.validate_single_file(temp_file)
                    if temp_file.exists():
                        temp_file.unlink()

                    if validation["is_valid"]:
                        # 评估代码质量（通过后续审查轮次的通过率）
                        code_quality_score = await self._evaluate_code_quality(fixed_content, file_path)

                        self.fix_history.append(FixAttempt(
                            file_path=str(file_path),
                            error_type=classification.error_type,
                            error_message="; ".join(self._extract_error_messages(errors)),
                            fix_applied=True,
                            attempts=attempt + 1,
                            model_used=fix_model
                        ))

                        # 记录成功评估结果
                        if strategy_id:
                            strategy_evaluator.record_evaluation_result(
                                StrategyEvaluationResult(
                                    strategy_id=strategy_id,
                                    success=True,
                                    fix_time=fix_time,
                                    code_quality_score=code_quality_score,
                                    timestamp=time.time()
                                )
                            )

                        return {"success": True, "fixed_content": fixed_content}
                    else:
                        # 构建详细的错误信息
                        error_details = []
                        if validation.get("syntax_errors"):
                            error_details.extend([f"语法: {e}" for e in validation["syntax_errors"]])
                        if validation.get("import_errors"):
                            error_details.extend([f"导入: {e}" for e in validation["import_errors"]])
                        if validation.get("runtime_errors"):
                            error_details.extend([f"运行时: {e}" for e in validation["runtime_errors"]])
                        if validation.get("api_errors"):
                            error_details.extend([f"API 兼容性: {e}" for e in validation["api_errors"]])
                        if validation.get("frontend_errors"):
                            error_details.extend([f"前端: {e}" for e in validation["frontend_errors"]])
                        error_msg = "; ".join(error_details) if error_details else "验证失败（无详细错误）"
                        logger.warning(f"修复尝试 {attempt + 1} 未通过验证 (模型: {fix_model}): {error_msg}")

                        # 记录失败评估结果
                        if strategy_id:
                            strategy_evaluator.record_evaluation_result(
                                StrategyEvaluationResult(
                                    strategy_id=strategy_id,
                                    success=False,
                                    fix_time=fix_time,
                                    code_quality_score=0.0,
                                    timestamp=time.time()
                                )
                            )

                        # 更新错误上下文用于下一次尝试
                        errors = validation

                except Exception as e:
                    logger.error(f"修复尝试 {attempt + 1} 失败 (模型: {fix_model}): {e}")
                    # 记录异常评估结果
                    if strategy_id:
                        strategy_evaluator.record_evaluation_result(
                            StrategyEvaluationResult(
                                strategy_id=strategy_id,
                                success=False,
                                fix_time=time.time() - start_time if 'start_time' in locals() else 0,
                                code_quality_score=0.0,
                                timestamp=time.time()
                            )
                        )

        self.fix_history.append(FixAttempt(
            file_path=str(file_path),
            error_type=classification.error_type,
            error_message="多次修复失败: " + "; ".join(self._extract_error_messages(errors)),
            fix_applied=False,
            attempts=self.MAX_FIX_ATTEMPTS
        ))

        # 记录最终失败评估结果
        if strategy_id:
            strategy_evaluator.record_evaluation_result(
                StrategyEvaluationResult(
                    strategy_id=strategy_id,
                    success=False,
                    fix_time=0.0,
                    code_quality_score=0.0,
                    timestamp=time.time()
                )
            )

        return {"success": False, "fixed_content": content}

    async def _evaluate_code_quality(self, code: str, file_path: Path) -> float:
        """评估修复后代码的质量（通过模拟审查轮次）"""
        try:
            # 创建临时文件进行审查
            temp_file = file_path.parent / f".temp_quality_{file_path.name}"
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(code)

            # 运行轻量级审查（只检查基本问题）
            validation = await self.validator.validate_single_file(temp_file)
            if temp_file.exists():
                temp_file.unlink()

            if validation["is_valid"]:
                return 1.0
            else:
                # 根据错误数量计算质量分数
                error_count = 0
                for key in ["syntax_errors", "import_errors", "runtime_errors", "api_errors", "frontend_errors"]:
                    error_count += len(validation.get(key, []))

                # 最多5个错误，超过5个按5算
                error_count = min(error_count, 5)
                return max(0.0, 1.0 - (error_count * 0.2))

        except Exception as e:
            logger.warning(f"代码质量评估失败: {e}")
            return 0.5  # 默认中等质量

    def _build_default_fix_template(self) -> str:
        """构建默认修复模板"""
        return """请修复以下代码中的错误。

【当前代码】
```
{content}
```

【发现的错误】
{error_context}

【修复要求】
1. {suggested_fix_strategy}
2. 仅修复指出的问题，保持其他代码不变
3. 确保修复后的代码能通过语法、导入和依赖验证
4. 返回完整修复后的代码，不要省略任何部分"""

    def _build_targeted_error_context_with_template(
        self,
        errors: Dict,
        content: str,
        attempt: int,
        classification: ErrorClassification,
        template: str
    ) -> str:
        """使用策略模板构建针对性的错误上下文"""
        # 先构建基础错误上下文
        base_context = self._build_targeted_error_context(errors, content, attempt, classification)

        # 如果有策略模板，将错误上下文注入模板中
        if template and "{error_context}" in template:
            return template.replace("{error_context}", base_context)

        return base_context

    def _select_fix_model_by_error_type(self, error_type: str, models_to_try: List[str], attempt: int) -> str:
        """根据错误类型选择最佳修复模型"""
        # 从配置文件加载错误类型到模型的映射
        from app.agent.dynamic_model_router import load_agent_model_config, resolve_model_key
        config = load_agent_model_config()

        # 默认映射（硬编码兜底）
        DEFAULT_ERROR_MODEL_MAPPING = {
            "NameError": "Qwen/Qwen3.5-4B",      # 简单变量错误，快速模型即可
            "AttributeError": "Qwen/Qwen3-8B",  # 需要理解对象结构
            "ImportError": "Qwen/Qwen3-8B",     # 需要理解模块系统
            "SyntaxError": "Qwen/Qwen3.5-4B",    # 语法错误，简单修复
            "TypeError": "Qwen/Qwen3-8B",       # 类型系统理解
            "KeyError": "Qwen/Qwen3.5-4B",       # 简单字典操作
            "IndexError": "Qwen/Qwen3.5-4B",     # 简单索引操作
            "LogicError": "Qwen/Qwen3-8B"        # 复杂逻辑需要强推理
        }

        # 尝试从配置文件加载
        ERROR_MODEL_MAPPING = DEFAULT_ERROR_MODEL_MAPPING.copy()
        if config and "error_type_models" in config:
            for error_type_key, model_id in config["error_type_models"].items():
                ERROR_MODEL_MAPPING[error_type_key] = resolve_model_key(model_id)

        # 获取推荐模型
        recommended_model = ERROR_MODEL_MAPPING.get(error_type, models_to_try[0])

        # 如果推荐模型不在可用模型列表中，使用第一个模型
        if recommended_model in models_to_try:
            return recommended_model

        # 否则按尝试次数选择模型
        return models_to_try[attempt % len(models_to_try)]

    def _build_targeted_error_context(self, errors: Dict, content: str, attempt: int, classification: ErrorClassification) -> str:
        """构建针对性的错误上下文（基于错误分类）"""
        context_parts = []

        # 添加错误分类信息
        context_parts.append(f"## 错误类型\n{classification.error_type}: {classification.description}")
        context_parts.append(f"**针对性修复建议**: {classification.suggested_fix_strategy}")

        # 根据错误类型添加特定上下文
        if errors.get("syntax_errors"):
            context_parts.append("## 语法错误\n" + "\n".join(f"- {e}" for e in errors["syntax_errors"]))
            if classification.error_type == "SyntaxError":
                context_parts.append("**重点检查**: 括号匹配、缩进、冒号、引号闭合等基本语法")

        if errors.get("import_errors"):
            context_parts.append("## 导入错误\n" + "\n".join(f"- {e}" for e in errors["import_errors"]))
            if classification.error_type == "ImportError":
                context_parts.append("**重点检查**: 模块已安装、导入路径正确、__init__.py 存在")

        if errors.get("dependency_errors"):
            context_parts.append("## 依赖错误\n" + "\n".join(f"- {e}" for e in errors["dependency_errors"]))
            context_parts.append("**修复建议**: 运行 `pip install <包名>` 或在 requirements.txt 中添加缺失的包")

        if errors.get("runtime_errors"):
            runtime_errs = errors["runtime_errors"]
            context_parts.append("## 运行时错误\n" + "\n".join(f"- {e}" for e in runtime_errs))
            fix_suggestions = []
            for e in runtime_errs:
                if "passlib" in e:
                    fix_suggestions.append("将 `import passlib.hash.bcrypt` 改为 `from passlib.hash import bcrypt`")
                elif "运行时导入失败" in e:
                    fix_suggestions.append(f"检查导入路径和模块是否存在: {e}")
                elif "属性错误" in e or "API 版本" in e:
                    fix_suggestions.append("检查库的 API 是否与已安装版本兼容，查阅官方文档确认正确的属性名")
                elif "类型错误" in e or "API 参数" in e:
                    fix_suggestions.append("检查函数调用参数名和类型是否与 API 定义匹配")

            # 根据错误类型添加特定建议
            if classification.error_type == "NameError":
                fix_suggestions.append("仔细检查所有变量名拼写，确保在使用前已定义")
            elif classification.error_type == "AttributeError":
                fix_suggestions.append("确认对象类型，检查是否有该属性，注意大小写")
            elif classification.error_type == "TypeError":
                fix_suggestions.append("检查函数参数数量和类型，确保传入正确的参数")

            if fix_suggestions:
                context_parts.append("**针对性修复建议**:\n" + "\n".join(f"- {s}" for s in fix_suggestions))

        if errors.get("api_errors"):
            api_errs = errors["api_errors"]
            context_parts.append("## API 兼容性错误\n" + "\n".join(f"- {e}" for e in api_errs))
            fix_suggestions = []
            for e in api_errs:
                if "tokenUrl" in e:
                    fix_suggestions.append("将 `OAuth2PasswordBearer(tokenUrl=...)` 改为 `OAuth2PasswordBearer(token_url=...)`")
                elif "Middleware" in e:
                    fix_suggestions.append("将 `from fastapi import Middleware` 改为 `from fastapi.middleware.cors import CORSMiddleware`")
                elif "MRO" in e or "BaseModel" in e:
                    fix_suggestions.append("SQLAlchemy 模型不应同时继承 Base 和 BaseModel，选择其一或使用 Pydantic v2 的模型验证")
                elif "exception_handler" in e:
                    fix_suggestions.append("异常处理器应在 app 级别注册: `app.exception_handler(Exception)(handler)`，而非 router 级别")
            if fix_suggestions:
                context_parts.append("**修复建议**:\n" + "\n".join(f"- {s}" for s in fix_suggestions))

        if errors.get("frontend_errors"):
            frontend_errs = errors["frontend_errors"]
            context_parts.append("## 前端错误\n" + "\n".join(f"- {e}" for e in frontend_errs))
            fix_suggestions = []
            for e in frontend_errs:
                if "JS 语法错误" in e:
                    fix_suggestions.append("检查 JavaScript 语法：分号、括号匹配、变量声明等")
                elif "HTML 结构" in e:
                    fix_suggestions.append("检查 HTML 标签是否正确闭合，确保 html/head/body 标签完整")
                elif "CSS 语法" in e:
                    fix_suggestions.append("检查 CSS 大括号匹配、选择器语法、属性值格式")
            if fix_suggestions:
                context_parts.append("**修复建议**:\n" + "\n".join(f"- {s}" for s in fix_suggestions))

        if errors.get("cross_file_errors"):
            cross_errs = errors["cross_file_errors"]
            context_parts.append("## 跨文件一致性错误\n" + "\n".join(f"- {e}" for e in cross_errs))
            context_parts.append("**修复建议**: 确保导入的模块存在且导出了所需的符号，检查文件路径是否正确")

        if attempt > 0:
            context_parts.append(f"\n## 注意\n此前已尝试修复 {attempt} 次但未通过验证，请检查是否有遗漏的错误或逻辑问题。")

        return "\n".join(context_parts) if context_parts else "未知验证错误"

    def _build_error_context(self, errors: Dict, content: str, attempt: int) -> str:
        """构建详细的错误上下文（包含修复建议）"""
        context_parts = []

        if errors.get("syntax_errors"):
            context_parts.append("## 语法错误\n" + "\n".join(f"- {e}" for e in errors["syntax_errors"]))
            context_parts.append("**修复建议**: 检查括号匹配、缩进、冒号、引号闭合等基本语法")

        if errors.get("import_errors"):
            context_parts.append("## 导入错误\n" + "\n".join(f"- {e}" for e in errors["import_errors"]))
            context_parts.append("**修复建议**: 确认模块已安装，检查导入路径是否正确，确保 __init__.py 存在")

        if errors.get("dependency_errors"):
            context_parts.append("## 依赖错误\n" + "\n".join(f"- {e}" for e in errors["dependency_errors"]))
            context_parts.append("**修复建议**: 运行 `pip install <包名>` 或在 requirements.txt 中添加缺失的包")

        if errors.get("runtime_errors"):
            runtime_errs = errors["runtime_errors"]
            context_parts.append("## 运行时错误\n" + "\n".join(f"- {e}" for e in runtime_errs))
            fix_suggestions = []
            for e in runtime_errs:
                if "passlib" in e:
                    fix_suggestions.append("将 `import passlib.hash.bcrypt` 改为 `from passlib.hash import bcrypt`")
                elif "运行时导入失败" in e:
                    fix_suggestions.append(f"检查导入路径和模块是否存在: {e}")
                elif "属性错误" in e or "API 版本" in e:
                    fix_suggestions.append("检查库的 API 是否与已安装版本兼容，查阅官方文档确认正确的属性名")
                elif "类型错误" in e or "API 参数" in e:
                    fix_suggestions.append("检查函数调用参数名和类型是否与 API 定义匹配")
            if fix_suggestions:
                context_parts.append("**修复建议**:\n" + "\n".join(f"- {s}" for s in fix_suggestions))

        if errors.get("api_errors"):
            api_errs = errors["api_errors"]
            context_parts.append("## API 兼容性错误\n" + "\n".join(f"- {e}" for e in api_errs))
            fix_suggestions = []
            for e in api_errs:
                if "tokenUrl" in e:
                    fix_suggestions.append("将 `OAuth2PasswordBearer(tokenUrl=...)` 改为 `OAuth2PasswordBearer(token_url=...)`")
                elif "Middleware" in e:
                    fix_suggestions.append("将 `from fastapi import Middleware` 改为 `from fastapi.middleware.cors import CORSMiddleware`")
                elif "MRO" in e or "BaseModel" in e:
                    fix_suggestions.append("SQLAlchemy 模型不应同时继承 Base 和 BaseModel，选择其一或使用 Pydantic v2 的模型验证")
                elif "exception_handler" in e:
                    fix_suggestions.append("异常处理器应在 app 级别注册: `app.exception_handler(Exception)(handler)`，而非 router 级别")
            if fix_suggestions:
                context_parts.append("**修复建议**:\n" + "\n".join(f"- {s}" for s in fix_suggestions))

        if errors.get("frontend_errors"):
            frontend_errs = errors["frontend_errors"]
            context_parts.append("## 前端错误\n" + "\n".join(f"- {e}" for e in frontend_errs))
            fix_suggestions = []
            for e in frontend_errs:
                if "JS 语法错误" in e:
                    fix_suggestions.append("检查 JavaScript 语法：分号、括号匹配、变量声明等")
                elif "HTML 结构" in e:
                    fix_suggestions.append("检查 HTML 标签是否正确闭合，确保 html/head/body 标签完整")
                elif "CSS 语法" in e:
                    fix_suggestions.append("检查 CSS 大括号匹配、选择器语法、属性值格式")
            if fix_suggestions:
                context_parts.append("**修复建议**:\n" + "\n".join(f"- {s}" for s in fix_suggestions))

        if errors.get("cross_file_errors"):
            cross_errs = errors["cross_file_errors"]
            context_parts.append("## 跨文件一致性错误\n" + "\n".join(f"- {e}" for e in cross_errs))
            context_parts.append("**修复建议**: 确保导入的模块存在且导出了所需的符号，检查文件路径是否正确")

        if attempt > 0:
            context_parts.append(f"\n## 注意\n此前已尝试修复 {attempt} 次但未通过验证，请检查是否有遗漏的错误或逻辑问题。")

        return "\n".join(context_parts) if context_parts else "未知验证错误"

    def _extract_error_messages(self, errors: Dict) -> List[str]:
        """提取所有错误信息"""
        msgs = []
        for key in ["syntax_errors", "import_errors", "dependency_errors", "runtime_errors", "api_errors", "frontend_errors", "cross_file_errors"]:
            msgs.extend(errors.get(key, []))
        return msgs

    async def fix_from_test_logs(
        self,
        test_runner: TestRunner,
        failed_tests: List[str],
        test_logs: str,
        project_path: Path,
        callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """根据测试日志自动修复失败的测试用例"""
        if not failed_tests:
            return {"success": True, "message": "没有失败的测试"}

        logger.info(f"开始测试失败自动修复 | 失败用例: {len(failed_tests)}")
        recovery_results = {"total": len(failed_tests), "fixed": 0, "failures": []}

        # 按失败用例名推断可能对应的源文件
        # e.g., test_user_service.py -> app/services/user_service.py

        for attempt in range(self.MAX_FIX_ATTEMPTS):
            if not recovery_results["failures"]:
                break

            current_model = self.MODEL_FALLBACK_CHAIN[attempt % len(self.MODEL_FALLBACK_CHAIN)]
            fix_model_config = LayeredModelRouter.get_model_config(current_model, task_type="fix")

            system_prompt = """你是一位资深测试与修复专家。
你的任务是根据 pytest 失败日志修复源代码中的 Bug。
请遵循以下原则：
1. 精准定位导致失败的源代码文件
2. 仅修复 Bug，不要修改无关逻辑
3. 确保修复后测试能够通过
4. 返回完整修复后的代码，不要省略任何部分"""

            failed_details = "\n".join(recovery_results["failures"])
            fix_prompt = f"""以下测试用例失败，请修复对应的源代码：

【失败日志】
{test_logs}

【具体失败用例】
{failed_details}

【修复要求】
1. 针对每个失败的测试用例，推断其对应的源代码文件并进行修复
2. 返回格式为 JSON 列表，每个元素包含:
   - "file_path": 源代码相对路径
   - "content": 修复后的完整代码
3. 确保代码能通过 pytest 验证
4. {"（这是最后一次尝试，请使用不同的修复策略）" if attempt == self.MAX_FIX_ATTEMPTS - 1 else ""}
"""

            async with self._semaphore:
                try:
                    response = await call_llm(
                        model=current_model,
                        prompt=f"【USER】\n{fix_prompt}",
                        stream=False,
                        max_tokens=fix_model_config["max_tokens"],
                        thinking_budget=fix_model_config["thinking_budget"],
                        temperature=fix_model_config["temperature"],
                        system_prompt=system_prompt
                    )

                    raw = response.get("choices", [{}])[0].get("message", {}).get("content", "")
                    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', raw)
                    if json_match:
                        raw = json_match.group(1)

                    fixes = json.loads(raw)
                    if not isinstance(fixes, list):
                        fixes = [fixes]

                    # 应用修复
                    for fix in fixes:
                        fp = fix.get("file_path")
                        content = fix.get("content")
                        if not fp or not content:
                            continue

                        # 清理代码块
                        code_match = re.search(r'```(?:\w+)?\s*(.*?)\s*```', content, re.DOTALL)
                        if code_match:
                            content = code_match.group(1).strip()

                        target = project_path / fp
                        if target.exists():
                            target.write_text(content, encoding='utf-8')
                            logger.info(f"已应用测试修复: {fp}")
                            self.fix_history.append(FixAttempt(
                                file_path=str(target),
                                error_type="test_failure",
                                error_message="pytest failed",
                                fix_applied=True,
                                attempts=attempt + 1,
                                model_used=current_model
                            ))

                    # 重新运行测试验证
                    logger.info(f"修复尝试 {attempt + 1} 完成，重新运行测试...")
                    result = await test_runner.run_tests()
                    if result.success:
                        recovery_results["success"] = True
                        recovery_results["message"] = f"修复成功 (尝试 {attempt + 1} 次)"
                        return recovery_results
                    else:
                        recovery_results["failures"] = result.failed_tests
                        test_logs = result.logs

                except Exception as e:
                    logger.error(f"测试修复尝试 {attempt + 1} 失败: {e}")

        recovery_results["success"] = False
        recovery_results["message"] = f"修复失败，已尝试 {self.MAX_FIX_ATTEMPTS} 次"
        return recovery_results

    def _infer_source_files(self, failed_tests: List[str], project_path: Path) -> List[Path]:
        """根据测试文件名推断对应的源代码文件"""
        # e.g., test_user_service -> user_service.py
        inferred = []
        for t in failed_tests:
            # 清理测试名前缀
            clean = t.replace("test_", "").split("::")[0]
            # 搜索项目中的匹配文件
            for f in project_path.rglob(f"*{clean}.py"):
                if "test" not in f.name and "__pycache__" not in str(f):
                    inferred.append(f)
        return list(set(inferred))
