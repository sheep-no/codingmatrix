"""AsyncProcessGuardian 分支覆盖：端口检测、PID 解析、进程终止与熔断。"""

import asyncio
import contextlib
import platform
from types import SimpleNamespace

import pytest

from app.utils import process_guard as module
from app.utils.process_guard import AsyncProcessGuardian


class _Writer:
    def __init__(self):
        self.closed = False
        self.waited = False

    def close(self):
        self.closed = True

    async def wait_closed(self):
        self.waited = True


@pytest.mark.asyncio
async def test_is_port_open_success_and_failures(monkeypatch):
    guardian = AsyncProcessGuardian()
    writer = _Writer()

    async def open_ok(*_args):
        return object(), writer

    monkeypatch.setattr(module.asyncio, "open_connection", open_ok)
    assert await guardian.is_port_open(1) is True
    assert writer.closed and writer.waited

    async def open_refused(*_args):
        raise ConnectionRefusedError

    monkeypatch.setattr(module.asyncio, "open_connection", open_refused)
    assert await guardian.is_port_open(1) is False

    async def open_oserror(*_args):
        raise OSError

    monkeypatch.setattr(module.asyncio, "open_connection", open_oserror)
    assert await guardian.is_port_open(1) is False

    async def open_value_error(*_args):
        raise ValueError("bad")

    monkeypatch.setattr(module.asyncio, "open_connection", open_value_error)
    assert await guardian.is_port_open(1) is False


class _Proc:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self.killed = False

    async def communicate(self):
        return self._stdout, self._stderr

    def kill(self):
        self.killed = True


@pytest.mark.asyncio
async def test_find_pid_windows_listening_line(monkeypatch):
    guardian = AsyncProcessGuardian()
    monkeypatch.setattr(module.platform, "system", lambda: "Windows")

    proc = _Proc(
        returncode=0,
        stdout=b"  TCP 0.0.0.0:8080 LISTENING 4321\nignored\n",
    )

    async def fake_shell(*_args, **_kwargs):
        return proc

    monkeypatch.setattr(module.asyncio, "create_subprocess_shell", fake_shell)

    assert await guardian.find_pid_by_port(8080) == 4321


@pytest.mark.asyncio
async def test_find_pid_windows_no_match_and_nonzero(monkeypatch):
    guardian = AsyncProcessGuardian()
    monkeypatch.setattr(module.platform, "system", lambda: "Windows")

    proc = _Proc(returncode=0, stdout=b"nothing\n")
    async def fake_shell(*_args, **_kwargs):
        return proc

    monkeypatch.setattr(module.asyncio, "create_subprocess_shell", fake_shell)
    assert await guardian.find_pid_by_port(1) is None

    proc.returncode = 1
    assert await guardian.find_pid_by_port(1) is None


@pytest.mark.asyncio
async def test_find_pid_posix_no_pid_and_exception(monkeypatch):
    guardian = AsyncProcessGuardian()
    monkeypatch.setattr(module.platform, "system", lambda: "Linux")

    proc = _Proc(returncode=0, stdout=b"")
    async def fake_shell(*_args, **_kwargs):
        return proc

    monkeypatch.setattr(module.asyncio, "create_subprocess_shell", fake_shell)
    assert await guardian.find_pid_by_port(1) is None

    async def boom(*_args, **_kwargs):
        raise OSError("lsof missing")

    monkeypatch.setattr(module.asyncio, "create_subprocess_shell", boom)
    assert await guardian.find_pid_by_port(1) is None

    proc = _Proc(returncode=1, stdout=b"123\n")
    monkeypatch.setattr(
        module.asyncio, "create_subprocess_shell", lambda *a, **k: _return(proc)
    )
    assert await guardian.find_pid_by_port(1) is None


async def _return(value):
    return value


@pytest.mark.asyncio
async def test_kill_process_graceful_success(monkeypatch):
    guardian = AsyncProcessGuardian()
    process = SimpleNamespace(terminate=lambda: None, kill=lambda: None)
    monkeypatch.setattr(module.psutil, "Process", lambda _pid: process)

    async def exited(_process):
        return None

    monkeypatch.setattr(guardian, "_wait_process_exit", exited)

    assert await guardian.kill_process(1, graceful=True) is True


