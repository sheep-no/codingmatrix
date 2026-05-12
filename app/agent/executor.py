    async def _tool_git_status(self, params: Dict) -> ToolResult:
        """Git 状态工具"""
        import time
        import subprocess
        start = time.time()
        
        try:
            path = params.get("path", ".")
            # 验证路径安全性
            if not self._is_safe_path(path):
                return ToolResult(False, None, "路径不安全", time.time() - start, "git_status")
            
            result = subprocess.run(
                ["git", "status", "--porcelain", "-b"],
                cwd=path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return ToolResult(False, None, result.stderr.strip(), time.time() - start, "git_status")
            
            output = result.stdout.strip()
            if not output:
                output = "工作目录干净，没有未提交的更改"
            
            return ToolResult(True, {"status": output}, None, time.time() - start, "git_status")
            
        except subprocess.TimeoutExpired:
            return ToolResult(False, None, "命令执行超时", time.time() - start, "git_status")
        except Exception as e:
            return ToolResult(False, None, str(e), time.time() - start, "git_status")

    async def _tool_git_log(self, params: Dict) -> ToolResult:
        """Git 日志工具"""
        import time
        import subprocess
        start = time.time()
        
        try:
            path = params.get("path", ".")
            limit = params.get("limit", 10)
            
            if not self._is_safe_path(path):
                return ToolResult(False, None, "路径不安全", time.time() - start, "git_log")
            
            result = subprocess.run(
                ["git", "log", f"--max-count={limit}", "--pretty=format:%H|%an|%ad|%s", "--date=iso"],
                cwd=path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return ToolResult(False, None, result.stderr.strip(), time.time() - start, "git_log")
            
            commits = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.split('|', 3)
                    if len(parts) == 4:
                        commits.append({
                            "commit_id": parts[0],
                            "author": parts[1],
                            "date": parts[2],
                            "message": parts[3]
                        })
            
            return ToolResult(True, {"commits": commits}, None, time.time() - start, "git_log")
            
        except subprocess.TimeoutExpired:
            return ToolResult(False, None, "命令执行超时", time.time() - start, "git_log")
        except Exception as e:
            return ToolResult(False, None, str(e), time.time() - start, "git_log")

    async def _tool_git_diff(self, params: Dict) -> ToolResult:
        """Git 差异工具"""
        import time
        import subprocess
        start = time.time()
        
        try:
            path = params.get("path", ".")
            commit1 = params.get("commit1")
            commit2 = params.get("commit2")
            file_path = params.get("file_path")
            
            if not self._is_safe_path(path):
                return ToolResult(False, None, "路径不安全", time.time() - start, "git_diff")
            
            cmd = ["git", "diff"]
            
            if commit1 and commit2:
                cmd.extend([commit1, commit2])
            elif commit1:
                cmd.append(commit1)
            
            if file_path:
                if not self._is_safe_path(file_path):
                    return ToolResult(False, None, "文件路径不安全", time.time() - start, "git_diff")
                cmd.append(file_path)
            
            result = subprocess.run(
                cmd,
                cwd=path,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode not in [0, 1]:  # git diff 返回 1 表示有差异，这是正常的
                return ToolResult(False, None, result.stderr.strip(), time.time() - start, "git_diff")
            
            diff_output = result.stdout.strip()
            if not diff_output:
                diff_output = "没有发现差异"
            
            return ToolResult(True, {"diff": diff_output}, None, time.time() - start, "git_diff")
            
        except subprocess.TimeoutExpired:
            return ToolResult(False, None, "命令执行超时", time.time() - start, "git_diff")
        except Exception as e:
            return ToolResult(False, None, str(e), time.time() - start, "git_diff")

    async def _tool_git_checkout(self, params: Dict) -> ToolResult:
        """Git 切换工具"""
        import time
        import subprocess
        start = time.time()
        
        try:
            path = params.get("path", ".")
            target = params.get("target")
            create_branch = params.get("create_branch", False)
            
            if not target:
                return ToolResult(False, None, "缺少 target 参数", time.time() - start, "git_checkout")
            
            if not self._is_safe_path(path):
                return ToolResult(False, None, "路径不安全", time.time() - start, "git_checkout")
            
            cmd = ["git", "checkout"]
            if create_branch:
                cmd.append("-b")
            cmd.append(target)
            
            result = subprocess.run(
                cmd,
                cwd=path,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                return ToolResult(False, None, result.stderr.strip(), time.time() - start, "git_checkout")
            
            return ToolResult(True, {"message": f"成功切换到 {target}"}, None, time.time() - start, "git_checkout")
            
        except subprocess.TimeoutExpired:
            return ToolResult(False, None, "命令执行超时", time.time() - start, "git_checkout")
        except Exception as e:
            return ToolResult(False, None, str(e), time.time() - start, "git_checkout")

    async def _tool_git_reset(self, params: Dict) -> ToolResult:
        """Git 重置工具"""
        import time
        import subprocess
        start = time.time()
        
        try:
            path = params.get("path", ".")
            commit = params.get("commit")
            mode = params.get("mode", "mixed")
            
            if not commit:
                return ToolResult(False, None, "缺少 commit 参数", time.time() - start, "git_reset")
            
            if mode not in ["soft", "mixed", "hard"]:
                return ToolResult(False, None, "无效的重置模式", time.time() - start, "git_reset")
            
            if not self._is_safe_path(path):
                return ToolResult(False, None, "路径不安全", time.time() - start, "git_reset")
            
            # 安全检查：硬重置需要额外确认（这里通过参数控制）
            if mode == "hard":
                return ToolResult(False, None, "硬重置操作被禁止，请使用其他重置模式或联系管理员", time.time() - start, "git_reset")
            
            cmd = ["git", "reset", f"--{mode}", commit]
            result = subprocess.run(
                cmd,
                cwd=path,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                return ToolResult(False, None, result.stderr.strip(), time.time() - start, "git_reset")
            
            return ToolResult(True, {"message": f"成功重置到 {commit} ({mode} 模式)"}, None, time.time() - start, "git_reset")
            
        except subprocess.TimeoutExpired:
            return ToolResult(False, None, "命令执行超时", time.time() - start, "git_reset")
        except Exception as e:
            return ToolResult(False, None, str(e), time.time() - start, "git_reset")

    async def _tool_git_restore_file(self, params: Dict) -> ToolResult:
        """Git 文件恢复工具"""
        import time
        import subprocess
        import shutil
        start = time.time()
        
        try:
            path = params.get("path", ".")
            file_path = params.get("file_path")
            commit = params.get("commit")
            backup_current = params.get("backup_current", True)
            
            if not file_path:
                return ToolResult(False, None, "缺少 file_path 参数", time.time() - start, "git_restore_file")
            
            if not self._is_safe_path(path) or not self._is_safe_path(file_path):
                return ToolResult(False, None, "路径不安全", time.time() - start, "git_restore_file")
            
            full_file_path = os.path.join(path, file_path)
            
            # 备份当前文件（如果存在）
            if backup_current and os.path.exists(full_file_path):
                backup_path = f"{full_file_path}.backup.{int(time.time())}"
                shutil.copy2(full_file_path, backup_path)
            
            # 如果没有指定提交，默认使用 HEAD
            if not commit:
                commit = "HEAD"
            
            cmd = ["git", "show", f"{commit}:{file_path}"]
            result = subprocess.run(
                cmd,
                cwd=path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                error_msg = result.stderr.strip()
                if "exists on disk, but not in" in error_msg:
                    # 文件在指定提交中不存在
                    return ToolResult(False, None, f"文件 {file_path} 在提交 {commit} 中不存在", time.time() - start, "git_restore_file")
                else:
                    return ToolResult(False, None, error_msg, time.time() - start, "git_restore_file")
            
            # 写入恢复的文件内容
            with open(full_file_path, 'w', encoding='utf-8') as f:
                f.write(result.stdout)
            
            message = f"成功从提交 {commit} 恢复文件 {file_path}"
            if backup_current:
                message += f"（当前文件已备份为 {os.path.basename(backup_path)}）"
            
            return ToolResult(True, {"message": message}, None, time.time() - start, "git_restore_file")
            
        except subprocess.TimeoutExpired:
            return ToolResult(False, None, "命令执行超时", time.time() - start, "git_restore_file")
        except Exception as e:
            return ToolResult(False, None, str(e), time.time() - start, "git_restore_file")

    async def _tool_git_rollback(self, params: Dict) -> ToolResult:
        """Git 回滚工具"""
        import time
        import subprocess
        start = time.time()
        
        try:
            path = params.get("path", ".")
            target = params.get("target")
            create_backup = params.get("create_backup", True)
            backup_name = params.get("backup_name")
            
            if not target:
                return ToolResult(False, None, "缺少 target 参数", time.time() - start, "git_rollback")
            
            if not self._is_safe_path(path):
                return ToolResult(False, None, "路径不安全", time.time() - start, "git_rollback")
            
            # 创建备份分支
            if create_backup:
                if not backup_name:
                    backup_name = f"backup-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
                
                backup_cmd = ["git", "checkout", "-b", backup_name]
                backup_result = subprocess.run(
                    backup_cmd,
                    cwd=path,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if backup_result.returncode != 0:
                    return ToolResult(False, None, f"创建备份分支失败: {backup_result.stderr.strip()}", time.time() - start, "git_rollback")
                
                # 切回原分支
                original_branch_result = subprocess.run(
                    ["git", "checkout", "-"],
                    cwd=path,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if original_branch_result.returncode != 0:
                    return ToolResult(False, None, "无法切回原分支", time.time() - start, "git_rollback")
            
            # 找到目标提交
            if not self._is_commit_hash(target):
                # 尝试解析为时间点
                rev_parse_result = subprocess.run(
                    ["git", "rev-parse", target],
                    cwd=path,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if rev_parse_result.returncode != 0:
                    # 尝试查找最近的提交
                    log_result = subprocess.run(
                        ["git", "log", "--before", target, "--max-count=1", "--pretty=format:%H"],
                        cwd=path,
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    
                    if log_result.returncode == 0 and log_result.stdout.strip():
                        target_commit = log_result.stdout.strip()
                    else:
                        return ToolResult(False, None, f"无法解析目标: {target}", time.time() - start, "git_rollback")
                else:
                    target_commit = rev_parse_result.stdout.strip()
            else:
                target_commit = target
            
            # 执行回滚（使用 reset --mixed，不使用 --hard）
            rollback_cmd = ["git", "reset", "--mixed", target_commit]
            rollback_result = subprocess.run(
                rollback_cmd,
                cwd=path,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if rollback_result.returncode != 0:
                return ToolResult(False, None, rollback_result.stderr.strip(), time.time() - start, "git_rollback")
            
            message = f"成功回滚到 {target_commit}"
            if create_backup:
                message += f"（备份分支: {backup_name}）"
            
            return ToolResult(True, {"message": message, "commit": target_commit}, None, time.time() - start, "git_rollback")
            
        except subprocess.TimeoutExpired:
            return ToolResult(False, None, "命令执行超时", time.time() - start, "git_rollback")
        except Exception as e:
            return ToolResult(False, None, str(e), time.time() - start, "git_rollback")

    def _is_safe_path(self, path: str) -> bool:
        """检查路径是否安全（防止路径遍历）"""
        try:
            # 解析绝对路径
            abs_path = os.path.abspath(path)
            # 确保路径在工作目录内
            workspace_root = os.path.abspath(".")
            return os.path.commonpath([abs_path, workspace_root]) == workspace_root
        except:
            return False

    def _is_commit_hash(self, s: str) -> bool:
        """检查字符串是否为有效的 Git 提交哈希"""
        return bool(re.match(r'^[0-9a-f]{7,40}$', s))


class StreamingExecutor(EnhancedExecutor):
    """支持流式输出的执行器"""

    def __init__(self, file_operator=None):
        super().__init__(file_operator)
        self._stream_callback: Optional[Callable[[str], None]] = None

    def set_stream_callback(self, callback: Callable[[str], None]) -> None:
        self._stream_callback = callback

    async def _stream_output(self, text: str) -> None:
        """流式输出"""
        if self._stream_callback:
            try:
                self._stream_callback(text)
            except Exception as e:
                logger.error(f"流式输出回调失败: {e}")

    async def execute_with_stream(self, step: Dict) -> ToolResult:
        """带流式输出的执行"""
        step_type = step.get("type")

        await self._stream_output(f"[开始执行: {step_type}]\n")

        result = await self.execute(step)

        if result.success:
            await self._stream_output(f"[成功] {result.result}\n")
        else:
            await self._stream_output(f"[失败] {result.error}\n")

        return result

    async def execute_git_operation_with_sse(self, operation: str, params: Dict, sse_callback: Callable[[Dict], None]) -> ToolResult:
        """执行 Git 操作并发送 SSE 事件"""
        try:
            # 发送开始事件
            sse_callback({
                "type": "git_operation_start",
                "operation": operation,
                "params": params
            })
            
            # 执行操作
            result = await self.execute_tool(operation, params)
            
            if result.success:
                # 发送成功事件
                sse_callback({
                    "type": "git_operation_success",
                    "operation": operation,
                    "result": result.result
                })
            else:
                # 发送失败事件
                sse_callback({
                    "type": "git_operation_error",
                    "operation": operation,
                    "error": result.error
                })
            
            return result
            
        except Exception as e:
            # 发送异常事件
            sse_callback({
                "type": "git_operation_error",
                "operation": operation,
                "error": str(e)
            })
            return ToolResult(False, None, str(e), 0, operation)