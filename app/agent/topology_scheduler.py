"""
TopologyScheduler - 动态拓扑调度器

核心理念：实时触发调度，当文件完成时立即触发下游文件就绪。
保证任意文件生成时，其所有上游代码已确定，彻底杜绝接口猜测。

工作流程：
1. 从依赖图构建初始就绪队列（依赖计数为 0 的文件）
2. 并行执行就绪队列中的任务
3. 任务完成时，遍历下游文件，将依赖计数减 1
4. 若下游依赖计数变为 0，立即加入就绪队列
5. 持续循环直至所有文件完成
"""

import asyncio
import logging
import time
from typing import Dict, Any, Callable, List, Optional, Set, Awaitable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class HeartbeatTracker:
    """心跳活动跟踪器

    用于监控异步任务的生命体征。
    生成器在每次 LLM 调用时更新 last_activity，
    心跳监控器检查这个时间戳来判断任务是否存活。
    """

    def __init__(self, timeout: float = 300.0):
        self.timeout = timeout
        self.last_activity = time.time()
        self._lock = asyncio.Lock()

    def touch(self):
        """更新活动时间戳（由生成器在每次 LLM 调用时调用）"""
        self.last_activity = time.time()

    def is_alive(self) -> bool:
        """检查是否还在活动"""
        return time.time() - self.last_activity < self.timeout

    def elapsed(self) -> float:
        """距离上次活动的时间"""
        return time.time() - self.last_activity


class FileStatus(Enum):
    PENDING = "pending"
    READY = "ready"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass
class ScheduleNode:
    """调度节点状态"""
    file_path: str
    dependency_count: int
    status: FileStatus = FileStatus.PENDING
    generated_at: Optional[float] = None
    error: Optional[str] = None
    retry_count: int = 0


@dataclass
class ScheduleStats:
    """调度统计"""
    total_files: int = 0
    completed_files: int = 0
    failed_files: int = 0
    max_parallelism: int = 0
    avg_parallelism: float = 0.0
    total_wait_time: float = 0.0
    interface_errors: int = 0
    schedule_log: List[Dict[str, Any]] = field(default_factory=list)


