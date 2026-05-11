"""
关键词触发器

监听用户输入，匹配关键词后：
1. 搜索相关文件
2. 结构化追问用户
3. 自动生成规格书

用法:
    from scripts.trigger_keyword import KeywordTrigger
    trigger = KeywordTrigger()
    if trigger.matches("我需要重构 auth 模块"):
        result = trigger.process("我需要重构 auth 模块")
"""

import json
import logging
import re
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class TriggerResult:
    """触发结果"""
    matched: bool
    trigger_type: str = ""
    questions: List[str] = None
    related_files: List[str] = None
    spec_template: Dict = None


class KeywordTrigger:
    """关键词触发器"""

    def __init__(self, config_path: str = None):
        self.config_path = Path(config_path or settings.KEYWORD_TRIGGERS_PATH)
        self.triggers = []
        self._load_config()

    def _load_config(self):
        """加载配置"""
        if not self.config_path.exists():
            logger.warning(f"关键词触发配置不存在: {self.config_path}")
            return

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            self.triggers = config.get("triggers", [])
            self.follow_up_config = config.get("follow_up", {
                "max_questions": 3,
                "max_rounds": 2,
                "auto_generate_spec": True,
            })
            logger.info(f"加载 {len(self.triggers)} 个关键词触发规则")
        except Exception as e:
            logger.error(f"加载关键词触发配置失败: {e}")
            self.triggers = []

    def matches(self, user_input: str) -> Optional[Dict]:
        """
        检查用户输入是否匹配关键词

        Returns:
            匹配的触发规则，或 None
        """
        for trigger in self.triggers:
            keywords = trigger.get("keywords", [])
            for keyword in keywords:
                if keyword.lower() in user_input.lower():
                    return trigger
        return None

    def process(self, user_input: str) -> TriggerResult:
        """
        处理用户输入

        如果匹配关键词：
        1. 搜索相关文件
        2. 生成追问问题
        3. 准备规格书模板
        """
        trigger = self.matches(user_input)
        if not trigger:
            return TriggerResult(matched=False)

        # 提取关键词
        keywords = trigger.get("keywords", [])
        matched_keyword = None
        for kw in keywords:
            if kw.lower() in user_input.lower():
                matched_keyword = kw
                break

        # 搜索相关文件
        related_files = self._search_related_files(user_input)

        return TriggerResult(
            matched=True,
            trigger_type=trigger.get("type", "unknown"),
            questions=trigger.get("questions", [])[:self.follow_up_config.get("max_questions", 3)],
            related_files=related_files,
            spec_template=self._get_spec_template(trigger.get("type", "new_feature")),
        )

    def _search_related_files(self, user_input: str) -> List[str]:
        """
        根据用户输入搜索相关文件
        尝试从输入中提取模块/文件名，然后搜索匹配的文件
        """
        files = []

        # 尝试提取可能的文件/模块名
        # 支持中文和英文
        patterns = [
            r'([\w\./]+\.py)',  # xxx.py
            r'([\w\./]+/\w+)',   # path/to/something
            r'([\u4e00-\u9fa5]+)',  # 中文模块名
        ]

        for pattern in patterns:
            matches = re.findall(pattern, user_input)
            for match in matches:
                # 在 app 目录中搜索
                app_dir = Path(__file__).parent.parent / "app"
                for f in app_dir.rglob(f"*{match}*"):
                    if f.is_file() and f.suffix in ('.py',):
                        files.append(str(f.relative_to(app_dir.parent)))

        # 去重
        return list(set(files))

    def _get_spec_template(self, task_type: str) -> Dict:
        """获取规格书模板"""
        spec_template_path = Path(settings.SPEC_TEMPLATE_PATH)
        if not spec_template_path.exists():
            return {}

        try:
            with open(spec_template_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            templates = config.get("templates", {})
            return templates.get(task_type, templates.get("new_feature", {}))
        except Exception as e:
            logger.error(f"加载规格书模板失败: {e}")
            return {}

    def generate_spec_from_answers(self, task_type: str, answers: Dict[str, str]) -> str:
        """
        根据用户回答生成规格书

        Args:
            task_type: 任务类型 (refactor/modify/new_feature)
            answers: 用户回答的字典 {问题: 回答}

        Returns:
            规格书 Markdown 内容
        """
        template = self._get_spec_template(task_type)
        if not template:
            return "# 规格书\n\n无法加载模板"

        lines = [f"# {template.get('title', '规格书')}", ""]

        for section in template.get("sections", []):
            lines.append(f"## {section['name']}")
            lines.append(f"")
            lines.append(f"{section['description']}")
            lines.append(f"")

            for field in section.get("fields", []):
                answer = answers.get(field, "待补充")
                lines.append(f"- **{field}**: {answer}")

            lines.append("")

        return "\n".join(lines)


# 便捷函数
def check_and_trigger(user_input: str) -> TriggerResult:
    """检查并触发关键词"""
    trigger = KeywordTrigger()
    return trigger.process(user_input)


if __name__ == '__main__':
    trigger = KeywordTrigger()

    # 测试
    test_inputs = [
        "我需要重构 auth 模块",
        "修复一下登录报错",
        "添加新的 API 接口",
        "性能优化，查询太慢了",
    ]

    for inp in test_inputs:
        result = trigger.process(inp)
        if result.matched:
            print(f"输入: {inp}")
            print(f"  类型: {result.trigger_type}")
            print(f"  问题: {result.questions}")
            print(f"  相关文件: {result.related_files}")
            print()
        else:
            print(f"输入: {inp} -> 未匹配")
            print()
