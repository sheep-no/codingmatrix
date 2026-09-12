import logging
import re
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

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

    @staticmethod
    def _build_scope_rules_text(complexity: ComplexityAnalysis) -> str:
        fe_rule = (
            "需求包含前端：file_plan 需包含前端文件。"
            if complexity.has_frontend
            else "需求不含前端：file_plan 不得包含页面、组件、HTML、CSS。"
        )
        api_rule = (
            "需求包含后端：必须输出非空 api_spec。"
            if complexity.has_backend
            else "需求不含后端：api_spec 必须为 {}，禁止默认 FastAPI/Flask/Express/Gin/Spring 等 Web 框架，file_plan 不得包含路由或控制器。"
        )
        db_rule = (
            "需求包含数据库：必须输出非空 db_schema。"
            if complexity.has_database
            else "需求不含数据库：db_schema 必须为 {}，dependencies 不得包含 ORM 或数据库驱动。"
        )
        simple_rule = ""
        if complexity.level.value in ("simple", "small") and not complexity.has_backend:
            simple_rule = (
                "\n- 这是简单脚本/小项目：file_plan 只保留用户点名的源文件；"
                "project_spec.default.framework 填 none 或语言标准库，禁止填 Web 框架。"
            )
        return (
            "范围约束（最高优先级，必须遵守）：\n"
            "- 用户用「不要/无需/禁止/without/no」排除的能力，不得出现在架构、依赖和 file_plan 中\n"
            f"- {fe_rule}\n"
            f"- {api_rule}\n"
            f"- {db_rule}{simple_rule}"
        )

    def _build_language_rules_text(
        self,
        target_language: str,
        frontend_language: Optional[str],
        backend_language: Optional[str],
        all_languages: List[str],
        lang_detection: 'LanguageDetectionResult',
        has_backend: bool = True,
    ) -> str:
        """构建语言规则文本（支持多语言项目）"""
        lang_rules = LanguageDetector.get_language_specific_rules(target_language)

        # 基础语言规则
        if lang_detection.needs_clarification or lang_rules.get('needs_clarification'):
            base_text = f"""目标语言：{target_language}
注意：该语言不在已知列表中，请根据语言名称推断正确的文件扩展名、入口文件、语法约定等。
例如：Zig → .zig，Nim → .nim，Crystal → .cr 等。"""
        else:
            if has_backend:
                framework_line = f"- 默认后端框架：{lang_rules.get('default_framework') or '根据语言约定'}"
                structure = lang_rules['common_structure']
            else:
                framework_line = "- 默认后端框架：无（未要求 Web/API，禁止套用 FastAPI/Flask/Express/Gin/Spring 等）"
                structure = ["按用户指定的文件路径生成，不要套用分层 Web 模板"]
            base_text = f"""目标语言：{target_language}
语言规则：
- 文件扩展名：{lang_rules['file_extension']}
- 包入口文件：{lang_rules['package_init']}
- 导入语法：{lang_rules['import_syntax']}
- 入口文件：{lang_rules['entry_point']}
{framework_line}
- 测试框架：{lang_rules['test_framework']}
- 包管理器：{lang_rules['package_manager']}
 - 配置文件：{', '.join(lang_rules['config_files']) if lang_rules['config_files'] else '无'}
 - 推荐结构：{chr(10).join('- ' + s for s in structure)}"""

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

        def finalize(architecture: Dict) -> Dict:
            return self._canonicalize_architecture(
                architecture, requirement, complexity, target_language, frontend_language
            )

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
            target_language, frontend_language, backend_language, all_languages, lang_detection,
            has_backend=complexity.has_backend,
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

{self._build_scope_rules_text(complexity)}

请输出完整的架构设计。

输出格式要求：
- 只输出 JSON 格式
- 不要包含任何解释文字
 - 必须包含以下字段：project_type, file_plan, project_spec
 - api_spec、db_schema、frontend_structure、backend_structure 在不适用时输出空对象 {{}}
- 所有文件必须使用正确的文件扩展名和语法

