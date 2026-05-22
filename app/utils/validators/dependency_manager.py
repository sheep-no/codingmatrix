"""
依赖管理器 - 自动安装和验证 Python 项目依赖
"""
import asyncio
import subprocess
import sys
import tempfile
import venv
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class DependencyInfo:
    """依赖信息"""
    name: str
    version_spec: str
    installed_version: Optional[str] = None
    status: str = "pending"  # pending/installed/failed/conflict
    error: Optional[str] = None


@dataclass
class InstallResult:
    """安装结果"""
    success: bool
    total_packages: int
    installed: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    already_installed: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    venv_path: Optional[Path] = None
    duration_seconds: float = 0.0


class DependencyManager:
    """依赖管理器"""
    
    def __init__(self, project_path: Path, auto_create_venv: bool = True):
        self.project_path = project_path
        self.auto_create_venv = auto_create_venv
        self.python_executable: Optional[str] = None
        self.venv_path: Optional[Path] = None
    
    async def install_requirements(
        self,
        use_venv: bool = True,
        timeout: int = 300
    ) -> InstallResult:
        """
        安装项目依赖
        
        Args:
            use_venv: 是否使用虚拟环境
            timeout: 超时时间（秒）
        
        Returns:
            InstallResult: 安装结果
        """
        import time
        start_time = time.time()
        
        requirements_file = self.project_path / "requirements.txt"
        if not requirements_file.exists():
            logger.warning("未找到 requirements.txt 文件")
            return InstallResult(
                success=False,
                total_packages=0,
                errors=["未找到 requirements.txt 文件"]
            )
        
        # 解析依赖
        dependencies = self._parse_requirements(requirements_file)
        logger.info(f"解析到 {len(dependencies)} 个依赖")
        
        # 创建虚拟环境
        if use_env and self.auto_create_venv:
            venv_result = await self._create_venv()
            if not venv_result.success:
                return InstallResult(
                    success=False,
                    total_packages=len(dependencies),
                    errors=venv_result.errors
                )
            self.venv_path = venv_result.venv_path
        
        # 安装依赖
        result = await self._install_packages(dependencies, timeout)
        result.duration_seconds = time.time() - start_time
        
        return result
    
    def _parse_requirements(self, file_path: Path) -> List[DependencyInfo]:
        """解析 requirements.txt"""
        dependencies = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # 跳过注释和空行
                    if not line or line.startswith('#'):
                        continue
                    
                    # 解析包名和版本
                    if '==' in line:
                        name, version = line.split('==', 1)
                        dependencies.append(DependencyInfo(
                            name=name.strip(),
                            version_spec=f'=={version.strip()}'
                        ))
                    elif '>=' in line:
                        name, version = line.split('>=', 1)
                        dependencies.append(DependencyInfo(
                            name=name.strip(),
                            version_spec=f'>={version.strip()}'
                        ))
                    elif '<=' in line:
                        name, version = line.split('<=', 1)
                        dependencies.append(DependencyInfo(
                            name=name.strip(),
                            version_spec=f'<={version.strip()}'
                        ))
                    else:
                        dependencies.append(DependencyInfo(
                            name=line,
                            version_spec=''
                        ))
        except (ValueError, TypeError, RuntimeError, OSError) as e:
            logger.error(f"解析 requirements.txt 失败：{e}")
        
        return dependencies
    
    async def _create_venv(self) -> InstallResult:
        """创建虚拟环境"""
        try:
            self.venv_path = self.project_path / ".venv"
            logger.info(f"创建虚拟环境：{self.venv_path}")
            
            # 使用异步方式创建 venv
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: venv.create(self.venv_path, with_pip=True)
            )
            
            # 设置虚拟环境的 Python 解释器
            if sys.platform == 'win32':
                self.python_executable = str(self.venv_path / "Scripts" / "python.exe")
            else:
                self.python_executable = str(self.venv_path / "bin" / "python")
            
            logger.info(f"虚拟环境创建成功，Python: {self.python_executable}")
            
            return InstallResult(
                success=True,
                total_packages=0,
                venv_path=self.venv_path
            )
            
        except (ValueError, TypeError, RuntimeError, OSError) as e:
            logger.error(f"创建虚拟环境失败：{e}")
            return InstallResult(
                success=False,
                total_packages=0,
                errors=[f"创建虚拟环境失败：{str(e)}"]
            )
    
    async def _install_packages(
        self,
        dependencies: List[DependencyInfo],
        timeout: int
    ) -> InstallResult:
        """安装依赖包"""
        result = InstallResult(
            success=True,
            total_packages=len(dependencies),
            venv_path=self.venv_path
        )
        
        # 升级 pip
        await self._upgrade_pip()
        
        # 批量安装
        for dep in dependencies:
            try:
                logger.info(f"安装 {dep.name}{dep.version_spec}")
                
                cmd = [
                    self.python_executable or sys.executable,
                    "-m", "pip", "install",
                    "-q",  # 安静模式
                    f"{dep.name}{dep.version_spec}"
                ]
                
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout / len(dependencies) if dependencies else timeout
                )
                
                if process.returncode == 0:
                    result.installed.append(dep.name)
                    dep.status = "installed"
                    logger.debug(f"安装成功：{dep.name}")
                else:
                    error_msg = stderr.decode('utf-8', errors='ignore').strip()
                    result.failed.append(dep.name)
                    result.errors.append(f"{dep.name}: {error_msg}")
                    dep.status = "failed"
                    dep.error = error_msg
                    logger.error(f"安装失败：{dep.name} - {error_msg}")
                    
            except asyncio.TimeoutError:
                result.failed.append(dep.name)
                result.errors.append(f"{dep.name}: 安装超时")
                dep.status = "failed"
                dep.error = "安装超时"
                logger.error(f"安装超时：{dep.name}")
                
            except (ValueError, TypeError, RuntimeError, OSError) as e:
                result.failed.append(dep.name)
                result.errors.append(f"{dep.name}: {str(e)}")
                dep.status = "failed"
                dep.error = str(e)
                logger.error(f"安装异常：{dep.name} - {e}")
        
        if result.failed:
            result.success = False
        
        return result
    
    async def _upgrade_pip(self):
        """升级 pip"""
        try:
            cmd = [
                self.python_executable or sys.executable,
                "-m", "pip", "install", "--upgrade", "pip"
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
        except (ValueError, TypeError, RuntimeError, OSError) as e:
            logger.warning(f"升级 pip 失败：{e}，继续安装依赖")
    
    async def verify_imports(self, file_path: Path) -> Dict[str, bool]:
        """
        验证文件中的所有 import 是否能成功加载
        
        Returns:
            Dict[str, bool]: {模块名：是否可导入}
        """
        import ast
        
        if not file_path.exists():
            return {}
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content)
            imports = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name.split('.')[0])
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module.split('.')[0])
            
            results = {}
            for module in imports:
                try:
                    cmd = [
                        self.python_executable or sys.executable,
                        "-c", f"import {module}"
                    ]
                    process = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    _, stderr = await process.communicate()
                    
                    if process.returncode == 0:
                        results[module] = True
                    else:
                        results[module] = False
                        logger.warning(f"模块 {module} 导入失败")
                        
                except (ValueError, TypeError, RuntimeError, OSError) as e:
                    results[module] = False
                    logger.error(f"验证模块 {module} 失败：{e}")
            
            return results
            
        except (ValueError, TypeError, RuntimeError, OSError) as e:
            logger.error(f"验证导入失败：{e}")
            return {}
    
    async def check_conflicts(self) -> List[str]:
        """检查依赖冲突"""
        conflicts = []
        
        # 检查已安装的包
        try:
            cmd = [
                self.python_executable or sys.executable,
                "-m", "pip", "list", "--format=freeze"
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()
            
            if process.returncode == 0:
                installed = {}
                for line in stdout.decode('utf-8').splitlines():
                    if '==' in line:
                        name, version = line.split('==', 1)
                        installed[name.lower()] = version
                
                # 检查 requirements.txt 中的依赖
                requirements_file = self.project_path / "requirements.txt"
                if requirements_file.exists():
                    dependencies = self._parse_requirements(requirements_file)
                    
                    for dep in dependencies:
                        dep_name_lower = dep.name.lower()
                        if dep_name_lower in installed:
                            installed_version = installed[dep_name_lower]
                            # 简单的版本冲突检查
                            if dep.version_spec:
                                if '==' in dep.version_spec:
                                    required_version = dep.version_spec.replace('==', '')
                                    if installed_version != required_version:
                                        conflicts.append(
                                            f"{dep.name}: 需要 {required_version}, "
                                            f"已安装 {installed_version}"
                                        )
        except (ValueError, TypeError, RuntimeError, OSError) as e:
            logger.error(f"检查依赖冲突失败：{e}")
        
        return conflicts
