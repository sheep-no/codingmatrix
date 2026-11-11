"""ResourceGuard 阈值与回退路径分支回归。

现有 `test_resource_guard.py` 只做冒烟，这里用 mock 固定环境，覆盖
psutil 与 /proc/meminfo 两条路径、阈值边界与并发档位。
"""

from unittest.mock import MagicMock, patch

import pytest

import app.utils.resource_guard as rg
from app.utils.resource_guard import ResourceGuard, get_resource_guard


def _mem(percent, available=2 * 1024**3):
    m = MagicMock()
    m.percent = percent
    m.available = available
    return m


def _disk(percent, free=2 * 1024**3):
    d = MagicMock()
    d.percent = percent
    d.free = free
    return d


@pytest.fixture
def guard():
    return ResourceGuard()


@pytest.fixture
def psutil_path():
    with patch.object(rg, "_HAS_PSUTIL", True):
        yield


@pytest.mark.parametrize(
    "mem,disk,cpu,expected",
    [
        (10, 10, 10, True),
        (84, 10, 10, True),
        (85, 10, 10, False),
        (10, 85, 10, False),
        (10, 10, 90, False),
        (10, 10, 89, True),
    ],
)
def test_check_resources_thresholds(guard, psutil_path, mem, disk, cpu, expected):
    with patch.object(rg.psutil, "virtual_memory", return_value=_mem(mem)), \
         patch.object(rg.psutil, "disk_usage", return_value=_disk(disk)), \
         patch.object(rg.psutil, "cpu_percent", return_value=cpu):
        assert guard.check_resources() is expected


def test_check_resources_fallback_without_psutil(guard):
    meminfo = "MemTotal: 1000 kB\nMemAvailable: 500 kB\n"
    stat = MagicMock()
    stat.f_blocks = 100
    stat.f_frsize = 1024
    stat.f_bavail = 50

    with patch.object(rg, "_HAS_PSUTIL", False), \
         patch("builtins.open", MagicMock(return_value=MagicMock(
             read=MagicMock(return_value=meminfo),
             __enter__=MagicMock(return_value=MagicMock(read=MagicMock(return_value=meminfo))),
             __exit__=MagicMock(return_value=False),
         ))), \
         patch("os.statvfs", return_value=stat):
        # 内存 50%、磁盘 50% 均低于阈值。
        assert guard.check_resources() is True


def test_check_resources_fallback_meminfo_unreadable(guard, psutil_path):
    stat = MagicMock()
    stat.f_blocks = 100
    stat.f_frsize = 1024
    stat.f_bavail = 50

    with patch.object(rg, "_HAS_PSUTIL", False), \
         patch("builtins.open", side_effect=OSError("unreadable")), \
         patch("os.statvfs", return_value=stat):
        assert guard.check_resources() is True


def _meminfo_handle(text):
    handle = MagicMock()
    handle.read.return_value = text
    handle.__enter__ = MagicMock(return_value=handle)
    handle.__exit__ = MagicMock(return_value=False)
    return handle


def test_check_resources_fallback_memory_over_threshold(guard):
    stat = MagicMock()
    stat.f_blocks = 100
    stat.f_frsize = 1024
    stat.f_bavail = 50
    meminfo = "MemTotal: 1000 kB\nMemAvailable: 100 kB\n"

    with patch.object(rg, "_HAS_PSUTIL", False), \
         patch("builtins.open", return_value=_meminfo_handle(meminfo)), \
         patch("os.statvfs", return_value=stat):
        assert guard.check_resources() is False


def test_check_resources_fallback_disk_over_threshold(guard):
    stat = MagicMock()
    stat.f_blocks = 100
    stat.f_frsize = 1024
    stat.f_bavail = 10
    meminfo = "MemTotal: 1000 kB\nMemAvailable: 500 kB\n"

    with patch.object(rg, "_HAS_PSUTIL", False), \
         patch("builtins.open", return_value=_meminfo_handle(meminfo)), \
         patch("os.statvfs", return_value=stat):
        assert guard.check_resources() is False


def test_check_resources_fallback_incomplete_meminfo(guard):
    stat = MagicMock()
    stat.f_blocks = 100
    stat.f_frsize = 1024
    stat.f_bavail = 50

    with patch.object(rg, "_HAS_PSUTIL", False), \
         patch("builtins.open", return_value=_meminfo_handle("MemTotal: 1000 kB\n")), \
         patch("os.statvfs", return_value=stat):
        assert guard.check_resources() is True


@pytest.mark.parametrize(
    "mem,cpu,load,expected",
    [
        (10, 10, 0.1, 4),
        (80, 10, 0.1, 2),
        (60, 10, 0.1, 3),
        (10, 80, 0.1, 2),
        (10, 60, 0.1, 3),
        (10, 10, 4.0, 2),
        (10, 10, 2.0, 3),
        (59, 59, 1.9, 4),
        (60, 59, 1.9, 3),
    ],
)
def test_safe_concurrency_tiers(guard, psutil_path, mem, cpu, load, expected):
    with patch.object(rg.psutil, "virtual_memory", return_value=_mem(mem)), \
         patch.object(rg.psutil, "cpu_percent", return_value=cpu), \
         patch("os.getloadavg", return_value=(load, load, load)):
        assert guard.get_safe_concurrency() == expected


