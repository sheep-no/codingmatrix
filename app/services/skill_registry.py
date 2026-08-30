"""
全局 Skill 注册表
提供统一的 Skill 注册、加载和访问机制

使用方式：
1. 模块注册 Skill：registry.register("image_styles", "tool", loader_func)
2. 模块获取 Skill：skill = registry.get("image_styles")
3. 用户上传 Skill：通过 API 上传，自动触发注册
"""
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)

# 自定义 Skill 存储目录
CUSTOM_SKILLS_DIR = Path("/workspace/data/custom_skills")
METADATA_FILE = CUSTOM_SKILLS_DIR / "_metadata.json"


@dataclass
class SkillInfo:
    """Skill 信息"""
    name: str
    category: str
    description: str = ""
    content: str = ""
    author: str = "system"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""
    # 加载器函数（用于动态加载）
    loader: Optional[Callable[[], Any]] = None
    # 缓存的数据
    _cached_data: Any = None
    _cache_valid: bool = False


class SkillRegistry:
    """
    全局 Skill 注册表
    
    功能：
    1. 注册内置 Skill（代码中定义）
    2. 注册用户自定义 Skill（从文件加载）
    3. 提供统一的访问接口
    4. 支持缓存和热重载
    """
    
    def __init__(self):
        self._skills: Dict[str, SkillInfo] = {}
        self._initialized = False
    
    def initialize(self):
        """初始化注册表，加载所有 Skill"""
        if self._initialized:
            return
        
        # 加载用户自定义 Skill
        self._load_custom_skills()
        
        self._initialized = True
        logger.info(f"Skill 注册表初始化完成，共 {len(self._skills)} 个 Skill")
    
    def register(
        self,
        name: str,
        category: str,
        loader: Optional[Callable[[], Any]] = None,
        description: str = "",
        content: str = "",
        author: str = "system"
    ) -> SkillInfo:
        """
        注册 Skill
        
        Args:
            name: Skill 名称（全局唯一）
            category: 分类（orchestrator/reviewer/validation/workflow/api/tool/other）
            loader: 加载器函数（返回 Skill 数据）
            description: 描述
            content: 原始内容（Markdown）
            author: 作者
        
        Returns:
            SkillInfo 对象
        """
        now = datetime.utcnow().isoformat() + "Z"
        
        skill = SkillInfo(
            name=name,
            category=category,
            description=description,
            content=content,
            author=author,
            created_at=now,
            updated_at=now,
            loader=loader
        )
        
        self._skills[name] = skill
        logger.debug(f"注册 Skill: {name} (category={category}, author={author})")
        
        return skill
    
    def unregister(self, name: str) -> bool:
        """
        注销 Skill
        
        Args:
            name: Skill 名称
        
        Returns:
            是否成功注销
        """
        if name in self._skills:
            del self._skills[name]
            logger.debug(f"注销 Skill: {name}")
            return True
        return False
    
    def get(self, name: str, use_cache: bool = True) -> Any:
        """
        获取 Skill 数据
        
        Args:
            name: Skill 名称
            use_cache: 是否使用缓存
        
        Returns:
            Skill 数据（通过 loader 加载），如果不存在返回 None
        """
        if name not in self._skills:
            return None
        
        skill = self._skills[name]
        
        # 使用缓存
        if use_cache and skill._cache_valid:
            return skill._cached_data
        
        # 通过 loader 加载
        if skill.loader:
            try:
                data = skill.loader()
                skill._cached_data = data
                skill._cache_valid = True
                return data
            except Exception as e:
                logger.error(f"加载 Skill {name} 失败: {e}")
                return None
        
        # 返回原始内容
        return skill.content
    
    def get_info(self, name: str) -> Optional[SkillInfo]:
        """获取 Skill 信息（不含数据）"""
        return self._skills.get(name)
    
    def list_skills(
        self,
        category: Optional[str] = None,
        author: Optional[str] = None
    ) -> List[SkillInfo]:
        """
        列出 Skill
        
        Args:
            category: 按分类过滤
            author: 按作者过滤
        """
        skills = list(self._skills.values())
        
        if category:
            skills = [s for s in skills if s.category == category]
        if author:
            skills = [s for s in skills if s.author == author]
        
        return skills
    
    def get_by_category(self, category: str) -> List[SkillInfo]:
        """获取指定分类的所有 Skill"""
        return [s for s in self._skills.values() if s.category == category]
    
    def invalidate_cache(self, name: str) -> bool:
        """使 Skill 缓存失效"""
        if name in self._skills:
            self._skills[name]._cache_valid = False
            self._skills[name]._cached_data = None
            return True
        return False
    
    def invalidate_all_cache(self):
        """使所有 Skill 缓存失效"""
        for skill in self._skills.values():
            skill._cache_valid = False
            skill._cached_data = None
    
    def reload_skill(self, name: str) -> bool:
        """重新加载 Skill"""
        self.invalidate_cache(name)
        return self.get(name) is not None
    
    def _load_custom_skills(self):
        """从文件系统加载用户自定义 Skill"""
        if not CUSTOM_SKILLS_DIR.exists():
            return
        
        if not METADATA_FILE.exists():
            return
        
        try:
            metadata = json.loads(METADATA_FILE.read_text(encoding="utf-8"))
            skills = metadata.get("skills", [])
            
            for skill_info in skills:
                name = skill_info.get("name", "")
                owner_user_id = skill_info.get("owner_user_id")
                registry_name = f"user:{owner_user_id}:{name}" if owner_user_id else name
                category = skill_info.get("category", "other")
                file_path = CUSTOM_SKILLS_DIR / skill_info.get("file", "")
                description = skill_info.get("description", "")
                author = skill_info.get("author", "unknown")
                version = skill_info.get("version", 1)
                
                if file_path.exists():
                    content = file_path.read_text(encoding="utf-8")
                    
                    # 创建 loader 函数
                    def make_loader(fp):
                        def loader():
                            return fp.read_text(encoding="utf-8")
                        return loader
                    
                    self.register(
                        name=registry_name,
                        category=category,
                        loader=make_loader(file_path),
                        description=description,
                        content=content,
                        author=author
                    )
            
            logger.info(f"从自定义 Skill 目录加载了 {len(skills)} 个 Skill")
        except Exception as e:
            logger.error(f"加载自定义 Skill 失败: {e}")
    
    def reload_custom_skills(self):
        """重新加载所有自定义 Skill"""
        # 移除所有用户自定义 Skill
        custom_names = [name for name, skill in self._skills.items() if skill.author != "system"]
        for name in custom_names:
            del self._skills[name]
        
        # 重新加载
        self._load_custom_skills()


# 全局单例
_registry: Optional[SkillRegistry] = None


def get_registry() -> SkillRegistry:
    """获取全局 Skill 注册表"""
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
        _registry.initialize()
    return _registry


# ============================================================================
# 便捷函数
# ============================================================================

def register_skill(
    name: str,
    category: str,
    loader: Optional[Callable[[], Any]] = None,
    description: str = "",
    content: str = "",
    author: str = "system"
) -> SkillInfo:
    """注册 Skill 的便捷函数"""
    return get_registry().register(name, category, loader, description, content, author)


def get_skill(name: str, use_cache: bool = True) -> Any:
    """获取 Skill 的便捷函数"""
    return get_registry().get(name, use_cache)


def list_skills(category: Optional[str] = None) -> List[SkillInfo]:
    """列出 Skill 的便捷函数"""
    return get_registry().list_skills(category)
