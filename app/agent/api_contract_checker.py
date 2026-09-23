"""
APIContractChecker - API 契约一致性检查器

解决多 Agent 架构中的幻觉与一致性问题：
1. 从前端代码中提取 API 调用端点
2. 从后端代码中提取路由定义
3. 对比前后端端点是否匹配（路径、方法、参数）
4. 生成不一致报告并提供修复建议

使用场景：
- ErrorRecoveryLoop 中增加一致性检查
- 文件生成完成后自动验证
- 增量更新时检查契约变更
"""

import re
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class EndpointMethod(Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


@dataclass
class APIEndpoint:
    """API 端点定义"""
    path: str
    method: EndpointMethod
    file_path: str
    line_number: int = 0
    params: List[str] = field(default_factory=list)
    request_body: Optional[str] = None
    response_type: Optional[str] = None
    description: str = ""


@dataclass
class ConsistencyIssue:
    """一致性问题"""
    severity: str  # 'error', 'warning', 'info'
    issue_type: str  # 'missing_backend', 'missing_frontend', 'method_mismatch'
    message: str
    frontend_endpoint: Optional[APIEndpoint] = None
    backend_endpoint: Optional[APIEndpoint] = None
    suggestion: str = ""


class APIContractChecker:
    """
    API 契约一致性检查器

    工作原理：
    1. 解析后端代码，提取所有路由定义（FastAPI/Flask/Django）
    2. 解析前端代码，提取所有 API 调用（fetch/axios/XMLHttpRequest）
    3. 对比两端端点，找出不一致
    4. 生成修复建议
    """

    # FastAPI 路由（捕获 router 变量名，用于拼接 APIRouter(prefix=...)）
    _FASTAPI_DECORATOR_RE = re.compile(
        r'@(\w+)\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']'
    )
    _FASTAPI_API_ROUTE_RE = re.compile(
        r'@(\w+)\.(?:api_route|route)\(\s*["\']([^"\']+)["\'][^)]*?methods\s*=\s*\[([^\]]+)\]'
    )
    # Flask 路由（捕获蓝图变量名，用于拼接 Blueprint(url_prefix=...)）
    _FLASK_ROUTE_RE = re.compile(
        r'@(\w+)\.route\(\s*["\']([^"\']+)["\'][^)]*?methods\s*=\s*\[([^\]]+)\]'
    )
    # Django 路由：只在 urlpatterns 块内匹配，且跳过 include() 子路由
    _DJANGO_URLPATTERNS_RE = re.compile(r'urlpatterns\s*=\s*\[(?P<body>.*?)\]', re.DOTALL)
    _DJANGO_ROUTE_RE = re.compile(r'(?:path|url)\(\s*["\']([^"\']+)["\']\s*,\s*(?!\s*include\()')

    # APIRouter(prefix=...) / Blueprint(..., url_prefix=...)
    _ROUTER_PREFIX_RE = re.compile(r'(\w+)\s*=\s*APIRouter\((?P<args>[^)]*)\)', re.DOTALL)
    _BLUEPRINT_RE = re.compile(r'(\w+)\s*=\s*Blueprint\((?P<args>[^)]*)\)', re.DOTALL)
    _PREFIX_KW_RE = re.compile(r'prefix\s*=\s*["\']([^"\']+)["\']')
    _URL_PREFIX_KW_RE = re.compile(r'url_prefix\s*=\s*["\']([^"\']+)["\']')

    # 前端调用（跨行；路径可为引号/反引号；拼接标记与 options 对象可选）
    _FETCH_RE = re.compile(
        r'fetch\(\s*(?P<path>`[^`]*`|"[^"]*"|\'[^\']*\')'
        r'\s*(?P<concat>\+)?'
        r'(?:\s*,\s*(?P<opts>\{(?:[^{}]|\{[^{}]*\})*\}))?',
        re.DOTALL,
    )
    _FETCH_OBJ_RE = re.compile(
        r'fetch\(\s*\{(?P<opts>(?:[^{}]|\{[^{}]*\})*)\}', re.DOTALL
    )
    _AXIOS_METHOD_RE = re.compile(
        r'axios\.(get|post|put|delete|patch)\(\s*(?P<path>`[^`]*`|"[^"]*"|\'[^\']*\')',
        re.DOTALL,
    )
    _AXIOS_CONFIG_RE = re.compile(
        r'axios\(\s*\{(?P<opts>(?:[^{}]|\{[^{}]*\})*)\}', re.DOTALL
    )

    _METHOD_KW_RE = re.compile(r'method\s*:\s*["\'](\w+)["\']')
    _URL_KW_RE = re.compile(r'url\s*:\s*(`[^`]*`|"[^"]*"|\'[^\']*\')')
    # 路径参数（任意命名）折叠为 :param 用于键匹配
    _CANONICAL_PARAM_RE = re.compile(r':[A-Za-z_]\w*')
    _UUID_RE = re.compile(
        r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    )

    def __init__(self):
        self.backend_endpoints: List[APIEndpoint] = []
        self.frontend_endpoints: List[APIEndpoint] = []
        self.issues: List[ConsistencyIssue] = []

    def extract_backend_endpoints(self, code: str, file_path: str, framework: Optional[str] = None) -> List[APIEndpoint]:
        """
        从后端代码中提取 API 端点

        Args:
            code: 源代码
            file_path: 文件路径
            framework: 框架类型（fastapi/flask/django），自动检测

        Returns:
            提取的端点列表
        """
        endpoints: List[APIEndpoint] = []

        if framework is None:
            framework = self._detect_framework(code)

        if framework == 'fastapi':
            prefixes = self._collect_prefixes(self._ROUTER_PREFIX_RE, code, self._PREFIX_KW_RE)
            for match in self._FASTAPI_DECORATOR_RE.finditer(code):
                prefix = prefixes.get(match.group(1), '')
                self._add_backend_endpoint(
                    endpoints, [match.group(2)], prefix + match.group(3),
                    file_path, code, match.start(),
                )
            for match in self._FASTAPI_API_ROUTE_RE.finditer(code):
                prefix = prefixes.get(match.group(1), '')
                self._add_backend_endpoint(
                    endpoints, match.group(3).split(','), prefix + match.group(2),
                    file_path, code, match.start(),
                )
        elif framework == 'flask':
            prefixes = self._collect_prefixes(self._BLUEPRINT_RE, code, self._URL_PREFIX_KW_RE)
            for match in self._FLASK_ROUTE_RE.finditer(code):
                prefix = prefixes.get(match.group(1), '')
                self._add_backend_endpoint(
                    endpoints, match.group(3).split(','), prefix + match.group(2),
                    file_path, code, match.start(),
                )
        else:
            # Django：仅在 urlpatterns 块内提取，避免 view 内部 path("...") 误报
            for block in self._DJANGO_URLPATTERNS_RE.finditer(code):
                body = block.group('body')
                base = block.start('body')
                for match in self._DJANGO_ROUTE_RE.finditer(body):
                    self._add_backend_endpoint(
                        endpoints, ['GET'], match.group(1),
                        file_path, code, base + match.start(),
                    )

        return endpoints

    def extract_frontend_endpoints(self, code: str, file_path: str) -> List[APIEndpoint]:
        """
        从前端代码中提取 API 调用端点

        Args:
            code: 源代码
            file_path: 文件路径

        Returns:
            提取的端点列表
        """
        endpoints: List[APIEndpoint] = []

        # fetch('/path', {method: '...'}) / fetch(`/path/${id}`)
        for match in self._FETCH_RE.finditer(code):
            path = self._unquote(match.group('path'))
            if match.group('concat') and path.endswith('/'):
                path += ':param'
            endpoints.append(APIEndpoint(
                path=self._normalize_path(path, dynamic_tail=True),
                method=self._method_from_text(match.group('opts')),
                file_path=file_path,
                line_number=self._line_number(code, match.start()),
            ))

        # fetch({url: '/path', method: '...'})
        for match in self._FETCH_OBJ_RE.finditer(code):
            url = self._URL_KW_RE.search(match.group('opts'))
            if not url:
                continue
            endpoints.append(APIEndpoint(
                path=self._normalize_path(self._unquote(url.group(1)), dynamic_tail=True),
                method=self._method_from_text(match.group('opts')),
                file_path=file_path,
                line_number=self._line_number(code, match.start()),
            ))

        # axios.get('/path')
        for match in self._AXIOS_METHOD_RE.finditer(code):
            endpoints.append(APIEndpoint(
                path=self._normalize_path(self._unquote(match.group('path')), dynamic_tail=True),
                method=self._enum_method(match.group(1)),
                file_path=file_path,
                line_number=self._line_number(code, match.start()),
            ))

        # axios({url: '/path', method: '...'})
        for match in self._AXIOS_CONFIG_RE.finditer(code):
            url = self._URL_KW_RE.search(match.group('opts'))
            if not url:
                continue
            endpoints.append(APIEndpoint(
                path=self._normalize_path(self._unquote(url.group(1)), dynamic_tail=True),
                method=self._method_from_text(match.group('opts')),
                file_path=file_path,
                line_number=self._line_number(code, match.start()),
            ))

        return endpoints

    def check_consistency(
        self,
        frontend_files: Dict[str, str],
        backend_files: Dict[str, str]
    ) -> List[ConsistencyIssue]:
        """
        检查前后端 API 一致性

        Args:
            frontend_files: {文件路径: 代码内容}
            backend_files: {文件路径: 代码内容}

        Returns:
            一致性问题列表
        """
        self.issues = []
        self.backend_endpoints = []
        self.frontend_endpoints = []

        # 提取后端端点
        for file_path, code in backend_files.items():
            endpoints = self.extract_backend_endpoints(code, file_path)
            self.backend_endpoints.extend(endpoints)

        # 提取前端端点
        for file_path, code in frontend_files.items():
            endpoints = self.extract_frontend_endpoints(code, file_path)
            self.frontend_endpoints.extend(endpoints)

        # 按「路径」分组（参数名折叠为 :param），方法维度在组内比较
        backend_index = self._build_path_index(self.backend_endpoints)
        frontend_index = self._build_path_index(self.frontend_endpoints)

        # 前端调用了后端完全没有的路径
        for path, fe_endpoints in frontend_index.items():
            if path in backend_index:
                continue
            for fe_ep in fe_endpoints:
                self.issues.append(ConsistencyIssue(
                    severity='error',
                    issue_type='missing_backend',
                    message=f"前端调用了 {fe_ep.method.value} {fe_ep.path}，但后端未定义",
                    frontend_endpoint=fe_ep,
                    suggestion=f"在后端添加路由: @router.{fe_ep.method.value.lower()}(\"{fe_ep.path}\")"
                ))

        # 后端定义了前端完全没有的路径
        for path, be_endpoints in backend_index.items():
            if path in frontend_index:
                continue
            for be_ep in be_endpoints:
                self.issues.append(ConsistencyIssue(
                    severity='warning',
                    issue_type='missing_frontend',
                    message=f"后端定义了 {be_ep.method.value} {be_ep.path}，但前端未调用",
                    backend_endpoint=be_ep,
                    suggestion="确认是否需要此端点，或在前端添加调用"
                ))

        # 路径两侧都有，但方法集合不一致
        for path, be_endpoints in backend_index.items():
            fe_endpoints = frontend_index.get(path)
            if not fe_endpoints:
                continue
            be_methods = {ep.method.value for ep in be_endpoints}
            fe_methods = {ep.method.value for ep in fe_endpoints}

            for method in sorted(fe_methods - be_methods):
                fe_ep = next(ep for ep in fe_endpoints if ep.method.value == method)
                self.issues.append(ConsistencyIssue(
                    severity='error',
                    issue_type='method_mismatch',
                    message=f"前端使用 {method} {path}，但后端不支持此方法",
                    frontend_endpoint=fe_ep,
                    suggestion=f"在后端为 {path} 添加 {method} 方法支持"
                ))

            for method in sorted(be_methods - fe_methods):
                be_ep = next(ep for ep in be_endpoints if ep.method.value == method)
                self.issues.append(ConsistencyIssue(
                    severity='warning',
                    issue_type='method_mismatch',
                    message=f"后端支持 {method} {path}，但前端未调用",
                    backend_endpoint=be_ep,
                    suggestion=f"确认是否需要保留 {method} {path}，或在前端补充调用"
                ))

        return self.issues

    def check_single_file_consistency(
        self,
        file_path: str,
        code: str,
        is_frontend: bool,
        counterpart_files: Dict[str, str]
    ) -> List[ConsistencyIssue]:
        """
        检查单个文件与对应端的一致性

        Args:
            file_path: 当前文件路径
            code: 当前文件代码
            is_frontend: 是否为前端文件
            counterpart_files: 对应端的文件字典

        Returns:
            一致性问题列表
        """
        issues = []

        if is_frontend:
            current_endpoints = self.extract_frontend_endpoints(code, file_path)
            counterpart_endpoints = []
            for fp, c in counterpart_files.items():
                counterpart_endpoints.extend(self.extract_backend_endpoints(c, fp))
        else:
            current_endpoints = self.extract_backend_endpoints(code, file_path)
            counterpart_endpoints = []
            for fp, c in counterpart_files.items():
                counterpart_endpoints.extend(self.extract_frontend_endpoints(c, fp))

        counterpart_index = self._build_path_index(counterpart_endpoints)

        for ep in current_endpoints:
            counterparts = counterpart_index.get(self._canonical_path(ep.path))
            if not counterparts:
                if is_frontend:
                    issues.append(ConsistencyIssue(
                        severity='error',
                        issue_type='missing_backend',
                        message=f"前端调用 {ep.method.value} {ep.path}，后端未定义",
                        frontend_endpoint=ep,
                        suggestion=f"后端需添加: @router.{ep.method.value.lower()}(\"{ep.path}\")"
                    ))
                else:
                    issues.append(ConsistencyIssue(
                        severity='warning',
                        issue_type='missing_frontend',
                        message=f"后端定义 {ep.method.value} {ep.path}，前端未调用",
                        backend_endpoint=ep,
                        suggestion="确认是否需要或在前端添加调用"
                    ))
                continue

            counterpart_methods = {c.method.value for c in counterparts}
            if ep.method.value not in counterpart_methods:
                if is_frontend:
                    issues.append(ConsistencyIssue(
                        severity='error',
                        issue_type='method_mismatch',
                        message=f"前端调用 {ep.method.value} {ep.path}，后端不支持此方法",
                        frontend_endpoint=ep,
                        suggestion=f"后端需添加 {ep.method.value} 方法支持"
                    ))
                else:
                    issues.append(ConsistencyIssue(
                        severity='warning',
                        issue_type='method_mismatch',
                        message=f"后端定义 {ep.method.value} {ep.path}，前端未调用此方法",
                        backend_endpoint=ep,
                        suggestion="确认是否需要或在前端添加调用"
                    ))

        return issues

    def generate_api_contract(self, backend_files: Dict[str, str]) -> Dict[str, List[Dict]]:
        """
        从后端代码生成 API 契约（用于注入到前端生成的 prompt 中）

        Args:
            backend_files: {文件路径: 代码内容}

        Returns:
            API 契约字典，按模块分组
        """
        all_endpoints = []
        for file_path, code in backend_files.items():
            endpoints = self.extract_backend_endpoints(code, file_path)
            all_endpoints.extend(endpoints)

        # 按路径前缀分组
        contract = {}
        for ep in all_endpoints:
            # 提取模块名（路径的第一段）
            parts = ep.path.strip('/').split('/')
            module = parts[0] if parts else 'default'

            if module not in contract:
                contract[module] = []

            contract[module].append({
                "path": ep.path,
                "method": ep.method.value,
                "file": ep.file_path,
                "line": ep.line_number
            })

        return contract

    def get_consistency_report(self) -> str:
        """生成一致性报告文本"""
        if not self.issues:
            return "API 一致性检查通过：前后端端点完全匹配"

        lines = ["API 一致性检查报告", "=" * 40]

        errors = [i for i in self.issues if i.severity == 'error']
        warnings = [i for i in self.issues if i.severity == 'warning']

        if errors:
            lines.append(f"\n错误 ({len(errors)}):")
            for issue in errors:
                lines.append(f"  - {issue.message}")
                lines.append(f"    建议: {issue.suggestion}")

        if warnings:
            lines.append(f"\n警告 ({len(warnings)}):")
            for issue in warnings:
                lines.append(f"  - {issue.message}")
                lines.append(f"    建议: {issue.suggestion}")

        lines.append(f"\n总计: {len(self.issues)} 个问题 ({len(errors)} 错误, {len(warnings)} 警告)")
        return "\n".join(lines)

    # ==================== 内部方法 ====================

    @staticmethod
    def _detect_framework(code: str) -> str:
        """按关键字自动检测后端框架"""
        lowered = code.lower()
        if 'fastapi' in lowered:
            return 'fastapi'
        if 'flask' in lowered:
            return 'flask'
        if 'django' in lowered:
            return 'django'
        return 'fastapi'

    @staticmethod
    def _collect_prefixes(assign_re, code: str, kw_re) -> Dict[str, str]:
        """收集 APIRouter(prefix=...) / Blueprint(url_prefix=...) 变量到前缀的映射"""
        prefixes: Dict[str, str] = {}
        for match in assign_re.finditer(code):
            kw = kw_re.search(match.group('args'))
            if kw:
                prefixes[match.group(1)] = kw.group(1)
        return prefixes

    @staticmethod
    def _unquote(token: str) -> str:
        """去掉包裹路径的引号/反引号"""
        token = token.strip()
        if len(token) >= 2 and token[0] in '"\'`' and token[-1] == token[0]:
            return token[1:-1]
        return token

    @staticmethod
    def _line_number(code: str, offset: int) -> int:
        return code.count('\n', 0, offset) + 1

    @staticmethod
    def _enum_method(name: str) -> EndpointMethod:
        try:
            return EndpointMethod(name.upper())
        except ValueError:
            return EndpointMethod.GET

    def _method_from_text(self, text: Optional[str]) -> EndpointMethod:
        """从 options 对象文本中提取 method，缺省为 GET"""
        if text:
            match = self._METHOD_KW_RE.search(text)
            if match:
                try:
                    return EndpointMethod(match.group(1).upper())
                except ValueError:
                    pass
        return EndpointMethod.GET

    def _add_backend_endpoint(
        self,
        endpoints: List[APIEndpoint],
        methods: List[str],
        path: str,
        file_path: str,
        code: str,
        offset: int,
    ) -> None:
        """归一化并追加后端端点（忽略不支持的方法名）"""
        normalized = self._normalize_path(path)
        for method in methods:
            try:
                endpoints.append(APIEndpoint(
                    path=normalized,
                    method=EndpointMethod(method.strip().strip('"\'').upper()),
                    file_path=file_path,
                    line_number=self._line_number(code, offset),
                ))
            except ValueError:
                continue

    def _normalize_path(self, path: str, dynamic_tail: bool = False) -> str:
        """标准化 API 路径"""
        # 移除查询参数
        path = path.split('?')[0]

        # 前端模板串 ${id} 与后端 {id} 统一为 :id
        path = re.sub(r'\$\{(\w+)\}', r':\1', path)
        path = re.sub(r'\{(\w+)\}', r':\1', path)

        # 前端裸具体值（/api/users/123、UUID）视为路径参数
        if dynamic_tail:
            last = path.rsplit('/', 1)[-1]
            if last and (last.isdigit() or self._UUID_RE.match(last)):
                path = path[: -len(last)] + ':param'

        # 移除尾部斜杠
        path = path.rstrip('/')

        # 确保以 / 开头
        if not path.startswith('/'):
            path = '/' + path

        return path

    def _canonical_path(self, path: str) -> str:
        """把任意命名的路径参数折叠为 :param，用于前后端键匹配"""
        return self._CANONICAL_PARAM_RE.sub(':param', path)

    def _build_path_index(self, endpoints: List[APIEndpoint]) -> Dict[str, List[APIEndpoint]]:
        """构建端点索引：canonical_path -> [endpoints]"""
        index: Dict[str, List[APIEndpoint]] = {}
        for ep in endpoints:
            index.setdefault(self._canonical_path(ep.path), []).append(ep)
        return index


