"""
File Operator - 公共文件操作工具

提供安全的文件操作能力，供以下模块复用：
- AIProject (ProjectFileManager)
- Workflow (FileProcessingNode)
- AICloud

安全特性：
- 路径白名单验证
- 敏感路径保护
- 操作审计
"""

import os
import re
import shutil
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from collections import defaultdict


class FileOperatorError(Exception):
    """文件操作异常"""
    pass


class PathSecurityError(FileOperatorError):
    """路径安全验证失败"""
    pass


class FileOperator:
    """
    公共文件操作工具

    安全特性：
    - 禁止操作系统关键路径 (/etc, /root, /proc, /sys 等)
    - 禁止敏感文件 (.env, *.key, *.pem, id_rsa, .git/config)
    - 白名单扩展名检查
    """

    PROTECTED_PATHS: Set[str] = {
        "/etc", "/root", "/proc", "/sys", "/boot", "/dev",
        "/var/log", "/var/cache", "/var/run", "/tmp"  # /tmp 限制写入
    }

    PROTECTED_FILES: Set[str] = {
        ".env", ".git/config", "id_rsa", "id_ed25519",
        "known_hosts", "authorized_keys", ".bashrc", ".profile",
        ".bash_history", ".zsh_history", ".sudo_as_admin_successful"
    }

    SAFE_EXTENSIONS: Set[str] = {
        # 代码文件
        ".py", ".js", ".ts", ".jsx", ".tsx", ".vue", ".html", ".css", ".scss",
        ".sass", ".less", ".json", ".yaml", ".yml", ".xml", ".toml", ".ini",
        ".cfg", ".conf", ".properties", ".env", ".gitignore", ".dockerignore",
        # 后端
        ".java", ".c", ".cpp", ".h", ".hpp", ".go", ".rs", ".rb", ".php",
        ".swift", ".kt", ".scala", ".cs", ".fs",
        # 前端/移动
        ".md", ".txt", ".pdf", ".doc", ".docx",
        # 脚本
        ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd",
        # 数据
        ".sql", ".db", ".sqlite", ".csv", ".xlsx", ".xls",
        # 容器/部署
        ".dockerfile", "dockerfile", ".gitignore", ".dockerignore",
        "makefile", "makefile", "recipe", ".env", ".env.example",
        # 配置
        ".lock", ".md", ".txt", ".rst",
        # 静态资源
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico",
        ".woff", ".woff2", ".ttf", ".eot", ".otf",
    }

    SKIP_DIRS: Set[str] = {
        "__pycache__", ".git", ".svn", ".hg", "node_modules",
        ".pytest_cache", ".mypy_cache", ".tox", "venv", ".venv",
        "env", ".env", ".idea", ".vscode", ".vs", "dist", "build",
        ".next", ".nuxt", ".cache", ".parcel-cache", ".sass-cache"
    }

    def __init__(
        self,
        base_path: Optional[str] = None,
        allow_protected_paths: bool = False,
        safe_extensions: Optional[Set[str]] = None,
    ):
        """
        初始化文件操作工具

        Args:
            base_path: 基础路径，限制所有操作在此目录下
            allow_protected_paths: 是否允许操作受保护路径（危险，仅用于测试）
            safe_extensions: 自定义安全扩展名集合
        """
        self.base_path = Path(base_path) if base_path else None
        self.allow_protected_paths = allow_protected_paths
        self.safe_extensions = safe_extensions or self.SAFE_EXTENSIONS

    def _validate_path(
        self,
        path: str,
        must_exist: bool = False,
        check_extension: bool = True,
    ) -> Path:
        """
        验证路径安全性

        Args:
            path: 待验证的路径
            must_exist: 路径是否必须存在
            check_extension: 是否检查扩展名

        Returns:
            Path: 验证后的绝对路径

        Raises:
            PathSecurityError: 路径不安全
            FileNotFoundError: 路径不存在（当 must_exist=True）
        """
        if self.base_path:
            target = (self.base_path / path).resolve()
            resolved_base = self.base_path.resolve()
            if not str(target).startswith(str(resolved_base) + os.sep) and target != resolved_base:
                raise PathSecurityError(f"路径超出允许范围: {path}")
        else:
            target = Path(path).resolve()

        abs_path_str = str(target).lower()

        if not self.allow_protected_paths:
            for protected in self.PROTECTED_PATHS:
                if abs_path_str.startswith(protected.lower()):
                    raise PathSecurityError(f"禁止访问系统路径: {path}")

            for protected_file in self.PROTECTED_FILES:
                if protected_file.lower() in abs_path_str:
                    raise PathSecurityError(f"禁止访问敏感文件: {path}")

        if check_extension:
            ext = target.suffix.lower()
            if ext and ext not in self.safe_extensions:
                if ".env" not in abs_path_str:
                    raise PathSecurityError(f"不支持的文件扩展名: {ext}")

        if must_exist and not target.exists():
            raise FileNotFoundError(f"路径不存在: {path}")

        return target

    def _collect_files(self, base_dir: Path) -> List[Path]:
        """收集目录下所有文件"""
        files = []
        try:
            for item in base_dir.rglob("*"):
                if item.is_file():
                    rel_path = item.relative_to(base_dir)
                    skip = False
                    for part in rel_path.parts:
                        if part.startswith('.') or part in self.SKIP_DIRS:
                            skip = True
                            break
                    if not skip:
                        files.append(rel_path)
        except PermissionError:
            pass
        return files

    def read(
        self,
        path: str,
        offset: int = 0,
        limit: int = 100,
        encoding: str = "utf-8",
    ) -> Dict[str, Any]:
        """
        读取文件内容

        Args:
            path: 文件路径
            offset: 起始行号
            limit: 读取行数
            encoding: 编码

        Returns:
            包含文件内容的字典
        """
        target = self._validate_path(path, must_exist=True, check_extension=False)

        if not target.is_file():
            raise FileNotFoundError(f"不是文件: {path}")

        with open(target, 'r', encoding=encoding, errors='replace') as f:
            lines = f.readlines()

        total_lines = len(lines)
        start = min(offset, total_lines)
        end = min(start + limit, total_lines)
        page_lines = lines[start:end]

        return {
            "path": path,
            "total_lines": total_lines,
            "offset": start,
            "limit": limit,
            "has_more": end < total_lines,
            "content": ''.join(page_lines),
            "size": target.stat().st_size,
        }

    def write(
        self,
        path: str,
        content: str,
        encoding: str = "utf-8",
        create_backup: bool = False,
    ) -> Dict[str, Any]:
        """
        写入文件内容

        Args:
            path: 文件路径
            content: 文件内容
            encoding: 编码
            create_backup: 是否创建备份

        Returns:
            操作结果
        """
        target = self._validate_path(path, must_exist=False, check_extension=False)

        old_size = target.stat().st_size if target.exists() else 0

        if create_backup and target.exists():
            backup_file = target.with_suffix(target.suffix + '.bak')
            shutil.copy2(target, backup_file)

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding=encoding)

        new_size = len(content.encode(encoding))

        return {
            "success": True,
            "path": path,
            "size": new_size,
            "size_changed": new_size - old_size,
            "backup": f"{path}.bak" if create_backup else None,
        }

    def create(
        self,
        path: str,
        is_directory: bool = False,
        content: str = "",
    ) -> Dict[str, Any]:
        """
        创建文件或目录

        Args:
            path: 路径
            is_directory: 是否创建目录
            content: 文件内容（仅文件）

        Returns:
            操作结果
        """
        target = self._validate_path(path, must_exist=False)

        if target.exists():
            raise FileExistsError(f"路径已存在: {path}")

        if is_directory:
            target.mkdir(parents=True, exist_ok=True)
            return {"success": True, "path": path, "type": "directory"}
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8')
            return {"success": True, "path": path, "type": "file"}

    def delete(self, path: str, recursive: bool = False) -> Dict[str, Any]:
        """
        删除文件或目录

        Args:
            path: 路径
            recursive: 是否递归删除

        Returns:
            操作结果
        """
        target = self._validate_path(path, must_exist=True, check_extension=False)

        if target.is_dir():
            if recursive:
                shutil.rmtree(target)
            else:
                target.rmdir()
        else:
            target.unlink()

        return {"success": True, "path": path, "deleted": True}

    def move(
        self,
        source: str,
        destination: str,
    ) -> Dict[str, Any]:
        """
        移动/重命名文件或目录

        Args:
            source: 源路径
            destination: 目标路径

        Returns:
            操作结果
        """
        src_target = self._validate_path(source, must_exist=True, check_extension=False)
        dst_target = self._validate_path(destination, must_exist=False, check_extension=False)

        if dst_target.exists():
            raise FileExistsError(f"目标路径已存在: {destination}")

        dst_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_target), str(dst_target))

        return {"success": True, "source": source, "destination": destination}

    def copy(
        self,
        source: str,
        destination: str,
    ) -> Dict[str, Any]:
        """
        复制文件或目录

        Args:
            source: 源路径
            destination: 目标路径

        Returns:
            操作结果
        """
        src_target = self._validate_path(source, must_exist=True, check_extension=False)
        dst_target = self._validate_path(destination, must_exist=False, check_extension=False)

        os.makedirs(dst_target.parent, exist_ok=True)

        if src_target.is_dir():
            shutil.copytree(src_target, dst_target, dirs_exist_ok=True)
        else:
            shutil.copy2(src_target, dst_target)

        return {
            "success": True,
            "source": source,
            "destination": destination,
            "size": dst_target.stat().st_size if dst_target.exists() else 0,
        }

    def list_dir(
        self,
        path: str = ".",
        recursive: bool = False,
        pattern: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        列出目录内容

        Args:
            path: 目录路径
            recursive: 是否递归
            pattern: 文件名过滤正则

        Returns:
            目录内容
        """
        target = self._validate_path(path, must_exist=True, check_extension=False)

        if not target.is_dir():
            raise NotADirectoryError(f"不是目录: {path}")

        file_pattern = re.compile(pattern) if pattern else None
        entries = []

        def add_entries(dir_path: Path, rel_base: Path):
            try:
                for item in sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name)):
                    rel_path = item.relative_to(rel_base)

                    skip = False
                    for part in rel_path.parts:
                        if part.startswith('.') or part in self.SKIP_DIRS:
                            skip = True
                            break

                    if skip:
                        continue

                    if file_pattern and not file_pattern.match(item.name):
                        continue

                    if item.is_dir():
                        if recursive:
                            entries.append({
                                "name": item.name,
                                "path": str(rel_path),
                                "type": "directory",
                            })
                            add_entries(item, rel_base)
                        else:
                            entries.append({
                                "name": item.name,
                                "path": str(rel_path),
                                "type": "directory",
                            })
                    else:
                        entries.append({
                            "name": item.name,
                            "path": str(rel_path),
                            "type": "file",
                            "size": item.stat().st_size,
                        })
            except PermissionError:
                pass

        add_entries(target, target)

        return {
            "path": path,
            "entries": entries,
            "count": len(entries),
            "recursive": recursive,
        }

    def search(
        self,
        pattern: str,
        path: str = ".",
        file_pattern: str = ".*",
        case_sensitive: bool = True,
        max_results: int = 100,
    ) -> Dict[str, Any]:
        """
        正则搜索文件内容

        Args:
            pattern: 正则表达式
            path: 搜索路径
            file_pattern: 文件名匹配模式
            case_sensitive: 是否区分大小写
            max_results: 最大结果数

        Returns:
            搜索结果
        """
        target = self._validate_path(path, must_exist=True)

        try:
            regex_flags = 0 if case_sensitive else re.IGNORECASE
            search_pattern = re.compile(pattern, regex_flags)
            name_pattern = re.compile(file_pattern, regex_flags)
        except re.error as e:
            raise ValueError(f"无效的正则表达式: {e}")

        results = []
        files_searched = 0

        for rel_path in self._collect_files(target):
            if not name_pattern.match(rel_path.name):
                continue

            files_searched += 1
            file_path = target / rel_path

            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line_num, line in enumerate(f, 1):
                        if search_pattern.search(line):
                            match = search_pattern.search(line)
                            results.append({
                                'file': str(rel_path),
                                'line': line_num,
                                'content': line.rstrip(),
                                'match': line[match.start():match.end()]
                            })
                            if len(results) >= max_results:
                                break
            except (IOError, OSError):
                continue

            if len(results) >= max_results:
                break

        return {
            "pattern": pattern,
            "files_searched": files_searched,
            "matches_found": len(results),
            "results": results[:max_results],
        }

    def grep(
        self,
        keyword: str,
        path: str = ".",
        file_types: Optional[str] = None,
        case_sensitive: bool = True,
    ) -> Dict[str, Any]:
        """
        快速全文搜索

        Args:
            keyword: 搜索关键词
            path: 搜索路径
            file_types: 文件类型过滤，如 .py,.js
            case_sensitive: 是否区分大小写

        Returns:
            搜索结果
        """
        target = self._validate_path(path, must_exist=True)

        allowed_types = None
        if file_types:
            allowed_types = set(file_types.replace(' ', '').split(','))

        results = []
        files_searched = 0

        for rel_path in self._collect_files(target):
            if allowed_types and not any(rel_path.name.endswith(t) for t in allowed_types):
                continue

            files_searched += 1
            file_path = target / rel_path

            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')

                search_content = content if case_sensitive else content.lower()
                search_keyword = keyword if case_sensitive else keyword.lower()

                if search_keyword in search_content:
                    matches = []
                    for i, line in enumerate(content.split('\n'), 1):
                        search_line = line if case_sensitive else line.lower()
                        if search_keyword in search_line:
                            matches.append({"line": i, "content": line[:200]})
                            if len(matches) >= 5:
                                break

                    results.append({
                        "file": str(rel_path),
                        "total_matches": search_content.count(search_keyword),
                        "preview": matches
                    })
            except (IOError, OSError, UnicodeDecodeError):
                continue

            if len(results) >= 50:
                break

        return {
            "keyword": keyword,
            "files_searched": files_searched,
            "matched_files": len(results),
            "results": results,
        }

    def tree(self, path: str = ".", max_depth: int = 5) -> Dict[str, Any]:
        """
        获取目录结构树

        Args:
            path: 起始路径
            max_depth: 最大深度

        Returns:
            目录树
        """
        target = self._validate_path(path, must_exist=True, check_extension=False)

        def build_tree(current_path: Path, current_depth: int) -> Optional[Dict]:
            if current_depth > max_depth:
                return None

            node = {
                "name": current_path.name,
                "type": "directory" if current_path.is_dir() else "file"
            }

            if current_path.is_dir() and current_depth < max_depth:
                children = []
                try:
                    for item in sorted(current_path.iterdir(), key=lambda x: (not x.is_dir(), x.name)):
                        if item.name.startswith('.') or item.name in self.SKIP_DIRS:
                            continue
                        child = build_tree(item, current_depth + 1)
                        if child:
                            children.append(child)
                except PermissionError:
                    pass
                node["children"] = children

            return node

        tree = build_tree(target, 0)
        file_count = sum(1 for _ in target.rglob("*") if _.is_file() and not _.name.startswith('.'))

        return {
            "path": path,
            "tree": tree,
            "file_count": file_count,
        }

    def stats(self, path: str = ".") -> Dict[str, Any]:
        """
        获取统计信息

        Args:
            path: 路径

        Returns:
            统计信息
        """
        target = self._validate_path(path, must_exist=True)

        stats = {
            "total_files": 0,
            "total_lines": 0,
            "total_size": 0,
            "by_extension": defaultdict(lambda: {"count": 0, "lines": 0})
        }

        for rel_path in self._collect_files(target):
            stats["total_files"] += 1
            file_path = target / rel_path
            stats["total_size"] += file_path.stat().st_size

            ext = rel_path.suffix or "(no extension)"
            stats["by_extension"][ext]["count"] += 1

            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    line_count = len(f.readlines())
                    stats["total_lines"] += line_count
                    stats["by_extension"][ext]["lines"] += line_count
            except (IOError, OSError):
                pass

        stats["by_extension"] = dict(stats["by_extension"])

        return {
            "path": path,
            **stats
        }

    async def read_async(
        self,
        path: str,
        offset: int = 0,
        limit: int = 100,
        encoding: str = "utf-8",
    ) -> Dict[str, Any]:
        """异步读取文件"""
        return await asyncio.to_thread(self.read, path, offset, limit, encoding)

    async def write_async(
        self,
        path: str,
        content: str,
        encoding: str = "utf-8",
        create_backup: bool = False,
    ) -> Dict[str, Any]:
        """异步写入文件"""
        return await asyncio.to_thread(self.write, path, content, encoding, create_backup)

    async def list_dir_async(
        self,
        path: str = ".",
        recursive: bool = False,
        pattern: Optional[str] = None,
    ) -> Dict[str, Any]:
        """异步列出目录"""
        return await asyncio.to_thread(self.list_dir, path, recursive, pattern)

    async def search_async(
        self,
        pattern: str,
        path: str = ".",
        file_pattern: str = ".*",
        case_sensitive: bool = True,
        max_results: int = 100,
    ) -> Dict[str, Any]:
        """异步搜索"""
        return await asyncio.to_thread(
            self.search, pattern, path, file_pattern, case_sensitive, max_results
        )