@pytest.mark.asyncio
async def test_kill_process_graceful_timeout_then_kill(monkeypatch):
    guardian = AsyncProcessGuardian()
    killed = []
    process = SimpleNamespace(terminate=lambda: None, kill=lambda: killed.append(True))
    monkeypatch.setattr(module.psutil, "Process", lambda _pid: process)

    async def never_exits(_process):
        await asyncio.sleep(10)

    monkeypatch.setattr(guardian, "_wait_process_exit", never_exits)
    monkeypatch.setattr(
        module.asyncio, "wait_for", lambda coro, timeout: _raise_timeout(coro)
    )

    assert await guardian.kill_process(1, graceful=True) is True
    assert killed


async def _raise_timeout(_coro=None):
    raise asyncio.TimeoutError


@pytest.mark.asyncio
async def test_kill_process_no_such_and_error(monkeypatch):
    guardian = AsyncProcessGuardian()

    def raise_missing(_pid):
        raise module.psutil.NoSuchProcess(1)

    monkeypatch.setattr(module.psutil, "Process", raise_missing)
    assert await guardian.kill_process(1) is True

    def raise_value(_pid):
        raise ValueError("bad")

    monkeypatch.setattr(module.psutil, "Process", raise_value)
    assert await guardian.kill_process(1) is False


@pytest.mark.asyncio
async def test_wait_process_exit_loop(monkeypatch):
    guardian = AsyncProcessGuardian()
    calls = {"n": 0}

    async def no_sleep(_seconds):
        calls["n"] += 1

    monkeypatch.setattr(module.asyncio, "sleep", no_sleep)
    process = SimpleNamespace(is_running=lambda: calls["n"] < 2)

    await guardian._wait_process_exit(process)
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_restart_without_port_success_and_failure(monkeypatch):
    guardian = AsyncProcessGuardian()
    proc = _Proc(returncode=0)

    async def communicate():
        return b"", b""

    proc.communicate = communicate

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(module.asyncio, "sleep", no_sleep)
    assert await guardian._restart_without_port(proc, 5) is True

    failing = _Proc(returncode=2, stderr=b"bad")
    async def communicate_fail():
        return b"", b"bad"

    failing.communicate = communicate_fail
    assert await guardian._restart_without_port(failing, 5) is False


@pytest.mark.asyncio
async def test_restart_without_port_timeout_detaches(monkeypatch):
    guardian = AsyncProcessGuardian()
    detached = []
    guardian._detach_subprocess = lambda proc: detached.append(proc)

    async def timeout(_coro, timeout):
        raise asyncio.TimeoutError

    monkeypatch.setattr(module.asyncio, "wait_for", timeout)
    proc = _Proc()

    assert await guardian._restart_without_port(proc, 1) is True
    assert detached == [proc]


@pytest.mark.asyncio
async def test_restart_service_without_port_and_exceptions(monkeypatch):
    guardian = AsyncProcessGuardian()

    async def fake_shell(*_args, **_kwargs):
        return _Proc()

    monkeypatch.setattr(module.asyncio, "create_subprocess_shell", fake_shell)

    async def restart_ok(_proc, _timeout):
        return True

    monkeypatch.setattr(guardian, "_restart_without_port", restart_ok)
    assert await guardian.restart_service("run") is True

    async def boom(*_args, **_kwargs):
        raise ValueError("bad")

    monkeypatch.setattr(module.asyncio, "create_subprocess_shell", boom)
    assert await guardian.restart_service("run", port=1) is False


