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
    issue_type: str  # 'missing_backend', 'missing_frontend', 'method_mismatch', 'param_mismatch', 'path_mismatch'
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

    # FastAPI 路由模式
    FASTAPI_ROUTE_PATTERNS = [
        r'@router\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']',
        r'@app\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']',
        r'@(?:api_route|route)\(\s*["\']([^"\']+)["\'].*?methods=\[([^\]]+)\]',
    ]

    # Flask 路由模式
    FLASK_ROUTE_PATTERNS = [
        r'@app\.route\(\s*["\']([^"\']+)["\'].*?methods=\[([^\]]+)\]',
        r'@blueprint\.route\(\s*["\']([^"\']+)["\'].*?methods=\[([^\]]+)\]',
    ]

    # Django 路由模式
    DJANGO_ROUTE_PATTERNS = [
        r'(?:path|url)\(\s*["\']([^"\']+)["\']',
    ]

    # 前端 fetch 调用模式
    FETCH_PATTERNS = [
        r'fetch\(\s*["\']([^"\']+)["\']',
        r'fetch\(\s*`([^`]+)`',
        r'fetch\(\s*\{?\s*url:\s*["\']([^"\']+)["\']',
    ]

    # 前端 axios 调用模式
    AXIOS_PATTERNS = [
        r'axios\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']',
        r'axios\(\s*\{\s*method:\s*["\']([^"\']+)["\'].*?url:\s*["\']([^"\']+)["\']',
        r'(?:get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']',
    ]

    # API 前缀模式（用于标准化路径）
    API_PREFIXES = ['/api', '/api/v1', '/api/v2']

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
        endpoints = []
        lines = code.split('\n')

        # 自动检测框架
        if framework is None:
            if 'fastapi' in code.lower() or 'from fastapi' in code.lower():
                framework = 'fastapi'
            elif 'flask' in code.lower() or 'from flask' in code.lower():
                framework = 'flask'
            elif 'django' in code.lower() or 'from django' in code.lower():
                framework = 'django'
            else:
                framework = 'fastapi'  # 默认

        # 根据框架选择模式
        if framework == 'fastapi':
            patterns = self.FASTAPI_ROUTE_PATTERNS
        elif framework == 'flask':
            patterns = self.FLASK_ROUTE_PATTERNS
        else:
            patterns = self.DJANGO_ROUTE_PATTERNS

        for line_num, line in enumerate(lines, 1):
            for pattern in patterns:
                match = re.search(pattern, line)
                if match:
                    groups = match.groups()
                    if len(groups) == 2:
                        method_str, path = groups
                        if ',' in method_str:
                            # methods=["GET", "POST"]
                            methods = [m.strip().strip('"').strip("'").upper() for m in method_str.split(',')]
                        else:
                            methods = [method_str.upper()]

                        for method in methods:
                            try:
                                endpoint = APIEndpoint(
                                    path=self._normalize_path(path),
                                    method=EndpointMethod(method),
                                    file_path=file_path,
                                    line_number=line_num
                                )
                                endpoints.append(endpoint)
                            except ValueError:
                                continue

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
        endpoints = []
        lines = code.split('\n')

        for line_num, line in enumerate(lines, 1):
            # 提取 fetch 调用
            for pattern in self.FETCH_PATTERNS:
                match = re.search(pattern, line)
                if match:
                    path = match.group(1)
                    # 推断方法（默认 GET）
                    method = EndpointMethod.GET
                    if 'method:' in line:
                        method_match = re.search(r'method:\s*["\'](\w+)["\']', line)
                        if method_match:
                            try:
                                method = EndpointMethod(method_match.group(1).upper())
                            except ValueError:
                                pass

                    endpoints.append(APIEndpoint(
                        path=self._normalize_path(path),
                        method=method,
                        file_path=file_path,
                        line_number=line_num
                    ))

            # 提取 axios 调用
            for pattern in self.AXIOS_PATTERNS:
                match = re.search(pattern, line)
                if match:
                    groups = match.groups()
                    if len(groups) == 2:
                        method_str, path = groups
                        try:
                            method = EndpointMethod(method_str.upper())
                        except ValueError:
                            method = EndpointMethod.GET
                    elif len(groups) == 2 and groups[0] in ('get', 'post', 'put', 'delete', 'patch'):
                        method = EndpointMethod(groups[0].upper())
                        path = groups[1]
                    else:
                        continue

                    endpoints.append(APIEndpoint(
                        path=self._normalize_path(path),
                        method=method,
                        file_path=file_path,
                        line_number=line_num
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

        # 构建后端端点索引
        backend_index = self._build_endpoint_index(self.backend_endpoints)
        frontend_index = self._build_endpoint_index(self.frontend_endpoints)

        # 检查前端调用但后端缺失的端点
        for key, fe_endpoints in frontend_index.items():
            if key not in backend_index:
                for fe_ep in fe_endpoints:
                    self.issues.append(ConsistencyIssue(
                        severity='error',
                        issue_type='missing_backend',
                        message=f"前端调用了 {fe_ep.method.value} {fe_ep.path}，但后端未定义",
                        frontend_endpoint=fe_ep,
                        suggestion=f"在后端添加路由: @router.{fe_ep.method.value.lower()}(\"{fe_ep.path}\")"
                    ))

        # 检查后端定义但前端未使用的端点
        for key, be_endpoints in backend_index.items():
            if key not in frontend_index:
                for be_ep in be_endpoints:
                    self.issues.append(ConsistencyIssue(
                        severity='warning',
                        issue_type='missing_frontend',
                        message=f"后端定义了 {be_ep.method.value} {be_ep.path}，但前端未调用",
                        backend_endpoint=be_ep,
                        suggestion="确认是否需要此端点，或在前端添加调用"
                    ))

        # 检查方法不匹配
        for key in frontend_index:
            if key in backend_index:
                fe_methods = set(ep.method.value for ep in frontend_index[key])
                be_methods = set(ep.method.value for ep in backend_index[key])

                if fe_methods != be_methods:
                    extra_fe = fe_methods - be_methods

                    for method in extra_fe:
                        fe_ep = next(ep for ep in frontend_index[key] if ep.method.value == method)
                        self.issues.append(ConsistencyIssue(
                            severity='error',
                            issue_type='method_mismatch',
                            message=f"前端使用 {method} {key}，但后端不支持此方法",
                            frontend_endpoint=fe_ep,
                            suggestion=f"在后端添加 {method} 方法支持"
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

        counterpart_index = self._build_endpoint_index(counterpart_endpoints)

        for ep in current_endpoints:
            key = f"{ep.method.value}:{ep.path}"
            if key not in counterpart_index:
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

    def _normalize_path(self, path: str) -> str:
        """标准化 API 路径"""
        # 移除查询参数
        path = path.split('?')[0]

        # 移除尾部斜杠
        path = path.rstrip('/')

        # 替换路径参数 {id} -> :id
        path = re.sub(r'\{(\w+)\}', r':\1', path)

        # 确保以 / 开头
        if not path.startswith('/'):
            path = '/' + path

        return path

    def _build_endpoint_index(self, endpoints: List[APIEndpoint]) -> Dict[str, List[APIEndpoint]]:
        """构建端点索引：method:path -> [endpoints]"""
        index = {}
        for ep in endpoints:
            key = f"{ep.method.value}:{ep.path}"
            if key not in index:
                index[key] = []
            index[key].append(ep)
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
