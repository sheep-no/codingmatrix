"""
自定义 Skill 管理模块
管理用户上传的自定义提示词 skill
"""
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# 自定义 skill 存储目录
CUSTOM_SKILLS_DIR = Path("/workspace/data/custom_skills")
METADATA_FILE = CUSTOM_SKILLS_DIR / "_metadata.json"

# 支持的分类
VALID_CATEGORIES = [
    "orchestrator",  # 编排器角色
    "reviewer",      # 审查角色
    "validation",    # 验证与修复
    "workflow",      # 工作流
    "api",           # API 层
    "tool",          # 工具
    "other",         # 其他
]

# 文件大小限制 (100KB)
MAX_FILE_SIZE = 100 * 1024

# 每个用户最大 skill 数量
MAX_SKILLS_PER_USER = 50


def _notify_registry(name: str, action: str):
    """通知注册表更新"""
    try:
        from app.services.skill_registry import get_registry
        registry = get_registry()
        if action == "delete":
            registry.unregister(name)
        elif action in ("create", "update"):
            registry.reload_custom_skills()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"通知 Skill 注册表失败: {e}")


class CustomSkillManager:
    """自定义 Skill 管理器"""

    def __init__(self):
        self._ensure_dirs()
        self._metadata = self._load_metadata()

    def _ensure_dirs(self):
        """确保目录结构存在"""
        CUSTOM_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        for category in VALID_CATEGORIES:
            (CUSTOM_SKILLS_DIR / category).mkdir(exist_ok=True)

    def _load_metadata(self) -> Dict:
        """加载元数据"""
        if METADATA_FILE.exists():
            try:
                return json.loads(METADATA_FILE.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {"skills": []}
        return {"skills": []}

    def _save_metadata(self):
        """保存元数据"""
        METADATA_FILE.write_text(
            json.dumps(self._metadata, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def _validate_name(self, name: str) -> bool:
        """验证 skill 名称"""
        # 只允许字母、数字、下划线、连字符
        pattern = r'^[a-zA-Z][a-zA-Z0-9_-]{0,63}$'
        return bool(re.match(pattern, name))

    def _validate_content(self, content: str) -> tuple[bool, str]:
        """验证内容"""
        if not content or not content.strip():
            return False, "内容不能为空"
        if len(content.encode('utf-8')) > MAX_FILE_SIZE:
            return False, f"文件大小超过限制 ({MAX_FILE_SIZE // 1024}KB)"
        return True, ""

    def _get_skill_path(self, category: str, name: str) -> Path:
        """获取 skill 文件路径"""
        return CUSTOM_SKILLS_DIR / category / f"{name}.md"

    def _find_skill(self, name: str) -> Optional[Dict]:
        """查找 skill"""
        for skill in self._metadata["skills"]:
            if skill["name"] == name:
                return skill
        return None

    def upload_skill(
        self,
        name: str,
        category: str,
        content: str,
        description: str = "",
        author: str = "anonymous"
    ) -> tuple[bool, str, Optional[Dict]]:
        """
        上传/创建 skill
        
        Returns:
            (success, message, skill_info)
        """
        # 验证名称
        if not self._validate_name(name):
            return False, "名称无效，只允许字母、数字、下划线、连字符，且以字母开头，长度 1-64", None

        # 验证分类
        if category not in VALID_CATEGORIES:
            return False, f"无效分类，支持的分类: {', '.join(VALID_CATEGORIES)}", None

        # 验证内容
        valid, msg = self._validate_content(content)
        if not valid:
            return False, msg, None

        # 检查是否已存在
        existing = self._find_skill(name)
        if existing:
            return False, f"Skill '{name}' 已存在，请使用更新接口", None

        # 检查用户 skill 数量
        user_skills = [s for s in self._metadata["skills"] if s.get("author") == author]
        if len(user_skills) >= MAX_SKILLS_PER_USER:
            return False, f"已达到最大 skill 数量限制 ({MAX_SKILLS_PER_USER})", None

        # 保存文件
        skill_path = self._get_skill_path(category, name)
        skill_path.write_text(content, encoding="utf-8")

        # 更新元数据
        skill_info = {
            "name": name,
            "category": category,
            "file": f"{category}/{name}.md",
            "description": description,
            "author": author,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "version": 1
        }
        self._metadata["skills"].append(skill_info)
        self._save_metadata()

        # 通知注册表
        _notify_registry(name, "create")

        return True, "Skill 创建成功", skill_info

    def update_skill(
        self,
        name: str,
        content: str,
        description: Optional[str] = None
    ) -> tuple[bool, str, Optional[Dict]]:
        """
        更新 skill 内容
        
        Returns:
            (success, message, skill_info)
        """
        # 查找 skill
        skill = self._find_skill(name)
        if not skill:
            return False, f"Skill '{name}' 不存在", None

        # 验证内容
        valid, msg = self._validate_content(content)
        if not valid:
            return False, msg, None

        # 更新文件
        skill_path = self._get_skill_path(skill["category"], name)
        skill_path.write_text(content, encoding="utf-8")

        # 更新元数据
        skill["updated_at"] = datetime.utcnow().isoformat() + "Z"
        skill["version"] += 1
        if description is not None:
            skill["description"] = description
        self._save_metadata()

        # 通知注册表
        _notify_registry(name, "update")

        return True, "Skill 更新成功", skill

    def delete_skill(self, name: str) -> tuple[bool, str]:
        """
        删除 skill
        
        Returns:
            (success, message)
        """
        # 查找 skill
        skill = self._find_skill(name)
        if not skill:
            return False, f"Skill '{name}' 不存在"

        # 删除文件
        skill_path = self._get_skill_path(skill["category"], name)
        if skill_path.exists():
            skill_path.unlink()

        # 更新元数据
        self._metadata["skills"] = [s for s in self._metadata["skills"] if s["name"] != name]
        self._save_metadata()

        # 通知注册表
        _notify_registry(name, "delete")

        return True, "Skill 删除成功"

    def get_skill(self, name: str) -> Optional[Dict]:
        """获取 skill 信息和内容"""
        skill = self._find_skill(name)
        if not skill:
            return None

        # 读取内容
        skill_path = self._get_skill_path(skill["category"], name)
        content = ""
        if skill_path.exists():
            content = skill_path.read_text(encoding="utf-8")

        return {**skill, "content": content}

    def list_skills(
        self,
        category: Optional[str] = None,
        author: Optional[str] = None
    ) -> List[Dict]:
        """
        列出 skill
        
        Args:
            category: 按分类过滤
            author: 按作者过滤
        """
        skills = self._metadata["skills"]

        if category:
            skills = [s for s in skills if s["category"] == category]
        if author:
            skills = [s for s in skills if s.get("author") == author]

        return skills

    def get_all_skills(self) -> List[Dict]:
        """获取所有 skill（包含内容）"""
        result = []
        for skill in self._metadata["skills"]:
            skill_path = self._get_skill_path(skill["category"], skill["name"])
            content = ""
            if skill_path.exists():
                content = skill_path.read_text(encoding="utf-8")
            result.append({**skill, "content": content})
        return result

    def get_skills_by_category(self) -> Dict[str, List[Dict]]:
        """按分类获取 skill"""
        by_category = {cat: [] for cat in VALID_CATEGORIES}
        for skill in self._metadata["skills"]:
            category = skill["category"]
            if category in by_category:
                by_category[category].append(skill)
        return by_category


# 全局单例
_skill_manager: Optional[CustomSkillManager] = None


def get_skill_manager() -> CustomSkillManager:
    """获取 skill 管理器单例"""
    global _skill_manager
    if _skill_manager is None:
        _skill_manager = CustomSkillManager()
    return _skill_manager