@pytest.mark.asyncio
async def test_restart_service_exit_nonzero_cancels_port_task(monkeypatch):
    guardian = AsyncProcessGuardian()
    proc = _Proc(returncode=1, stderr=b"boom")

    async def fake_shell(*_args, **_kwargs):
        return proc

    monkeypatch.setattr(module.asyncio, "create_subprocess_shell", fake_shell)

    cancelled = []

    class _Task:
        def __init__(self, name):
            self.name = name
            self._done = False

        def cancel(self):
            cancelled.append(self.name)
            self._done = True

        def done(self):
            return self._done

        def result(self):
            return b"", b"boom"

    exit_task = _Task("exit")
    port_task = _Task("port")

    def fake_ensure(coro):
        if hasattr(coro, "close"):
            coro.close()
        return exit_task if not hasattr(coro, "_port") else port_task

    async def fake_ready(*_args, **_kwargs):
        return False

    async def fake_wait(tasks, **_kwargs):
        return {exit_task}, {port_task}

    pending = iter([exit_task, port_task])
    monkeypatch.setattr(
        module.asyncio, "ensure_future", lambda coro: _next_or_close(coro, pending)
    )
    monkeypatch.setattr(module.asyncio, "wait", fake_wait)
    monkeypatch.setattr(guardian, "_wait_for_service_ready", fake_ready)

    assert await guardian.restart_service("run", port=1, startup_timeout=1) is False
    assert cancelled == ["port"]


async def _wrap(coro, task):
    if hasattr(coro, "close"):
        coro.close()
    return task


def _next_or_close(coro, pending):
    if hasattr(coro, "close"):
        coro.close()
    return next(pending)


@pytest.mark.asyncio
async def test_restart_service_port_ready_while_command_running(monkeypatch):
    guardian = AsyncProcessGuardian()
    proc = _Proc()

    async def fake_shell(*_args, **_kwargs):
        return proc

    monkeypatch.setattr(module.asyncio, "create_subprocess_shell", fake_shell)
    detached = []
    guardian._detach_subprocess = lambda p, task=None: detached.append(p)

    class _Task:
        def __init__(self, done):
            self._done = done
            self.cancelled = False

        def done(self):
            return self._done

        def cancel(self):
            self.cancelled = True

        def result(self):
            return True

    exit_task = _Task(False)
    port_task = _Task(True)

    async def fake_wait(tasks, **_kwargs):
        return {port_task}, {exit_task}

    pending = iter([exit_task, port_task])
    monkeypatch.setattr(
        module.asyncio, "ensure_future", lambda coro: _next_or_close(coro, pending)
    )
    monkeypatch.setattr(module.asyncio, "wait", fake_wait)

    assert await guardian.restart_service("run", port=1, startup_timeout=1) is True
    assert detached


@pytest.mark.asyncio
async def test_restart_service_command_exits_and_port_ready(monkeypatch):
    guardian = AsyncProcessGuardian()
    proc = _Proc(returncode=0)

    async def fake_shell(*_args, **_kwargs):
        return proc

    monkeypatch.setattr(module.asyncio, "create_subprocess_shell", fake_shell)

    class _Task:
        def __init__(self, done):
            self._done = done

        def done(self):
            return self._done

        def cancel(self):
            pass

        def result(self):
            return b"", b""

    exit_task = _Task(True)
    port_task = _Task(True)

    async def fake_wait(tasks, **_kwargs):
        return {exit_task, port_task}, set()

    pending = iter([exit_task, port_task])
    monkeypatch.setattr(
        module.asyncio, "ensure_future", lambda coro: _next_or_close(coro, pending)
    )
    monkeypatch.setattr(module.asyncio, "wait", fake_wait)

    assert await guardian.restart_service("run", port=1, startup_timeout=1) is True


