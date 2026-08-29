"""独立运行 APScheduler，确保生产环境只有一个 scheduler 进程。"""

from __future__ import annotations

import asyncio
import logging
import signal

from app.db.scheduler import start_scheduler, stop_scheduler


logger = logging.getLogger(__name__)


async def main() -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop_event.set)

    start_scheduler()
    try:
        await stop_event.wait()
    finally:
        stop_scheduler()


if __name__ == "__main__":
    asyncio.run(main())
