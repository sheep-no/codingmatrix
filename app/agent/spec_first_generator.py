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
import asyncio
import logging
from typing import Optional, Dict, Any, Callable

from app.utils import call_llm
from app.agent.shared_context import SharedContext

logger = logging.getLogger(__name__)


class SpecFirstGenerator:
    """
    规范先行生成器

    生成顺序：
    1. OpenAPI 接口规范（定义所有 API 端点、请求/响应格式）
    2. 类型定义（语言原生类型系统）
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

    TYPES_SYSTEM_PROMPT = """你是一位资深类型系统设计师。

你的任务：根据 OpenAPI 规范，生成对应的类型定义文件。

要求：
1. 为每个 API schema 生成类型定义
2. 包含字段验证（必填/可选、长度限制、范围限制等）
3. 包含注释说明
4. 使用语言原生的类型系统

输出要求：
- 只返回代码
- 不要返回 markdown 代码块标记
- 包含所有必要的 import/using/include"""

    DB_SCHEMA_SYSTEM_PROMPT = """你是一位资深数据库设计师。

你的任务：根据项目需求和 OpenAPI 规范，生成数据库 Schema 定义。

要求：
1. 为每个实体生成数据库模型定义
2. 包含主键、外键、索引
3. 包含字段类型和约束
4. 定义表之间的关系
5. 管理公共字段（created_at, updated_at 等）

输出要求：
- 只返回代码
- 不要返回 markdown 代码块标记
- 包含所有必要的 import/using/include"""

    CONFIG_SYSTEM_PROMPT = """你是一位资深配置管理专家。

你的任务：生成项目的配置规范，包括环境变量定义和配置文件结构。

要求：
1. 定义所有必要的环境变量
2. 每个变量包含：名称、类型、默认值、说明
3. 生成配置文件模板（.env.example）
4. 生成配置加载代码

输出要求：
- 返回配置类代码
- 同时返回 .env.example 内容（用分隔符分开）"""

    def __init__(self, context: SharedContext, language: str = "python"):
        self.context = context
        self.language = language
        from app.agent.models import DEFAULT_ARCHITECT_MODEL
        self.architect_model = context.model_assignment.get("architect_model", DEFAULT_ARCHITECT_MODEL) if context.model_assignment else DEFAULT_ARCHITECT_MODEL
        from app.agent.orchestrator import LayeredModelRouter
        self.model_config = LayeredModelRouter.get_model_config(self.architect_model)
        self._pending_tasks = set()

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

        # 根据语言选择类型生成策略
        lang = self.language
        if lang == "python":
            type_hint = "生成 Python Pydantic BaseModel 类，使用 typing 模块的 Optional, List, Dict 等"
        elif lang == "javascript":
            type_hint = "生成 TypeScript interface 和 type 定义"
        elif lang == "go":
            type_hint = "生成 Go struct 定义，包含 json tag"
        elif lang == "java":
            type_hint = "生成 Java POJO 类，使用 Jakarta Validation 注解"
        elif lang == "rust":
            type_hint = "生成 Rust struct 和 enum 定义，使用 serde 注解"
        else:
            type_hint = f"生成 {lang} 的类型定义"

        prompt = f"""请根据以下 OpenAPI 规范生成类型定义：

OpenAPI 规范：
```json
{json.dumps(openapi_spec, ensure_ascii=False, indent=2)[:3000]}
```

{type_hint}。"""

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

        # 根据语言选择 ORM 策略
        lang = self.language
        if lang == "python":
            db_hint = "生成 SQLAlchemy Model 定义，包含主键、外键、索引和 relationship"
        elif lang == "javascript":
            db_hint = "生成 Prisma Schema 或 TypeORM Entity 定义"
        elif lang == "go":
            db_hint = "生成 GORM Model 定义，包含 gorm tag"
        elif lang == "java":
            db_hint = "生成 JPA Entity 定义，使用 Jakarta Persistence 注解"
        elif lang == "rust":
            db_hint = "生成 Diesel 或 SeaORM Model 定义"
        else:
            db_hint = f"生成 {lang} 的数据库模型定义"

        prompt = f"""请为以下项目生成数据库模型定义：