@pytest.mark.asyncio
async def test_restart_service_port_never_ready_kills_process(monkeypatch):
    guardian = AsyncProcessGuardian()
    proc = _Proc()

    async def fake_shell(*_args, **_kwargs):
        return proc

    monkeypatch.setattr(module.asyncio, "create_subprocess_shell", fake_shell)
    detached = []
    guardian._detach_subprocess = lambda p, task=None: detached.append(p)

    class _Pending:
        def done(self):
            return False

        def cancel(self):
            pass

        def result(self):
            return False

    class _Ready:
        def done(self):
            return True

        def cancel(self):
            pass

        def result(self):
            return False

    exit_task = _Pending()
    port_task = _Ready()

    async def fake_wait(tasks, **_kwargs):
        return {port_task}, {exit_task}

    async def no_sleep(_seconds):
        return None

    pending = iter([exit_task, port_task])
    monkeypatch.setattr(
        module.asyncio, "ensure_future", lambda coro: _next_or_close(coro, pending)
    )
    monkeypatch.setattr(module.asyncio, "wait", fake_wait)
    monkeypatch.setattr(module.asyncio, "sleep", no_sleep)

    assert await guardian.restart_service("run", port=1, startup_timeout=1) is False
    assert proc.killed
    assert detached


@pytest.mark.asyncio
async def test_restart_service_command_exits_but_port_not_ready(monkeypatch):
    guardian = AsyncProcessGuardian()
    proc = _Proc(returncode=0)

    async def fake_shell(*_args, **_kwargs):
        return proc

    monkeypatch.setattr(module.asyncio, "create_subprocess_shell", fake_shell)

    class _Task:
        def __init__(self, done):
            self._done = done
            self.cancelled = False

        def done(self):
            return self._done

        def cancel(self):
            self.cancelled = True

        def result(self):
            return b"", b""

    exit_task = _Task(True)
    port_task = _Task(False)

    async def fake_wait(_tasks, **_kwargs):
        return {exit_task}, {port_task}

    async def not_ready(*_args, **_kwargs):
        return False

    pending = iter([exit_task, port_task])
    monkeypatch.setattr(
        module.asyncio, "ensure_future", lambda coro: _next_or_close(coro, pending)
    )
    monkeypatch.setattr(module.asyncio, "wait", fake_wait)
    monkeypatch.setattr(guardian, "_wait_for_service_ready", not_ready)

    assert await guardian.restart_service("run", port=1, startup_timeout=1) is False
    assert port_task.cancelled


@pytest.mark.asyncio
async def test_restart_service_port_ready_after_exit_no_detach(monkeypatch):
    guardian = AsyncProcessGuardian()
    proc = _Proc(returncode=0)

    async def fake_shell(*_args, **_kwargs):
        return proc

    monkeypatch.setattr(module.asyncio, "create_subprocess_shell", fake_shell)
    detached = []
    guardian._detach_subprocess = lambda p, task=None: detached.append(p)

    class _Task:
        def __init__(self, done):
            self._done = done

        def done(self):
            return self._done

        def cancel(self):
            pass

        def result(self):
            return True

    exit_task = _Task(True)
    port_task = _Task(True)

    async def fake_wait(_tasks, **_kwargs):
        return {port_task}, {exit_task}

    pending = iter([exit_task, port_task])
    monkeypatch.setattr(
        module.asyncio, "ensure_future", lambda coro: _next_or_close(coro, pending)
    )
    monkeypatch.setattr(module.asyncio, "wait", fake_wait)

    assert await guardian.restart_service("run", port=1, startup_timeout=1) is True
    assert detached == []


@pytest.mark.asyncio
async def test_restart_service_timeout_exception(monkeypatch):
    guardian = AsyncProcessGuardian()

    async def timeout(*_args, **_kwargs):
        raise asyncio.TimeoutError

    monkeypatch.setattr(module.asyncio, "create_subprocess_shell", timeout)
    assert await guardian.restart_service("run", port=1, startup_timeout=1) is False


@pytest.mark.asyncio
async def test_wait_for_service_ready_success_and_timeout(monkeypatch):
    guardian = AsyncProcessGuardian()
    outcomes = iter([False, True])

    async def port_open(_port):
        return next(outcomes)

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(guardian, "is_port_open", port_open)
    monkeypatch.setattr(module.asyncio, "sleep", no_sleep)

    assert await guardian._wait_for_service_ready(1, 10) is True

    async def never(_port):
        return False

    monkeypatch.setattr(guardian, "is_port_open", never)
    times = iter([0, 0, 100])
    monkeypatch.setattr(module.time, "time", lambda: next(times, 100))
    assert await guardian._wait_for_service_ready(1, 1) is False