class TopologyScheduler:
    """
    动态拓扑调度器

    与静态分层调度的区别：
    - 静态分层：预先计算所有层，同层文件并行但看不到同层输出
    - 动态拓扑：实时触发，文件完成时下游立即就绪，保证上下文确定性
    """

    def __init__(
        self,
        max_concurrent: int = 5,
        max_retries: int = 2,
        timeout_per_file: float = 180.0,
        heartbeat_timeout: float = 600.0,  # 心跳超时：600 秒无 LLM 调用活动视为僵尸（推理模型需要更长时间）
        cancel_event: Optional[asyncio.Event] = None,
        output_dir: Optional[str] = None  # 输出目录，用于文件写入
    ):
        self.max_concurrent = max_concurrent
        self.max_retries = max_retries
        self.timeout_per_file = timeout_per_file
        self.heartbeat_timeout = heartbeat_timeout
        self._external_cancel_event = cancel_event
        self.output_dir = output_dir

        self.nodes: Dict[str, ScheduleNode] = {}
        self.adjacency: Dict[str, Set[str]] = {}  # file -> files it depends on
        self.reverse_adjacency: Dict[str, Set[str]] = {}  # file -> files that depend on it

        self.ready_queue: asyncio.Queue = asyncio.Queue()
        self.completed_files: Dict[str, str] = {}  # path -> content
        self.stats = ScheduleStats()

        self._running_tasks: Set[asyncio.Task] = set()
        self._lock = asyncio.Lock()
        self._stop_event = asyncio.Event()

    def build_from_dependency_graph(self, dep_graph: Any) -> None:
        """从 DependencyGraph 构建调度状态"""
        self.nodes.clear()
        self.adjacency.clear()
        self.reverse_adjacency.clear()

        for path, node in dep_graph.nodes.items():
            dep_count = len(dep_graph.adjacency.get(path, set()))
            self.nodes[path] = ScheduleNode(
                file_path=path,
                dependency_count=dep_count,
                status=FileStatus.PENDING
            )
            self.adjacency[path] = set(dep_graph.adjacency.get(path, set()))

        for path, deps in dep_graph.reverse_adjacency.items():
            self.reverse_adjacency[path] = set(deps)

        self.stats.total_files = len(self.nodes)
        logger.info(f"TopologyScheduler 构建完成: {self.stats.total_files} 个文件节点")

    async def initialize_ready_queue(self) -> List[str]:
        """初始化就绪队列，返回初始就绪文件列表"""
        ready_files = []
        for path, node in self.nodes.items():
            if node.dependency_count == 0:
                node.status = FileStatus.READY
                await self.ready_queue.put(path)
                ready_files.append(path)

        self._log_schedule("initial_ready", ready_files)
        logger.info(f"初始就绪队列: {len(ready_files)} 个文件")
        return ready_files

    async def run(
        self,
        generator: Callable[[str, Dict[str, str], Optional["HeartbeatTracker"]], Awaitable[str]],
        progress_callback: Optional[Callable[[str, str, int, int], None]] = None,
        global_timeout: float = 7200.0  # 全局超时 120 分钟（免费模型慢）
    ) -> Dict[str, Any]:
        """
        执行动态拓扑调度

        Args:
            generator: 文件生成函数，签名 async (file_path, upstream_context) -> content
            progress_callback: 进度回调，签名 (event, file_path, completed, total)
            global_timeout: 全局超时时间（秒），默认 60 分钟

        Returns:
            {
                "success": bool,
                "generated_files": Dict[str, str],
                "failed_files": List[str],
                "stats": ScheduleStats
            }
        """
        await self.initialize_ready_queue()

        self._stop_event.clear()
        active_count = 0
        parallelism_samples = []
        start_time = time.time()

        # 联动外部 cancel_event：当用户取消时同步设置 _stop_event
        cancel_watcher = None
        if self._external_cancel_event:
            async def _watch_cancel():
                await self._external_cancel_event.wait()
                self._stop_event.set()
                logger.info("[Scheduler] 外部取消信号已同步到调度器")
            cancel_watcher = asyncio.create_task(_watch_cancel())

        try:
            while not self._should_stop():
                # 全局超时检查
                elapsed = time.time() - start_time
                if elapsed > global_timeout:
                    logger.error(f"[Scheduler] 全局超时 ({global_timeout}s)，强制终止")
                    self._stop_event.set()
                    break

                async with self._lock:
                    ready_count = self.ready_queue.qsize()
                    pending_count = sum(
                        1 for n in self.nodes.values()
                        if n.status in (FileStatus.PENDING, FileStatus.READY, FileStatus.GENERATING)
                    )

                    if ready_count == 0 and pending_count == 0:
                        blocked = sum(1 for n in self.nodes.values() if n.status == FileStatus.BLOCKED)
                        failed = sum(1 for n in self.nodes.values() if n.status == FileStatus.FAILED)
                        completed = sum(1 for n in self.nodes.values() if n.status == FileStatus.COMPLETED)
                        logger.info(f"[Scheduler] 无就绪/待处理文件，退出循环: completed={completed}, failed={failed}, blocked={blocked}")
                        break

                    if ready_count == 0 and pending_count > 0:
                        # 检查是否所有 pending 文件实际上都在 GENERATING（没有真正可做的）
                        generating_count = sum(1 for n in self.nodes.values() if n.status == FileStatus.GENERATING)
                        if generating_count == 0 and active_count == 0:
                            # 有 PENDING 文件但没有 READY 也没有 GENERATING，说明依赖图有死锁
                            pending_files = [p for p, n in self.nodes.items() if n.status == FileStatus.PENDING]
                            logger.error(f"[Scheduler] 疑似死锁: {len(pending_files)} 个 PENDING 文件但无 READY/GENERATING: {pending_files}")
                            self._stop_event.set()
                            break
                        await asyncio.sleep(0.1)
                        continue

                while active_count < self.max_concurrent and self.ready_queue.qsize() > 0:
                    try:
                        file_path = self.ready_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                    task = asyncio.create_task(
                        self._generate_file_with_retry(file_path, generator, progress_callback)
                    )
                    self._running_tasks.add(task)
                    task.add_done_callback(self._running_tasks.discard)
                    active_count += 1

                parallelism_samples.append(active_count)

                done, _ = await asyncio.wait(
                    self._running_tasks,
                    timeout=0.5,
                    return_when=asyncio.FIRST_COMPLETED
                )

                for task in done:
                    active_count -= 1
                    try:
                        await task
                    except asyncio.CancelledError:
                        logger.warning(f"[Scheduler] 任务被取消: {task.get_name()}")
                    except Exception as e:
                        logger.error(f"任务执行异常: {e}")

            # 全局超时或正常结束后，取消所有还在运行的任务
            if self._running_tasks:
                logger.warning(f"[Scheduler] 取消 {len(self._running_tasks)} 个未完成的任务")
                for task in self._running_tasks:
                    task.cancel()
                await asyncio.gather(*self._running_tasks, return_exceptions=True)

            # 取消后统一收敛节点状态，防止工作流留下 GENERATING/PENDING 节点并持续等待。
            async with self._lock:
                for node in self.nodes.values():
                    if node.status in (FileStatus.PENDING, FileStatus.READY, FileStatus.GENERATING):
                        node.status = FileStatus.FAILED
                        node.error = node.error or "调度器在任务完成前停止"
                        self.stats.failed_files += 1
        finally:
            if cancel_watcher and not cancel_watcher.done():
                cancel_watcher.cancel()
                try:
                    await cancel_watcher
                except asyncio.CancelledError:
                    pass

        self.stats.max_parallelism = max(parallelism_samples) if parallelism_samples else 0
        self.stats.avg_parallelism = sum(parallelism_samples) / len(parallelism_samples) if parallelism_samples else 0

        failed_files = [
            path for path, node in self.nodes.items()
            if node.status in (FileStatus.FAILED, FileStatus.BLOCKED)
        ]
        terminal = all(
            node.status in (FileStatus.COMPLETED, FileStatus.FAILED, FileStatus.BLOCKED)
            for node in self.nodes.values()
        )

        return {
            "success": terminal and len(failed_files) == 0,
            "generated_files": self.completed_files,
            "failed_files": failed_files,
            "stats": self.stats
        }

    async def _generate_file_with_retry(
        self,
        file_path: str,
        generator: Callable,
        progress_callback: Optional[Callable] = None
    ) -> None:
        """带重试的单文件生成（心跳监控）"""
        node = self.nodes[file_path]
        node.status = FileStatus.GENERATING

        upstream_context = self._build_upstream_context(file_path)
        tracker = HeartbeatTracker(timeout=self.heartbeat_timeout)

        for attempt in range(self.max_retries + 1):
            try:
                if progress_callback:
                    progress_callback("start", file_path, self.stats.completed_files, self.stats.total_files)

                content = await asyncio.wait_for(
                    self._run_with_heartbeat(
                        generator(file_path, upstream_context, tracker),
                        file_path,
                        tracker
                    ),
                    timeout=self.timeout_per_file,
                )

                async with self._lock:
                    self.completed_files[file_path] = content
                    node.status = FileStatus.COMPLETED
                    node.generated_at = time.time()
                    self.stats.completed_files += 1

                    await self._trigger_downstream(file_path)

                self._log_schedule("completed", [file_path])

                if progress_callback:
                    progress_callback("completed", file_path, self.stats.completed_files, self.stats.total_files)

                return

            except asyncio.TimeoutError:
                node.retry_count += 1
                logger.warning(f"文件生成超时（心跳超时）: {file_path} (尝试 {attempt + 1}/{self.max_retries + 1})")

            except asyncio.CancelledError:
                node.retry_count += 1
                node.error = "任务被取消"
                logger.warning(f"文件生成被取消: {file_path} (尝试 {attempt + 1}/{self.max_retries + 1})")
                raise

            except Exception as e:
                node.retry_count += 1
                node.error = str(e)
                logger.error(f"文件生成失败: {file_path} - {e} (尝试 {attempt + 1}/{self.max_retries + 1})")

        async with self._lock:
            node.status = FileStatus.FAILED
            self.stats.failed_files += 1
            await self._block_downstream(file_path)

        self._log_schedule("failed", [file_path], error=node.error)

        if progress_callback:
            progress_callback("failed", file_path, self.stats.completed_files, self.stats.total_files)

    async def _run_with_heartbeat(self, coro, file_path: str, tracker: Optional[HeartbeatTracker] = None) -> str:
        """带心跳监控的协程执行

        监控 LLM 调用活动，如果 heartbeat_timeout 秒内没有 LLM 调用，
        认为是僵尸任务并取消。

        Args:
            coro: 要执行的协程
            file_path: 目标文件路径（用于日志）
            tracker: 心跳活动跟踪器（由生成器更新）

        Returns:
            协程的返回值
        """
        if tracker is None:
            tracker = HeartbeatTracker(timeout=self.heartbeat_timeout)

        task = asyncio.create_task(coro)
        check_interval = 10.0  # 每 10 秒检查一次

        try:
            while not task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=check_interval)
                    # 任务完成，返回结果
                    return task.result()
                except asyncio.TimeoutError:
                    # shield 超时，但任务还在运行
                    if not tracker.is_alive():
                        # 心跳超时，取消任务
                        task.cancel()
                        await asyncio.gather(task, return_exceptions=True)
                        raise asyncio.TimeoutError(
                            f"心跳超时: {self.heartbeat_timeout}s 内无 LLM 调用活动"
                        )
                    # else: 继续等待

            # 任务已完成（可能被取消或异常）
            return task.result()
        except asyncio.CancelledError:
            # 外层单文件超时或调度器停止时，回收内部生成任务。
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise

    async def _trigger_downstream(self, completed_file: str) -> None:
        """触发下游文件就绪检查"""
        downstream_files = self.reverse_adjacency.get(completed_file, set())
        newly_ready = []

        for downstream in downstream_files:
            if downstream not in self.nodes:
                continue

            node = self.nodes[downstream]
            # PENDING 和 BLOCKED 状态都需要检查（BLOCKED 可能因上游重试成功而解除）
            if node.status not in (FileStatus.PENDING, FileStatus.BLOCKED):
                continue

            if node.status == FileStatus.BLOCKED:
                # 重新检查所有上游依赖是否都已完成
                all_deps = self.adjacency.get(downstream, set())
                all_completed = all(
                    dep not in self.nodes or self.nodes[dep].status == FileStatus.COMPLETED
                    for dep in all_deps
                )
                if not all_deps or all_completed:
                    node.status = FileStatus.READY
                    node.dependency_count = 0
                    await self.ready_queue.put(downstream)
                    newly_ready.append(downstream)
            else:
                node.dependency_count -= 1
                if node.dependency_count == 0:
                    node.status = FileStatus.READY
                    await self.ready_queue.put(downstream)
                    newly_ready.append(downstream)

        if newly_ready:
            self._log_schedule("triggered", newly_ready, source=completed_file)
            logger.info(f"文件 {completed_file} 完成，触发下游就绪: {newly_ready}")

    async def _block_downstream(self, failed_file: str) -> None:
        """阻塞下游文件"""
        downstream_files = self.reverse_adjacency.get(failed_file, set())
        blocked = []

        for downstream in downstream_files:
            if downstream not in self.nodes:
                continue

            node = self.nodes[downstream]
            if node.status in (FileStatus.PENDING, FileStatus.READY):
                node.status = FileStatus.BLOCKED
                blocked.append(downstream)

        if blocked:
            self._log_schedule("blocked", blocked, source=failed_file)
            logger.warning(f"文件 {failed_file} 失败，阻塞下游: {blocked}")

    def _build_upstream_context(self, file_path: str) -> Dict[str, str]:
        """构建上游文件上下文"""
        upstream_deps = self.adjacency.get(file_path, set())
        context = {}

        for dep_path in upstream_deps:
            if dep_path in self.completed_files:
                context[dep_path] = self.completed_files[dep_path]

        return context

    def _should_stop(self) -> bool:
        """检查是否应该停止调度"""
        if self._stop_event.is_set():
            return True

        # 没有 PENDING / READY / GENERATING 的文件了 → 所有文件都已终态（COMPLETED / FAILED / BLOCKED）
        has_actionable = any(
            n.status in (FileStatus.PENDING, FileStatus.READY, FileStatus.GENERATING)
            for n in self.nodes.values()
        )
        if has_actionable:
            return False

        # 所有文件都已终态，检查是否有 BLOCKED 的文件需要记录
        blocked_count = sum(1 for n in self.nodes.values() if n.status == FileStatus.BLOCKED)
        if blocked_count > 0:
            logger.warning(f"[Scheduler] {blocked_count} 个文件被阻塞（上游依赖失败），停止调度")

        return True

    def cancel(self) -> None:
        """取消调度"""
        self._stop_event.set()
        for task in self._running_tasks:
            task.cancel()

    def get_stats(self) -> Dict[str, Any]:
        """获取调度统计"""
        return {
            "total_files": self.stats.total_files,
            "completed_files": self.stats.completed_files,
            "failed_files": self.stats.failed_files,
            "blocked_files": sum(1 for n in self.nodes.values() if n.status == FileStatus.BLOCKED),
            "max_parallelism": self.stats.max_parallelism,
            "avg_parallelism": round(self.stats.avg_parallelism, 2),
            "interface_errors": self.stats.interface_errors,
        }

    def get_file_status(self, file_path: str) -> Optional[FileStatus]:
        """获取单个文件状态"""
        node = self.nodes.get(file_path)
        return node.status if node else None

    def is_file_ready(self, file_path: str) -> bool:
        """检查文件是否就绪"""
        return self.get_file_status(file_path) == FileStatus.READY

    def _log_schedule(
        self,
        event: str,
        files: List[str],
        source: Optional[str] = None,
        error: Optional[str] = None
    ) -> None:
        """记录调度日志"""
        entry = {
            "timestamp": time.time(),
            "event": event,
            "files": files,
            "source": source,
            "error": error
        }
        self.stats.schedule_log.append(entry)