file_plan 格式要求（每个文件必须包含 imports、file_type、language 和 contract 字段）：
```json
{{{{"file_plan": [
    {{"path": "<入口文件>", "description": "主程序入口", "priority": 1, "file_type": "entry", "language": "{target_language}", "imports": [...]}},
    {{"path": "<模型文件>", "description": "数据模型", "priority": 2, "file_type": "model", "language": "{target_language}", "imports": [...]}},
    {{"path": "<API文件>", "description": "API路由", "priority": 2, "file_type": "api", "language": "{target_language}", "imports": [...]}},
    ...
]}}}}
```

上述 model/api 示例仅在需求包含后端时使用；简单脚本的 file_plan 只含用户点名的文件。

file_type 可选值（每个文件必须选择一个，不得留空或使用其他值）：entry, model, api, service, repository, types, database, config, middleware, frontend_component, frontend_page, frontend_style, template, test, utils, docs

每个 file_plan 项目还必须包含 contract 对象。contract 描述该文件的职责边界和跨文件接口，字段可包括 role、exports、forbidden_imports、required_imports、shared_symbols、database_abstraction、runtime 和 notes。依赖方向使用 imports 或 dependencies 声明，公共符号使用 exports 声明；这些契约必须根据实际职责填写，不能根据固定文件名推断。同一模块禁止同时出现在 required_imports 和 forbidden_imports 中；入口和 API 文件必须允许导入 project_spec 声明的框架。

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
      "framework": "none|stdlib|用户指定的框架"
    }},
    "frontend_component": {{
      "storage": {{"type": "localStorage"}},
      "terminology": {{"income": "Income", "expense": "Expense", ...}},
      "framework": "Vue|React|..."
    }},
    "backend_component": {{
      "storage": {{"type": "json_file", "filename": "data.json"}},
      "terminology": {{"income": "收入", "expense": "支出", ...}},
      "framework": "用户指定的后端框架；无后端时省略本组"
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
 - **框架一致性（重要）**：有后端时同一运行时必须使用同一个框架；无后端时 framework 填 none，禁止填 FastAPI/Flask/Express 等

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
8. 仅当需求包含前端时才加入 HTML/CSS/JS 等前端文件
9. 避免同名文件：不同目录下的文件尽量使用不同的文件名（如 models/user.py 和 routers/user.py 都叫 user.py，容易混淆）。建议使用更具描述性的名称，如 models/user_model.py、routers/user_router.py、services/user_service.py
10. 框架一致性（重要）：有后端时同一运行时必须使用同一个框架；无后端时 project_spec.default.framework 填 none，禁止填 FastAPI/Flask/Express。依赖文件只列出需求真正需要的包
11. file_plan 只包含本项目源码和清单文件，禁止把第三方库或标准库写成项目路径"""

        if feedback:
            prompt += f"""

重要：上次生成的依赖图验证未通过，请根据以下反馈修正：
{feedback}

请确保修正后重新生成 file_plan，避免上述问题。"""

        logger.info(f"架构师调用 LLM | system_prompt={len(self.SYSTEM_PROMPT)} chars, user_prompt={len(prompt)} chars, total={len(self.SYSTEM_PROMPT) + len(prompt)} chars")

        # 使用流式 thinking 调用 LLM
        try:
            if callback:
                response = await self.call_llm_with_tools(
                    prompt, self.SYSTEM_PROMPT,
                    tools={},  # 架构师不需要工具
                    enable_streaming_thinking=True,
                    callback=callback,
                )
            else:
                response = await self.call_llm(prompt, self.SYSTEM_PROMPT)
        except Exception as exc:
            logger.warning("架构师首次调用失败，返回默认架构: %s", exc)
            return finalize(self._get_requirement_aware_default_architecture(
                requirement, complexity, target_language, frontend_language
            ))

        if not response or not str(response).strip():
            logger.warning("架构师输出为空，禁用思考后重试一次")
            try:
                response = await self.call_llm(
                    prompt, self.SYSTEM_PROMPT, thinking_budget=0
                )
            except Exception as exc:
                logger.warning("架构师重试失败，返回默认架构: %s", exc)
                return finalize(self._get_requirement_aware_default_architecture(
                    requirement, complexity, target_language, frontend_language
                ))

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
                logger.warning("架构师重试仍为空，返回默认架构")
                return finalize(self._get_requirement_aware_default_architecture(
                    requirement, complexity, target_language, frontend_language
                ))

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
                    "file_plan": self._normalize_file_plan(architecture, target_language),
                    "project_spec": self._build_default_project_spec(target_language, frontend_language, complexity),
                    "dependencies": {},
                    "risks": complexity.risk_factors
                }
            elif not isinstance(architecture, dict):
                logger.warning(f"架构师输出类型不正确: {type(architecture).__name__}，返回默认架构")
                return finalize(self._get_requirement_aware_default_architecture(
                    requirement, complexity, target_language, frontend_language
                ))
        except ValueError:
            logger.warning("架构师输出解析失败，尝试 LLM 辅助提取")
            architecture = await self._extract_json_with_llm(response, complexity)
            if not architecture:
                logger.warning("LLM 辅助提取失败，返回默认架构")
                return finalize(self._get_requirement_aware_default_architecture(
                    requirement, complexity, target_language, frontend_language
                ))

        if architecture:
            architecture = self._coerce_architecture_fields(architecture)
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
            architecture = self._validate_and_enhance_api_spec(architecture, complexity)
            architecture = self._validate_and_enhance_db_schema(architecture, complexity)

            architecture = self._ensure_architecture_file_plan(
                architecture, requirement, complexity, target_language, frontend_language
            )

            # 确保 project_spec 存在
            if not isinstance(architecture.get("project_spec"), dict):
                logger.warning("架构师未返回 project_spec，使用默认规范")
                architecture["project_spec"] = self._build_default_project_spec(
                    target_language, frontend_language, complexity
                )

            # 为 file_plan 中缺少 language 字段的文件补充默认值
            for f in architecture.get("file_plan", []):
                if not isinstance(f, dict):
                    continue
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
                architecture, target_language, strict_paths=strict_paths, complexity=complexity
            )

            architecture["requirement"] = requirement
            return finalize(architecture)
        else:
            return finalize(self._get_requirement_aware_default_architecture(
                requirement, complexity, target_language, frontend_language
            ))

    async def _extract_json_with_llm(self, raw_text: str, complexity: ComplexityAnalysis) -> Optional[Dict]:
        """使用 LLM 从非标准输出中提取 JSON"""
        extract_prompt = f"""请将以下文本转换为标准 JSON 格式：

原始文本：
{raw_text[:3000]}

要求：
1. 只输出 JSON，不要包含其他内容
2. 确保 JSON 格式正确
3. 必须包含：project_type, file_plan, project_spec；无后端时 api_spec 为 {{}}，无数据库时 db_schema 为 {{}}
4. 修复以下常见问题：
   - 值中错误的反斜杠引号："INTEGER\\" 应为 "INTEGER"
   - dependencies 中的数组格式应为对象或数组
   - 文件路径中的空格应为斜杠：src store/ 应为 src/store/"""

        try:
            response = await self.call_llm(extract_prompt, "")
            content = response if isinstance(response, str) else str(response or "")
            if not content.strip():
                return None
            parsed = self._safe_parse_json(content)
            return parsed if isinstance(parsed, dict) else None
        except Exception as e:
            logger.error(f"LLM 辅助提取 JSON 失败: {e}")
            return None

    def _validate_and_enhance_api_spec(self, architecture: Dict, complexity: ComplexityAnalysis) -> Dict:
        """只修 JSON 形状：缺字段补空对象，路径补前导斜杠。不发明接口。"""
        api_spec = architecture.get("api_spec", {})
        if not isinstance(api_spec, dict):
            architecture["api_spec"] = {}
            return architecture
        paths = api_spec.get("paths")
        if isinstance(paths, dict):
            for path in [p for p in list(paths) if not str(p).startswith("/")]:
                paths[f"/{path}"] = paths.pop(path)
        architecture["api_spec"] = api_spec
        return architecture

    def _validate_and_enhance_db_schema(self, architecture: Dict, complexity: ComplexityAnalysis) -> Dict:
        """只修 JSON 形状：缺字段补空对象。不发明表或列。"""
        db_schema = architecture.get("db_schema", {})
        architecture["db_schema"] = db_schema if isinstance(db_schema, dict) else {}
        return architecture

    def _safe_parse_json(self, text: str) -> Dict:
        """安全解析 JSON，处理各种格式问题"""
        return self.json_parser.safe_parse_json(text)

    _FILE_PLAN_KEYS = (
        "file_plan", "files", "filePlan", "planned_files", "file_list",
        "project_files", "source_files",
    )
    _FILE_PLAN_NEST_KEYS = (
        "architecture", "design", "project", "result", "data",
        "backend_structure", "frontend_structure",
    )

    @classmethod
    def _normalize_file_plan_item(cls, item: Any, language: str) -> Optional[Dict]:
        if isinstance(item, str) and item.strip():
            path = item.strip().replace("\\", "/")
            return {
                "path": path,
                "description": "",
                "priority": 3,
                "file_type": "unknown",
                "language": language,
                "imports": [],
            }
        if not isinstance(item, dict):
            return None
        path = item.get("path") or item.get("file") or item.get("filename") or item.get("name")
        if not path or not isinstance(path, str):
            return None
        path = path.strip().replace("\\", "/")
        if not path or path in {".", ".."}:
            return None
        looks_like_file = (
            "." in Path(path).name
            or "/" in path
            or path.lower() in {"makefile", "dockerfile", "gemfile", "go.mod", "cargo.toml"}
        )
        if not looks_like_file:
            return None
        normalized = dict(item)
        normalized["path"] = path
        normalized.setdefault("description", "")
        normalized.setdefault("priority", 3)
        normalized.setdefault("file_type", "unknown")
        normalized.setdefault("language", language)
        normalized.setdefault("imports", [])
        return normalized

    @classmethod
    def _normalize_file_plan(cls, items: Any, language: str) -> List[Dict]:
        if not isinstance(items, list):
            return []
        normalized = []
        seen: Set[str] = set()
        for item in items:
            entry = cls._normalize_file_plan_item(item, language)
            if not entry or entry["path"] in seen:
                continue
            seen.add(entry["path"])
            normalized.append(entry)
        return normalized

    @classmethod
    def _harvest_file_plan(cls, obj: Any, language: str, depth: int = 0, seen: Optional[Set[int]] = None) -> List[Dict]:
        if depth > 5 or obj is None:
            return []
        seen = seen if seen is not None else set()
        obj_id = id(obj)
        if obj_id in seen:
            return []
        seen.add(obj_id)
        if isinstance(obj, list):
            normalized = cls._normalize_file_plan(obj, language)
            if normalized:
                return normalized
            for item in obj:
                harvested = cls._harvest_file_plan(item, language, depth + 1, seen)
                if harvested:
                    return harvested
            return []
        if not isinstance(obj, dict):
            return []
        for key in cls._FILE_PLAN_KEYS:
            if key in obj:
                harvested = cls._harvest_file_plan(obj[key], language, depth + 1, seen)
                if harvested:
                    return harvested
        for key in cls._FILE_PLAN_NEST_KEYS:
            if key in obj:
                harvested = cls._harvest_file_plan(obj[key], language, depth + 1, seen)
                if harvested:
                    return harvested
        return []

    def _ensure_architecture_file_plan(
        self,
        architecture: Dict,
        requirement: str,
        complexity: ComplexityAnalysis,
        target_language: str,
        frontend_language: Optional[str],
    ) -> Dict:
        if isinstance(architecture.get("file_plan"), str):
            architecture["file_plan"] = self._parse_jsonish(architecture["file_plan"])
        harvested = self._harvest_file_plan(architecture, target_language)
        if harvested:
            architecture["file_plan"] = harvested
            self._drop_stale_file_plan_aliases(architecture)
            return architecture
        existing = architecture.get("file_plan")
        if isinstance(existing, list) and self._normalize_file_plan(existing, target_language):
            architecture["file_plan"] = self._normalize_file_plan(existing, target_language)
            self._drop_stale_file_plan_aliases(architecture)
            return architecture
        logger.warning("架构师未返回 file_plan，补入默认文件计划并保留已解析字段")
        default = self._get_requirement_aware_default_architecture(
            requirement, complexity, target_language, frontend_language
        )
        architecture["file_plan"] = default["file_plan"]
        architecture["used_default_file_plan"] = True
        if not architecture.get("project_spec"):
            architecture["project_spec"] = default.get("project_spec")
        if not architecture.get("tech_stack"):
            architecture["tech_stack"] = default.get("tech_stack")
        architecture.setdefault("language", target_language)
        architecture.setdefault("requirement", requirement)
        self._drop_stale_file_plan_aliases(architecture)
        return architecture

    def _parse_jsonish(self, value: Any) -> Any:
        """Parse LLM JSON-in-string values; leave prose strings unchanged."""
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return value
        looks_like_json = text[0] in "{[" or text.startswith("```")
        if not looks_like_json:
            return value
        try:
            return self.json_parser.safe_parse_json(text)
        except Exception:
            try:
                return json.loads(text)
            except Exception:
                return value

    def _canonicalize_interfaces(self, value: Any) -> Any:
        parsed = self._parse_jsonish(value)
        if parsed is None:
            return {}
        if isinstance(parsed, list):
            return parsed
        if not isinstance(parsed, dict):
            return {}
        if "module" in parsed or "path" in parsed:
            return parsed
        if isinstance(parsed.get("entries"), list):
            return parsed["entries"]
        if parsed and all(isinstance(item, dict) for item in parsed.values()):
            entries = []
            for name, spec in parsed.items():
                entry = dict(spec)
                entry.setdefault("module", name)
                entry.setdefault("owner", name)
                if "exports" in entry and "symbols" not in entry:
                    entry["symbols"] = entry["exports"]
                entries.append(entry)
            return entries
        return parsed

    def _coerce_architecture_fields(self, architecture: Any) -> Dict:
        """Turn GLM string-shaped objects into dict/list before downstream .get()."""
        if not isinstance(architecture, dict):
            return {}
        architecture = dict(architecture)
        mapping_keys = (
            "project_spec",
            "api_spec",
            "db_schema",
            "interfaces",
            "frontend_structure",
            "backend_structure",
        )
        for key in mapping_keys:
            if key not in architecture:
                continue
            parsed = self._parse_jsonish(architecture[key])
            if isinstance(parsed, dict):
                architecture[key] = parsed
            elif isinstance(parsed, list) and key == "interfaces":
                architecture[key] = parsed
        architecture["interfaces"] = self._canonicalize_interfaces(architecture.get("interfaces"))
        for key in ("file_plan", "dependencies", "tech_stack"):
            if key not in architecture:
                continue
            parsed = self._parse_jsonish(architecture[key])
            if isinstance(parsed, (list, dict)):
                architecture[key] = parsed
        file_plan = architecture.get("file_plan")
        if isinstance(file_plan, list):
            for item in file_plan:
                if not isinstance(item, dict):
                    continue
                if isinstance(item.get("contract"), str):
                    contract = self._parse_jsonish(item["contract"])
                    item["contract"] = contract if isinstance(contract, dict) else {}
                if isinstance(item.get("imports"), str):
                    imports = self._parse_jsonish(item["imports"])
                    if isinstance(imports, list):
                        item["imports"] = imports
                    elif item["imports"].strip():
                        item["imports"] = [item["imports"]]
                    else:
                        item["imports"] = []
        return architecture

    def _canonicalize_architecture(
        self,
        architecture: Any,
        requirement: str,
        complexity: ComplexityAnalysis,
        target_language: str,
        frontend_language: Optional[str],
    ) -> Dict:
        """Single export shape for design_architecture: objects, not JSON strings."""
        if not isinstance(architecture, dict) or not architecture:
            architecture = self._get_requirement_aware_default_architecture(
                requirement, complexity, target_language, frontend_language
            )
        architecture = self._coerce_architecture_fields(architecture)
        architecture.setdefault("language", target_language)
        architecture.setdefault("frontend_language", frontend_language)
        architecture.setdefault("requirement", requirement)
        if not isinstance(architecture.get("project_spec"), dict) or not architecture.get("project_spec"):
            architecture["project_spec"] = self._build_default_project_spec(
                target_language, frontend_language, complexity
            )
        if not isinstance(architecture.get("api_spec"), dict):
            architecture["api_spec"] = {}
        if not isinstance(architecture.get("db_schema"), dict):
            architecture["db_schema"] = {}
        if not isinstance(architecture.get("interfaces"), (dict, list)):
            architecture["interfaces"] = {}
        if not isinstance(architecture.get("dependencies"), (dict, list)):
            architecture["dependencies"] = {}
        return self._ensure_architecture_file_plan(
            architecture, requirement, complexity, target_language, frontend_language
        )

    @classmethod
    def _drop_stale_file_plan_aliases(cls, architecture: Dict) -> None:
        """Keep a single canonical file_plan so scaffolds cannot read leftover nested files."""
        for key in cls._FILE_PLAN_KEYS:
            if key != "file_plan":
                architecture.pop(key, None)
        for nest in cls._FILE_PLAN_NEST_KEYS:
            nested = architecture.get(nest)
            if isinstance(nested, dict):
                for key in cls._FILE_PLAN_KEYS:
                    nested.pop(key, None)

    def _get_default_architecture(self, complexity: ComplexityAnalysis, language: str = "python", frontend_language: Optional[str] = None) -> Dict:
        """返回默认架构（根据语言生成）"""
        from app.agent.language_detector import LanguageDetector
        lang_rules = LanguageDetector.get_language_specific_rules(language)

        # 根据语言生成不同的默认文件结构
        if language == "python":
            entry_point = "main.py"
        elif language == "javascript":
            entry_point = "src/index.ts"
        elif language == "go":
            entry_point = "main.go"
        elif language == "java":
            entry_point = "src/main/java/com/example/Application.java"
        elif language == "rust":
            entry_point = "src/main.rs"
        else:
            # 通用结构
            ext = lang_rules.get('file_extension')
            if ext:
                ext_name = ext.lstrip('.')
            else:
                ext_name = language  # 未知语言使用语言名作为扩展名
            entry_point = f"main.{ext_name}"

        file_plan = [
            {"path": entry_point, "description": "主程序入口", "priority": 1, "file_type": "entry", "language": language, "imports": []},
        ]

        return {
            "project_type": (
                "fullstack" if complexity.has_frontend and complexity.has_backend
                else "frontend" if complexity.has_frontend
                else "backend" if complexity.has_backend
                else "script"
            ),
            "tech_stack": complexity.key_technologies,
            "language": language,
            "frontend_language": frontend_language,
            "backend_language": language,
            "all_languages": [l for l in set([language, frontend_language]) if l],
            "file_plan": file_plan,
            "project_spec": self._build_default_project_spec(language, frontend_language, complexity),
            "dependencies": {},
            "api_spec": {},
            "db_schema": {},
            "risks": complexity.risk_factors
        }

    def _get_compact_eight_file_architecture(
        self,
        requirement: str,
        complexity: ComplexityAnalysis,
        language: str = "python",
        frontend_language: Optional[str] = None,
    ) -> Dict:
        """实测用精简 8 文件架构，跳过 LLM 架构师与分批扩展。"""
        architecture = self._get_default_architecture(complexity, language, frontend_language)
        architecture["requirement"] = requirement
        architecture["used_default_architecture"] = True
        architecture["used_compact_eight_file_plan"] = True

        if language == "python":
            keep_order = [
                "main.py",
                "requirements.txt",
                "README.md",
                "app/database.py",
                "app/models.py",
                "app/services.py",
                "app/routers.py",
                "tests/test_app.py",
            ]
            descriptions = {
                "main.py": "FastAPI 入口，注册路由并启动服务",
                "requirements.txt": "依赖清单，包含运行与测试所需包",
                "README.md": "说明启动方式和测试命令",
                "app/database.py": "SQLite 连接、建表与会话",
                "app/models.py": "User、Ticket、AuditLog 模型与工单状态枚举",
                "app/services.py": "注册登录密码哈希、工单 CRUD/筛选/指派/关闭、权限、状态机与审计日志",
                "app/routers.py": "用户鉴权与工单 HTTP 接口",
                "tests/test_app.py": "覆盖鉴权失败、越权访问、非法状态流转、正常关闭",
            }
            imports = {
                "main.py": ["app/routers.py"],
                "requirements.txt": [],
                "README.md": [],
                "app/database.py": [],
                "app/models.py": ["app/database.py"],
                "app/services.py": ["app/models.py", "app/database.py"],
                "app/routers.py": ["app/services.py", "app/models.py"],
                "tests/test_app.py": ["main.py"],
            }
            file_types = {
                "main.py": "entry",
                "requirements.txt": "config",
                "README.md": "docs",
                "app/database.py": "database",
                "app/models.py": "model",
                "app/services.py": "service",
                "app/routers.py": "api",
                "tests/test_app.py": "test",
            }
            existing = {item.get("path"): item for item in architecture.get("file_plan", [])}
            compact = []
            for path in keep_order:
                item = dict(existing.get(path) or {"path": path, "priority": 3, "language": language})
                item["path"] = path
                item["description"] = descriptions[path]
                item["imports"] = list(imports[path])
                item["file_type"] = file_types[path]
                item["language"] = language
                compact.append(item)
            architecture["file_plan"] = compact
        else:
            architecture["file_plan"] = list(architecture.get("file_plan") or [])[:8]

        requirement_lower = requirement.lower()
        default_spec = architecture["project_spec"]["default"]
        if re.search(r"ticket|工单", requirement_lower):
            if language == "python":
                default_spec["framework"] = "FastAPI"
            default_spec["terminology"] = {
                "ticket": "Ticket",
                "title": "Title",
                "description": "Description",
                "status": "Status",
                "priority": "Priority",
                "assignee": "Assignee",
            }
            default_spec["storage"] = {
                "type": "sqlite",
                "filename": "tickets.db",
                "backend": "sqlalchemy",
            }
            default_spec["auth"] = {"scheme": "jwt_hs256"}
            architecture["db_schema"] = {
                "tickets": {
                    "columns": {
                        "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
                        "title": "TEXT NOT NULL",
                        "description": "TEXT",
                        "status": "TEXT NOT NULL DEFAULT 'open'",
                        "priority": "TEXT NOT NULL DEFAULT 'medium'",
                        "assignee": "TEXT",
                    }
                }
            }
        from app.agent.symbol_table import freeze_symbol_table
        freeze_symbol_table(architecture)
        return architecture

    def _domain_file_plan(self, language: str, domain: str) -> List[Dict]:
        """默认架构中按领域补充分层文件。"""
        extensions = {
            "python": "py",
            "javascript": "js",
            "typescript": "ts",
            "go": "go",
            "java": "java",
            "rust": "rs",
        }
        ext = extensions.get(language, "py")
        if language == "go":
            prefix = "internal/"
        elif language in ("javascript", "typescript"):
            prefix = "src/"
        elif language == "python":
            prefix = "app/"
        else:
            prefix = ""
        entries = [
            (f"{prefix}models/{domain}_model.{ext}", "model", 2, f"{domain} 数据模型"),
            (f"{prefix}repositories/{domain}_repository.{ext}", "repository", 3, f"{domain} 数据访问"),
            (f"{prefix}services/{domain}_service.{ext}", "service", 3, f"{domain} 业务逻辑"),
            (f"{prefix}controllers/{domain}_controller.{ext}", "api", 3, f"{domain} HTTP 接口"),
            (f"{prefix}tests/test_{domain}.{ext}", "test", 5, f"{domain} 自动化测试"),
        ]
        return [
            {
                "path": path,
                "description": description,
                "priority": priority,
                "file_type": file_type,
                "language": language,
                "imports": [],
            }
            for path, file_type, priority, description in entries
        ]

    def _get_requirement_aware_default_architecture(
        self,
        requirement: str,
        complexity: ComplexityAnalysis,
        language: str = "python",
        frontend_language: Optional[str] = None,
    ) -> Dict:
        """架构输出异常时保留需求中明确列出的项目文件。"""
        architecture = self._get_default_architecture(complexity, language, frontend_language)
        architecture["requirement"] = requirement
        architecture["used_default_architecture"] = True
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

        strict_paths = self._extract_strict_file_paths(requirement)
        return self._ensure_file_plan_completeness(
            architecture,
            language,
            strict_paths=strict_paths,
            complexity=complexity,
        )

    def _build_default_project_spec(self, language: str, frontend_language: Optional[str], complexity: ComplexityAnalysis) -> Dict:
        """解析失败时的空 project_spec，不发明框架或存储。"""
        return {"default": {"terminology": {}}}

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
    def _is_external_module(adapter, name: str) -> bool:
        if not name or adapter is None:
            return False
        checker = getattr(adapter, "is_known_external_module", None)
        return bool(checker and checker(name))

    @staticmethod
    def _extract_strict_file_paths(requirement: str) -> Optional[set]:
        """识别需求中明确限定的文件集合。"""
        if not requirement:
            return None
        file_pat = r"[\w./-]+\.(?:py|js|ts|jsx|tsx|vue|html|css|scss|json|yaml|yml|toml|xml|go|java|rs)"
        match = re.search(r"(?:只需要|仅需要|只要|only)\s*(.{1,300}?)(?:个|份)?\s*文件", requirement, re.IGNORECASE)
        if not match:
            match = re.search(
                r"(?:只生成|仅生成)\s*(?:以下\s*)?(?:\d+\s*个\s*)?(.{1,300}?)(?:。|$)",
                requirement,
                re.IGNORECASE,
            )
        if not match:
            match = re.search(
                r"generate\s+exactly\s+(?:these|the following)\s+files(?:\s+and\s+no\s+others)?\s*:\s*(.{1,500}?)(?=\.\s+(?-i:[A-Z])|$)",
                requirement,
                re.IGNORECASE,
            )
        if not match:
            return None
        blob = match.group(1)
        after = requirement[match.end():match.end() + 200]
        paths = set(re.findall(file_pat, blob + " " + after))
        if not paths:
            paths = set(re.findall(file_pat, requirement))
        return paths or None

    @staticmethod
    def _skip_boilerplate_files(complexity: Optional[Any]) -> bool:
        if not complexity:
            return False
        if isinstance(complexity, dict):
            level = complexity.get("level") or ""
            estimated = complexity.get("estimated_files") or 0
        else:
            level = getattr(complexity, "level", "")
            estimated = getattr(complexity, "estimated_files", 0) or 0
        if hasattr(level, "value"):
            level = level.value
        try:
            estimated = int(estimated)
        except (TypeError, ValueError):
            estimated = 0
        return str(level).lower() == "simple" and estimated <= 1

    def _ensure_file_plan_completeness(
        self,
        architecture: Dict,
        target_language: Optional[str] = None,
        strict_paths: Optional[set] = None,
        complexity: Optional[Any] = None,
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
            architecture["strict_file_paths"] = sorted(strict_paths)
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

        kept_plan = []
        for item in file_plan:
            path = item.get("path", "")
            if self._is_external_module(adapter, path):
                logger.info("从 file_plan 移除第三方路径: %s", path)
                continue
            kept_plan.append(item)
        if len(kept_plan) != len(file_plan):
            file_plan = kept_plan
            architecture["file_plan"] = file_plan

        # 提取所有已规划的文件路径（安全访问，避免 KeyError）
        planned_paths = {f["path"] for f in file_plan if "path" in f}

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
            if self._is_external_module(adapter, module):
                logger.info("跳过外部模块，不写入 file_plan: %s", module)
                continue
            import_info = ImportInfo(module=module, symbols=[], is_relative=False)
            candidates = adapter.resolve_import_to_file(import_info, "")

            exists = any(c in planned_paths for c in candidates)

            if not exists and candidates:
                file_path = candidates[0]
                # 验证文件路径是否合法（不包含空格或特殊字符）
                if ' ' in file_path or ',' in file_path:
                    logger.warning(f"跳过非法文件路径: {file_path}")
                    continue
                if self._is_external_module(adapter, file_path):
                    logger.info("跳过外部模块路径，不写入 file_plan: %s", file_path)
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
        strict_paths = architecture.get("strict_file_paths")
        if strict_paths:
            logger.info("严格文件集合已冻结，跳过 file_plan 扩展: %s", strict_paths)
            return architecture
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
        architecture = self._ensure_file_plan_completeness(
            architecture, target_language, complexity=complexity
        )
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

        requirement_text = (architecture.get("requirement") or "").strip()
        if not requirement_text:
            requirement_text = architecture.get("project_type", "未知项目")

        prompt = f"""请为以下项目补充文件规划。

需求：{requirement_text}
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
9. 避免同名文件：新文件不要与已有文件同名，使用更具描述性的名称（如 user_model.py 而非 user.py）
10. 补充文件必须覆盖需求中的核心业务对象，保持与需求领域一致
11. 不要把第三方库或标准库写成项目文件路径"""

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
