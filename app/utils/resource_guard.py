import logging
import asyncio
import os
from typing import Dict, Optional

try:
    import psutil

    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

logger = logging.getLogger(__name__)


class ResourceGuard:

    MAX_MEMORY_PERCENT = 85
    MAX_DISK_PERCENT = 85
    MAX_CPU_PERCENT = 90

    def check_resources(self) -> bool:
        if _HAS_PSUTIL:
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            cpu = psutil.cpu_percent(interval=0.5)
            if mem.percent >= self.MAX_MEMORY_PERCENT:
                logger.warning("memory usage %.1f%% exceeds threshold", mem.percent)
                return False
            if disk.percent >= self.MAX_DISK_PERCENT:
                logger.warning("disk usage %.1f%% exceeds threshold", disk.percent)
                return False
            if cpu >= self.MAX_CPU_PERCENT:
                logger.warning("cpu usage %.1f%% exceeds threshold", cpu)
                return False
            return True
        else:
            try:
                with open("/proc/meminfo") as f:
                    lines = f.read().splitlines()
                mem_total = None
                mem_available = None
                for line in lines:
                    parts = line.split()
                    if parts[0] == "MemTotal:":
                        mem_total = int(parts[1])
                    elif parts[0] == "MemAvailable:":
                        mem_available = int(parts[1])
                if mem_total and mem_available:
                    mem_percent = (1 - mem_available / mem_total) * 100
                    if mem_percent >= self.MAX_MEMORY_PERCENT:
                        logger.warning("memory usage %.1f%% exceeds threshold", mem_percent)
                        return False
            except OSError:
                pass
            stat = os.statvfs("/")
            disk_total = stat.f_blocks * stat.f_frsize
            disk_free = stat.f_bavail * stat.f_frsize
            disk_percent = (1 - disk_free / disk_total) * 100 if disk_total > 0 else 0
            if disk_percent >= self.MAX_DISK_PERCENT:
                logger.warning("disk usage %.1f%% exceeds threshold", disk_percent)
                return False
            return True

    def get_safe_concurrency(self) -> int:
        if _HAS_PSUTIL:
            mem = psutil.virtual_memory()
            cpu = psutil.cpu_percent(interval=0.5)
            load_avg = os.getloadavg()[0] if hasattr(os, "getloadavg") else 0
        else:
            mem_percent = 50
            cpu = 50
            load_avg = 0
            try:
                with open("/proc/meminfo") as f:
                    lines = f.read().splitlines()
                mem_total = None
                mem_available = None
                for line in lines:
                    parts = line.split()
                    if parts[0] == "MemTotal:":
                        mem_total = int(parts[1])
                    elif parts[0] == "MemAvailable:":
                        mem_available = int(parts[1])
                if mem_total and mem_available:
                    mem_percent = (1 - mem_available / mem_total) * 100
            except OSError:
                pass
            mem = type("_Mem", (), {"percent": mem_percent})()
            try:
                load_avg = os.getloadavg()[0]
            except OSError:
                load_avg = 0

        if mem.percent >= 80 or cpu >= 80 or load_avg >= 4:
            return 2
        if mem.percent >= 60 or cpu >= 60 or load_avg >= 2:
            return 3
        return 4

    def get_resource_status(self) -> Dict:
        if _HAS_PSUTIL:
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            cpu = psutil.cpu_percent(interval=0.5)
            return {
                "memory_percent": mem.percent,
                "memory_available_mb": mem.available / (1024 * 1024),
                "disk_percent": disk.percent,
                "disk_free_mb": disk.free / (1024 * 1024),
                "cpu_percent": cpu,
                "concurrency_limit": self.get_safe_concurrency(),
            }
        else:
            mem_percent = 0
            mem_available_mb = 0
            try:
                with open("/proc/meminfo") as f:
                    lines = f.read().splitlines()
                mem_total = None
                mem_available = None
                for line in lines:
                    parts = line.split()
                    if parts[0] == "MemTotal:":
                        mem_total = int(parts[1])
                    elif parts[0] == "MemAvailable:":
                        mem_available = int(parts[1])
                if mem_total and mem_available:
                    mem_percent = (1 - mem_available / mem_total) * 100
                    mem_available_mb = mem_available / 1024
            except OSError:
                pass
            stat = os.statvfs("/")
            disk_total = stat.f_blocks * stat.f_frsize
            disk_free = stat.f_bavail * stat.f_frsize
            disk_percent = (1 - disk_free / disk_total) * 100 if disk_total > 0 else 0
            disk_free_mb = disk_free / (1024 * 1024)
            return {
                "memory_percent": mem_percent,
                "memory_available_mb": mem_available_mb,
                "disk_percent": disk_percent,
                "disk_free_mb": disk_free_mb,
                "cpu_percent": 0,
                "concurrency_limit": self.get_safe_concurrency(),
            }

    def should_reduce_cache(self) -> bool:
        if _HAS_PSUTIL:
            mem = psutil.virtual_memory()
            return mem.percent >= 75
        else:
            try:
                with open("/proc/meminfo") as f:
                    lines = f.read().splitlines()
                mem_total = None
                mem_available = None
                for line in lines:
                    parts = line.split()
                    if parts[0] == "MemTotal:":
                        mem_total = int(parts[1])
                    elif parts[0] == "MemAvailable:":
                        mem_available = int(parts[1])
                if mem_total and mem_available:
                    mem_percent = (1 - mem_available / mem_total) * 100
                    return mem_percent >= 75
            except OSError:
                pass
            return False

    def get_available_disk_mb(self) -> float:
        if _HAS_PSUTIL:
            disk = psutil.disk_usage("/")
            return disk.free / (1024 * 1024)
        stat = os.statvfs("/")
        return stat.f_bavail * stat.f_frsize / (1024 * 1024)

    def should_archive_data(self) -> bool:
        if _HAS_PSUTIL:
            disk = psutil.disk_usage("/")
            return disk.percent >= 70
        stat = os.statvfs("/")
        disk_total = stat.f_blocks * stat.f_frsize
        disk_free = stat.f_bavail * stat.f_frsize
        disk_percent = (1 - disk_free / disk_total) * 100 if disk_total > 0 else 0
        return disk_percent >= 70


_resource_guard: Optional[ResourceGuard] = None


def get_resource_guard() -> ResourceGuard:
    global _resource_guard
    if _resource_guard is None:
        _resource_guard = ResourceGuard()
    return _resource_guard