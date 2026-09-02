import json
import logging
import re
from typing import Dict, Optional, Any

from app.agent.specialist_base import Specialist
from app.utils.prompt_loader import load_backend_engineer_prompt
from app.agent.tracing import traced
from app.agent.language_detector import LanguageDetector

logger = logging.getLogger(__name__)


class BackendEngineer(Specialist):
    """后端工程师 - 专注后端代码生成"""

    @property
    def SYSTEM_PROMPT(self) -> str:
        # 优先从注册表获取用户自定义版本
        try:
            from app.services.skill_registry import get_skill
            custom_prompt = get_skill("backend_engineer_prompt")
            if custom_prompt:
                return custom_prompt
        except Exception:
            pass
        
        # 否则使用默认加载逻辑
        prompt = load_backend_engineer_prompt()
        if prompt is None:
            logger.error("后端工程师提示词加载失败，使用兜底提示词")
            return self._fallback_prompt()
        return prompt

    def _fallback_prompt(self) -> str:
        return """你是一位世界级后端工程师，精通所有主流后端编程语言和框架。
你的职责：创建后端文件、实现 API 端点、数据库模型、业务逻辑、错误处理。
规则：每次只创建一个文件，代码必须完整可运行，包含错误处理和类型注解。"""

    @staticmethod
    def _infer_file_type_from_path(file_path: str) -> str:
        """从文件路径推断 file_type"""
        path_lower = file_path.lower()
        if 'model' in path_lower:
            return 'model'
        if 'api' in path_lower or 'router' in path_lower or 'handler' in path_lower or 'controller' in path_lower:
            return 'api'
        if 'service' in path_lower:
            return 'service'
        if 'repo' in path_lower or 'repository' in path_lower or 'dao' in path_lower:
            return 'repository'
        if path_lower.endswith('crud.py') or '/crud/' in path_lower:
            return 'repository'
        if 'schema' in path_lower or 'dto' in path_lower:
            return 'schema'
        if 'database' in path_lower or 'db' in path_lower:
            return 'database'
        if 'config' in path_lower or 'settings' in path_lower:
            return 'config'
        if 'middleware' in path_lower:
            return 'middleware'
        if 'test' in path_lower:
            return 'test'
        if 'util' in path_lower or 'helper' in path_lower:
            return 'utils'
        if 'main' in path_lower or 'app' in path_lower or 'index' in path_lower:
            return 'entry'
        return 'unknown'

    @staticmethod
    def _build_spec_constraints(file_type: str, file_spec: Dict) -> str:
        """构建 project_spec 约束文本"""
        if not file_spec:
            return ""

        lines = []
        storage = file_spec.get("storage", {})
        terminology = file_spec.get("terminology", {})
        framework = file_spec.get("framework")

        if framework:
            lines.append(f"【框架约束 - 必须遵守】")
            lines.append(f"- 本项目统一使用 {framework} 框架")
            lines.append(f"- 所有后端文件必须使用 {framework} 的 API 和导入方式")
            lines.append(f"- 禁止混用其他框架（如 Flask、Django、Tornado 等）")
            lines.append(f"- requirements.txt / go.mod 等依赖文件必须包含 {framework} 的依赖")
            lines.append("")

        if storage:
            storage_type = storage.get("type", "unknown")
            lines.append(f"【存储约束 - 必须遵守】")
            lines.append(f"- 存储方式: {storage_type}")
            if storage.get("filename"):
                lines.append(f"- 存储文件: {storage['filename']}")
            if storage_type == "localStorage":
                lines.append(f"- 注意：localStorage 是浏览器 API，后端文件禁止使用，请使用文件存储或数据库替代")
            lines.append("")

        if terminology:
            lines.append(f"【术语约束 - 必须遵守】")
            lines.append(f"- 项目统一使用以下术语（字段名、变量名、API 路径必须遵循）:")
            for en_term, actual_term in terminology.items():
                lines.append(f"  - {en_term} -> {actual_term}")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _build_file_scope_constraints(file_path: str, architecture: Dict) -> str:
        """构建架构文件集合和项目内导入约束。"""
        planned_files = [
            item.get("path", "")
            for item in architecture.get("file_plan", [])
            if isinstance(item, dict) and item.get("path")
        ]
        if not planned_files:
            return ""

        normalized_path = file_path.replace("\\", "/")
        if "/" in normalized_path:
            import_style = "包内项目文件使用相对导入，例如 from .models import Todo。"
        else:
            import_style = "同目录项目文件使用顶层绝对导入，例如 from models import Todo。"

        return "\n".join([
            "【项目文件集合 - 严格遵守】",
            f"- 架构声明的完整文件集合：{', '.join(planned_files)}",
            "- 项目内模块只能从上述文件集合导入。",
            "- 所需路由、端点和业务逻辑必须在上述文件集合内实现。",
            f"- {import_style}",
        ])

    @staticmethod
    def _get_file_contract(file_path: str, architecture: Dict) -> Dict:
        normalized = file_path.replace("\\", "/")
        for item in architecture.get("file_plan", []):
            if isinstance(item, dict) and item.get("path", "").replace("\\", "/") == normalized:
                contract = item.get("contract", {})
                return contract if isinstance(contract, dict) else {}
        return {}

    @classmethod
    def _build_contract_constraints(cls, file_path: str, architecture: Dict) -> str:
        contract = cls._get_file_contract(file_path, architecture)
        if not contract:
            return ""
        lines = ["【架构职责契约 - 必须遵守】"]
        for key, label in (("role", "职责"), ("runtime", "运行时"), ("database_abstraction", "数据库抽象")):
            if contract.get(key):
                lines.append(f"- {label}: {contract[key]}")
        for key, label in (("exports", "必须导出的公共符号"), ("required_imports", "必须满足的导入"),
                           ("forbidden_imports", "禁止导入"), ("shared_symbols", "必须复用的共享符号")):
            values = contract.get(key, [])
            if values:
                values = values if isinstance(values, list) else [values]
                lines.append(f"- {label}: {', '.join(map(str, values))}")
        if contract.get("notes"):
            lines.append(f"- 补充约束: {contract['notes']}")
        return "\n".join(lines)

    @staticmethod
    def _build_runtime_consistency_constraints(
        file_path: str, file_type: str, project_language: str, architecture: Dict
    ) -> str:
        """构建跨文件运行时和测试 API 一致性约束。"""
        if project_language.lower() != "python":
            return ""

        framework = str(architecture.get("framework", "")).lower()
        project_spec = architecture.get("project_spec", {})
        if isinstance(project_spec, dict):
            framework = framework or str(project_spec.get("framework", "")).lower()

        planned_items = [
            item
            for item in architecture.get("file_plan", [])
            if isinstance(item, dict) and item.get("path")
        ]

        def item_type(item: Dict) -> str:
            contract = item.get("contract", {})
            contract_role = contract.get("role") if isinstance(contract, dict) else ""
            return str(
                item.get("file_type")
                or contract_role
                or BackendEngineer._infer_file_type_from_path(str(item.get("path", "")))
            ).lower()

        def planned_path(*roles: str) -> str:
            return next(
                (
                    str(item["path"])
                    for item in planned_items
                    if item_type(item) in roles
                ),
                "",
            )

        database_path = planned_path("database", "persistence", "storage") or "database.py"
        model_path = planned_path("model", "entity", "entities") or "models.py"
        database_module = database_path.replace("\\", "/").removesuffix(".py").replace("/", ".")

        lines = [
            "【Python 运行时一致性 - 必须遵守】",
            "- 每个被引用的项目模块、类、函数和变量都必须显式导入，且导入来源必须与依赖文件的实际定义一致。",
            "- 同名符号只能从一个模块导入；模型类与 Schema 类重名时必须使用明确别名。",
            "- 同一调用链的同步/异步风格必须一致：async 函数必须 await，普通函数禁止 await。",
            "- 只能调用依赖文件中已经存在的方法、装饰器和导出符号，禁止臆造接口。",
        ]
        if file_type == "repository":
            lines.extend([
                "- 必须导入并复用 database、model、schema 依赖中的现有定义，禁止复制或重新定义这些依赖的类和函数。",
                "- 调用依赖函数时必须严格匹配其参数类型、参数顺序和返回值；CRUD 返回值必须可供 API 层直接判断和序列化。",
                f"- 数据库访问必须与 {database_path} 采用同一抽象层；SQLAlchemy Session 与原生 sqlite3 Connection 禁止混用。",
            ])
            contract = BackendEngineer._get_file_contract(file_path, architecture)
            declared_exports = contract.get("exports", [])
            if isinstance(declared_exports, str):
                declared_exports = [declared_exports]
            if declared_exports:
                lines.extend([
                    f"- 架构契约要求当前模块直接导出公共符号：{', '.join(map(str, declared_exports))}。",
                    "- 仓储公共函数必须实现真实持久化操作，并可由入口层直接导入调用。",
                    "- CRUD 只能读取请求 Schema 实际声明的字段；数据库生成的 id、created_at、updated_at 等字段由模型默认值负责，禁止从未声明的请求字段读取。",
                ])
        if file_type == "model":
            lines.extend([
                f"- {database_path} 已提供 SQLAlchemy Base 时，模型必须通过 from {database_module} import Base 复用同一元数据注册表。",
                f"- 禁止在 {file_path} 中再次调用 declarative_base() 创建独立 Base。",
                "- API 创建资源时不会提交主键；主键必须使用自增 Integer，或提供可序列化的 UUID 默认值。",
                "- created_at、updated_at 等时间列存在时必须提供 datetime 默认值，并与响应 Schema 的类型和可空性一致。",
            ])
        if file_type in {"schema", "types"}:
            lines.extend([
                "- 请求 Schema 只声明客户端可提交字段；数据库生成的主键和时间字段只出现在响应 Schema。",
                "- 响应 Schema 的字段类型、可空性和默认值必须逐项匹配依赖源码中的 ORM 模型列。",
                "- Pydantic 响应模型必须启用从 ORM 属性读取数据的配置。",
            ])
        if file_type == "database":
            lines.extend([
                "- FastAPI TestClient 可能跨线程调用数据库；SQLite 连接必须按请求/调用创建并关闭，或明确使用 check_same_thread=False，并保证提交和关闭安全。",
                "- database.py 必须导出与依赖文件实际使用一致的连接获取接口，禁止让单个初始化线程创建的连接直接跨线程复用。",
                "- 整个项目必须统一选择 SQLAlchemy 或原生 sqlite3；使用 SQLAlchemy 模型时，database.py 必须导出同一个 Base、engine、SessionLocal 和可关闭 Session 的 get_db。",
                "- get_db 使用 @contextmanager 时，调用方必须使用 with get_db() as db；作为 FastAPI yield 依赖时，调用方必须使用 Depends(get_db)。",
            ])
            if (
                project_language.lower() == "python"
                and framework == "fastapi"
                and any(item_type(item) in {"model", "entity", "entities"} for item in planned_items)
            ):
                lines.extend([
                    "- 当前项目包含模型层；数据库层统一采用 SQLAlchemy，禁止在同一文件中导入或调用 sqlite3。",
                    "- 当前数据库文件是依赖基础层，禁止导入模型、仓储、Schema 或任何下游项目模块。",
                    "- 数据库文件必须定义并导出 Base = declarative_base()、engine、SessionLocal 和 get_db，供模型层复用同一 Base。",
                    "- 数据库文件只提供数据库基础设施；禁止创建 Web 应用、声明路由或引用未定义的框架符号。",
                    f"- 当前模型文件为 {model_path}；数据库层禁止导入该模型文件或其他下游项目模块。",
                ])
        if file_type == "entry":
            lines.extend([
                "- FastAPI startup 和 shutdown 事件函数不得声明框架不会注入的参数。",
                "- response_model 必须与实际返回值匹配；创建、读取、更新、删除端点必须返回可序列化的真实资源或明确状态码。",
                "- 数据库初始化和 CRUD 调用必须严格使用依赖源码中的真实函数签名。",
                "- get_db 返回生成器或上下文管理器时，必须通过 Depends(get_db) 或 with get_db() as db 获取真实会话，禁止把包装对象当作 Session。",
            ])
            planned_types = {item_type(item) for item in planned_items}
            if "repository" in planned_types:
                lines.append(
                    "- 入口层调用仓储模块的命名空间或符号前，必须显式导入架构声明的仓储文件，并使用其真实导出接口。"
                )
            if project_language.lower() == "python":
                route_modules = [
                    str(item["path"])
                    for item in planned_items
                    if str(item["path"]) != file_path
                    and item_type(item) in {"api", "router", "routes"}
                ]
                if not route_modules:
                    lines.extend([
                        f"- 当前文件集合未声明独立路由层；所有 API 路由必须直接定义在 {file_path}，禁止导入未声明的路由模块。",
                    ])
                if planned_path("database", "persistence", "storage"):
                    lines.extend([
                        f"- 使用数据库 engine、SessionLocal 或 get_db 前，必须从 {database_path} 显式导入，并严格使用其实际导出符号。",
                    ])
                lines.append(
                    "- 同一资源集合的所有方法必须使用需求指定的同一个规范路径；需求为 /api/v1/todos 时，GET、POST 均使用 /api/v1/todos，禁止单独添加尾斜杠。"
                )
        if file_type == "test" or "test" in file_path.lower():
            lines.extend([
                "- pytest fixture、测试函数和客户端调用的同步/异步风格必须一致。",
                "- 文件持久化测试必须使用 tmp_path 创建真实临时文件，并用 pytest monkeypatch 替换存储路径解析函数或路径常量。",
                "- 禁止 patch 或 mock builtins.open、pathlib.Path、os.path.exists、json.load、json.dump；连续 CRUD 操作必须读写同一个真实临时文件。",
                "- 需求指定 monkeypatch 时必须直接使用 pytest 的 monkeypatch fixture，禁止用 unittest.mock.patch 或 MagicMock 替代。",
                "- monkeypatch 文件路径时必须导入模块（例如 import todo）并使用 monkeypatch.setattr(todo, '_get_storage_path', lambda: str(tmp_path / 'data.json'))；禁止给导入到测试局部作用域的函数名重新赋值。",
                "- 测试函数或 fixture 必须声明 monkeypatch 参数并直接调用 monkeypatch.setattr；禁止实例化 pytest.MonkeyPatch，禁止使用 with pytest.MonkeyPatch()，因为该对象不提供上下文管理器协议。",
                "- 每个文件持久化测试的函数签名必须包含 (tmp_path, monkeypatch)，函数体直接使用 monkeypatch.setattr(todo, '_get_storage_path', ...)；不要创建任何 MonkeyPatch 对象。",
                "- fixture 必须声明 monkeypatch 依赖并在 fixture 结束后由 pytest 自动恢复；禁止手动保存和恢复被 patch 的符号，禁止在 fixture 中删除 tmp_path 内容。",
                "- 持久化状态断言必须在每个操作后重新调用 list_todos() 或从文件重新读取，不能检查操作前保留的对象列表。",
                "- pytest 测试函数必须直接定义在模块顶层，禁止把 test_* 函数嵌套在另一个函数或条件块中。",
                "- 模块直接执行入口只能调用 pytest 或 raise SystemExit(main())；禁止在模块顶层使用 return。",
                "- 测试文件只定义 pytest 测试和必要 fixture，不要额外创建一个包裹全部测试的 test_main 函数。",
                "- FastAPI 同步测试优先使用 fastapi.testclient.TestClient。",
                "- 测试断言必须匹配入口模块的实际路径、状态码以及 CRUD 函数的真实签名和返回值。",
                "- SQLite CRUD 测试必须调用真实 API 和临时数据库验证持久化，禁止 mock 或 patch CRUD 函数。",
                "- 调用 init_database、get_db 等依赖函数前必须逐项核对依赖源码参数；依赖未提供数据库路径参数时禁止自行传入。",
                f"- 测试必须复用已生成 {database_path} 的 engine、Base、SessionLocal 或 get_db；禁止引入依赖源码中未出现的数据库包。",
                "- 每个测试中引用的 Schema、fixture 和客户端变量都必须在模块顶层显式导入或定义。",
            ])
            if framework == "fastapi":
                lines.extend([
                    "- 使用 httpx.AsyncClient 时必须传入 httpx.ASGITransport(app=app) 作为 transport。",
                    "- 禁止从 httpx 导入 ASGIApp，禁止向 AsyncClient 传入 app 参数。",
                ])
        return "\n".join(lines)

    @staticmethod
    def _build_dependency_import_constraints(dep_context: str) -> str:
        """限制项目内导入只能指向当前拓扑层已经生成的依赖。"""
        dependency_files = []
        for match in re.finditer(r"^## 依赖文件:\s*(.+?)\s*$", dep_context, re.MULTILINE):
            dependency_files.append(match.group(1).strip())

        if not dependency_files:
            return "\n".join([
                "【项目内导入白名单 - 最高优先级】",
                "- 当前文件没有已生成的上游依赖，禁止导入任何其他项目文件。",
                "- 当前文件必须作为独立基础层实现，供后续文件导入。",
            ])

        return "\n".join([
            "【项目内导入白名单 - 最高优先级】",
            f"- 当前文件只允许导入这些已生成项目文件：{', '.join(dependency_files)}",
            "- 禁止导入白名单之外的项目文件，避免逆向依赖和循环导入。",
            "- 导入前必须依据下方依赖源码核对真实导出符号。",
        ])

    @staticmethod
    def _build_interface_constraints(dep_context: str) -> str:
        """把依赖签名提升为不可变的跨文件接口事实。"""
        interface_lines = []
        for block in re.split(r"(?=^## 依赖文件:)", dep_context, flags=re.MULTILINE):
            match = re.search(r"^## 依赖文件:\s*(.+?)\s*$", block, re.MULTILINE)
            if not match:
                continue
            signatures = [
                line.strip()
                for line in block.splitlines()
                if re.match(r"^\s*(?:async\s+)?def\s+|^\s*class\s+", line)
            ]
            if signatures:
                interface_lines.append(f"- {match.group(1)}: {'; '.join(signatures)}")
        if not interface_lines:
            return ""
        return "\n".join([
            "【跨文件接口事实 - 最高优先级】",
            "- 以下签名来自已生成依赖文件，必须原样遵守，尤其是返回类型和类字段。",
            *interface_lines,
            "- 返回对象类型使用属性访问（例如 todo.id、todo.title）；返回字典类型才使用下标访问（例如 item['id']）。",
            "- 调用方的测试、服务和入口代码必须与被调用函数的实际返回类型保持一致。",
            "- 以下划线开头的函数、类和变量属于模块私有实现，跨文件调用方禁止导入或调用；只能使用公共导出符号。",
        ])

    @traced("backend.generate_file", attributes={"component": "specialist", "role": "backend"})
    async def generate_file(
        self,
        file_path: str,
        description: str,
        project_context: Dict,
        spec_context: str = "",
        dep_context: str = "",
        project_path: Optional[str] = None,
        callback: Optional[Any] = None,
        is_existing_file: bool = False,
        heartbeat_tracker=None,
    ) -> str:
        # 从 project_context 中提取语言信息
        architecture = project_context.get("architecture", {})
        project_language = architecture.get("language", "python")

        # 根据文件路径动态决定此文件的实际语言（避免配置文件被错误标记）
        from app.agent.utils import get_expected_language_for_file
        file_actual_language = get_expected_language_for_file(file_path, project_language)
        if not file_actual_language:
            file_actual_language = project_language
        lang_rules = LanguageDetector.get_language_specific_rules(project_language)

        # 从 project_spec 中提取当前文件的约束
        project_spec = architecture.get("project_spec", {})
        file_plan_item = next(
            (item for item in architecture.get("file_plan", [])
             if isinstance(item, dict) and item.get("path", "").replace("\\", "/") == file_path.replace("\\", "/")),
            {},
        )
        file_type = file_plan_item.get("file_type") or self._infer_file_type_from_path(file_path)
        file_spec = project_spec.get(file_type, project_spec.get("default", {}))
        spec_constraints = self._build_spec_constraints(file_type, file_spec)
        contract_constraints = self._build_contract_constraints(file_path, architecture)
        file_scope_constraints = self._build_file_scope_constraints(file_path, architecture)
        runtime_consistency_constraints = self._build_runtime_consistency_constraints(
            file_path, file_type, project_language, architecture
        )
        dependency_import_constraints = self._build_dependency_import_constraints(dep_context)
        interface_constraints = self._build_interface_constraints(dep_context)
        if file_type == "model" and re.search(
            r"^\s*(?:import\s+sqlite3|from\s+sqlite3\s+import\s+)",
            dep_context,
            re.MULTILINE,
        ):
            runtime_consistency_constraints += (
                "\n- 已生成的 database.py 使用原生 sqlite3；models.py 必须继续使用原生 sqlite3 数据访问，"
                "禁止导入 SQLAlchemy、declarative_base、Column、Integer、String 或 relationship。"
            )
        if file_type == "model" and re.search(
            r"(?:^|\n)\s*(?:Base\s*=\s*declarative_base\(\)|from\s+sqlalchemy(?:\.orm)?\s+import[^\n]*declarative_base)",
            dep_context,
        ):
            runtime_consistency_constraints += (
                "\n- 已生成的 database.py 已导出 SQLAlchemy Base；本文件必须直接使用 `from database import Base`。"
                "\n- 只能在 Base 上声明模型类；禁止导入或调用 declarative_base()，禁止创建第二个 Base。"
            )

        prompt = f"""【严格约束】你必须严格按文件路径指定的语言编写代码，禁止自行添加或修改扩展名。

请创建以下文件：

文件路径：{file_path}
文件描述：{description}
此文件的语言：{file_actual_language}
项目主语言：{project_language}
文件类型：{file_type}

【任务约束 - 最高优先级】
- 你本次任务只创建 {file_path} 这一个文件
- 先用 read_file / list_files / search_files 等工具探索项目结构和已有代码，了解上下文
- 探索完成后，直接以纯文本形式返回 {file_path} 的完整内容
- 不要尝试创建或修改其他文件

{spec_constraints}

{contract_constraints}

{file_scope_constraints}

{runtime_consistency_constraints}

{dependency_import_constraints}

{interface_constraints}

【语言约束 - 必须遵守】
- 文件路径中已经包含正确的扩展名（如 .py、.go、.java、.json、.toml、.md 等），你必须保留原始路径，不允许添加项目主语言的扩展名
- 例如：文件路径是 "requirements.txt"，你创建的文件路径必须是 "requirements.txt"，不能是 "requirements.txt.py"
- 例如：文件路径是 "package.json"，你必须返回的是 JSON 内容
- 文件内容必须与此文件路径的扩展名匹配
- 如果文件路径是 .py/.go/.java 等后端文件，使用 {project_language} 编写
- 如果文件路径是 .json/.toml/.md/.yml/.yaml 等配置文件或文档文件，使用对应格式编写
- 禁止在 javascript 文件中使用 Python 语法（如 def、class、import os、from xxx import）
- 禁止在 python 文件中使用 JavaScript 语法（如 const、let、require、module.exports）

【运行时约束 - 严格遵守】
- 你的 file_type 是 {file_type}，这是一个后端文件
- 禁止使用浏览器 API：window, document, localStorage, sessionStorage, navigator, fetch(浏览器版)
- 禁止使用 DOM 操作：getElementById, querySelector, addEventListener
- 只能使用 {project_language} 的标准库和后端框架 API

导入规则（重要）：
- 严格采用“项目文件集合”指定的导入风格
- 第三方库使用绝对导入

【跨文件导入验证 - 必须执行】
在生成代码前，你必须验证所有跨文件导入的正确性：
1. 用 read_symbols 或 read_file 查看目标模块实际导出了哪些符号（函数、类、变量）
2. 用 search_files 搜索你要导入的符号名是否在目标文件中正确定义
   示例：search_files(pattern="def FastAPI|class FastAPI", file_pattern="*.py")
3. 如果目标文件中不存在该符号，你必须：
   a) 修正导入路径（找到真正定义该符号的文件），或
   b) 在目标文件中添加该符号的定义
4. 确认所有跨文件导入正确后再返回代码
不要凭猜测导入不存在的符号。每次导入项目内模块前，先验证再使用。

项目上下文：{json.dumps(project_context, ensure_ascii=False, indent=2)}
"""

        if spec_context:
            prompt += f"""
## 相关规范（必须严格遵守）
{spec_context}
"""

        if dep_context:
            prompt += f"""
## 已生成依赖文件（请基于以下已存在的代码保持接口/类型一致）
{dep_context}
"""

        if is_existing_file:
            prompt += f"""
这是一个已有文件的增量修改任务。

你可以使用以下工具进行精准编辑：
- partial_update: 替换指定函数或代码块（推荐，按函数名精准替换）
- insert_content: 在指定位置插入内容（按行号或锚点文本）
- regex_replace: 批量正则替换
- execute_code: 验证修改后的代码是否正确（仅 Python）

编辑规则：
1. 先用 read_file 读取文件现有内容，理解结构
2. 用 partial_update 或 insert_content 做精准编辑，不要重写整个文件
3. 编辑完成后，返回 JSON：{{"action": "edited", "files": ["{file_path}"], "summary": "修改摘要"}}
4. 如果改动太大无法局部修改，用 write_file 重写整个文件，返回完整内容
"""
        elif '__init__' in file_path:
            prompt += """
这是一个包入口文件（__init__.py）。

重要：你必须先读取同包目录下的其他 Python 文件，了解它们实际导出了哪些函数、类和变量，然后基于实际导出内容编写 __init__.py。

步骤：
1. 用 list_files 列出同包目录下的所有文件
2. 用 read_file 读取每个 .py 文件，提取它们的导出（def、class、__all__）
3. 基于实际导出内容编写 __init__.py 的 import 语句
4. 返回完整的 __init__.py 内容

示例：如果 utils.py 导出了 greet 和 farewell 函数，__init__.py 应该是：
```python
from .utils import greet, farewell
```
"""
        else:
            prompt += f"""
【输出格式 - 严格遵守】
- 直接返回 {file_actual_language} 代码，不要包裹在 JSON 对象中
- 不要返回 status、message、file_path、file_size 等元数据字段
- 不要返回 "以下是代码" 等引导语
- 不要用 ```markdown 代码块标记包裹整个文件
- 第一行必须是实际代码（import、定义、注释等）

请返回完整的文件内容，使用 {file_actual_language} 语法编写，不要省略任何部分。"""

        # 有项目路径时使用 ReAct 工具调用，否则退化为普通 call_llm
        # 编码阶段限制 thinking：省 token 留给代码输出，同时保留少量思考给用户展示
        # 报错修复场景（error_recovery/_fix_sandbox_errors）走独立路径，保持默认 thinking
        logger.info(f"BackendEngineer.generate_file: project_path={project_path}, callback={callback is not None}")
        if heartbeat_tracker:
            heartbeat_tracker.touch()
        if project_path:
            # 只给只读工具：LLM 用它们探索项目上下文，然后直接返回文件内容
            # 禁止 write_file/create_file：避免 LLM 写入其他文件（如 requirements.txt）而非目标文件
            from app.agent.tools import SPECIALIST_TOOLS
            read_only_tools = {
                k: v for k, v in SPECIALIST_TOOLS.items()
                if k in ('read_file', 'list_files', 'read_symbols', 'read_imports',
                         'summarize_file', 'search_files')
            }
            dependency_files = re.findall(
                r"^## 依赖文件:\s*(.+?)\s*$", dep_context, re.MULTILINE
            )
            preverified_tool_names = set()
            read_symbols_tool = read_only_tools.get("read_symbols")
            if read_symbols_tool:
                for dependency_file in dependency_files:
                    try:
                        result = read_symbols_tool["fn"](
                            project_path=project_path,
                            file_path=dependency_file.strip(),
                        )
                        if isinstance(result, dict) and result.get("success", True):
                            preverified_tool_names.add("read_symbols")
                    except Exception as exc:
                        logger.debug("宿主侧依赖符号预读失败: %s: %s", dependency_file, exc)
            result = await self.call_llm_with_tools(
                prompt, self.SYSTEM_PROMPT, tools=read_only_tools,
                project_path=project_path, react_mode="simple", callback=callback,
                heartbeat_tracker=heartbeat_tracker, enable_streaming_thinking=True,
                thinking_budget=50,
                required_tool_names={"read_symbols"} if dependency_files else set(),
                preverified_tool_names=preverified_tool_names,
            )
        else:
            result = await self.call_llm(prompt, self.SYSTEM_PROMPT, thinking_budget=50)
        if heartbeat_tracker:
            heartbeat_tracker.touch()
        return result

    @traced("backend.analyze", attributes={"component": "specialist", "role": "backend"})
    async def analyze(
        self,
        question: str,
        project_path: str,
        project_context: Optional[Dict] = None,
        callback: Optional[Any] = None,
        heartbeat_tracker=None,
    ) -> str:
        """分析模式 — 只读代码，用自然语言回答用户问题

        Args:
            question: 用户的问题（如"有哪些改进空间？"）
            project_path: 项目路径
            project_context: 项目上下文（可选）
            callback: 进度回调
            heartbeat_tracker: 心跳跟踪器

        Returns:
            自然语言分析结果
        """
        context_info = ""
        if project_context:
            architecture = project_context.get("architecture", {})
            language = architecture.get("language", "未知")
            context_info = f"\n项目主语言: {language}"

        # 先用工具读取项目结构
        project_files = []
        if project_path:
            from app.agent.tools import SPECIALIST_TOOLS
            read_only_tools = {
                k: v for k, v in SPECIALIST_TOOLS.items()
                if k in ('read_file', 'list_files', 'read_symbols', 'read_imports',
                         'summarize_file', 'search_files')
            }

            # 用 list_files 获取项目结构
            list_files_tool = read_only_tools.get('list_files')
            if list_files_tool:
                try:
                    files_result = await list_files_tool['function'](
                        directory=project_path,
                        max_depth=3
                    )
                    if files_result:
                        project_files = files_result.get('files', [])[:20]  # 限制文件数量
                except Exception as e:
                    logger.warning(f"获取文件列表失败: {e}")

        # 构建分析 prompt
        files_info = ""
        if project_files:
            files_info = f"\n项目文件结构:\n{json.dumps(project_files, ensure_ascii=False, indent=2)}"

        prompt = f"""你是一位资深代码分析师和架构师。用户向你提问，请分析项目并用自然语言回答。

用户问题：{question}
{context_info}
{files_info}

【分析流程】
1. 根据项目文件结构，分析项目的整体架构
2. 识别潜在的问题和改进空间
3. 给出具体的改进建议

【输出要求】
- 用自然语言回答，不要生成代码文件
- 如果是"改进空间"类问题，从以下维度分析：
  - 代码质量（命名、结构、可读性）
  - 架构设计（分层、耦合、扩展性）
  - 安全性（输入验证、错误处理、敏感信息）
  - 性能（潜在瓶颈、优化空间）
  - 最佳实践（框架约定、设计模式）
- 给出具体的改进建议，指出问题所在文件和行号
- 使用中文回答
"""

        logger.info(f"BackendEngineer.analyze: project_path={project_path}")
        if heartbeat_tracker:
            heartbeat_tracker.touch()

        # 直接调用 LLM，不使用 ReAct 引擎
        result = await self.call_llm(prompt, self.SYSTEM_PROMPT)

        if heartbeat_tracker:
            heartbeat_tracker.touch()
        return result
