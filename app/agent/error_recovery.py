"""
错误恢复循环 - 智能自我修正（验证-修复-重试 + 模型降级）
"""

import re
import json
import asyncio
import logging
from typing import Optional, Dict, List, Callable, Tuple, Any
from dataclasses import dataclass
from pathlib import Path

from app.utils.AiCodeUtil import call_siliconflow
from app.agent.code_validator import CodeValidator
from app.agent.specialists import CodeReviewer
from app.agent.dynamic_model_router import LayeredModelRouter
from app.agent.test_runner import TestRunner, TestResult

# 从 orchestrator 获取的并发限制常量
MAX_CONCURRENT_LLM_CALLS = 4

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

    MAX_FIX_ATTEMPTS = 2  # 智能修正循环最多尝试 2 次（避免过度耗时）

    # 模型降级链：主模型失败时按顺序尝试备选模型
    MODEL_FALLBACK_CHAIN = [
        "Qwen/Qwen2.5-7B-Instruct",  # 代码修复首选
        "Qwen/Qwen3-8B",             # 通用修复
        "Qwen/Qwen3.5-4B",           # 快速降级
    ]

    def __init__(self, validator: CodeValidator, reviewer: CodeReviewer):
        self.validator = validator
        self.reviewer = reviewer
        self.fix_history: List[FixAttempt] = []
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)

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
        """智能修正循环：带模型降级策略"""
        # 确定修复模型链：主模型 -> Qwen2.5-7B -> Qwen3-8B -> Qwen3.5-4B
        models_to_try = [
            backend_model,
            "Qwen/Qwen2.5-7B-Instruct",
            "Qwen/Qwen3-8B",
            "Qwen/Qwen3.5-4B"
        ]
        # 去重并保持顺序
        seen = set()
        unique_models = []
        for m in models_to_try:
            if m not in seen:
                seen.add(m)
                unique_models.append(m)
        models_to_try = unique_models

        for attempt in range(self.MAX_FIX_ATTEMPTS):
            # 选择当前尝试使用的模型（每次尝试使用不同模型）
            current_model = models_to_try[attempt % len(models_to_try)]
            fix_model_config = LayeredModelRouter.get_model_config(current_model, task_type="fix")

            # 构建更精准的修复提示
            error_context = self._build_error_context(errors, content, attempt)

            # 增强修复提示词
            system_prompt = """你是一位资深代码修复专家。你的任务是修复代码中的特定错误。
请遵循以下原则：
1. 仅修复指出的问题，不要修改其他代码
2. 保持原有代码结构和风格
3. 确保修复后的代码语法正确、导入完整
4. 返回完整代码，不要省略任何部分"""

            fix_prompt = f"""请修复以下代码中的错误。

【当前代码】
```
{content}
```

【发现的错误】
{error_context}

【修复要求】
1. 仅修复指出的问题，保持其他代码不变
2. 确保修复后的代码能通过语法、导入和依赖验证
3. 返回完整修复后的代码，不要省略任何部分
4. {"（这是最后一次尝试，请使用不同的修复策略）" if attempt == self.MAX_FIX_ATTEMPTS - 1 else ""}
"""

            async with self._semaphore:
                try:
                    response = await call_siliconflow(
                        prompt=f"【USER】\n{fix_prompt}",
                        model=current_model,
                        stream=False,
                        max_tokens=fix_model_config["max_tokens"],
                        thinking_budget=fix_model_config["thinking_budget"],
                        temperature=fix_model_config["temperature"],
                        system_prompt=system_prompt
                    )

                    fixed_content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
                    code_match = re.search(r'```(?:\w+)?\s*(.*?)\s*```', fixed_content, re.DOTALL)
                    if code_match:
                        fixed_content = code_match.group(1).strip()

                    if not fixed_content:
                        logger.warning(f"修复尝试 {attempt + 1} 返回空内容 (模型: {current_model})")
                        continue

                    # 验证修复后的代码（只验证单个文件）
                    temp_file = file_path.parent / f".temp_fix_{file_path.name}"
                    with open(temp_file, 'w', encoding='utf-8') as f:
                        f.write(fixed_content)

                    validation = await self.validator.validate_single_file(temp_file)
                    if temp_file.exists():
                        temp_file.unlink()

                    if validation["is_valid"]:
                        self.fix_history.append(FixAttempt(
                            file_path=str(file_path),
                            error_type="validation_error",
                            error_message="; ".join(self._extract_error_messages(errors)),
                            fix_applied=True,
                            attempts=attempt + 1,
                            model_used=current_model
                        ))
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
                        logger.warning(f"修复尝试 {attempt + 1} 未通过验证 (模型: {current_model}): {error_msg}")
                        # 更新错误上下文用于下一次尝试
                        errors = validation

                except Exception as e:
                    logger.error(f"修复尝试 {attempt + 1} 失败 (模型: {current_model}): {e}")

        self.fix_history.append(FixAttempt(
            file_path=str(file_path),
            error_type="validation_error",
            error_message="多次修复失败: " + "; ".join(self._extract_error_messages(errors)),
            fix_applied=False,
            attempts=self.MAX_FIX_ATTEMPTS
        ))
        return {"success": False, "fixed_content": content}

    def _build_error_context(self, errors: Dict, content: str, attempt: int) -> str:
        """构建详细的错误上下文（包含修复建议）"""
        context_parts = []

        if errors.get("syntax_errors"):
            context_parts.append(f"## 语法错误\n" + "\n".join(f"- {e}" for e in errors["syntax_errors"]))
            context_parts.append("**修复建议**: 检查括号匹配、缩进、冒号、引号闭合等基本语法")

        if errors.get("import_errors"):
            context_parts.append(f"## 导入错误\n" + "\n".join(f"- {e}" for e in errors["import_errors"]))
            context_parts.append("**修复建议**: 确认模块已安装，检查导入路径是否正确，确保 __init__.py 存在")

        if errors.get("dependency_errors"):
            context_parts.append(f"## 依赖错误\n" + "\n".join(f"- {e}" for e in errors["dependency_errors"]))
            context_parts.append("**修复建议**: 运行 `pip install <包名>` 或在 requirements.txt 中添加缺失的包")

        if errors.get("runtime_errors"):
            runtime_errs = errors["runtime_errors"]
            context_parts.append(f"## 运行时错误\n" + "\n".join(f"- {e}" for e in runtime_errs))
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
            context_parts.append(f"## API 兼容性错误\n" + "\n".join(f"- {e}" for e in api_errs))
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
            context_parts.append(f"## 前端错误\n" + "\n".join(f"- {e}" for e in frontend_errs))
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
            context_parts.append(f"## 跨文件一致性错误\n" + "\n".join(f"- {e}" for e in cross_errs))
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
        source_files = self._infer_source_files(failed_tests, project_path)

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
                    response = await call_siliconflow(
                        prompt=f"【USER】\n{fix_prompt}",
                        model=current_model,
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