@pytest.mark.asyncio
async def test_detach_subprocess_background_task(monkeypatch):
    guardian = AsyncProcessGuardian()

    class _Task:
        def add_done_callback(self, cb):
            self.cb = cb

        def cancel(self):
            pass

    task = _Task()
    monkeypatch.setattr(module.asyncio, "ensure_future", lambda coro: task)
    guardian._detach_subprocess(_Proc())

    assert task in guardian._background_tasks
    task.cb(task)
    assert task not in guardian._background_tasks


@pytest.mark.asyncio
async def test_watch_port_disabled_fuse_stops(monkeypatch):
    guardian = AsyncProcessGuardian(check_interval=0.01, max_restart_attempts=1)
    guardian.service_state["svc"] = {
        "state": "fused",
        "fuse_retry_count": 1,
        "last_fuse_time": 0,
        "cooldown": 0,
    }

    config = {
        "name": "svc",
        "port": 1,
        "restart_cmd": "run",
        "fuse_enabled": False,
    }

    result = await asyncio.wait_for(guardian.watch_port(config), timeout=2)
    assert result is None


@pytest.mark.asyncio
async def test_watch_port_fuse_cooldown_and_retry_limit(monkeypatch):
    guardian = AsyncProcessGuardian(check_interval=0.01, max_restart_attempts=1)

    async def fused_loop(**_kwargs):
        return None

    guardian.is_port_open = fused_loop

    config = {
        "name": "svc",
        "port": 1,
        "restart_cmd": "run",
        "fuse_retry_times": 1,
        "fuse_cooldown": 0,
        "fuse_enabled": True,
    }
    guardian.service_state["svc"] = {
        "state": "fused",
        "fuse_retry_count": 1,
        "last_fuse_time": 0,
        "cooldown": 0,
    }

    result = await asyncio.wait_for(guardian.watch_port(config), timeout=2)
    assert result is None


@pytest.mark.asyncio
async def test_watch_port_restart_success_resets_state(monkeypatch):
    guardian = AsyncProcessGuardian(check_interval=0.01, max_restart_attempts=1)
    calls = {"n": 0}

    async def port_open(_port):
        calls["n"] += 1
        return calls["n"] > 1

    async def restart(*_args, **_kwargs):
        return True

    async def no_pid(_port):
        return None

    monkeypatch.setattr(guardian, "is_port_open", port_open)
    monkeypatch.setattr(guardian, "restart_service", restart)
    monkeypatch.setattr(guardian, "find_pid_by_port", no_pid)

    guardian.service_state["svc"] = {
        "state": "normal",
        "fuse_retry_count": 2,
        "last_fuse_time": 0,
        "cooldown": 0,
    }

    config = {"name": "svc", "port": 1, "restart_cmd": "run", "check_interval": 0.001}
    task = asyncio.create_task(guardian.watch_port(config))
    for _ in range(200):
        if guardian.restart_count.get("svc") == 0 and calls["n"] > 1:
            break
        await asyncio.sleep(0.001)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert guardian.service_state["svc"]["fuse_retry_count"] == 0


@pytest.mark.asyncio
async def test_watch_port_fuse_disabled_stops_after_failures(monkeypatch):
    guardian = AsyncProcessGuardian(check_interval=0.01, max_restart_attempts=1)

    async def port_closed(_port):
        return False

    async def restart(*_args, **_kwargs):
        return False

    async def no_pid(_port):
        return None

    monkeypatch.setattr(guardian, "is_port_open", port_closed)
    monkeypatch.setattr(guardian, "restart_service", restart)
    monkeypatch.setattr(guardian, "find_pid_by_port", no_pid)

    config = {
        "name": "svc",
        "port": 1,
        "restart_cmd": "run",
        "fuse_enabled": False,
        "check_interval": 0.001,
    }
    result = await asyncio.wait_for(guardian.watch_port(config), timeout=2)
    assert result is None


