"""
安全扫描器 - bandit 安全检测
"""
import asyncio
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
import logging
import re
import sys

logger = logging.getLogger(__name__)


@dataclass
class SecurityIssue:
    """安全问题"""
    file: str
    line: int
    severity: str  # HIGH/MEDIUM/LOW
    issue_type: str
    description: str
    code_snippet: Optional[str] = None
    cwe_id: Optional[str] = None


@dataclass
class SecurityReport:
    """安全报告"""
    success: bool
    total_issues: int
    high_severity: int = 0
    medium_severity: int = 0
    low_severity: int = 0
    issues: List[SecurityIssue] = field(default_factory=list)
    scanned_files: int = 0
    duration_seconds: float = 0.0


class SecurityScanner:
    """安全扫描器"""
    
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.python_executable: str = sys.executable
    
    async def scan_vulnerabilities(
        self,
        use_bandit: bool = True,
        manual_scan: bool = True
    ) -> SecurityReport:
        """
        扫描安全漏洞
        
        Args:
            use_bandit: 是否使用 bandit 工具
            manual_scan: 是否执行手动规则扫描
        
        Returns:
            SecurityReport: 安全报告
        """
        import time
        start_time = time.time()
        
        report = SecurityReport(success=True, total_issues=0)
        
        # bandit 扫描
        if use_bandit:
            bandit_report = await self._run_bandit()
            report.issues.extend(bandit_report.issues)
            report.high_severity += bandit_report.high_severity
            report.medium_severity += bandit_report.medium_severity
            report.low_severity += bandit_report.low_severity
            report.scanned_files += bandit_report.scanned_files
        
        # 手动规则扫描
        if manual_scan:
            manual_report = await self._manual_security_scan()
            report.issues.extend(manual_report.issues)
            report.high_severity += manual_report.high_severity
            report.medium_severity += manual_report.medium_severity
            report.low_severity += manual_report.low_severity
        
        report.total_issues = len(report.issues)
        report.duration_seconds = time.time() - start_time
        report.success = report.high_severity == 0
        
        return report
    
    async def _run_bandit(self) -> SecurityReport:
        """运行 bandit 扫描"""
        report = SecurityReport(success=True, total_issues=0)
        
        try:
            # 检查是否安装了 bandit
            if not await self._check_bandit_installed():
                logger.warning("bandit 未安装，跳过自动扫描")
                return report
            
            cmd = [
                self.python_executable,
                "-m", "bandit",
                "-r", str(self.project_path),
                "-f", "json",
                "-q"  # 安静模式
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0 or stdout:
                try:
                    import json
                    data = json.loads(stdout.decode('utf-8'))
                    
                    if 'results' in data:
                        for issue in data['results']:
                            severity = issue.get('issue_severity', 'LOW').upper()
                            
                            security_issue = SecurityIssue(
                                file=issue.get('filename', ''),
                                line=issue.get('line_number', 0),
                                severity=severity,
                                issue_type=issue.get('test_id', ''),
                                description=issue.get('issue_text', ''),
                                code_snippet=issue.get('code_context', ''),
                                cwe_id=issue.get('issue_cwe', {}).get('id')
                            )
                            
                            report.issues.append(security_issue)
                            report.total_issues += 1
                            
                            if severity == 'HIGH':
                                report.high_severity += 1
                            elif severity == 'MEDIUM':
                                report.medium_severity += 1
                            else:
                                report.low_severity += 1
                    
                    report.scanned_files = data.get('loc', 0)
                    
                except (ValueError, TypeError, RuntimeError, OSError) as e:
                    logger.error(f"解析 bandit 输出失败：{e}")
            
            if report.high_severity > 0:
                report.success = False
                
        except (ValueError, TypeError, RuntimeError, OSError) as e:
            logger.error(f"运行 bandit 失败：{e}")
        
        return report
    
    async def _check_bandit_installed(self) -> bool:
        """检查 bandit 是否已安装"""
        try:
            cmd = [
                self.python_executable,
                "-m", "bandit",
                "--version"
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            return process.returncode == 0
            
        except (ValueError, TypeError, RuntimeError, OSError):
            return False
    
    async def _manual_security_scan(self) -> SecurityReport:
        """手动规则扫描（不依赖 bandit）"""
        report = SecurityReport(success=True, total_issues=0)
        
        py_files = list(self.project_path.rglob("*.py"))
        report.scanned_files = len(py_files)
        
        for py_file in py_files:
            try:
                content = py_file.read_text(encoding='utf-8')
                lines = content.splitlines()
                rel_path = str(py_file.relative_to(self.project_path))
                
                # 检查项
                await self._check_hardcoded_secrets(lines, rel_path, report)
                await self._check_dangerous_functions(lines, rel_path, report)
                await self._check_sql_injection(lines, rel_path, report)
                await self._check_insecure_operations(lines, rel_path, report)
                
            except (ValueError, TypeError, RuntimeError, OSError) as e:
                logger.error(f"扫描文件 {py_file} 失败：{e}")
        
        if report.high_severity > 0:
            report.success = False
        
        return report
    
    async def _check_hardcoded_secrets(
        self,
        lines: List[str],
        file_path: str,
        report: SecurityReport
    ):
        """检查硬编码密钥"""
        patterns = [
            (r"(?i)(password|passwd|pwd)\s*=\s*[\"'][^\"']+[\"']", "硬编码密码"),
            (r"(?i)(api[_-]?key|apikey)\s*=\s*[\"'][^\"']+[\"']", "硬编码 API 密钥"),
            (r"(?i)(secret|token)\s*=\s*[\"'][^\"']+[\"']", "硬编码密钥/令牌"),
            (r"(?i)(access[_-]?key)\s*=\s*[\"'][^\"']+[\"']", "硬编码访问密钥"),
            (r"(?i)(private[_-]?key)\s*=\s*[\"'][^\"']+[\"']", "硬编码私钥"),
        ]
        
        for line_num, line in enumerate(lines, 1):
            # 跳过注释
            if line.strip().startswith('#'):
                continue
            
            for pattern, description in patterns:
                if re.search(pattern, line):
                    report.issues.append(SecurityIssue(
                        file=file_path,
                        line=line_num,
                        severity="HIGH",
                        issue_type="HARDCODED_SECRET",
                        description=description,
                        code_snippet=line.strip()[:100]
                    ))
                    report.high_severity += 1
                    report.total_issues += 1
    
    async def _check_dangerous_functions(
        self,
        lines: List[str],
        file_path: str,
        report: SecurityReport
    ):
        """检查危险函数使用"""
        dangerous_funcs = [
            ('eval(', '使用 eval() 可能导致代码注入'),
            ('exec(', '使用 exec() 可能导致代码注入'),
            ('__import__(', '使用 __import__() 可能不安全'),
            ('pickle.loads(', '使用 pickle.loads() 可能反序列化恶意数据'),
            ('marshal.loads(', '使用 marshal.loads() 可能不安全'),
            ('subprocess.call(', '使用 subprocess.call() 需检查命令注入'),
            ('subprocess.Popen(', '使用 subprocess.Popen() 需检查命令注入'),
            ('os.system(', '使用 os.system() 需检查命令注入'),
        ]
        
        for line_num, line in enumerate(lines, 1):
            if line.strip().startswith('#'):
                continue
            
            for func, description in dangerous_funcs:
                if func in line:
                    severity = "HIGH" if func in ['eval(', 'exec('] else "MEDIUM"
                    
                    report.issues.append(SecurityIssue(
                        file=file_path,
                        line=line_num,
                        severity=severity,
                        issue_type="DANGEROUS_FUNCTION",
                        description=description,
                        code_snippet=line.strip()[:100]
                    ))
                    
                    if severity == "HIGH":
                        report.high_severity += 1
                    else:
                        report.medium_severity += 1
                    report.total_issues += 1
    
    async def _check_sql_injection(
        self,
        lines: List[str],
        file_path: str,
        report: SecurityReport
    ):
        """检查 SQL 注入风险"""
        sql_patterns = [
            (r"execute\s*\(\s*[\"'].*%s", "使用字符串格式化构建 SQL"),
            (r"execute\s*\(\s*f[\"']", "使用 f-string 构建 SQL"),
            (r"execute\s*\(\s*[\"'].*\+.*\+", "使用字符串拼接构建 SQL"),
            (r"cursor\.execute\s*\([^,]+%", "参数化查询未使用"),
        ]
        
        for line_num, line in enumerate(lines, 1):
            if line.strip().startswith('#'):
                continue
            
            for pattern, description in sql_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    report.issues.append(SecurityIssue(
                        file=file_path,
                        line=line_num,
                        severity="HIGH",
                        issue_type="SQL_INJECTION_RISK",
                        description=description,
                        code_snippet=line.strip()[:100],
                        cwe_id="CWE-89"
                    ))
                    report.high_severity += 1
                    report.total_issues += 1
    
    async def _check_insecure_operations(
        self,
        lines: List[str],
        file_path: str,
        report: SecurityReport
    ):
        """检查不安全操作"""
        insecure_patterns = [
            (r"http\.client\.HTTPConnection\s*\([^)]*http://", "使用不安全的 HTTP 连接"),
            (r"urllib\.request\.urlopen\s*\([^)]*http://", "使用不安全的 HTTP 请求"),
            (r"ssl\.create_[a-z]+\s*\([^)]*verify\s*=\s*False", "禁用 SSL 证书验证"),
            (r"crypto\.md5", "使用不安全的 MD5 哈希"),
            (r"crypto\.sha1", "使用不安全的 SHA1 哈希"),
            (r"random\.(random|randint|choice)\s*\(", "使用非加密安全随机数"),
        ]
        
        for line_num, line in enumerate(lines, 1):
            if line.strip().startswith('#'):
                continue
            
            for pattern, description in insecure_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    severity = "MEDIUM"
                    if "verify\s*=\s*False" in pattern:
                        severity = "HIGH"
                    
                    report.issues.append(SecurityIssue(
                        file=file_path,
                        line=line_num,
                        severity=severity,
                        issue_type="INSECURE_OPERATION",
                        description=description,
                        code_snippet=line.strip()[:100]
                    ))
                    
                    if severity == "HIGH":
                        report.high_severity += 1
                    else:
                        report.medium_severity += 1
                    report.total_issues += 1
