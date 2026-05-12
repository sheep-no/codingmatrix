"""
提示词加载器 - 从 .claude/skills/ 目录加载提示词模板
"""

from pathlib import Path
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

# 提示词根目录 - 使用项目根目录定位
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PROMPTS_ROOT = _PROJECT_ROOT / ".claude" / "skills"


class PromptLoader:
    """提示词加载器"""

    @classmethod
    def load(cls, path: str) -> Optional[str]:
        """
        加载指定路径的提示词文件

        Args:
            path: 相对于 prompts 根目录的路径

        Returns:
            提示词内容，加载失败返回 None
        """
        file_path = PROMPTS_ROOT / path
        if not file_path.exists():
            logger.warning(f"提示词文件不存在: {file_path}")
            return None

        try:
            return file_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"加载提示词失败: {e}")
            return None

    @classmethod
    def format(cls, path: str, **kwargs) -> Optional[str]:
        """
        加载并格式化提示词

        Args:
            path: 相对于 prompts 根目录的路径
            **kwargs: 用于替换的变量

        Returns:
            格式化后的提示词
        """
        template = cls.load(path)
        if template is None:
            return None

        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.error(f"提示词格式化失败，缺少变量: {e}")
            return None


# ==================== 快捷方法 ====================

def load_project_generation_prompt(output_dir: str, tools_description: str) -> Optional[str]:
    """加载项目生成系统提示词"""
    return PromptLoader.format(
        "project_generation/enhanced_system_prompt.md",
        output_dir=output_dir,
        tools_description=tools_description
    )


def load_resume_prompt(requirement: str, current_files: list) -> Optional[str]:
    """加载继续生成提示词"""
    files_list = "\n".join(["- " + f for f in current_files[:30]]) if current_files else "(暂无文件)"
    return PromptLoader.format(
        "project_generation/resume_prompt.md",
        current_files_list=files_list,
        requirement=requirement
    )


def load_directory_status_prompt(existing_files: list) -> Optional[str]:
    """加载目录状态提示词"""
    files_list = "\n".join(existing_files[:20]) if existing_files else ""
    return PromptLoader.format(
        "project_generation/directory_status_prompt.md",
        existing_files_list=files_list
    )


def load_orchestrator_prompt() -> Optional[str]:
    """加载增强的 Orchestrator 提示词"""
    return PromptLoader.load("orchestrator/enhanced_orchestrator_prompt.md")


def load_architect_prompt() -> Optional[str]:
    """加载增强的架构师提示词"""
    return PromptLoader.load("orchestrator/enhanced_architect_prompt.md")


def load_frontend_engineer_prompt() -> Optional[str]:
    """加载增强的前端工程师提示词"""
    return PromptLoader.load("orchestrator/enhanced_frontend_engineer_prompt.md")


def load_backend_engineer_prompt() -> Optional[str]:
    """加载增强的后端工程师提示词"""
    return PromptLoader.load("orchestrator/enhanced_backend_engineer_prompt.md")


def load_code_reviewer_prompt() -> Optional[str]:
    """加载增强的代码审查员提示词"""
    return PromptLoader.load("orchestrator/enhanced_code_reviewer_prompt.md")


def load_complexity_analysis_prompt() -> Optional[str]:
    """加载复杂度分析提示词"""
    return PromptLoader.load("orchestrator/complexity_analysis_prompt.md")


def load_openapi_generator_prompt() -> Optional[str]:
    """加载 OpenAPI 生成提示词"""
    return PromptLoader.load("specs/openapi_generator_prompt.md")


def load_types_generator_prompt() -> Optional[str]:
    """加载类型定义生成提示词"""
    return PromptLoader.load("specs/types_generator_prompt.md")


def load_db_schema_generator_prompt() -> Optional[str]:
    """加载数据库 Schema 生成提示词"""
    return PromptLoader.load("specs/db_schema_generator_prompt.md")


def load_config_generator_prompt() -> Optional[str]:
    """加载配置生成提示词"""
    return PromptLoader.load("specs/config_generator_prompt.md")


def load_code_patcher_prompt() -> Optional[str]:
    """加载代码 Patch 生成提示词"""
    return PromptLoader.load("validation/code_patcher_prompt.md")


def load_code_refinement_prompt() -> Optional[str]:
    """加载代码修复提示词"""
    return PromptLoader.load("validation/code_refinement_prompt.md")


def load_cross_validator_prompt() -> Optional[str]:
    """加载交叉验证提示词"""
    return PromptLoader.load("validation/cross_validator_prompt.md")


def load_cognitive_skills_prompt() -> Optional[str]:
    """加载认知技能提示词"""
    return PromptLoader.load("skills/cognitive_skills_prompt.md")