def test_safe_concurrency_fallback_without_psutil(guard):
    with patch.object(rg, "_HAS_PSUTIL", False), \
         patch("builtins.open", side_effect=OSError("unreadable")), \
         patch("os.getloadavg", side_effect=OSError("unsupported")):
        assert guard.get_safe_concurrency() == 4


def test_safe_concurrency_fallback_reads_meminfo(guard):
    meminfo = "MemTotal: 1000 kB\nMemAvailable: 100 kB\n"
    with patch.object(rg, "_HAS_PSUTIL", False), \
         patch("builtins.open", return_value=_meminfo_handle(meminfo)), \
         patch("os.getloadavg", return_value=(0.0, 0.0, 0.0)):
        # 内存 90% 走最高档。
        assert guard.get_safe_concurrency() == 2


def test_get_resource_status_psutil_shape(guard, psutil_path):
    with patch.object(rg.psutil, "virtual_memory", return_value=_mem(30, 1024**3)), \
         patch.object(rg.psutil, "disk_usage", return_value=_disk(40, 2 * 1024**3)), \
         patch.object(rg.psutil, "cpu_percent", return_value=20):
        status = guard.get_resource_status()

    assert status["memory_percent"] == 30
    assert status["disk_percent"] == 40
    assert status["cpu_percent"] == 20
    assert status["memory_available_mb"] == pytest.approx(1024)
    assert status["disk_free_mb"] == pytest.approx(2048)
    assert status["concurrency_limit"] == 4


def test_get_resource_status_fallback_shape(guard):
    stat = MagicMock()
    stat.f_blocks = 100
    stat.f_frsize = 1024
    stat.f_bavail = 50
    meminfo = "MemTotal: 2000 kB\nMemAvailable: 1000 kB\n"
    handle = MagicMock()
    handle.read.return_value = meminfo
    handle.__enter__ = MagicMock(return_value=handle)
    handle.__exit__ = MagicMock(return_value=False)

    with patch.object(rg, "_HAS_PSUTIL", False), \
         patch("builtins.open", return_value=handle), \
         patch("os.statvfs", return_value=stat), \
         patch("os.getloadavg", return_value=(0.0, 0.0, 0.0)):
        status = guard.get_resource_status()

    assert status["memory_percent"] == pytest.approx(50)
    assert status["cpu_percent"] == 0
    assert status["disk_percent"] == pytest.approx(50)


@pytest.mark.parametrize("percent,expected", [(74, False), (75, True), (99, True)])
def test_should_reduce_cache(guard, psutil_path, percent, expected):
    with patch.object(rg.psutil, "virtual_memory", return_value=_mem(percent)):
        assert guard.should_reduce_cache() is expected


def test_should_reduce_cache_fallback(guard):
    with patch.object(rg, "_HAS_PSUTIL", False), \
         patch("builtins.open", side_effect=OSError("unreadable")):
        assert guard.should_reduce_cache() is False


@pytest.mark.parametrize("meminfo,expected", [
    ("MemTotal: 1000 kB\nMemAvailable: 100 kB\n", True),
    ("MemTotal: 1000 kB\nMemAvailable: 500 kB\n", False),
    ("MemTotal: 1000 kB\n", False),
])
def test_should_reduce_cache_fallback_meminfo(guard, meminfo, expected):
    with patch.object(rg, "_HAS_PSUTIL", False), \
         patch("builtins.open", return_value=_meminfo_handle(meminfo)):
        assert guard.should_reduce_cache() is expected


@pytest.mark.parametrize("percent,expected", [(69, False), (70, True)])
def test_should_archive_data(guard, psutil_path, percent, expected):
    with patch.object(rg.psutil, "disk_usage", return_value=_disk(percent)):
        assert guard.should_archive_data() is expected


def test_available_disk_mb_both_paths(guard, psutil_path):
    with patch.object(rg.psutil, "disk_usage", return_value=_disk(10, 5 * 1024**3)):
        assert guard.get_available_disk_mb() == pytest.approx(5120)

    stat = MagicMock()
    stat.f_bavail = 1024
    stat.f_frsize = 1024
    with patch.object(rg, "_HAS_PSUTIL", False), patch("os.statvfs", return_value=stat):
        assert guard.get_available_disk_mb() == pytest.approx(1)


def test_should_archive_data_fallback(guard):
    stat = MagicMock()
    stat.f_blocks = 100
    stat.f_frsize = 1024
    stat.f_bavail = 10
    with patch.object(rg, "_HAS_PSUTIL", False), patch("os.statvfs", return_value=stat):
        assert guard.should_archive_data() is True


def test_should_archive_data_fallback_zero_total(guard):
    stat = MagicMock()
    stat.f_blocks = 0
    stat.f_frsize = 1024
    stat.f_bavail = 0
    with patch.object(rg, "_HAS_PSUTIL", False), patch("os.statvfs", return_value=stat):
        assert guard.should_archive_data() is False


def test_singleton_is_stable():
    assert get_resource_guard() is get_resource_guard()