# ==================== 便捷函数 ====================

def check_api_consistency(frontend_files: Dict[str, str], backend_files: Dict[str, str]) -> Tuple[bool, List[ConsistencyIssue]]:
    """
    快速检查 API 一致性

    Args:
        frontend_files: 前端文件字典
        backend_files: 后端文件字典

    Returns:
        (是否通过，问题列表)
    """
    checker = APIContractChecker()
    issues = checker.check_consistency(frontend_files, backend_files)
    has_errors = any(i.severity == 'error' for i in issues)
    return not has_errors, issues


def generate_frontend_prompt_contract(backend_files: Dict[str, str]) -> str:
    """
    生成前端生成用的 API 契约 prompt

    Args:
        backend_files: 后端文件字典

    Returns:
        格式化的 API 契约文本
    """
    checker = APIContractChecker()
    contract = checker.generate_api_contract(backend_files)

    lines = ["## API 契约（必须遵守）", ""]
    lines.append("以下是后端已定义的 API 端点，前端调用时必须严格匹配路径和方法：")
    lines.append("")

    for module, endpoints in contract.items():
        lines.append(f"### 模块: {module}")
        lines.append("")
        lines.append("| 路径 | 方法 | 定义位置 |")
        lines.append("|------|------|----------|")
        for ep in endpoints:
            lines.append(f"| `{ep['path']}` | `{ep['method']}` | {ep['file']}:{ep['line']} |")
        lines.append("")

    lines.append("**重要**: 不要使用未在此列出的端点，不要修改路径格式。")
    return "\n".join(lines)
