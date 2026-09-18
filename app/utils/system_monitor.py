import logging
from datetime import datetime

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    psutil = None
    _HAS_PSUTIL = False

logger = logging.getLogger(__name__)


def _empty_stats(error: str = "") -> dict:
    """psutil 不可用或采集失败时的降级结构，保持与正常返回相同的键"""
    return {
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "cpu": {"total_percent": 0.0, "per_cpu": [], "core_count": 0},
        "memory": {"total_gb": 0.0, "used_gb": 0.0, "percent": 0.0},
        "disk": {"total_gb": 0.0, "used_gb": 0.0, "percent": 0.0},
        "network": {"bytes_sent": 0, "bytes_recv": 0},
        "error": error,
    }


def get_system_stats():
    """获取实时系统状态"""

    if not _HAS_PSUTIL:
        return _empty_stats("psutil 不可用")

    try:
        # CPU使用率（每个核心）
        cpu_percent = psutil.cpu_percent(interval=0, percpu=True)
        cpu_total = sum(cpu_percent) / len(cpu_percent) if cpu_percent else 0

        # 内存信息
        memory = psutil.virtual_memory()

        # 磁盘信息
        disk = psutil.disk_usage('/')

        # 网络IO
        net_io = psutil.net_io_counters()

        return {
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "cpu": {
                "total_percent": round(cpu_total, 1),
                "per_cpu": [round(x, 1) for x in cpu_percent],
                "core_count": psutil.cpu_count(logical=False)
            },
            "memory": {
                "total_gb": round(memory.total / (1024 ** 3), 2),
                "used_gb": round(memory.used / (1024 ** 3), 2),
                "percent": memory.percent
            },
            "disk": {
                "total_gb": round(disk.total / (1024 ** 3), 2),
                "used_gb": round(disk.used / (1024 ** 3), 2),
                "percent": disk.percent
            },
            "network": {
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv
            }
        }
    except Exception as e:
        logger.warning(f"采集系统状态失败，返回降级数据: {e}")
        return _empty_stats(str(e))
