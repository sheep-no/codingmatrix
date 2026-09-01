import logging
import re
from pathlib import Path
from typing import Optional, Dict, List

from app.utils import call_llm
from app.agent.complexity import ComplexityAnalysis
from app.agent.specialist_base import Specialist
from app.utils.prompt_loader import load_architect_prompt
from app.agent.tracing import traced
from app.agent.language_detector import LanguageDetector, LanguageDetectionResult
from app.agent.architect_json_parser import ArchitectJsonParser

logger = logging.getLogger(__name__)


class Architect(Specialist):
    """架构师 - 负责技术选型和整体架构设计"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.json_parser = ArchitectJsonParser()

    @property
    def SYSTEM_PROMPT(self) -> str:
        # 优先从注册表获取用户自定义版本
        try:
            from app.services.skill_registry import get_skill
            custom_prompt = get_skill("architect_prompt")
            if custom_prompt:
                return custom_prompt
        except Exception:
            pass
        
        # 否则使用默认加载逻辑
        prompt = load_architect_prompt()
        if prompt is None:
            logger.error("架构师提示词加载失败，使用兜底提示词")
            return self._fallback_prompt()
        return prompt

    def _fallback_prompt(self) -> str:
        return """你是一位世界级首席软件架构师，精通几乎所有编程语言和技术栈。
你的职责：分析需求、设计架构、定义 API 和数据库 Schema。
输出格式要求：必须只输出 JSON 格式，不要包含任何解释文字。"""

    def _build_language_rules_text(
        self,
        target_language: str,
        frontend_language: Optional[str],
        backend_language: Optional[str],
        all_languages: List[str],
        lang_detection: 'LanguageDetectionResult',
    ) -> str:
        """构建语言规则文本（支持多语言项目）"""
        lang_rules = LanguageDetector.get_language_specific_rules(target_language)

        # 基础语言规则
        if lang_detection.needs_clarification or lang_rules.get('needs_clarification'):
            base_text = f"""目标语言：{target_language}
注意：该语言不在已知列表中，请根据语言名称推断正确的文件扩展名、入口文件、语法约定等。
例如：Zig → .zig，Nim → .nim，Crystal → .cr 等。"""
        else:
            base_text = f"""目标语言：{target_language}
语言规则：
- 文件扩展名：{lang_rules['file_extension']}
- 包入口文件：{lang_rules['package_init']}
- 导入语法：{lang_rules['import_syntax']}
- 入口文件：{lang_rules['entry_point']}
- 默认后端框架：{lang_rules.get('default_framework') or '根据语言约定'}
- 测试框架：{lang_rules['test_framework']}
- 包管理器：{lang_rules['package_manager']}
- 配置文件：{', '.join(lang_rules['config_files']) if lang_rules['config_files'] else '无'}
- 推荐结构：{chr(10).join('- ' + s for s in lang_rules['common_structure'])}"""

        # 如果是全栈项目，添加前端语言规则
        if frontend_language and frontend_language != target_language:
            frontend_rules = LanguageDetector.get_language_specific_rules(frontend_language)
            if not frontend_rules.get('needs_clarification'):
                base_text += f"""

前端语言：{frontend_language}
前端规则：
- 文件扩展名：{frontend_rules['file_extension']}
- 入口文件：{frontend_rules['entry_point']}
- 包管理器：{frontend_rules['package_manager']}
- 配置文件：{', '.join(frontend_rules['config_files']) if frontend_rules['config_files'] else '无'}
- 推荐结构：{chr(10).join('- ' + s for s in frontend_rules['common_structure'])}"""

        # 如果是多语言后端项目（如 Python + Rust），添加额外语言规则
        extra_backend_langs = [l for l in all_languages if l != target_language and l != frontend_language]
        if extra_backend_langs:
            for extra_lang in extra_backend_langs:
                extra_rules = LanguageDetector.get_language_specific_rules(extra_lang)
                if not extra_rules.get('needs_clarification'):
                    base_text += f"""

