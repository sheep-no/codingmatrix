"""
专业角色 - 架构师、前端工程师、后端工程师、代码审查员

负责 LLM 调用封装和具体角色的职责实现。
"""

import re
import json
import time
import logging
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
import asyncio

from app.utils.AiCodeUtil import call_siliconflow
from app.agent.complexity import ComplexityAnalysis
from app.agent.dynamic_model_router import get_dynamic_router, LayeredModelRouter
from app.utils.prompt_loader import (
    load_architect_prompt,
    load_frontend_engineer_prompt,
    load_backend_engineer_prompt,
    load_code_reviewer_prompt,
)

logger = logging.getLogger(__name__)

# 从 orchestrator 获取的并发限制常量
MAX_CONCURRENT_LLM_CALLS = 4


class Specialist:
    """专业角色基类"""

    _semaphore: Optional[asyncio.Semaphore] = None

    @classmethod
    def set_semaphore(cls, sem: asyncio.Semaphore):
        cls._semaphore = sem

    def __init__(self, role_name: str, model_name: str, task_type: str = "generate"):
        self.role_name = role_name
        self.model_name = model_name
        self.task_type = task_type
        self.model_config = LayeredModelRouter.get_model_config(model_name, task_type=task_type)

    async def call_llm(self, prompt: str, system_prompt: str = "") -> str:
        """调用 LLM（带并发限制和动态指标记录）"""
        start_time = time.time()
        await (await get_dynamic_router()).start_call(self.model_name)

        try:
            if self._semaphore:
                async with self._semaphore:
                    response = await call_siliconflow(
                        prompt=prompt,
                        model=self.model_name,
                        stream=False,
                        max_tokens=self.model_config["max_tokens"],
                        thinking_budget=self.model_config["thinking_budget"],
                        temperature=self.model_config["temperature"],
                        system_prompt=system_prompt
                    )
            else:
                response = await call_siliconflow(
                    prompt=prompt,
                    model=self.model_name,
                    stream=False,
                    max_tokens=self.model_config["max_tokens"],
                    thinking_budget=self.model_config["thinking_budget"],
                    temperature=self.model_config["temperature"],
                    system_prompt=system_prompt
                )
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            latency_ms = (time.time() - start_time) * 1000
            await (await get_dynamic_router()).record_call(self.model_name, success=True, latency_ms=latency_ms)
            return content
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            await (await get_dynamic_router()).record_call(self.model_name, success=False, latency_ms=latency_ms, error=str(e))
            logger.error(f"{self.role_name} 调用 LLM 失败: {e}")
            return ""


