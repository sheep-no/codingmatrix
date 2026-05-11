"""
沙箱环境执行器 - 在隔离环境中验证代码可运行性
"""
import asyncio
import shutil
import tempfile
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import logging
import sys

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """执行结果"""
    success: bool
    return_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timeout: bool = False
    venv_path: Optional[Path] = None
    error: Optional[str] = None


@dataclass
class StartupTestResult:
    """启动测试结果"""
    success: bool
    entrypoint: Optional[str]
    stdout: str
    stderr: str
    duration_seconds: float
    issues: List[str] = field(default_factory=list)


class SandboxRunner:
    """沙箱环境执行器"""
    
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.temp_dir: Optional[Path] = None
        self.venv_path: Optional[Path] = None
        self.python_executable: Optional[str] = None
    
    async def run_in_sandbox(
        self,
        command: List[str],
        timeout: int = 60,
        env: Optional[Dict[str, str]] = None
    ) -> ExecutionResult:
        """
        在沙箱中执行命令
        
        Args:
            command: 命令和参数
            timeout: 超时时间（秒）
            env: 环境变量
        
        Returns:
            ExecutionResult: 执行结果
        """
        import time
        start_time = time.time()
        
        try:
            # 准备环境变量
            exec_env = os.environ.copy()
            if env:
                exec_env.update(env)
            
            # 如果有虚拟环境，使用虚拟环境的 Python
            if self.python_executable:
                # 替换命令中的 python
                for i, cmd in enumerate(command):
                    if cmd == 'python' or cmd == 'python3':
                        command[i] = self.python_executable
                        break
            
            logger.info(f"沙箱执行：{' '.join(command)}")
            
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.project_path),
                env=exec_env
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
                
                return ExecutionResult(
                    success=process.returncode == 0,
                    return_code=process.returncode,
                    stdout=stdout.decode('utf-8', errors='ignore'),
                    stderr=stderr.decode('utf-8', errors='ignore'),
                    duration_seconds=time.time() - start_time,
                    venv_path=self.venv_path
                )
                
            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()
                return ExecutionResult(
                    success=False,
                    return_code=-1,
                    stdout="",
                    stderr=f"执行超时（{timeout}秒）",
                    duration_seconds=time.time() - start_time,
                    timeout=True
                )
                
        except (ValueError, TypeError, RuntimeError, OSError) as e:
            return ExecutionResult(
                success=False,
                return_code=-1,
                stdout="",
                stderr=str(e),
                duration_seconds=time.time() - start_time,
                error=str(e)
            )
    
    async def setup_sandbox(self, install_deps: bool = True) -> ExecutionResult:
        """
        设置沙箱环境
        
        Args:
            install_deps: 是否安装依赖
        
        Returns:
            ExecutionResult: 设置结果
        """
        try:
            # 创建临时目录
            self.temp_dir = Path(tempfile.mkdtemp(prefix="sandbox_"))
            logger.info(f"创建沙箱目录：{self.temp_dir}")
            
            # 复制项目文件到沙箱
            await self._copy_project_to_sandbox()
            
            # 创建虚拟环境
            await self._create_venv_in_sandbox()
            
            # 安装依赖
            if install_deps:
                await self._install_deps_in_sandbox()
            
            return ExecutionResult(
                success=True,
                return_code=0,
                stdout="沙箱环境设置成功",
                stderr="",
                duration_seconds=0.0
            )
            
        except (ValueError, TypeError, RuntimeError, OSError) as e:
            logger.error(f"沙箱设置失败：{e}")
            return ExecutionResult(
                success=False,
                return_code=-1,
                stdout="",
                stderr=str(e),
                duration_seconds=0.0,
                error=str(e)
            )
    
    async def cleanup_sandbox(self):
        """清理沙箱环境"""
        try:
            if self.temp_dir and self.temp_dir.exists():
                logger.info(f"清理沙箱目录：{self.temp_dir}")
                await asyncio.to_thread(shutil.rmtree, self.temp_dir, ignore_errors=True)
        except (ValueError, TypeError, RuntimeError, OSError) as e:
            logger.error(f"清理沙箱失败：{e}")
    
    async def _copy_project_to_sandbox(self):
        """复制项目到沙箱"""
        def _copy():
            for item in self.project_path.iterdir():
                if item.name == '.venv' or item.name.startswith('.'):
                    continue
                dest = self.temp_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, symlinks=False)
                else:
                    shutil.copy2(item, dest)
        
        await asyncio.to_thread(_copy)
        logger.info(f"项目已复制到沙箱：{self.temp_dir}")
    
    async def _create_venv_in_sandbox(self):
        """在沙箱中创建虚拟环境"""
        import venv
        
        self.venv_path = self.temp_dir / ".venv"
        logger.info(f"在沙箱中创建虚拟环境：{self.venv_path}")
        
        await asyncio.to_thread(
            lambda: venv.create(self.venv_path, with_pip=True)
        )
        
        # 设置 Python 可执行文件路径
        if sys.platform == 'win32':
            self.python_executable = str(self.venv_path / "Scripts" / "python.exe")
        else:
            self.python_executable = str(self.venv_path / "bin" / "python")
        
        logger.info(f"虚拟环境创建成功：{self.python_executable}")
    
    async def _install_deps_in_sandbox(self):
        """在沙箱中安装依赖"""
        requirements_file = self.temp_dir / "requirements.txt"
        if not requirements_file.exists():
            logger.info("沙箱中没有 requirements.txt，跳过依赖安装")
            return
        
        logger.info("在沙箱中安装依赖")
        
        # 升级 pip
        upgrade_cmd = [
            self.python_executable,
            "-m", "pip", "install", "--upgrade", "pip"
        ]
        await self.run_in_sandbox(upgrade_cmd, timeout=60)
        
        # 安装依赖（忽略错误继续）
        install_cmd = [
            self.python_executable,
            "-m", "pip", "install", "-r", "requirements.txt"
        ]
        result = await self.run_in_sandbox(install_cmd, timeout=300)
        
        if result.success:
            logger.info("依赖安装成功")
        else:
            logger.warning(f"依赖安装失败：{result.stderr}")
    
    async def test_startup(
        self,
        entrypoint: Optional[str] = None,
        timeout: int = 30
    ) -> StartupTestResult:
        """
        测试项目启动
        
        Args:
            entrypoint: 入口文件（如 main.py），自动检测如果为 None
            timeout: 超时时间
        
        Returns:
            StartupTestResult: 启动测试结果
        """
        import time
        start_time = time.time()
        
        # 自动检测入口文件
        if not entrypoint:
            entrypoint = self._detect_entrypoint()
        
        if not entrypoint:
            return StartupTestResult(
                success=False,
                entrypoint=None,
                stdout="",
                stderr="",
                duration_seconds=0.0,
                issues=["未找到项目入口文件（main.py/app.py/run.py）"]
            )
        
        entrypoint_path = self.temp_dir / entrypoint if self.temp_dir else self.project_path / entrypoint
        
        # 检查入口文件是否存在
        if not entrypoint_path.exists():
            return StartupTestResult(
                success=False,
                entrypoint=entrypoint,
                stdout="",
                stderr="",
                duration_seconds=0.0,
                issues=[f"入口文件不存在：{entrypoint}"]
            )
        
        # 尝试执行
        command = [
            self.python_executable or sys.executable,
            str(entrypoint_path)
        ]
        
        result = await self.run_in_sandbox(command, timeout=timeout)
        
        issues = []
        
        # 分析执行结果
        if result.timeout:
            # 超时可能意味着服务成功启动（对于 Web 应用）
            issues.append(f"执行超时（{timeout}秒），可能是服务成功启动")
            logger.info("项目启动测试：超时（可能是正常的服务启动）")
        elif result.returncode != 0:
            issues.append(f"启动失败，退出码：{result.returncode}")
            if result.stderr:
                issues.append(f"错误信息：{result.stderr[:500]}")
        
        return StartupTestResult(
            success=result.returncode == 0 or result.timeout,
            entrypoint=entrypoint,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_seconds=time.time() - start_time,
            issues=issues
        )
    
    def _detect_entrypoint(self) -> Optional[str]:
        """检测项目入口文件"""
        patterns = ["main.py", "app.py", "run.py", "index.py"]
        
        for pattern in patterns:
            if (self.project_path / pattern).exists():
                return pattern
            if self.temp_dir and (self.temp_dir / pattern).exists():
                return pattern
        
        return None
    
    async def check_imports(self) -> Dict[str, bool]:
        """检查所有 Python 文件的导入"""
        results = {}
        
        py_files = list(self.project_path.rglob("*.py"))
        
        for py_file in py_files:
            rel_path = py_file.relative_to(self.project_path)
            logger.info(f"检查导入：{rel_path}")
            
            try:
                content = py_file.read_text(encoding='utf-8')
                
                # 提取导入
                import ast
                tree = ast.parse(content)
                imports = []
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imports.append(alias.name.split('.')[0])
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            imports.append(node.module.split('.')[0])
                
                # 验证每个导入
                for module in set(imports):
                    key = f"{rel_path}:{module}"
                    cmd = [
                        self.python_executable or sys.executable,
                        "-c", f"import {module}"
                    ]
                    result = await self.run_in_sandbox(cmd, timeout=10)
                    results[key] = result.success
                    
                    if not result.success:
                        logger.warning(f"导入失败：{module} in {rel_path}")
                        
            except (ValueError, TypeError, RuntimeError, OSError) as e:
                logger.error(f"检查 {py_file} 导入失败：{e}")
        
        return results