@pytest.mark.asyncio
async def test_watch_port_kills_old_pid_and_persists_fuse(monkeypatch):
    guardian = AsyncProcessGuardian(check_interval=0.01, max_restart_attempts=1)

    class _Manager:
        def __init__(self):
            self.configs = {}
            self.saved = 0

        def save_configs(self):
            self.saved += 1

    manager = _Manager()
    guardian.config_manager = manager
    killed = []

    async def port_closed(_port):
        return False

    async def old_pid(_port):
        return 123

    async def kill(pid, graceful=True):
        killed.append(pid)
        return True

    async def restart(*_args, **_kwargs):
        return False

    monkeypatch.setattr(guardian, "is_port_open", port_closed)
    monkeypatch.setattr(guardian, "find_pid_by_port", old_pid)
    monkeypatch.setattr(guardian, "kill_process", kill)
    monkeypatch.setattr(guardian, "restart_service", restart)

    config = {
        "name": "svc",
        "port": 1,
        "restart_cmd": "run",
        "process_signature": "sig",
        "check_interval": 0.001,
    }
    task = asyncio.create_task(guardian.watch_port(config))
    for _ in range(200):
        await asyncio.sleep(0.001)
        if manager.saved:
            break
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert killed == [123]
    assert manager.saved == 1
    assert manager.configs["1_sig"]["fuse_retry_count"] == 1


@pytest.mark.asyncio
async def test_watch_port_exception_and_cancel(monkeypatch):
    guardian = AsyncProcessGuardian(check_interval=0.01)

    async def port_open(_port):
        raise OSError("down")

    monkeypatch.setattr(guardian, "is_port_open", port_open)

    config = {"name": "svc", "port": 1, "restart_cmd": "run", "check_interval": 0.001}
    task = asyncio.create_task(guardian.watch_port(config))
    await asyncio.sleep(0.05)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert guardian.restart_count["svc"] == 0


@pytest.mark.asyncio
async def test_watch_port_resumes_after_fuse_cooldown_and_success(monkeypatch):
    guardian = AsyncProcessGuardian(check_interval=0.01, max_restart_attempts=3)
    calls = {"n": 0}

    async def port_open(_port):
        calls["n"] += 1
        return calls["n"] > 1

    async def restart(*_args, **_kwargs):
        return True

    monkeypatch.setattr(guardian, "is_port_open", port_open)
    monkeypatch.setattr(guardian, "restart_service", restart)
    guardian.restart_count["svc"] = 2
    guardian.service_state["svc"] = {
        "state": "fused",
        "fuse_retry_count": 1,
        "last_fuse_time": 0,
        "cooldown": 0,
    }

    config = {
        "name": "svc",
        "port": 1,
        "restart_cmd": "run",
        "fuse_cooldown": 0,
        "check_interval": 0.001,
    }
    task = asyncio.create_task(guardian.watch_port(config))
    for _ in range(200):
        await asyncio.sleep(0.001)
        if calls["n"] > 2:
            break
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert guardian.service_state["svc"]["state"] == "normal"
    assert guardian.service_state["svc"]["fuse_retry_count"] == 0
    assert guardian.restart_count["svc"] == 0


@pytest.mark.asyncio
async def test_watch_port_failure_below_threshold_keeps_count(monkeypatch):
    guardian = AsyncProcessGuardian(check_interval=0.01, max_restart_attempts=5)

    async def port_closed(_port):
        return False

    async def restart(*_args, **_kwargs):
        return False

    async def no_pid(_port):
        return None

    monkeypatch.setattr(guardian, "is_port_open", port_closed)
    monkeypatch.setattr(guardian, "restart_service", restart)
    monkeypatch.setattr(guardian, "find_pid_by_port", no_pid)

    config = {
        "name": "svc",
        "port": 1,
        "restart_cmd": "run",
        "check_interval": 0.001,
    }
    task = asyncio.create_task(guardian.watch_port(config))
    for _ in range(200):
        await asyncio.sleep(0.001)
        if guardian.restart_count.get("svc", 0) >= 2:
            break
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert guardian.restart_count["svc"] >= 2
    assert guardian.service_state["svc"]["state"] == "normal"