需求：{requirement}

"""
        if openapi_spec:
            prompt += f"""OpenAPI 规范中的数据结构：
```json
{json.dumps(openapi_spec.get('components', {}).get('schemas', {}), ensure_ascii=False, indent=2)[:2000]}
```
"""
        prompt += f"""
{db_hint}。"""

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
        # 根据语言选择配置策略
        lang = self.language
        if lang == "python":
            config_hint = "使用 pydantic-settings 的配置类，生成 .env.example"
        elif lang == "javascript":
            config_hint = "生成 dotenv 配置和 .env.example"
        elif lang == "go":
            config_hint = "生成 Viper 配置结构和 .env.example"
        elif lang == "java":
            config_hint = "生成 application.yml 和 Spring Boot 配置类"
        elif lang == "rust":
            config_hint = "生成 config crate 配置和 .env.example"
        else:
            config_hint = f"生成 {lang} 的配置管理代码和 .env.example"

        prompt = f"""请为以下项目生成配置管理代码：

需求：{requirement}
技术栈：{', '.join(complexity.get('key_technologies', []))}

{config_hint}。"""

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
        """从文本中提取 JSON（委托给 json_parser）"""
        from app.agent.json_parser import safe_parse_json
        try:
            return safe_parse_json(text)
        except ValueError:
            return None

    def _clean_code_block(self, content: str) -> str:
        """清理代码块标记"""
        from app.agent.utils import clean_code_block
        return clean_code_block(content)

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
            result = callback(json.dumps(progress, ensure_ascii=False))
            if asyncio.iscoroutine(result):
                task = asyncio.create_task(result)
                self._pending_tasks.add(task)
                task.add_done_callback(self._pending_tasks.discard)
        except Exception as e:
            logger.error(f"Spec 进度回调失败: {e}")

    @staticmethod
    def get_spec_budget(context_length: int) -> int:
        """根据模型上下文窗口计算规范注入预算（字符/每规范）

        小上下文 (<=32K)：2000 字符
        中上下文 (32K-64K)：3500 字符
        大上下文 (>64K)：5000 字符
        """
        if context_length <= 32768:
            return 2000
        elif context_length <= 65536:
            return 3500
        else:
            return 5000

    def get_spec_context_for_file(self, file_path: str, file_type: str, max_chars_per_spec: int = 0) -> str:
        """
        根据文件类型获取相关的规范上下文

        用于注入到代码生成的 prompt 中，让代码生成器知道相关规范
        max_chars_per_spec=0 时使用默认值 2000
        """
        if max_chars_per_spec <= 0:
            max_chars_per_spec = 2000

        parts = []

        if file_type in ("api", "view", "controller", "router"):
            # API 相关文件需要 OpenAPI 规范
            openapi = self.context.get_spec("openapi")
            if openapi:
                parts.append("## OpenAPI 接口规范\n```json\n" + json.dumps(openapi, ensure_ascii=False, indent=2)[:max_chars_per_spec] + "\n```")

        if file_type in ("model", "entity", "dto"):
            # 模型相关文件需要类型定义
            types = self.context.get_spec("types")
            if types:
                parts.append("## 类型定义\n```python\n" + types.get("code", "")[:max_chars_per_spec] + "\n```")

        if file_type in ("model", "repository", "dao"):
            # 数据访问相关文件需要数据库 Schema
            db_schema = self.context.get_spec("db_schema")
            if db_schema:
                parts.append("## 数据库 Schema\n```python\n" + db_schema.get("code", "")[:max_chars_per_spec] + "\n```")

        if file_type in ("config", "settings"):
            config = self.context.get_spec("config")
            if config:
                parts.append("## 配置规范\n```python\n" + config.get("code", "")[:max_chars_per_spec] + "\n```")

        return "\n\n".join(parts) if parts else ""
