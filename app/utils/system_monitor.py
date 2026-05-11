import psutil
import platform
from datetime import datetime


def get_system_stats():
    """获取实时系统状态"""

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