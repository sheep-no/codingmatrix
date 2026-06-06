import asyncio
import json
import re
from datetime import datetime
from typing import Optional, Dict, Any, AsyncGenerator
from pathlib import Path
import aiofiles
from sqlalchemy.exc import SQLAlchemyError


class LogService:
    """日志读取服务，支持实时流式推送和过滤"""

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_files = {
            "app": self.log_dir / "app.log",
            "error": self.log_dir / "error.log",
            "debug": self.log_dir / "debug.log"
        }

    def _parse_log_line(self, line: str) -> Optional[Dict[str, Any]]:
        line = line.strip()
        if not line:
            return None

        try:
            return json.loads(line)
        except json.JSONDecodeError:
            # 修正：支持带点的 logger 名称
            pattern = (r'^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) - (?P<name>[\w\.]+)\[(?P<process>\d+)\] - '
                       r'(?P<level>\w+) - (?P<location>[^:]+:\d+) - (?P<message>.*)$')
            match = re.match(pattern, line)
            if match:
                return {
                    "timestamp": match.group("timestamp"),
                    "level": match.group("level"),
                    "name": match.group("name"),
                    "process": match.group("process"),
                    "location": match.group("location"),
                    "message": match.group("message"),
                    "_raw": line
                }
            return {
                "timestamp": datetime.now().isoformat(),
                "level": "UNKNOWN",
                "message": line,
                "_raw": line
            }

    def _apply_filters(self, log_entry: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """应用过滤器，返回是否保留该日志"""
        if not filters:
            return True

        level = filters.get("level")
        keyword = filters.get("keyword")

        if level and log_entry.get("level") != level.upper():
            return False

        if keyword:
            message = log_entry.get("message", "")
            if isinstance(message, str) and keyword.lower() not in message.lower():
                return False

        return True

    async def stream_logs_with_filter(
            self,
            log_type: str = "app",
            filters: Dict[str, Any] = None
    ) -> AsyncGenerator[str, None]:
        if filters is None:
            filters = {}

        log_file = self.log_files.get(log_type)
        if not log_file or not log_file.exists():
            yield json.dumps({"error": f"日志文件不存在: {log_type}"}, ensure_ascii=False) + "\n"
            return

        position = log_file.stat().st_size
        logger_name = __name__  # 当前模块名

        while True:
            try:
                if log_file.exists():
                    async with aiofiles.open(log_file, 'r', encoding='utf-8') as f:
                        await f.seek(position)
                        new_content = await f.read()

                        if new_content:
                            position = await f.tell()
                            lines = new_content.strip().split('\n')

                            for line in lines:
                                if line.strip():
                                    parsed = self._parse_log_line(line)
                                    if parsed:
                                        # 跳过日志服务自身的日志，避免循环
                                        msg = parsed.get("message", "")
                                        if "日志流" in msg or "日志过滤" in msg or "日志查询" in msg:
                                            continue

                                        if self._apply_filters(parsed, filters):
                                            yield json.dumps(parsed, ensure_ascii=False) + "\n"

                await asyncio.sleep(0.3)

            except asyncio.CancelledError:
                break
            except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
                yield json.dumps({
                    "timestamp": datetime.now().isoformat(),
                    "level": "ERROR",
                    "message": f"日志流异常: {str(e)}",
                    "error": str(e)
                }, ensure_ascii=False) + "\n"


class LogFilter:
    """管理日志过滤器状态"""

    def __init__(self, level: Optional[str] = None, keyword: Optional[str] = None):
        self.level = level
        self.keyword = keyword

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "keyword": self.keyword
        }
