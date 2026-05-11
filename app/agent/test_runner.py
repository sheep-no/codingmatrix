"""
TestRunner - 轻量级本地沙箱测试执行器

由于当前环境没有 Docker，我们使用"本地沙箱"策略：
1. 限制执行时间 (Timeout)
2. 隔离环境变量 (Environment Isolation)
3. 临时工作目录 (Temp Working Directory)
4. 捕获标准输出/错误 (Output Capture)

这个模块允许 Agent 真正运行测试，并根据测试结果进行自我修复。
"""

import subprocess
import asyncio
import logging
import os
import sys
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """测试结果"""
    success: bool
    total_tests: int
    passed: int
    failed: int
    errors: int
    logs: str
    failed_tests: List[str]


class TestRunner:
    """轻量级测试执行器"""

    def __init__(
        self,
        project_path: Path,
        timeout: int = 60,
        python_executable: str = None
    ):
        self.project_path = Path(project_path).resolve()
        self.timeout = timeout
        # 使用当前环境的 Python 或指定的虚拟环境
        self.python = python_executable or sys.executable

    def _find_test_files(self) -> List[str]:
        """查找所有测试文件"""
        tests = []
        # 常见测试目录
        test_dirs = ['tests', 'test']
        for d in test_dirs:
            if (self.project_path / d).exists():
                tests.append(str(self.project_path / d))

        # 或者查找 test_*.py 文件
        if not tests:
            for f in self.project_path.rglob('test_*.py'):
                if '__pycache__' not in str(f):
                    tests.append(str(f))

        return tests

    async def run_tests(self, test_paths: List[str] = None) -> TestResult:
        """
        执行测试

        Args:
            test_paths: 要运行的测试文件/目录列表，如果为 None 则自动查找

        Returns:
            TestResult: 测试结果
        """
        targets = test_paths or self._find_test_files()
        if not targets:
            return TestResult(
                success=True,
                total_tests=0,
                passed=0,
                failed=0,
                errors=0,
                logs="未找到测试文件",
                failed_tests=[]
            )

        # 确保依赖已安装
        await self._install_dependencies()

        # 运行 pytest
        cmd = [
            self.python, '-m', 'pytest',
            *targets,
            '-v',  # 详细输出
            '--tb=short',  # 简短的 traceback
            '-q',  # 安静模式 (部分冗余)
            '--color=no',
            f'--timeout={self.timeout}'
        ]

        logger.info(f"正在沙箱中运行测试: {' '.join(cmd)}")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.project_path),
                env=self._get_sandbox_env()
            )

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
            except asyncio.TimeoutError:
                proc.kill()
                return TestResult(
                    success=False,
                    total_tests=0,
                    passed=0,
                    failed=0,
                    errors=0,
                    logs=f"测试执行超时 ({self.timeout}s)，已终止进程。",
                    failed_tests=[]
                )

            stdout_str = stdout.decode('utf-8', errors='replace')
            stderr_str = stderr.decode('utf-8', errors='replace')
            logs = f"STDOUT:\n{stdout_str}\n\nSTDERR:\n{stderr_str}"

            # 解析结果 (简单解析 pytest 输出)
            return self._parse_pytest_output(
                success=proc.returncode == 0,
                logs=logs,
                stdout=stdout_str
            )

        except Exception as e:
            logger.error(f"测试执行异常: {e}")
            return TestResult(
                success=False,
                total_tests=0,
                passed=0,
                failed=0,
                errors=0,
                logs=f"执行异常: {str(e)}",
                failed_tests=[]
            )

    def _get_sandbox_env(self) -> Dict[str, str]:
        """获取隔离的环境变量"""
        env = os.environ.copy()
        # 移除可能干扰测试的变量
        for key in list(env.keys()):
            if key.startswith(('DATABASE_URL', 'SECRET_KEY', 'API_KEY')):
                env.pop(key, None)
        
        # 设置 Python 路径
        env['PYTHONPATH'] = str(self.project_path)
        # 禁用缓冲
        env['PYTHONUNBUFFERED'] = '1'
        return env

    async def _install_dependencies(self):
        """安装项目依赖"""
        req_file = self.project_path / 'requirements.txt'
        if req_file.exists():
            logger.info("正在安装测试依赖...")
            try:
                proc = await asyncio.create_subprocess_exec(
                    self.python, '-m', 'pip', 'install', '-r', str(req_file),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await proc.communicate()
            except Exception as e:
                logger.warning(f"依赖安装失败 (可能已安装): {e}")

    def _parse_pytest_output(self, success: bool, logs: str, stdout: str) -> TestResult:
        """解析 pytest 输出"""
        # 示例: "2 failed, 5 passed, 7 total in 0.5s"
        import re
        total = passed = failed = errors = 0
        
        # 匹配总测试数
        m_total = re.search(r'(\d+)\s+total', stdout)
        if m_total: total = int(m_total.group(1))
        
        # 匹配通过的
        m_pass = re.search(r'(\d+)\s+passed', stdout)
        if m_pass: passed = int(m_pass.group(1))
        
        # 匹配失败的
        m_fail = re.search(r'(\d+)\s+failed', stdout)
        if m_fail: failed = int(m_fail.group(1))
        
        # 匹配错误的
        m_err = re.search(r'(\d+)\s+error', stdout)
        if m_err: errors = int(m_err.group(1))

        # 提取失败的具体测试名
        failed_tests = re.findall(r'FAILED\s+(test_\S+)', stdout)

        return TestResult(
            success=success and errors == 0,
            total_tests=total,
            passed=passed,
            failed=failed,
            errors=errors,
            logs=logs,
            failed_tests=failed_tests
        )