class Architect(Specialist):
    """架构师 - 负责技术选型和整体架构设计"""

    @property
    def SYSTEM_PROMPT(self) -> str:
        prompt = load_architect_prompt()
        if prompt is None:
            logger.error("架构师提示词加载失败，使用兜底提示词")
            return self._fallback_prompt()
        return prompt

    def _fallback_prompt(self) -> str:
        return """你是一位世界级首席软件架构师，精通几乎所有编程语言和技术栈。
你的职责：分析需求、设计架构、定义 API 和数据库 Schema。
输出格式要求：必须只输出 JSON 格式，不要包含任何解释文字。"""

    async def design_architecture(self, requirement: str, complexity: ComplexityAnalysis) -> Dict:
        """设计项目架构"""
        prompt = f"""请为以下需求设计项目架构：

需求：{requirement}

复杂度分析：
- 等级：{complexity.level.value}
- 预估文件数：{complexity.estimated_files}
- 有前端：{complexity.has_frontend}
- 有后端：{complexity.has_backend}
- 有数据库：{complexity.has_database}
- 技术栈：{', '.join(complexity.key_technologies)}
- 风险因素：{', '.join(complexity.risk_factors)}

请输出完整的架构设计，必须包含 api_spec（后端接口定义）和 db_schema（数据库表结构）。

输出格式要求：
- 只输出 JSON 格式
- 不要包含任何解释文字
- 必须包含以下字段：project_type, frontend_structure, backend_structure, api_spec, db_schema, file_plan"""

        response = await self.call_llm(prompt, self.SYSTEM_PROMPT)

        # 解析 JSON
        try:
            if not response or not response.strip():
                logger.warning("架构师输出为空，返回默认架构")
                return self._get_default_architecture(complexity)

            architecture = self._safe_parse_json(response)
        except ValueError:
            logger.warning(f"架构师输出解析失败，尝试 LLM 辅助提取")
            architecture = await self._extract_json_with_llm(response, complexity)
            if not architecture:
                logger.warning("LLM 辅助提取失败，返回默认架构")
                return self._get_default_architecture(complexity)

        if architecture:
            # 验证并增强 api_spec
            if complexity.has_backend:
                architecture = self._validate_and_enhance_api_spec(architecture, complexity)

            # 验证并增强 db_schema
            if complexity.has_database:
                architecture = self._validate_and_enhance_db_schema(architecture, complexity)

            return architecture
        else:
            return self._get_default_architecture(complexity)
    
    async def _extract_json_with_llm(self, raw_text: str, complexity: ComplexityAnalysis) -> Optional[Dict]:
        """使用 LLM 从非标准输出中提取 JSON"""
        extract_prompt = f"""请将以下文本转换为标准 JSON 格式：

原始文本：
{raw_text[:3000]}

要求：
1. 只输出 JSON，不要包含其他内容
2. 确保 JSON 格式正确
3. 必须包含：project_type, frontend_structure, backend_structure, api_spec, db_schema, file_plan
4. 修复以下常见问题：
   - 值中错误的反斜杠引号："INTEGER\\" 应为 "INTEGER"
   - dependencies 中的数组格式应为对象或数组
   - 文件路径中的空格应为斜杠：src store/ 应为 src/store/"""

        try:
            response = await call_siliconflow(
                prompt=f"【USER】\n{extract_prompt}",
                model="Qwen/Qwen2.5-7B-Instruct",
                stream=False,
                max_tokens=4096,
                temperature=0.3
            )
            
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            return self._safe_parse_json(content)
        except Exception as e:
            logger.error(f"LLM 辅助提取 JSON 失败: {e}")
            return None

    def _validate_and_enhance_api_spec(self, architecture: Dict, complexity: ComplexityAnalysis) -> Dict:
        """验证并增强 API 规范"""
        api_spec = architecture.get("api_spec", {})

        # 如果没有 api_spec，生成基本的
        if not api_spec or "paths" not in api_spec:
            logger.warning("架构师未输出 api_spec，生成基本规范")
            api_spec = {
                "paths": {
                    "/api/v1/health": {
                        "get": {"summary": "健康检查", "responses": {"200": {"description": "OK"}}}
                    }
                }
            }

        # 验证路径格式
        paths = api_spec.get("paths", {})
        for path, methods in paths.items():
            if not path.startswith("/"):
                paths[f"/{path}"] = methods
                del paths[path]

        architecture["api_spec"] = api_spec
        return architecture

    def _validate_and_enhance_db_schema(self, architecture: Dict, complexity: ComplexityAnalysis) -> Dict:
        """验证并增强数据库 Schema"""
        db_schema = architecture.get("db_schema", {})

        # 如果没有 db_schema，生成基本的
        if not db_schema:
            logger.warning("架构师未输出 db_schema，生成基本规范")
            db_schema = {
                "users": {
                    "columns": {
                        "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
                        "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                    }
                }
            }

        # 确保每个表都有 id 和 created_at
        for table, schema in db_schema.items():
            columns = schema.get("columns", {})
            if "id" not in columns:
                columns["id"] = "INTEGER PRIMARY KEY AUTOINCREMENT"
            if "created_at" not in columns:
                columns["created_at"] = "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"

        architecture["db_schema"] = db_schema
        return architecture

    def _safe_parse_json(self, text: str) -> Dict:
        """安全解析 JSON，处理各种格式问题"""
        text = text.strip()

        # 1. 移除 thinking tags（深度思考模型输出）
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

        # 2. 提取 ```json 或 ``` 代码块
        json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            text = json_match.group(1).strip()

        # 3. 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 4. 查找第一个 { 和最后一个 } 之间的内容
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            json_str = text[start:end + 1]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass

            # 5. 尝试修复常见 JSON 问题
            fixed = self._fix_common_json_issues(json_str)
            if fixed:
                return fixed

        # 6. 尝试更激进的修复（处理嵌套对象、多 JSON 块）
        fixed = self._fix_complex_json_issues(text)
        if fixed:
            return fixed

        # 7. 最终兜底：逐行修复 + 控制字符清理
        fixed = self._fix_ultimate_json(text)
        if fixed:
            return fixed

        # 8. 记录解析失败的文本到文件，便于调试
        import os
        debug_file = "/tmp/architect_json_debug.txt"
        try:
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(f"=== JSON 解析失败 ===\n")
                f.write(f"时间: {os.popen('date').read().strip()}\n")
                f.write(f"文本长度: {len(text)}\n")
                f.write(f"完整文本:\n{text}\n")
                f.write(f"\n=== 结束 ===\n")
            logger.warning(f"JSON 解析失败，完整输出已保存到 {debug_file}")
        except Exception as e:
            logger.error(f"保存调试文件失败: {e}")

        raise ValueError("无法解析 JSON")

    def _fix_common_json_issues(self, text: str) -> Optional[Dict]:
        """修复常见 JSON 格式问题"""
        if not text or not text.strip():
            return None

        # 确保只处理 JSON 范围
        start = text.find('{')
        end = text.rfind('}')
        if start == -1 or end == -1:
            return None

        json_str = text[start:end + 1]

        # 1. 移除 // 行注释（在字符串外）
        json_str = self._remove_line_comments(json_str)

        # 2. 移除 /* */ 块注释
        json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)

        # 3. 移除尾随逗号
        json_str = re.sub(r',\s*([}\]])', r'\1', json_str)

        # 4. 修复值末尾的 \ 转义引号："INTEGER\" -> "INTEGER"
        json_str = re.sub(r'"\s*:\s*"([^"\\]*?)\\+"\s*([,}\n\r])', r'": "\1"\2', json_str)

        # 5. 修复键名中的错误转义："key\": -> "key":
        json_str = re.sub(r'"([^"\\]*?)\\+"\s*:', r'"\1":', json_str)

        # 6. 修复依赖中的数组格式：{ "vue@3.2.0", } -> ["vue@3.2.0"]
        def fix_bare_values(match):
            key = match.group(1)
            items = match.group(2)
            values = re.findall(r'"([^"]+)"', items)
            if values:
                return f'"{key}": {json.dumps(values)}'
            return match.group(0)

        json_str = re.sub(r'"(\w+)":\s*\{\s*((?:"[^"]+"\s*,?\s*)+)\}', fix_bare_values, json_str)

        # 7. 修复连续逗号
        json_str = re.sub(r',\s*,+', ',', json_str)

        # 8. 修复空数组元素 [,,] -> [] 和空对象键值 {,,} -> {}
        json_str = re.sub(r'\[\s*,+\s*\]', '[]', json_str)
        json_str = re.sub(r'\{\s*,+\s*\}', '{}', json_str)

        # 9. 修复缺少逗号：在 } 或 ] 后紧跟 " 或 { 的情况
        json_str = re.sub(r'([}\]])\s*"', r'\1, "', json_str)
        json_str = re.sub(r'([}\]])\s*{', r'\1, {', json_str)

        # 10. 清理控制字符（保留 \n \r \t）
        json_str = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', json_str)

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return None

    def _fix_complex_json_issues(self, text: str) -> Optional[Dict]:
        """修复复杂的 JSON 格式问题"""
        candidates = []

        depth = 0
        start_idx = None
        in_string = False
        escape_next = False
        for i, char in enumerate(text):
            if escape_next:
                escape_next = False
                continue
            if char == '\\' and in_string:
                escape_next = True
                continue
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == '{':
                if depth == 0:
                    start_idx = i
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0 and start_idx is not None:
                    candidates.append(text[start_idx:i+1])
                    start_idx = None

        for candidate in candidates:
            # 应用全部修复
            cleaned = self._remove_line_comments(candidate)
            cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
            cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)
            cleaned = re.sub(r',\s*,+', ',', cleaned)
            cleaned = re.sub(r'"\s*:\s*"([^"\\]*?)\\+"\s*([,}\n\r])', r'": "\1"\2', cleaned)
            cleaned = re.sub(r'"([^"\\]*?)\\+"\s*:', r'"\1":', cleaned)
            cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', cleaned)

            # 修复单引号
            cleaned = self._fix_single_quotes(cleaned)

            # 修复键名未加引号
            cleaned = re.sub(r'(?<=[{,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'"\1":', cleaned)

            try:
                result = json.loads(cleaned)
                if isinstance(result, dict) and len(result) > 0:
                    return result
            except json.JSONDecodeError:
                continue

        return None

    def _fix_ultimate_json(self, text: str) -> Optional[Dict]:
        """最终兜底修复：逐行处理 + 极端情况"""
        start = text.find('{')
        end = text.rfind('}')
        if start == -1 or end == -1:
            return None

        json_str = text[start:end + 1]

        # 1. 移除所有注释
        json_str = self._remove_line_comments(json_str)
        json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)

        # 2. 单引号替换为双引号
        json_str = self._fix_single_quotes(json_str)

        # 3. 修复键名未加引号
        json_str = re.sub(r'(?<=[{,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'"\1":', json_str)

        # 4. 修复裸值（无引号的值）
        json_str = re.sub(r':\s*([a-zA-Z_][a-zA-Z0-9_-]*)\s*([,}\]])', r': "\1"\2', json_str)

        # 5. 修复尾随逗号
        json_str = re.sub(r',\s*([}\]])', r'\1', json_str)

        # 6. 修复连续逗号
        json_str = re.sub(r',\s*,+', ',', json_str)

        # 7. 修复空数组元素 [,,] -> [] 和空对象键值 {,,} -> {}
        json_str = re.sub(r'\[\s*,+\s*\]', '[]', json_str)
        json_str = re.sub(r'\{\s*,+\s*\}', '{}', json_str)

        # 8. 修复缺少逗号
        json_str = re.sub(r'([}\]])\s*"', r'\1, "', json_str)
        json_str = re.sub(r'([}\]])\s*{', r'\1, {', json_str)
        json_str = re.sub(r'("\S*")\s*"', r'\1, "', json_str)

        # 8. 处理未转义的换行符（在字符串内）
        json_str = self._fix_unescaped_newlines(json_str)

        # 9. 清理控制字符
        json_str = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', json_str)

        # 10. 修复错误的反斜杠引号
        json_str = re.sub(r'\\+"(?=[\s,}\]])', '"', json_str)

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return None

    def _remove_line_comments(self, text: str) -> str:
        """移除 // 行注释，但保留字符串内的 //"""
        result = []
        in_string = False
        escape_next = False
        i = 0
        while i < len(text):
            char = text[i]
            if escape_next:
                result.append(char)
                escape_next = False
                i += 1
                continue
            if char == '\\' and in_string:
                escape_next = True
                result.append(char)
                i += 1
                continue
            if char == '"':
                in_string = not in_string
                result.append(char)
                i += 1
                continue
            if not in_string and i + 1 < len(text) and text[i:i+2] == '//':
                # 跳过到行尾
                while i < len(text) and text[i] != '\n':
                    i += 1
                continue
            result.append(char)
            i += 1
        return ''.join(result)

    def _fix_single_quotes(self, text: str) -> str:
        """将单引号替换为双引号（仅在 JSON 键值对中）"""
        result = []
        in_double_quote = False
        in_single_quote = False
        escape_next = False
        i = 0
        while i < len(text):
            char = text[i]
            if escape_next:
                result.append(char)
                escape_next = False
                i += 1
                continue
            if char == '\\' and (in_double_quote or in_single_quote):
                escape_next = True
                result.append(char)
                i += 1
                continue
            if char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
                result.append(char)
                i += 1
                continue
            if char == "'" and not in_double_quote:
                if not in_single_quote:
                    # 检查是否是键值对的开始
                    # 向前看：前面应该是 { 或 , 或 :
                    prev_text = ''.join(result).rstrip()
                    if prev_text and prev_text[-1] in '{:,':
                        result.append('"')
                        in_single_quote = True
                        i += 1
                        continue
                    else:
                        result.append(char)
                        i += 1
                        continue
                else:
                    # 结束单引号
                    # 向后看：后面应该是 : 或 , 或 } 或 ]
                    next_text = text[i+1:].lstrip()
                    if next_text and next_text[0] in ':,}]':
                        result.append('"')
                        in_single_quote = False
                        i += 1
                        continue
                    else:
                        result.append(char)
                        i += 1
                        continue
            result.append(char)
            i += 1
        return ''.join(result)

    def _fix_unescaped_newlines(self, text: str) -> str:
        """修复字符串内未转义的换行符"""
        result = []
        in_string = False
        escape_next = False
        for char in text:
            if escape_next:
                result.append(char)
                escape_next = False
                continue
            if char == '\\' and in_string:
                escape_next = True
                result.append(char)
                continue
            if char == '"':
                in_string = not in_string
                result.append(char)
                continue
            if in_string and char == '\n':
                result.append('\\n')
                continue
            if in_string and char == '\r':
                result.append('\\r')
                continue
            if in_string and char == '\t':
                result.append('\\t')
                continue
            result.append(char)
        return ''.join(result)

    def _get_default_architecture(self, complexity: ComplexityAnalysis) -> Dict:
        """返回默认架构"""
        file_plan = [
            {"path": "main.py", "description": "主程序入口", "priority": 1},
            {"path": "requirements.txt", "description": "依赖列表", "priority": 2},
            {"path": "README.md", "description": "项目文档", "priority": 3}
        ]

        if complexity.has_frontend:
            file_plan.extend([
                {"path": "index.html", "description": "前端页面", "priority": 4},
                {"path": "static/style.css", "description": "样式表", "priority": 5},
                {"path": "static/app.js", "description": "前端脚本", "priority": 5}
            ])

        if complexity.has_backend:
            file_plan.extend([
                {"path": "app/models.py", "description": "数据模型", "priority": 2},
                {"path": "app/routers.py", "description": "API 路由", "priority": 3},
            ])

        return {
            "project_type": "fullstack" if complexity.has_frontend and complexity.has_backend else ("frontend" if complexity.has_frontend else "backend"),
            "tech_stack": complexity.key_technologies,
            "file_plan": file_plan,
            "dependencies": {"fastapi": ">=0.100.0", "uvicorn": ">=0.23.0"} if complexity.has_backend else {},
            "risks": complexity.risk_factors
        }


class FrontendEngineer(Specialist):
    """前端工程师 - 专注前端代码生成"""

    @property
    def SYSTEM_PROMPT(self) -> str:
        prompt = load_frontend_engineer_prompt()
        if prompt is None:
            logger.error("前端工程师提示词加载失败，使用兜底提示词")
            return self._fallback_prompt()
        return prompt

    def _fallback_prompt(self) -> str:
        return """你是一位世界级前端工程师，精通所有主流前端技术和跨平台开发框架。
你的职责：创建前端文件、编写高质量可维护的代码、实现响应式 UI 和状态管理。
规则：每次只创建一个文件，代码必须完整可运行。"""

    async def generate_file(self, file_path: str, description: str, project_context: Dict) -> str:
        """生成前端文件内容"""
        prompt = f"""请创建以下前端文件：

文件路径：{file_path}
文件描述：{description}
项目上下文：{json.dumps(project_context, ensure_ascii=False, indent=2)}

请返回完整的文件内容，不要省略任何部分。"""

        return await self.call_llm(prompt, self.SYSTEM_PROMPT)


class BackendEngineer(Specialist):
    """后端工程师 - 专注后端代码生成"""

    @property
    def SYSTEM_PROMPT(self) -> str:
        prompt = load_backend_engineer_prompt()
        if prompt is None:
            logger.error("后端工程师提示词加载失败，使用兜底提示词")
            return self._fallback_prompt()
        return prompt

    def _fallback_prompt(self) -> str:
        return """你是一位世界级后端工程师，精通所有主流后端编程语言和框架。
你的职责：创建后端文件、实现 API 端点、数据库模型、业务逻辑、错误处理。
规则：每次只创建一个文件，代码必须完整可运行，包含错误处理和类型注解。"""

    async def generate_file(self, file_path: str, description: str, project_context: Dict) -> str:
        """生成后端文件内容"""
        prompt = f"""请创建以下后端文件：

文件路径：{file_path}
文件描述：{description}
项目上下文：{json.dumps(project_context, ensure_ascii=False, indent=2)}

请返回完整的文件内容，不要省略任何部分。"""

        return await self.call_llm(prompt, self.SYSTEM_PROMPT)


class CodeReviewer(Specialist):
    """代码审查员 - 负责代码质量和安全审查"""

    @property
    def SYSTEM_PROMPT(self) -> str:
        prompt = load_code_reviewer_prompt()
        if prompt is None:
            logger.error("代码审查员提示词加载失败，使用兜底提示词")
            return self._fallback_prompt()
        return prompt

    def _fallback_prompt(self) -> str:
        return """你是一位世界级代码审查专家，精通所有主流编程语言的安全、性能和最佳实践。
审查维度：安全性、正确性、性能、可维护性、最佳实践、版本兼容性。
输出格式：JSON，包含 approved、risk_level、issues、suggestions、needs_fix、version_issues。"""

    # 常见库的版本兼容性规则
    VERSION_RULES = {
        "fastapi": {
            "0.100.0": {"removed": ["Middleware"], "changed": {"OAuth2PasswordBearer": "tokenUrl -> token_url"}},
            "0.90.0": {"added": ["APIRouter.include_router"]},
        },
        "sqlalchemy": {
            "2.0.0": {"removed": ["session.query()"], "changed": {"declarative_base": "DeclarativeBase"}},
        },
        "pydantic": {
            "2.0.0": {"removed": ["Field.regex"], "changed": {"BaseModel.dict": "model_dump"}},
        },
        "passlib": {
            "1.7.0": {"changed": {"import passlib.hash.bcrypt": "from passlib.hash import bcrypt"}},
        },
    }

    async def review_code(self, code: str, file_path: str, context: str = "") -> Dict:
        """审查代码"""
        # 先进行版本兼容性检查
        version_issues = await self._check_version_compatibility(code)

        prompt = f"""请审查以下代码：

文件路径：{file_path}
上下文：{context}

代码：
```
{code}
```

请输出审查结果。"""

        response = await self.call_llm(prompt, self.SYSTEM_PROMPT)

        try:
            json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(1))
            else:
                result = json.loads(response)
        except json.JSONDecodeError:
            result = {
                "approved": True,
                "risk_level": "low",
                "issues": [],
                "suggestions": [],
                "needs_fix": False
            }

        # 合并版本兼容性问题
        if version_issues:
            result["version_issues"] = version_issues
            if not result.get("issues"):
                result["issues"] = []
            result["issues"].extend(version_issues)
            if version_issues and result.get("risk_level") == "low":
                result["risk_level"] = "medium"
            result["needs_fix"] = True

        return result

    async def _check_version_compatibility(self, code: str) -> List[str]:
        """动态检查代码中使用的库版本兼容性"""
        issues = []

        # 尝试获取已安装包的版本
        try:
            import importlib.metadata as metadata
            installed_versions = {}
            for pkg_name in self.VERSION_RULES.keys():
                try:
                    version = metadata.version(pkg_name)
                    installed_versions[pkg_name] = version
                except metadata.PackageNotFoundError:
                    pass
        except ImportError:
            # Python < 3.8 回退
            try:
                import pkg_resources
                installed_versions = {}
                for pkg_name in self.VERSION_RULES.keys():
                    try:
                        version = pkg_resources.get_distribution(pkg_name).version
                        installed_versions[pkg_name] = version
                    except pkg_resources.DistributionNotFound:
                        pass
            except ImportError:
                return issues

        # 检查代码中的导入语句
        import re
        import_matches = re.findall(r'(?:from\s+(\w+)|import\s+(\w+))', code)

        for match in import_matches:
            pkg_name = match[0] or match[1]
            if pkg_name in self.VERSION_RULES and pkg_name in installed_versions:
                installed_version = installed_versions[pkg_name]
                rules = self.VERSION_RULES[pkg_name]

                # 检查是否有已知的兼容性问题
                for rule_version, rule_details in rules.items():
                    if self._version_gte(installed_version, rule_version):
                        if "removed" in rule_details:
                            for removed_api in rule_details["removed"]:
                                if removed_api in code:
                                    issues.append(
                                        f"[{pkg_name} v{installed_version}] API '{removed_api}' 在 v{rule_version}+ 中已移除"
                                    )
                        if "changed" in rule_details:
                            for old_api, new_api in rule_details["changed"].items():
                                if old_api in code:
                                    issues.append(
                                        f"[{pkg_name} v{installed_version}] 建议将 '{old_api}' 改为 '{new_api}'"
                                    )

        return issues

    def _version_gte(self, version: str, target: str) -> bool:
        """比较版本号是否大于等于目标版本"""
        try:
            from packaging.version import Version
            return Version(version) >= Version(target)
        except ImportError:
            # 简单字符串比较（仅适用于语义化版本）
            v1_parts = [int(x) for x in version.split(".")]
            v2_parts = [int(x) for x in target.split(".")]
            return v1_parts >= v2_parts