辅助语言：{extra_lang}
语言规则：
- 文件扩展名：{extra_rules['file_extension']}
- 入口文件：{extra_rules['entry_point']}
- 包管理器：{extra_rules['package_manager']}
- 配置文件：{', '.join(extra_rules['config_files']) if extra_rules['config_files'] else '无'}"""

        return base_text

    @traced("architect.design", attributes={"component": "specialist", "role": "architect"})
    async def design_architecture(self, requirement: str, complexity: ComplexityAnalysis, feedback: str = "", callback: callable = None) -> Dict:
        """设计项目架构

        Args:
            requirement: 用户需求
            complexity: 复杂度分析
            feedback: 验证反馈（依赖图验证不通过时的修正意见）
            callback: 进度回调函数（用于流式 thinking 推送）
        """
        # 检测目标语言
        lang_detection = LanguageDetector.detect(requirement)
        target_language = lang_detection.language
        frontend_language = lang_detection.frontend_language
        backend_language = lang_detection.backend_language
        all_languages = lang_detection.all_languages or [target_language]

        logger.info(f"检测到目标语言: {target_language} (置信度: {lang_detection.confidence:.2f})")
        logger.info(f"检测依据: {lang_detection.evidence}")
        if frontend_language:
            logger.info(f"前端语言: {frontend_language}")
        if backend_language:
            logger.info(f"后端语言: {backend_language}")
        if len(all_languages) > 1:
            logger.info(f"所有语言: {all_languages}")

        # 构建语言规则部分
        lang_rules_text = self._build_language_rules_text(
            target_language, frontend_language, backend_language, all_languages, lang_detection
        )

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

{lang_rules_text}

请输出完整的架构设计，必须包含 api_spec（后端接口定义）和 db_schema（数据库表结构）。

输出格式要求：
- 只输出 JSON 格式
- 不要包含任何解释文字
- 必须包含以下字段：project_type, frontend_structure, backend_structure, api_spec, db_schema, file_plan, project_spec
- 所有文件必须使用正确的文件扩展名和语法

file_plan 格式要求（每个文件必须包含 imports、file_type 和 language 字段）：
```json
{{{{"file_plan": [
    {{"path": "<入口文件>", "description": "主程序入口", "priority": 1, "file_type": "entry", "language": "{target_language}", "imports": [...]}},
    {{"path": "<模型文件>", "description": "数据模型", "priority": 2, "file_type": "model", "language": "{target_language}", "imports": [...]}},
    {{"path": "<API文件>", "description": "API路由", "priority": 2, "file_type": "api", "language": "{target_language}", "imports": [...]}},
    ...
]}}}}
```

file_type 可选值（每个文件必须选择一个，不得留空或使用其他值）：entry, model, api, service, repository, types, database, config, middleware, frontend_component, frontend_page, frontend_style, template, test, utils, docs

file_type 选择指南：
- entry: 程序入口文件（如 main.py, app.py, index.js）
- model: 数据模型/实体定义
- api: API 路由/控制器
- service: 业务逻辑服务
- repository: 数据访问层
- types: 类型定义/接口
- database: 数据库配置/迁移
- config: 配置文件
- middleware: 中间件
- frontend_component: 前端组件
- frontend_page: 前端页面
- frontend_style: 样式文件
- template: HTML 模板
- test: 测试文件
- utils: 工具函数（仅当文件确实不属于以上任何类型时使用）
- docs: 文档文件

project_spec 格式要求（按 file_type 分组，定义每个类型的存储方式、术语表和框架）：
```json
{{{{"project_spec": {{
    "default": {{
      "storage": {{"type": "json_file|localStorage|sqlite|postgresql|redis|memory", "config": "..."}},
      "terminology": {{"income": "收入", "expense": "支出", "category": "分类", ...}},
      "framework": "FastAPI|Flask|Express.js|Gin|..."
    }},
    "frontend_component": {{
      "storage": {{"type": "localStorage"}},
      "terminology": {{"income": "Income", "expense": "Expense", ...}},
      "framework": "Vue|React|..."
    }},
    "backend_component": {{
      "storage": {{"type": "json_file", "filename": "data.json"}},
      "terminology": {{"income": "收入", "expense": "支出", ...}},
      "framework": "FastAPI|Flask|..."
    }}
}}}}
```

project_spec 规则：
- 必须包含 "default" 作为兜底规范
- 按 file_type 分组（如 frontend_component, backend_component, model, api 等）
- 每组定义 storage（存储方式）、terminology（术语表）和 framework（框架）
- 术语表的 key 是英文术语，value 是项目中使用的实际名称（中文或英文）
- 如果项目只有一种语言/运行时，只需 default 即可
- 如果项目有多种语言/运行时（如 JS 前端 + Python 后端），必须为每种 file_type 分组定义各自的规范
- **框架一致性（重要）**：同一运行时的所有文件必须使用相同的框架。例如后端所有 .py 文件统一用 FastAPI 或统一用 Flask，禁止混用

language 字段要求：
- 每个文件必须指定 language 字段，表示该文件使用的编程语言
- 前端文件（HTML/CSS/JS）使用 javascript 或 html 或 css
- 后端文件使用后端语言（如 python, java, go, rust 等）
- 如果项目只有一种语言，所有文件使用相同的 language 值

重要规则：
1. 每个被其他文件 import 的模块都必须在 file_plan 中有对应的文件
2. imports 字段列出该文件需要导入的其他项目内模块（不包括第三方库）
3. 确保所有 import 路径都能在 file_plan 中找到对应文件
4. 使用正确的文件扩展名和语法约定
5. 如果语言不在已知列表中，请根据语言名称推断正确的文件扩展名和语法约定
6. 文件路径中不得包含空格，使用正斜杠 / 分隔目录
7. 每个文件的 file_type 字段是必填项，必须从上述可选值中选择一个
8. 如果有前端，必须包含 HTML/CSS/JS 等前端文件
9. 避免同名文件：不同目录下的文件尽量使用不同的文件名（如 models/user.py 和 routers/user.py 都叫 user.py，容易混淆）。建议使用更具描述性的名称，如 models/user_model.py、routers/user_router.py、services/user_service.py
10. 框架一致性（重要）：同一运行时的所有后端文件必须使用同一个框架（如全部用 FastAPI 或全部用 Flask），禁止混用。project_spec.default.framework 指定了后端框架，所有后端文件必须遵守。requirements.txt / go.mod 等依赖文件必须包含所选框架的依赖"""

        if feedback:
            prompt += f"""

重要：上次生成的依赖图验证未通过，请根据以下反馈修正：
{feedback}

请确保修正后重新生成 file_plan，避免上述问题。"""

        logger.info(f"架构师调用 LLM | system_prompt={len(self.SYSTEM_PROMPT)} chars, user_prompt={len(prompt)} chars, total={len(self.SYSTEM_PROMPT) + len(prompt)} chars")

        # 使用流式 thinking 调用 LLM
        if callback:
            response = await self.call_llm_with_tools(
                prompt, self.SYSTEM_PROMPT,
                tools={},  # 架构师不需要工具
                enable_streaming_thinking=True,
                callback=callback,
            )
        else:
            response = await self.call_llm(prompt, self.SYSTEM_PROMPT)

        logger.info(
            "架构响应审计: model=%s response_type=%s response_chars=%d has_json_marker=%s",
            self.model_name,
            type(response).__name__,
            len(response or ""),
            bool(response and ("{" in response or "[" in response)),
        )

        # 解析 JSON
        try:
            if not response or not response.strip():
                logger.warning("架构师输出为空，返回默认架构")
                return self._get_requirement_aware_default_architecture(
                    requirement, complexity, target_language, frontend_language
                )

            architecture = self._safe_parse_json(response)
            
            # 处理不同的返回格式
            if isinstance(architecture, list):
                # LLM 直接返回了文件列表，包装成标准格式
                logger.info(f"架构师直接返回了文件列表 ({len(architecture)} 个文件)")
                architecture = {
                    "project_type": "fullstack" if complexity.has_frontend and complexity.has_backend else ("frontend" if complexity.has_frontend else "backend"),
                    "tech_stack": complexity.key_technologies,
                    "language": target_language,
                    "frontend_language": frontend_language,
                    "backend_language": backend_language,
                    "all_languages": all_languages,
                    "file_plan": architecture,
                    "project_spec": self._build_default_project_spec(target_language, frontend_language, complexity),
                    "dependencies": {},
                    "risks": complexity.risk_factors
                }
            elif not isinstance(architecture, dict):
                logger.warning(f"架构师输出类型不正确: {type(architecture).__name__}，返回默认架构")
                return self._get_requirement_aware_default_architecture(
                    requirement, complexity, target_language, frontend_language
                )
        except ValueError:
            logger.warning("架构师输出解析失败，尝试 LLM 辅助提取")
            architecture = await self._extract_json_with_llm(response, complexity)
            if not architecture:
                logger.warning("LLM 辅助提取失败，返回默认架构")
                return self._get_requirement_aware_default_architecture(
                    requirement, complexity, target_language, frontend_language
                )

        if architecture:
            # 确保 language 字段存在
            if "language" not in architecture:
                architecture["language"] = target_language

            # 确保多语言字段存在
            if "frontend_language" not in architecture:
                architecture["frontend_language"] = frontend_language
            if "backend_language" not in architecture:
                architecture["backend_language"] = backend_language
            if "all_languages" not in architecture:
                architecture["all_languages"] = all_languages

            # 验证并增强 api_spec
            if complexity.has_backend:
                architecture = self._validate_and_enhance_api_spec(architecture, complexity)

            # 验证并增强 db_schema
            if complexity.has_database:
                architecture = self._validate_and_enhance_db_schema(architecture, complexity)

            # 确保 file_plan 存在
            if not architecture.get("file_plan"):
                logger.warning("架构师未返回 file_plan，使用默认架构")
                architecture = self._get_requirement_aware_default_architecture(
                    requirement, complexity, target_language, frontend_language
                )

            # 确保 project_spec 存在
            if not architecture.get("project_spec"):
                logger.warning("架构师未返回 project_spec，使用默认规范")
                architecture["project_spec"] = self._build_default_project_spec(
                    target_language, frontend_language, complexity
                )

            # 为 file_plan 中缺少 language 字段的文件补充默认值
            for f in architecture.get("file_plan", []):
                if "language" not in f:
                    # 根据 file_type 推断语言
                    file_type = f.get("file_type", "")
                    if file_type in ("frontend_component", "frontend_page", "frontend_style", "template"):
                        f["language"] = frontend_language or "javascript"
                    else:
                        f["language"] = backend_language or target_language

            # 显式文件范围要求优先于通用完整性补全规则。
            strict_paths = self._extract_strict_file_paths(requirement)
            architecture = self._ensure_file_plan_completeness(
                architecture, target_language, strict_paths=strict_paths
            )

            return architecture
        else:
            return self._get_requirement_aware_default_architecture(
                requirement, complexity, target_language, frontend_language
            )

    async def _extract_json_with_llm(self, raw_text: str, complexity: ComplexityAnalysis) -> Optional[Dict]:
        """使用 LLM 从非标准输出中提取 JSON"""
        extract_prompt = f"""请将以下文本转换为标准 JSON 格式：

原始文本：
{raw_text[:3000]}

要求：
1. 只输出 JSON，不要包含其他内容
2. 确保 JSON 格式正确
3. 必须包含：project_type, frontend_structure, backend_structure, api_spec, db_schema, file_plan, project_spec
4. 修复以下常见问题：
   - 值中错误的反斜杠引号："INTEGER\\" 应为 "INTEGER"
   - dependencies 中的数组格式应为对象或数组
   - 文件路径中的空格应为斜杠：src store/ 应为 src/store/"""

        try:
            response = await self.call_llm(extract_prompt, "")

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
        fix_keys = [p for p in paths if not p.startswith("/")]
        for path in fix_keys:
            paths[f"/{path}"] = paths.pop(path)

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
        return self.json_parser.safe_parse_json(text)

    def _get_default_architecture(self, complexity: ComplexityAnalysis, language: str = "python", frontend_language: Optional[str] = None) -> Dict:
        """返回默认架构（根据语言生成）"""
        from app.agent.language_detector import LanguageDetector
        lang_rules = LanguageDetector.get_language_specific_rules(language)

        # 根据语言生成不同的默认文件结构
        if language == "python":
            entry_point = "main.py"
            db_file = "app/database.py"
            model_file = "app/models.py"
            router_file = "app/routers.py"
            init_file = "app/__init__.py"
            dep_file = "requirements.txt"
        elif language == "javascript":
            entry_point = "src/index.ts"
            db_file = "src/database.ts"
            model_file = "src/models/user.ts"
            router_file = "src/routes/index.ts"
            init_file = None  # JS 没有 __init__.py
            dep_file = "package.json"
        elif language == "go":
            entry_point = "main.go"
            db_file = "internal/database/database.go"
            model_file = "internal/models/user.go"
            router_file = "internal/handlers/user.go"
            init_file = None  # Go 没有 __init__.py
            dep_file = "go.mod"
        elif language == "java":
            entry_point = "src/main/java/com/example/Application.java"
            db_file = "src/main/java/com/example/config/DatabaseConfig.java"
            model_file = "src/main/java/com/example/model/User.java"
            router_file = "src/main/java/com/example/controller/UserController.java"
            init_file = None  # Java 没有 __init__.py
            dep_file = "pom.xml"
        elif language == "rust":
            entry_point = "src/main.rs"
            db_file = "src/database.rs"
            model_file = "src/models/user.rs"
            router_file = "src/handlers/user.rs"
            init_file = None  # Rust 没有 __init__.py
            dep_file = "Cargo.toml"
        else:
            # 通用结构
            ext = lang_rules.get('file_extension')
            if ext:
                ext_name = ext.lstrip('.')
            else:
                ext_name = language  # 未知语言使用语言名作为扩展名
            entry_point = f"main.{ext_name}"
            db_file = f"database.{ext_name}"
            model_file = f"models/user.{ext_name}"
            router_file = f"routes/user.{ext_name}"
            init_file = None
            dep_file = "README.md"

        file_plan = [
            {"path": entry_point, "description": "主程序入口", "priority": 1, "file_type": "entry", "language": language, "imports": []},
            {"path": dep_file, "description": "依赖配置", "priority": 2, "file_type": "config", "language": language, "imports": []},
            {"path": "README.md", "description": "项目文档", "priority": 3, "file_type": "docs", "language": language, "imports": []}
        ]

        if complexity.has_frontend:
            # 使用前端语言，如果未指定则默认 javascript
            fe_lang = frontend_language or "javascript"
            file_plan.extend([
                {"path": "templates/index.html", "description": "前端页面模板", "priority": 4, "file_type": "template", "language": "html", "imports": []},
                {"path": "static/style.css", "description": "样式表", "priority": 5, "file_type": "frontend_style", "language": "css", "imports": []},
                {"path": "static/app.js", "description": "前端脚本", "priority": 5, "file_type": "frontend_component", "language": fe_lang, "imports": []}
            ])

        if complexity.has_backend:
            backend_files = [
                {"path": db_file, "description": "数据库连接配置", "priority": 1, "file_type": "database", "language": language, "imports": []},
                {"path": model_file, "description": "数据模型", "priority": 2, "file_type": "model", "language": language, "imports": [db_file]},
                {"path": router_file, "description": "API 路由", "priority": 3, "file_type": "api", "language": language, "imports": [model_file, db_file]},
            ]
            # 如果有包入口文件，添加它
            if init_file:
                backend_files.insert(0, {"path": init_file, "description": "包初始化文件", "priority": 1, "file_type": "config", "language": language, "imports": []})
            
            # 添加服务层
            if language == "python":
                service_file = "app/services.py"
                config_file = "app/config.py"
                utils_file = "app/utils.py"
                test_file = "tests/test_app.py"
            elif language == "javascript":
                service_file = "src/services/user.ts"
                config_file = "src/config.ts"
                utils_file = "src/utils.ts"
                test_file = "tests/app.test.ts"
            elif language == "go":
                service_file = "internal/services/user.go"
                config_file = "internal/config/config.go"
                utils_file = "internal/utils/utils.go"
                test_file = "internal/handlers/user_test.go"
            else:
                service_file = None
                config_file = None
                utils_file = None
                test_file = None
            
            if service_file:
                backend_files.append({"path": service_file, "description": "业务逻辑服务", "priority": 3, "file_type": "service", "language": language, "imports": [model_file]})
            if config_file:
                backend_files.append({"path": config_file, "description": "应用配置", "priority": 2, "file_type": "config", "language": language, "imports": []})
            if utils_file:
                backend_files.append({"path": utils_file, "description": "工具函数", "priority": 4, "file_type": "utils", "language": language, "imports": []})
            if test_file:
                backend_files.append({"path": test_file, "description": "测试文件", "priority": 5, "file_type": "test", "language": language, "imports": [router_file]})
            
            file_plan.extend(backend_files)

        return {
            "project_type": "fullstack" if complexity.has_frontend and complexity.has_backend else ("frontend" if complexity.has_frontend else "backend"),
            "tech_stack": complexity.key_technologies,
            "language": language,
            "frontend_language": frontend_language,
            "backend_language": language,
            "all_languages": [l for l in set([language, frontend_language]) if l],
            "file_plan": file_plan,
            "project_spec": self._build_default_project_spec(language, frontend_language, complexity),
            "dependencies": {},
            "risks": complexity.risk_factors
        }

    def _get_requirement_aware_default_architecture(
        self,
        requirement: str,
        complexity: ComplexityAnalysis,
        language: str = "python",
        frontend_language: Optional[str] = None,
    ) -> Dict:
        """架构输出异常时保留需求中明确列出的项目文件。"""
        architecture = self._get_default_architecture(complexity, language, frontend_language)
        planned_paths = {item["path"] for item in architecture["file_plan"]}
        extensions = {"python": "py", "javascript": "js", "typescript": "ts", "go": "go"}
        extension = extensions.get(language, language)
        explicit_paths = re.findall(
            rf"(?<![\w/])(?:[\w.-]+/)*[\w.-]+\.{re.escape(extension)}\b",
            requirement,
        )

        for path in explicit_paths:
            if path in planned_paths:
                continue
            lower_path = path.lower()
            if "/models/" in f"/{lower_path}":
                file_type, description, priority = "model", "数据模型", 2
            elif "/services/" in f"/{lower_path}":
                file_type, description, priority = "service", "业务逻辑服务", 3
            elif "/routes/" in f"/{lower_path}" or "/api/" in f"/{lower_path}":
                file_type, description, priority = "api", "API 路由", 3
            else:
                file_type, description, priority = "utils", "需求指定模块", 3

            imports = []
            if "/services/" in f"/{lower_path}":
                imports = [candidate for candidate in planned_paths if "/models/" in f"/{candidate.lower()}" and candidate.endswith(f".{extension}")]
            elif path == "main.py" or path == "main.js" or path == "main.ts":
                imports = [candidate for candidate in planned_paths if "/services/" in f"/{candidate.lower()}" and candidate.endswith(f".{extension}")]

            architecture["file_plan"].append({
                "path": path,
                "description": description,
                "priority": priority,
                "file_type": file_type,
                "language": language,
                "imports": imports,
            })
            planned_paths.add(path)

        return architecture

    def _build_default_project_spec(self, language: str, frontend_language: Optional[str], complexity: ComplexityAnalysis) -> Dict:
        """构建默认的 project_spec（向后兼容）"""
        # 根据语言确定存储类型和默认框架
        storage_map = {
            "python": {"type": "json_file", "filename": "data.json"},
            "javascript": {"type": "localStorage"},
            "typescript": {"type": "localStorage"},
            "go": {"type": "json_file", "filename": "data.json"},
            "java": {"type": "json_file", "filename": "data.json"},
            "rust": {"type": "json_file", "filename": "data.json"},
        }
        framework_map = {
            "python": "FastAPI",
            "javascript": "Express.js",
            "typescript": "Express.js",
            "go": "Gin",
            "java": "Spring Boot",
            "rust": "Actix-web",
        }
        backend_storage = storage_map.get(language, {"type": "json_file", "filename": "data.json"})
        backend_framework = framework_map.get(language)
        frontend_storage = {"type": "localStorage"}
        frontend_framework = "Vue" if complexity.has_frontend else None

        # 默认术语表（中文项目）
        default_terminology = {
            "income": "收入",
            "expense": "支出",
            "category": "分类",
            "amount": "金额",
            "note": "备注",
            "date": "日期",
            "record": "记录",
            "user": "用户",
        }

        spec = {
            "default": {
                "storage": backend_storage,
                "terminology": default_terminology,
                "framework": backend_framework,
            }
        }

        # 如果有前端，添加前端规范
        if complexity.has_frontend:
            spec["frontend_component"] = {
                "storage": frontend_storage,
                "terminology": default_terminology,
                "framework": frontend_framework,
            }
            spec["frontend_page"] = {
                "storage": frontend_storage,
                "terminology": default_terminology,
                "framework": frontend_framework,
            }
            spec["frontend_style"] = {
                "storage": frontend_storage,
                "terminology": default_terminology,
                "framework": frontend_framework,
            }
            spec["template"] = {
                "storage": frontend_storage,
                "terminology": default_terminology,
                "framework": frontend_framework,
            }

        return spec

    @staticmethod
    def _parse_import_to_module(import_str: str) -> Optional[str]:
        """解析 import 语句，提取模块路径

        支持格式：
        - "from src.app.models import Expense" -> "src.app.models"
        - "from src.app.models.expense import Expense" -> "src.app.models.expense"
        - "import src.app.models" -> "src.app.models"
        - "src.app.models" -> "src.app.models" (已经是模块路径)

        Returns:
            模块路径或 None（如果无法解析）
        """
        if not import_str or not isinstance(import_str, str):
            return None

        import_str = import_str.strip()

        # 格式 1: "from xxx import yyy"
        match = re.match(r'^from\s+([\w.]+)\s+import\s+', import_str)
        if match:
            return match.group(1)

        # 格式 2: "import xxx"
        match = re.match(r'^import\s+([\w.]+)', import_str)
        if match:
            return match.group(1)

        # 格式 3: 已经是模块路径（只包含字母、数字、点、下划线）
        if re.match(r'^[\w.]+$', import_str):
            return import_str

        return None

    @staticmethod
    def _extract_strict_file_paths(requirement: str) -> Optional[set]:
        """识别需求中明确限定的文件集合。"""
        if not requirement:
            return None
        match = re.search(r"(?:只需要|仅需要|only)\s*(.{1,300}?)(?:个|份)?\s*文件", requirement, re.IGNORECASE)
        if not match:
            return None
        paths = set(re.findall(r"[\w./-]+\.(?:py|js|ts|jsx|tsx|vue|html|css|scss|json|yaml|yml|toml|go|java|rs)", match.group(1)))
        return paths or None

    def _ensure_file_plan_completeness(
        self,
        architecture: Dict,
        target_language: Optional[str] = None,
        strict_paths: Optional[set] = None,
    ) -> Dict:
        """确保 file_plan 完整性：补充 imports 中明确引用但 file_plan 中缺失的文件，以及缺失的前端文件

        注意：不再补充 index.js barrel export，不再遍历目录。
        依赖图的完整性验证和补充由 DependencyGraph 负责。
        """
        file_plan = architecture.get("file_plan", [])
        if not file_plan:
            return architecture
        
        # 确保所有文件都有必要的字段
        for f in file_plan:
            if "file_type" not in f:
                f["file_type"] = "unknown"
            if "description" not in f:
                f["description"] = ""
            if "priority" not in f:
                f["priority"] = 3
            if "imports" not in f:
                f["imports"] = []
            if "language" not in f:
                f["language"] = target_language or "python"

        if strict_paths:
            original_count = len(file_plan)
            strict_file_plan = []
            for strict_path in sorted(strict_paths):
                exact_match = next(
                    (f for f in file_plan if f.get("path") == strict_path),
                    None,
                )
                basename_matches = [
                    f
                    for f in file_plan
                    if Path(f.get("path", "")).name == Path(strict_path).name
                ]
                source = exact_match or (
                    min(basename_matches, key=lambda f: len(f.get("path", "")))
                    if basename_matches
                    else None
                )
                normalized = dict(source) if source else {
                    "description": f"实现 {strict_path}",
                    "file_type": "unknown",
                    "priority": 3,
                    "imports": [],
                    "language": target_language or "python",
                }
                normalized["path"] = strict_path
                strict_file_plan.append(normalized)
            architecture["file_plan"] = strict_file_plan
            logger.info(
                "严格文件集合生效: %d -> %d 个文件",
                original_count,
                len(architecture["file_plan"]),
            )
            return architecture

        # 检测语言（优先使用传入的语言，避免重复检测导致翻转）
        from app.agent.adapters import LanguageAdapterRegistry
        if target_language:
            detected_lang = target_language
        else:
            files_for_detection = {f["path"]: "" for f in file_plan}
            detected_lang = LanguageAdapterRegistry.detect_language(files_for_detection)
        adapter = LanguageAdapterRegistry.get_adapter(detected_lang)

        logger.info(f"_ensure_file_plan_completeness: 检测到语言={detected_lang}, 适配器={adapter.language}")

        # 提取所有已规划的文件路径（安全访问，避免 KeyError）
        planned_paths = {f["path"] for f in file_plan if "path" in f}
        planned_types = {f.get("file_type") for f in file_plan}

        # 确保依赖文件存在（requirements.txt / package.json / go.mod 等）
        DEP_FILES = {
            "python": "requirements.txt",
            "javascript": "package.json",
            "go": "go.mod",
            "java": "pom.xml",
            "rust": "Cargo.toml",
        }
        dep_file = DEP_FILES.get(detected_lang)
        if dep_file and dep_file not in planned_paths:
            file_plan.append({"path": dep_file, "description": "依赖配置", "priority": 2, "imports": [], "language": detected_lang})
            planned_paths.add(dep_file)
            logger.info(f"_ensure_file_plan_completeness: 补充依赖文件 {dep_file}")

        # 确保 README.md 存在
        if "README.md" not in planned_paths:
            file_plan.append({"path": "README.md", "description": "项目文档", "priority": 3, "imports": [], "language": detected_lang})
            planned_paths.add("README.md")
            logger.info(f"_ensure_file_plan_completeness: 补充 README.md")

        # 自动补充缺失的前端文件（当架构中标记有前端时）
        frontend_language = architecture.get("frontend_language")
        has_frontend_types = any(
            ft in planned_types
            for ft in ("frontend_component", "frontend_page", "frontend_style", "template")
        )
        # 检查是否有 HTML/CSS/JS 文件
        has_html = any(f["path"].endswith(".html") for f in file_plan)
        has_css = any(f["path"].endswith(".css") for f in file_plan)
        has_js = any(f["path"].endswith((".js", ".jsx", ".ts", ".tsx")) for f in file_plan)

        if frontend_language and not has_frontend_types and not has_html:
            fe_lang = frontend_language or "javascript"
            frontend_files = [
                {"path": "templates/index.html", "description": "前端页面模板", "priority": 4, "file_type": "template", "language": "html", "imports": []},
            ]
            if not has_css:
                frontend_files.append({"path": "static/style.css", "description": "样式表", "priority": 5, "file_type": "frontend_style", "language": "css", "imports": []})
            if not has_js:
                frontend_files.append({"path": "static/app.js", "description": "前端脚本", "priority": 5, "file_type": "frontend_component", "language": fe_lang, "imports": []})
            
            file_plan.extend(frontend_files)
            planned_paths.update(f["path"] for f in frontend_files)
            logger.info(f"_ensure_file_plan_completeness: 自动补充 {len(frontend_files)} 个前端文件")

        # 提取所有被引用的模块（解析 import 语句为模块路径）
        all_modules = set()
        for f in file_plan:
            imports = f.get("imports", [])
            if isinstance(imports, list):
                for imp in imports:
                    if isinstance(imp, str):
                        # 解析 import 语句，提取模块路径
                        module = self._parse_import_to_module(imp)
                        if module:
                            all_modules.add(module)
                    elif isinstance(imp, dict):
                        module = imp.get("module", "")
                        if module:
                            # 解析 import 语句，提取模块路径
                            parsed_module = self._parse_import_to_module(module)
                            if parsed_module:
                                all_modules.add(parsed_module)
                        for item in imp.get("items", []):
                            if isinstance(item, str):
                                # 解析 import 语句，提取模块路径
                                parsed_item = self._parse_import_to_module(item)
                                if parsed_item:
                                    all_modules.add(parsed_item)

        # 只补充 imports 中明确引用但 file_plan 中缺失的文件
        missing_files = []
        from app.agent.adapters import ImportInfo
        for module in all_modules:
            import_info = ImportInfo(module=module, symbols=[], is_relative=False)
            candidates = adapter.resolve_import_to_file(import_info, "")

            exists = any(c in planned_paths for c in candidates)

            if not exists and candidates:
                file_path = candidates[0]
                # 验证文件路径是否合法（不包含空格或特殊字符）
                if ' ' in file_path or ',' in file_path:
                    logger.warning(f"跳过非法文件路径: {file_path}")
                    continue
                # 推断文件类型
                inferred_type = adapter.infer_file_type(file_path) if adapter else "unknown"
                missing_files.append({
                    "path": file_path,
                    "description": "自动补充的模块文件",
                    "priority": 2,
                    "file_type": inferred_type,
                    "imports": [],
                    "language": detected_lang,
                })
                logger.info(f"自动补充缺失模块: {file_path} (type={inferred_type})")

        if missing_files:
            file_plan.extend(missing_files)
            architecture["file_plan"] = file_plan
            logger.info(f"共补充 {len(missing_files)} 个缺失文件")

        return architecture

    async def expand_file_plan(
        self,
        architecture: Dict,
        complexity: ComplexityAnalysis,
        target_file_count: int,
        target_language: Optional[str] = None,
    ) -> Dict:
        """依赖驱动扩展 file_plan

        基于 DependencyGraph 分析缺失模块，让 LLM 补充。
        不再使用关键词猜测。

        Args:
            architecture: 已有的架构设计（含 file_plan）
            complexity: 复杂度分析
            target_file_count: 目标文件总数

        Returns:
            扩展后的架构设计
        """
        existing_plan = architecture.get("file_plan", [])
        existing_paths = {f["path"] for f in existing_plan}

        if len(existing_plan) >= target_file_count:
            logger.info(f"file_plan 已有 {len(existing_plan)} 个文件，达到目标 {target_file_count}，跳过扩展")
            return architecture

        # 构建依赖图，分析缺失模块
        from app.agent.dependency_graph import DependencyGraph
        from app.agent.adapters import LanguageAdapterRegistry
        detected_language = target_language or architecture.get("language", "python")
        adapter = LanguageAdapterRegistry.get_adapter(detected_language)
        dep_graph = DependencyGraph(language_adapter=adapter)
        dep_graph.build_from_architecture(architecture)

        # 用依赖图验证完整性，找出缺失文件
        missing_from_graph = dep_graph.get_missing_files()
        if missing_from_graph:
            logger.info(f"依赖图发现 {len(missing_from_graph)} 个缺失文件: {missing_from_graph}")
            architecture = dep_graph.add_missing_files(architecture)
            existing_plan = architecture.get("file_plan", [])
            existing_paths = {f["path"] for f in existing_plan}

        batch = 0
        while True:
            remaining = target_file_count - len(existing_plan)
            if remaining <= 0:
                break

            batch += 1
            logger.info(f"分批规划第 {batch} 轮：已有 {len(existing_plan)} 个文件，目标 {target_file_count}，需补充 {remaining} 个")

            # 依赖驱动：让 LLM 基于现有 file_plan 和依赖关系补充文件
            batch_files = await self._generate_batch_files(
                architecture, complexity, remaining
            )

            # 去重合并
            from pathlib import Path as _P

            added = 0
            for f in batch_files:
                fpath = f.get("path", "")
                if not fpath:
                    continue
                if fpath not in existing_paths:
                    existing_plan.append(f)
                    existing_paths.add(fpath)
                    added += 1

            logger.info(f"分批规划第 {batch} 轮：新增 {added} 个文件，当前共 {len(existing_plan)} 个")

            # 本轮未新增任何文件，终止
            if added == 0:
                logger.info("本轮无新增文件，终止扩展")
                break

        architecture["file_plan"] = existing_plan
        architecture = self._ensure_file_plan_completeness(architecture, target_language)
        return architecture

    async def _generate_batch_files(
        self,
        architecture: Dict,
        complexity: ComplexityAnalysis,
        max_files: int
    ) -> list:
        """依赖驱动：让 LLM 基于现有 file_plan 和依赖关系补充文件"""
        existing_paths = {f["path"] for f in architecture.get("file_plan", [])}
        existing_summary = "\n".join(f"- {f['path']}: {f['description']}" for f in architecture.get("file_plan", [])[:20])

        # 获取多语言信息
        all_languages = architecture.get("all_languages", [architecture.get("language", "python")])
        frontend_language = architecture.get("frontend_language")
        backend_language = architecture.get("backend_language")

        # 构建语言说明
        lang_info = f"语言：{architecture.get('language', 'python')}"
        if frontend_language and frontend_language != architecture.get("language"):
            lang_info += f"\n前端语言：{frontend_language}"
        if backend_language and backend_language != architecture.get("language"):
            lang_info += f"\n后端语言：{backend_language}"
        if len(all_languages) > 1:
            lang_info += f"\n项目使用多种语言：{', '.join(all_languages)}"

        prompt = f"""请为以下项目补充文件规划。

需求：{architecture.get('project_type', '未知项目')}
技术栈：{', '.join(architecture.get('tech_stack', complexity.key_technologies))}
{lang_info}

已有文件（不要重复）：
{existing_summary}

最多补充 {max_files} 个文件。

输出格式要求：
- 只输出 JSON 格式
- 不要包含任何解释文字
- 只输出 file_plan 数组，不要其他字段

```json
{{{{"file_plan": [
    {{"path": "<文件路径>", "description": "<文件描述>", "priority": <1-5>, "file_type": "<类型>", "language": "<语言>", "imports": ["<导入的项目内模块>"]}},
    ...
]}}}}
```

file_type 可选值：entry, model, api, service, repository, types, database, config, middleware, frontend_component, frontend_page, frontend_style, template, test, utils, docs

language 字段要求：
- 每个文件必须指定 language 字段
- 前端文件（HTML/CSS/JS）使用 javascript 或 html 或 css
- 后端文件使用后端语言（如 python, java, go, rust 等）
- 如果项目只有一种语言，所有文件使用相同的 language 值

规则：
1. 不要生成已存在的文件
2. imports 只引用项目内模块（不包括第三方库）
3. 确保文件路径使用正确的扩展名
4. 每个文件描述要具体说明其职责
5. 仔细分析已有文件的依赖关系，补充被引用但缺失的模块
6. 如果已有文件足够完整，返回空的 file_plan 数组
7. 文件路径中不得包含空格
8. 如果有前端，确保包含 HTML/CSS/JS 等前端文件
9. 避免同名文件：新文件不要与已有文件同名，使用更具描述性的名称（如 user_model.py 而非 user.py）"""

        try:
            logger.info(f"架构师调用 LLM | system_prompt={len(self.SYSTEM_PROMPT)} chars, user_prompt={len(prompt)} chars, total={len(self.SYSTEM_PROMPT) + len(prompt)} chars")
            response = await self.call_llm(prompt, self.SYSTEM_PROMPT)
            if not response or not response.strip():
                return []

            parsed = self._safe_parse_json(response)
            
            # 处理不同的返回格式
            if isinstance(parsed, list):
                # LLM 直接返回了文件列表
                batch_plan = parsed
                logger.info(f"分批规划：LLM 直接返回了 {len(batch_plan)} 个文件")
            elif isinstance(parsed, dict):
                batch_plan = parsed.get("file_plan", [])
            else:
                logger.warning(f"分批规划输出类型不正确: {type(parsed).__name__}")
                return []
            
            # 验证每个文件的格式
            valid_files = []
            for f in batch_plan:
                if isinstance(f, dict) and f.get("path"):
                    # 确保必要字段存在
                    if "file_type" not in f:
                        f["file_type"] = "unknown"
                    if "description" not in f:
                        f["description"] = ""
                    if "priority" not in f:
                        f["priority"] = 3
                    if "imports" not in f:
                        f["imports"] = []
                    if "language" not in f:
                        # 根据 file_type 推断语言
                        file_type = f.get("file_type", "")
                        if file_type in ("frontend_component", "frontend_page", "frontend_style", "template"):
                            f["language"] = frontend_language or "javascript"
                        else:
                            f["language"] = backend_language or architecture.get("language", "python")
                    valid_files.append(f)
            
            # 过滤掉已存在的文件
            return [f for f in valid_files if f["path"] not in existing_paths]

        except Exception as e:
            logger.warning(f"分批规划生成失败: {e}")
            return []
