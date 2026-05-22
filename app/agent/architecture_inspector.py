"""
ArchitectureInspector - 架构检查器

核心理念：在文件生成完成后，调用架构师模型检查生成的代码是否符合全局架构设计，
以架构师的视角审查个体工程师的工作，避免各自为政。

工作流程：
1. 收集生成的文件内容摘要
2. 与架构设计进行对比检查
3. 识别架构偏离和潜在问题
4. 生成架构检查报告
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ArchitectureViolation:
    """架构违规定义"""
    file_path: str
    violation_type: str
    description: str
    severity: str
    suggestion: str


@dataclass
class ArchitectureCheckResult:
    """架构检查结果"""
    passed: bool
    violations: List[ArchitectureViolation]
    suggestions: List[str]
    architecture_alignment_score: float


class ArchitectureInspector:
    """
    架构检查器
    
    与架构师的协作：
    - 所有文件生成完成后，调用架构师审查
    - 以架构师的视角检查工程师的工作
    
    检查内容：
    - 文件职责是否符合架构设计
    - 接口命名是否符合规范
    - 模块依赖是否合理
    - 代码风格是否一致
    """

    VIOLATION_TYPES = {
        "layer_boundary": "分层边界违规",
        "dependency_direction": "依赖方向违规",
        "interface_style": "接口风格违规",
        "naming_convention": "命名规范违规",
        "module_cohesion": "模块内聚不足",
        "global_constraint": "全局约束违规",
        "tech_stack": "技术栈不一致",
        "security_pattern": "安全模式缺失"
    }

    def __init__(self):
        self.architecture_design: Dict[str, Any] = {}
        self.generated_files: Dict[str, str] = {}
        self.global_constraints: List[Any] = []
        self.user_decisions: Dict[str, str] = {}

    def set_context(
        self,
        architecture: Dict[str, Any],
        generated_files: Dict[str, str],
        constraints: Optional[List] = None,
        decisions: Optional[Dict[str, str]] = None
    ) -> None:
        """设置检查上下文"""
        self.architecture_design = architecture
        self.generated_files = generated_files
        self.global_constraints = constraints or []
        self.user_decisions = decisions or {}

    def inspect(
        self,
        llm_checker: Optional[callable] = None
    ) -> ArchitectureCheckResult:
        """
        执行架构检查
        
        Args:
            llm_checker: 可选的 LLM 检查函数
        
        Returns:
            架构检查结果
        """
        violations = []
        suggestions = []
        
        violations.extend(self._check_layer_boundaries())
        violations.extend(self._check_dependency_direction())
        violations.extend(self._check_interface_style())
        violations.extend(self._check_naming_conventions())
        violations.extend(self._check_global_constraints())
        violations.extend(self._check_tech_stack_consistency())
        
        if llm_checker:
            llm_violations = self._llm_architecture_review(llm_checker)
            violations.extend(llm_violations)
        
        critical_violations = [v for v in violations if v.severity == "critical"]
        passed = len(critical_violations) == 0
        
        alignment_score = self._calculate_alignment_score(violations)
        
        if violations:
            suggestions = self._generate_fix_suggestions(violations)
        
        logger.info(
            f"架构检查完成: 通过={passed}, 违规={len(violations)}, "
            f"一致性得分={alignment_score:.2f}"
        )
        
        return ArchitectureCheckResult(
            passed=passed,
            violations=violations,
            suggestions=suggestions,
            architecture_alignment_score=alignment_score
        )

    def _check_layer_boundaries(self) -> List[ArchitectureViolation]:
        """检查分层边界"""
        violations = []
        
        layer_definitions = self.architecture_design.get("layers", {})
        if not layer_definitions:
            return violations
        
        for file_path, content in self.generated_files.items():
            assigned_layer = self._get_assigned_layer(file_path, layer_definitions)
            if not assigned_layer:
                continue
            
            layer_boundary_rules = layer_definitions.get(assigned_layer, {}).get("boundaries", [])
            for rule in layer_boundary_rules:
                if self._violates_boundary(content, rule):
                    violations.append(ArchitectureViolation(
                        file_path=file_path,
                        violation_type="layer_boundary",
                        description=f"文件跨越 {assigned_layer} 层边界: {rule}",
                        severity="high",
                        suggestion=f"将违规逻辑移至正确的层"
                    ))
        
        return violations

    def _get_assigned_layer(
        self,
        file_path: str,
        layer_definitions: Dict
    ) -> Optional[str]:
        """获取文件所属层"""
        path_lower = file_path.lower()
        
        for layer_name, layer_config in layer_definitions.items():
            layer_paths = layer_config.get("paths", [])
            for layer_path in layer_paths:
                if layer_path.lower() in path_lower:
                    return layer_name
        
        return None

    def _violates_boundary(self, content: str, rule: str) -> bool:
        """检查是否违反边界规则"""
        rule_patterns = {
            "no_database_access": ["import.*sql", "import.*mongo", "import.*redis", "SELECT", "INSERT"],
            "no_business_logic": ["class.*Service", "def.*calculate", "def.*validate"],
            "no_ui_rendering": ["render", "template", "return.*html"],
            "no_http_handling": ["@app.route", "@router", "Request", "Response"]
        }
        
        patterns = rule_patterns.get(rule, [])
        for pattern in patterns:
            if pattern.lower() in content.lower():
                return True
        
        return False

    def _check_dependency_direction(self) -> List[ArchitectureViolation]:
        """检查依赖方向"""
        violations = []
        
        dependency_rules = self.architecture_design.get("dependency_rules", {})
        if not dependency_rules:
            return violations
        
        for file_path, content in self.generated_files.items():
            imports = self._extract_imports(content)
            for import_path in imports:
                violating_rule = self._check_import_direction(file_path, import_path, dependency_rules)
                if violating_rule:
                    violations.append(ArchitectureViolation(
                        file_path=file_path,
                        violation_type="dependency_direction",
                        description=f"依赖方向违规: {file_path} -> {import_path} ({violating_rule})",
                        severity="medium",
                        suggestion="调整依赖方向，避免反向依赖"
                    ))
        
        return violations

    def _extract_imports(self, content: str) -> List[str]:
        """提取文件中的 import 语句"""
        imports = []
        
        import_patterns = [
            "from app.",
            "from src.",
            "import app.",
            "import src."
        ]
        
        for line in content.split("\n"):
            for pattern in import_patterns:
                if pattern in line:
                    imports.append(line.strip())
        
        return imports

    def _check_import_direction(
        self,
        file_path: str,
        import_path: str,
        dependency_rules: Dict
    ) -> Optional[str]:
        """检查 import 方向是否违规"""
        for rule_name, rule_config in dependency_rules.items():
            source_pattern = rule_config.get("source")
            allowed_targets = rule_config.get("allowed_targets", [])
            
            if source_pattern and source_pattern in file_path:
                for allowed in allowed_targets:
                    if allowed not in import_path:
                        return rule_name
        
        return None

    def _check_interface_style(self) -> List[ArchitectureViolation]:
        """检查接口风格"""
        violations = []
        
        api_style = self.user_decisions.get("api_style", "REST")
        if not api_style:
            return violations
        
        for file_path, content in self.generated_files.items():
            if "api" not in file_path.lower() and "router" not in file_path.lower():
                continue
            
            style_violation = self._check_api_style(content, api_style)
            if style_violation:
                violations.append(ArchitectureViolation(
                    file_path=file_path,
                    violation_type="interface_style",
                    description=f"接口风格不符合 {api_style}: {style_violation}",
                    severity="medium",
                    suggestion=f"调整接口以符合 {api_style} 规范"
                ))
        
        return violations

    def _check_api_style(self, content: str, api_style: str) -> Optional[str]:
        """检查 API 风格"""
        if api_style == "REST":
            graphql_patterns = ["query {", "mutation {", "type Query", "type Mutation"]
            for pattern in graphql_patterns:
                if pattern in content:
                    return "包含 GraphQL 语法"
        
        elif api_style == "GraphQL":
            rest_patterns = ["@app.route", "@router.get", "@router.post", "HTTPMethod"]
            for pattern in rest_patterns:
                if pattern in content:
                    return "包含 REST 路由定义"
        
        return None

    def _check_naming_conventions(self) -> List[ArchitectureViolation]:
        """检查命名规范"""
        violations = []
        
        naming_rules = self.architecture_design.get("naming_conventions", {})
        if not naming_rules:
            return violations
        
        for file_path, content in self.generated_files.items():
            file_naming_violation = self._check_file_naming(file_path, naming_rules)
            if file_naming_violation:
                violations.append(ArchitectureViolation(
                    file_path=file_path,
                    violation_type="naming_convention",
                    description=f"文件命名不符合规范: {file_naming_violation}",
                    severity="low",
                    suggestion="重命名文件以符合规范"
                ))
        
        return violations

    def _check_file_naming(
        self,
        file_path: str,
        naming_rules: Dict
    ) -> Optional[str]:
        """检查文件命名"""
        file_ext = file_path.split(".")[-1] if "." in file_path else ""
        expected_pattern = naming_rules.get(file_ext, naming_rules.get("default", ""))
        
        if expected_pattern == "snake_case":
            filename = file_path.split("/")[-1].split(".")[0]
            if "-" in filename or " " in filename:
                return "应使用 snake_case (下划线分隔)"
        
        elif expected_pattern == "kebab-case":
            filename = file_path.split("/")[-1].split(".")[0]
            if "_" in filename or " " in filename:
                return "应使用 kebab-case (连字符分隔)"
        
        return None

    def _check_global_constraints(self) -> List[ArchitectureViolation]:
        """检查全局约束"""
        violations = []
        
        for constraint in self.global_constraints:
            for file_path in constraint.applies_to:
                if file_path == "all":
                    continue
                
                content = self.generated_files.get(file_path, "")
                if not content:
                    continue
                
                violation = self._check_constraint_in_content(constraint, content, file_path)
                if violation:
                    violations.append(violation)
        
        return violations

    def _check_constraint_in_content(
        self,
        constraint: Any,
        content: str,
        file_path: str
    ) -> Optional[ArchitectureViolation]:
        """检查内容中的约束"""
        constraint_text = constraint.description.lower()
        
        if "安全" in constraint_text or "权限" in constraint_text:
            security_patterns = ["@require_auth", "@login_required", "check_permission", "auth_required"]
            has_security = any(p in content for p in security_patterns)
            if not has_security and ("api" in file_path or "router" in file_path):
                return ArchitectureViolation(
                    file_path=file_path,
                    violation_type="global_constraint",
                    description=f"缺少安全校验: {constraint.description}",
                    severity="high",
                    suggestion="添加权限校验装饰器或中间件"
                )
        
        return None

    def _check_tech_stack_consistency(self) -> List[ArchitectureViolation]:
        """检查技术栈一致性"""
        violations = []
        
        tech_stack = self.architecture_design.get("tech_stack", {})
        if not tech_stack:
            return violations
        
        backend_framework = tech_stack.get("backend") or self.user_decisions.get("backend_framework")
        frontend_framework = tech_stack.get("frontend") or self.user_decisions.get("frontend_framework")
        
        for file_path, content in self.generated_files.items():
            if backend_framework and "backend" in file_path.lower():
                if self._check_framework_inconsistency(content, backend_framework):
                    violations.append(ArchitectureViolation(
                        file_path=file_path,
                        violation_type="tech_stack",
                        description=f"后端文件未使用指定框架 {backend_framework}",
                        severity="high",
                        suggestion=f"使用 {backend_framework} 框架语法"
                    ))
            
            if frontend_framework and "frontend" in file_path.lower():
                if self._check_framework_inconsistency(content, frontend_framework):
                    violations.append(ArchitectureViolation(
                        file_path=file_path,
                        violation_type="tech_stack",
                        description=f"前端文件未使用指定框架 {frontend_framework}",
                        severity="high",
                        suggestion=f"使用 {frontend_framework} 框架语法"
                    ))
        
        return violations

    def _check_framework_inconsistency(
        self,
        content: str,
        framework: str
    ) -> bool:
        """检查框架不一致"""
        framework_markers = {
            "FastAPI": ["from fastapi", "@app.get", "@app.post", "FastAPI"],
            "Flask": ["from flask", "@app.route", "Flask"],
            "Django": ["from django", "models.Model", "django.db"],
            "Vue": ["defineComponent", "ref(", "reactive(", "computed("],
            "React": ["useState", "useEffect", "React.createElement", "jsx"],
            "Angular": ["@Component", "@Injectable", "NgModule"]
        }
        
        markers = framework_markers.get(framework, [])
        if markers:
            return not any(marker in content for marker in markers)
        
        return False

    def _llm_architecture_review(
        self,
        llm_checker: callable
    ) -> List[ArchitectureViolation]:
        """使用 LLM 进行架构审查"""
        violations = []
        
        try:
            review_result = llm_checker(
                architecture=self.architecture_design,
                files=self.generated_files
            )
            
            if review_result and "violations" in review_result:
                for v in review_result["violations"]:
                    violations.append(ArchitectureViolation(
                        file_path=v.get("file", "unknown"),
                        violation_type=v.get("type", "architecture"),
                        description=v.get("description", ""),
                        severity=v.get("severity", "medium"),
                        suggestion=v.get("suggestion", "")
                    ))
        
        except Exception as e:
            logger.error(f"LLM 架构审查失败: {e}")
        
        return violations

    def _calculate_alignment_score(
        self,
        violations: List[ArchitectureViolation]
    ) -> float:
        """计算架构一致性得分"""
        if not violations:
            return 1.0
        
        severity_weights = {"critical": 0.3, "high": 0.2, "medium": 0.1, "low": 0.05}
        
        total_penalty = sum(
            severity_weights.get(v.severity, 0.1) for v in violations
        )
        
        score = max(0.0, 1.0 - total_penalty)
        return score

    def _generate_fix_suggestions(
        self,
        violations: List[ArchitectureViolation]
    ) -> List[str]:
        """生成修复建议"""
        suggestions = []
        
        for v in violations:
            suggestions.append(f"[{v.severity}] {v.file_path}: {v.suggestion}")
        
        return suggestions

    def get_violations_by_type(
        self,
        result: ArchitectureCheckResult
    ) -> Dict[str, List[ArchitectureViolation]]:
        """按类型分组违规"""
        grouped = {}
        for v in result.violations:
            if v.violation_type not in grouped:
                grouped[v.violation_type] = []
            grouped[v.violation_type].append(v)
        return grouped