@pytest.mark.asyncio
async def test_watch_port_open_resets_previous_restart_count(monkeypatch):
    guardian = AsyncProcessGuardian(check_interval=0.01, max_restart_attempts=3)
    guardian.restart_count["svc"] = 3

    async def port_open(_port):
        return True

    monkeypatch.setattr(guardian, "is_port_open", port_open)

    config = {"name": "svc", "port": 1, "restart_cmd": "run", "check_interval": 0.001}
    task = asyncio.create_task(guardian.watch_port(config))
    for _ in range(200):
        await asyncio.sleep(0.001)
        if guardian.restart_count["svc"] == 0:
            break
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert guardian.restart_count["svc"] == 0


@pytest.mark.asyncio
async def test_watch_port_fuse_enabled_without_config_manager(monkeypatch):
    guardian = AsyncProcessGuardian(check_interval=0.01, max_restart_attempts=1)
    assert guardian.config_manager is None

    async def port_closed(_port):
        return False

    async def no_pid(_port):
        return None

    async def restart(*_args, **_kwargs):
        return False

    monkeypatch.setattr(guardian, "is_port_open", port_closed)
    monkeypatch.setattr(guardian, "find_pid_by_port", no_pid)
    monkeypatch.setattr(guardian, "restart_service", restart)

    config = {
        "name": "svc",
        "port": 1,
        "restart_cmd": "run",
        "check_interval": 0.001,
        "fuse_cooldown": 0,
    }
    task = asyncio.create_task(guardian.watch_port(config))
    for _ in range(200):
        await asyncio.sleep(0.001)
        if guardian.service_state["svc"]["state"] == "fused":
            break
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert guardian.service_state["svc"]["state"] == "fused"


@pytest.mark.asyncio
async def test_watch_port_fuse_persisted_without_signature_warns(monkeypatch):
    guardian = AsyncProcessGuardian(check_interval=0.01, max_restart_attempts=1)

    class _Manager:
        def __init__(self):
            self.configs = {}
            self.saved = 0

        def save_configs(self):
            self.saved += 1

    manager = _Manager()
    guardian.config_manager = manager
    warnings = []
    guardian.logger = SimpleNamespace(
        info=lambda *a, **k: None,
        warning=lambda msg, *a, **k: warnings.append(msg),
        error=lambda *a, **k: None,
        critical=lambda *a, **k: None,
        debug=lambda *a, **k: None,
    )

    async def port_closed(_port):
        return False

    async def no_pid(_port):
        return None

    async def restart(*_args, **_kwargs):
        return False

    monkeypatch.setattr(guardian, "is_port_open", port_closed)
    monkeypatch.setattr(guardian, "find_pid_by_port", no_pid)
    monkeypatch.setattr(guardian, "restart_service", restart)

    config = {"name": "svc", "port": 1, "restart_cmd": "run"}
    task = asyncio.create_task(guardian.watch_port(config))
    for _ in range(200):
        await asyncio.sleep(0.001)
        if any("缺少 process_signature" in w for w in warnings):
            break
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert manager.saved == 0
    assert any("缺少 process_signature" in w for w in warnings)


@pytest.mark.asyncio
async def test_monitor_all_creates_tasks(monkeypatch):
    guardian = AsyncProcessGuardian()
    started = []

    async def watch(config):
        started.append(config["name"])

    monkeypatch.setattr(guardian, "watch_port", watch)

    await guardian.monitor_all([{"name": "a"}, {"name": "b"}])
    assert started == ["a", "b"]


@pytest.mark.asyncio
async def test_is_port_open_timeout(monkeypatch):
    guardian = AsyncProcessGuardian()

    async def timeout(*_args):
        raise asyncio.TimeoutError

    monkeypatch.setattr(module.asyncio, "open_connection", timeout)

    assert await guardian.is_port_open(1) is False
