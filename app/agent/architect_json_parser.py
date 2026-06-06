"""
Architect JSON 解析器（向后兼容包装）

实际实现已迁移到 app.agent.json_parser。
保留此类以兼容现有导入：from app.agent.architect_json_parser import ArchitectJsonParser
"""

from app.agent.json_parser import _get_parser


class ArchitectJsonParser:
    """Architect JSON 解析器（向后兼容）"""

    def safe_parse_json(self, text: str):
        return _get_parser().safe_parse_json(text)
