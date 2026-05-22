"""
SpecFirstGenerator - 规范先行生成器

核心理念：在生成任何代码之前，先生成规范（Specs），
包括：OpenAPI 接口定义、类型定义、数据库 Schema。

这样做的好处：
1. 小模型在明确的规范下生成代码质量更高
2. 减少幻觉和错误引用
3. 后续代码生成可以直接引用规范，减少上下文压力
4. 规范可以作为验证标准
"""

import json
import re
import logging
from typing import Optional, Dict, Any, List, Tuple, Callable

from app.utils import call_llm
from app.agent.shared_context import SharedContext

logger = logging.getLogger(__name__)


class SpecFirstGenerator:
    """
    规范先行生成器

    生成顺序：
    1. OpenAPI 接口规范（定义所有 API 端点、请求/响应格式）
    2. 类型定义（Pydantic models、TypeScript interfaces）
    3. 数据库 Schema（表结构、关系、索引）
    4. 配置规范（环境变量、配置文件结构）
    """

    # ==================== System Prompts ====================

    OPENAPI_SYSTEM_PROMPT = """你是一位资深 API 架构师，擅长使用 OpenAPI 3.0 规范设计 RESTful API。

你的任务：根据项目需求，生成完整的 OpenAPI 3.0 规范。

要求：
1. 定义所有 API 端点（paths）
2. 定义所有数据模型（schemas/components）
3. 每个端点包含：method、path、summary、requestBody、responses
4. 使用正确的 HTTP 状态码
5. 包含认证方案（如需要）
6. 输出纯 JSON 格式

输出格式（JSON）：
{
  "openapi": "3.0.0",
  "info": {"title": "...", "version": "..."},
  "paths": {
    "/api/resource": {
      "get": {"summary": "...", "responses": {"200": {...}}},
      "post": {"summary": "...", "requestBody": {...}, "responses": {"201": {...}}}
    }
  },
  "components": {
    "schemas": {
      "Resource": {"type": "object", "properties": {...}}
    }
  }
}"""

    TYPES_SYSTEM_PROMPT = """你是一位资深类型系统设计师，擅长 Pydantic 和 TypeScript 类型定义。

你的任务：根据 OpenAPI 规范，生成对应的类型定义文件。

要求：
1. 为每个 API schema 生成 Pydantic BaseModel
2. 包含字段验证（max_length, gt, ge, regex 等）
3. 包含 docstring 说明
4. 使用 typing 模块的 Optional, List, Dict 等
5. 输出 Python 代码

输出要求：
- 只返回 Python 代码
- 不要返回 markdown 代码块标记
- 包含所有必要的 import"""

    DB_SCHEMA_SYSTEM_PROMPT = """你是一位资深数据库设计师，擅长 SQLAlchemy ORM 和数据库建模。

你的任务：根据项目需求和 OpenAPI 规范，生成数据库 Schema 定义。

要求：
1. 为每个实体生成 SQLAlchemy Model 类
2. 包含主键、外键、索引
3. 包含字段类型和约束
4. 定义表之间的关系（relationship）
5. 使用 Mixin 类管理公共字段（created_at, updated_at）
6. 输出 Python 代码

输出要求：
- 只返回 Python 代码
- 不要返回 markdown 代码块标记
- 包含所有必要的 import"""

    CONFIG_SYSTEM_PROMPT = """你是一位资深配置管理专家。

你的任务：生成项目的配置规范，包括环境变量定义和配置文件结构。

要求：
1. 定义所有必要的环境变量
2. 每个变量包含：名称、类型、默认值、说明
3. 生成配置文件模板（.env.example）
4. 生成配置加载代码（使用 pydantic-settings）
5. 输出 Python 代码和 .env 内容

输出要求：
- 返回 Python 配置类代码
- 同时返回 .env.example 内容（用分隔符分开）"""

    def __init__(self, context: SharedContext):
        self.context = context
        self.architect_model = context.model_assignment.get("architect_model", "THUDM/GLM-Z1-9B-0414") if context.model_assignment else "THUDM/GLM-Z1-9B-0414"
        from app.agent.orchestrator import LayeredModelRouter
        self.model_config = LayeredModelRouter.get_model_config(self.architect_model)

    async def generate_all_specs(
        self,
        requirement: str,
        complexity: Dict[str, Any],
        callback: Optional[Callable] = None
    ) -> bool:
        """
        生成所有规范

        Returns:
            True 如果所有规范都成功生成
        """
        self.context.start_phase("spec_generation")

        # 1. 生成 OpenAPI 规范
        openapi_success = await self._generate_openapi_spec(requirement, complexity)
        if not openapi_success:
            self.context.add_error("OpenAPI 规范生成失败")
            self.context.complete_phase("spec_generation", ["OpenAPI 生成失败"])
            return False

        self._report_progress("openapi_generated", callback)

        # 2. 基于 OpenAPI 生成类型定义（依赖 OpenAPI）
        types_success = await self._generate_types()
        if not types_success:
            self.context.add_warning("类型定义生成失败（依赖 OpenAPI），将使用默认类型")

        self._report_progress("types_generated", callback)

        # 3. 生成数据库 Schema（依赖 OpenAPI）
        db_success = await self._generate_db_schema(requirement, complexity)
        if not db_success:
            self.context.add_warning("数据库 Schema 生成失败（依赖 OpenAPI），将使用默认模型")

        self._report_progress("db_schema_generated", callback)

        # 4. 生成配置规范（独立，不依赖 OpenAPI）
        config_success = await self._generate_config(requirement, complexity)
        if not config_success:
            self.context.add_warning("配置规范生成失败，将使用默认配置")

        self._report_progress("config_generated", callback)

        self.context.complete_phase("spec_generation")
        return openapi_success

    async def _generate_openapi_spec(self, requirement: str, complexity: Dict) -> bool:
        """生成 OpenAPI 3.0 规范"""
        prompt = f"""请为以下项目需求生成 OpenAPI 3.0 规范：

需求：{requirement}

项目复杂度：
- 等级：{complexity.get('level', 'unknown')}
- 有前端：{complexity.get('has_frontend', False)}
- 有后端：{complexity.get('has_backend', True)}
- 有数据库：{complexity.get('has_database', False)}
- 技术栈：{', '.join(complexity.get('key_technologies', []))}

请生成完整的 OpenAPI 3.0 规范，包含所有 API 端点和数据模型。"""

        try:
            response = await call_llm(
                model=self.architect_model,
                prompt=f"【USER】\n{prompt}",
                stream=False,
                max_tokens=8192,
                thinking_budget=4096,
                temperature=0.5  # 规范生成需要更确定性的输出
            )

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                return False

            # 解析 JSON
            openapi_spec = self._extract_json(content)
            if not openapi_spec:
                logger.warning("OpenAPI 规范解析失败")
                return False

            # 保存到上下文
            self.context.save_spec("openapi", openapi_spec, self.architect_model)
            logger.info(f"OpenAPI 规范生成成功，包含 {len(openapi_spec.get('paths', {}))} 个端点")
            return True

        except Exception as e:
            logger.error(f"OpenAPI 规范生成失败: {e}")
            return False

    async def _generate_types(self) -> bool:
        """基于 OpenAPI 规范生成类型定义"""
        openapi_spec = self.context.get_spec("openapi")
        if not openapi_spec:
            return False

        prompt = f"""请根据以下 OpenAPI 规范生成 Python Pydantic 类型定义：

OpenAPI 规范：
```json
{json.dumps(openapi_spec, ensure_ascii=False, indent=2)[:3000]}
```

请为每个 schema 生成对应的 Pydantic BaseModel 类。"""

        try:
            response = await call_llm(
                model=self.architect_model,
                prompt=f"【SYSTEM】\n{self.TYPES_SYSTEM_PROMPT}\n\n【USER】\n{prompt}",
                stream=False,
                max_tokens=self.model_config["max_tokens"],
                thinking_budget=self.model_config["thinking_budget"],
                temperature=0.6
            )

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                return False

            content = self._clean_code_block(content)

            # 保存到上下文
            self.context.save_spec("types", {"code": content}, self.architect_model)
            logger.info("类型定义生成成功")
            return True

        except Exception as e:
            logger.error(f"类型定义生成失败: {e}")
            return False

    async def _generate_db_schema(self, requirement: str, complexity: Dict) -> bool:
        """生成数据库 Schema"""
        openapi_spec = self.context.get_spec("openapi")

        prompt = f"""请为以下项目生成 SQLAlchemy 数据库模型定义：

需求：{requirement}

"""
        if openapi_spec:
            prompt += f"""OpenAPI 规范中的数据结构：
```json
{json.dumps(openapi_spec.get('components', {}).get('schemas', {}), ensure_ascii=False, indent=2)[:2000]}
```
"""
        prompt += """
请生成完整的 SQLAlchemy Model 定义，包含所有必要的关系和索引。"""

        try:
            response = await call_llm(
                model=self.architect_model,
                prompt=f"【SYSTEM】\n{self.DB_SCHEMA_SYSTEM_PROMPT}\n\n【USER】\n{prompt}",
                stream=False,
                max_tokens=self.model_config["max_tokens"],
                thinking_budget=self.model_config["thinking_budget"],
                temperature=0.6
            )

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                return False

            content = self._clean_code_block(content)

            # 保存到上下文
            self.context.save_spec("db_schema", {"code": content}, self.architect_model)
            logger.info("数据库 Schema 生成成功")
            return True

        except Exception as e:
            logger.error(f"数据库 Schema 生成失败: {e}")
            return False

    async def _generate_config(self, requirement: str, complexity: Dict) -> bool:
        """生成配置规范"""
        prompt = f"""请为以下项目生成配置管理代码：

需求：{requirement}
技术栈：{', '.join(complexity.get('key_technologies', []))}

请生成：
1. 使用 pydantic-settings 的配置类
2. .env.example 文件内容"""

        try:
            response = await call_llm(
                model=self.architect_model,
                prompt=f"【SYSTEM】\n{self.CONFIG_SYSTEM_PROMPT}\n\n【USER】\n{prompt}",
                stream=False,
                max_tokens=self.model_config["max_tokens"],
                thinking_budget=self.model_config["thinking_budget"],
                temperature=0.6
            )

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                return False

            content = self._clean_code_block(content)

            # 保存到上下文
            self.context.save_spec("config", {"code": content}, self.architect_model)
            logger.info("配置规范生成成功")
            return True

        except Exception as e:
            logger.error(f"配置规范生成失败: {e}")
            return False

    # ==================== 辅助方法 ====================

    def _extract_json(self, text: str) -> Optional[Dict]:
        """从文本中提取 JSON"""
        # 尝试从代码块中提取
        match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 尝试找到第一个 { 和最后一个 }
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                try:
                    return json.loads(text[start:end+1])
                except json.JSONDecodeError:
                    pass

        return None

    def _clean_code_block(self, content: str) -> str:
        """清理代码块标记"""
        pattern = r'```(?:\w+)?\s*(.*?)\s*```'
        match = re.search(pattern, content, re.DOTALL)
        if match:
            return match.group(1).strip()
        return content.strip()

    def _report_progress(self, step: str, callback: Optional[Callable]):
        """报告进度"""
        if not callback:
            return
        progress = {
            "type": "spec_progress",
            "step": step,
            "specs_generated": list(self.context.specs.keys())
        }
        try:
            callback(json.dumps(progress, ensure_ascii=False))
        except Exception as e:
            logger.error(f"Spec 进度回调失败: {e}")

    def get_spec_context_for_file(self, file_path: str, file_type: str) -> str:
        """
        根据文件类型获取相关的规范上下文

        用于注入到代码生成的 prompt 中，让代码生成器知道相关规范
        """
        parts = []

        if file_type in ("api", "view", "controller", "router"):
            # API 相关文件需要 OpenAPI 规范
            openapi = self.context.get_spec("openapi")
            if openapi:
                parts.append("## OpenAPI 接口规范\n```json\n" + json.dumps(openapi, ensure_ascii=False, indent=2)[:2000] + "\n```")

        if file_type in ("model", "entity", "dto"):
            # 模型相关文件需要类型定义
            types = self.context.get_spec("types")
            if types:
                parts.append("## 类型定义\n```python\n" + types.get("code", "")[:2000] + "\n```")

        if file_type in ("model", "repository", "dao"):
            # 数据访问相关文件需要数据库 Schema
            db_schema = self.context.get_spec("db_schema")
            if db_schema:
                parts.append("## 数据库 Schema\n```python\n" + db_schema.get("code", "")[:2000] + "\n```")

        if file_type in ("config", "settings"):
            config = self.context.get_spec("config")
            if config:
                parts.append("## 配置规范\n```python\n" + config.get("code", "")[:2000] + "\n```")

        return "\n\n".join(parts) if parts else ""
