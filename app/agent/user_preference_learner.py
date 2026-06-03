"""
UserPreferenceLearner - 用户偏好建模

通过学习用户的手动修改行为，推断用户的偏好：
1. 代码风格偏好（函数式 vs 面向对象）
2. 命名风格偏好（驼峰 vs 下划线）
3. 目录结构偏好
4. 注释详细程度偏好
5. 技术选型偏好

支持：
- 差异分析（original vs user_modified）
- 偏好向量建模
- 偏好注入到生成 Prompt
"""

import json
import logging
import asyncio
import re
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

# 偏好数据目录
PREFERENCE_DATA_DIR = Path("./data/user_preferences")
# 偏好文件
PREFERENCE_FILE = PREFERENCE_DATA_DIR / "user_preferences.json"


@dataclass
class CodeStylePreference:
    """代码风格偏好"""
    paradigm: str = "mixed"  # functional/object_oriented/mixed
    naming_convention: str = "snake_case"  # snake_case/camelCase/PascalCase
    function_length: str = "medium"  # short/medium/long
    class_design: str = "mixed"  # single_responsibility/monolithic/mixed


@dataclass
class DocumentationPreference:
    """文档注释偏好"""
    comment_density: str = "moderate"  # minimal/moderate/verbose
    docstring_style: str = "google"  # google/numpy/reST/plain
    inline_comments: bool = True
    type_annotations: bool = True


@dataclass
class ArchitecturePreference:
    """架构偏好"""
    layer_separation: str = "strict"  # strict/moderate/relaxed
    dependency_injection: bool = True
    interface_usage: str = "heavy"  # none/light/heavy
    error_handling: str = "explicit"  # explicit/minimal/mixed


@dataclass
class TechStackPreference:
    """技术栈偏好"""
    frameworks: Dict[str, str] = field(default_factory=dict)  # category -> framework
    libraries: List[str] = field(default_factory=list)
    database: str = ""
    api_style: str = "rest"  # rest/graphql/grpc


@dataclass
class UserPreferenceProfile:
    """用户偏好画像"""
    user_id: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = ""

    code_style: CodeStylePreference = field(default_factory=CodeStylePreference)
    documentation: DocumentationPreference = field(default_factory=DocumentationPreference)
    architecture: ArchitecturePreference = field(default_factory=ArchitecturePreference)
    tech_stack: TechStackPreference = field(default_factory=TechStackPreference)

    # 学习记录
    total_modifications: int = 0
    successful_predictions: int = 0
    confidence_scores: Dict[str, float] = field(default_factory=dict)

    # 偏好强度（0-1）
    preference_strength: Dict[str, float] = field(default_factory=dict)


class UserPreferenceLearner:
    """
    用户偏好学习器

    通过分析用户手动修改的代码，学习用户的编码偏好。

    分析方法：
    1. 对比原始生成代码 vs 用户修改后的代码
    2. 提取差异模式
    3. 更新偏好画像
    """

    def __init__(self, user_id: str = "default", data_dir: Optional[Path] = None):
        self.user_id = user_id
        self.data_dir = data_dir or PREFERENCE_DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.profile = UserPreferenceProfile(user_id=user_id)
        self._modification_history: List[Dict[str, Any]] = []

        self._load_preferences()

    def _load_preferences(self):
        """加载用户偏好"""
        user_file = self.data_dir / f"{self.user_id}.json"
        if user_file.exists():
            try:
                with open(user_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # 重构偏好对象
                if "code_style" in data:
                    data["code_style"] = CodeStylePreference(**data["code_style"])
                if "documentation" in data:
                    data["documentation"] = DocumentationPreference(**data["documentation"])
                if "architecture" in data:
                    data["architecture"] = ArchitecturePreference(**data["architecture"])
                if "tech_stack" in data:
                    data["tech_stack"] = TechStackPreference(**data["tech_stack"])

                self.profile = UserPreferenceProfile(**data)

                logger.info(f"UserPreferenceLearner: 加载了用户 {self.user_id} 的偏好画像")
            except Exception as e:
                logger.error(f"UserPreferenceLearner: 加载偏好失败 {e}")

    def _save_preferences(self):
        """保存用户偏好"""
        user_file = self.data_dir / f"{self.user_id}.json"
        self.profile.updated_at = datetime.now().isoformat()

        try:
            data = asdict(self.profile)
            with open(user_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.info(f"UserPreferenceLearner: 保存了用户 {self.user_id} 的偏好画像")
        except Exception as e:
            logger.error(f"UserPreferenceLearner: 保存偏好失败 {e}")

    def record_modification(
        self,
        file_path: str,
        file_type: str,
        original_code: str,
        user_modified_code: str,
        modification_type: Optional[str] = None
    ):
        """
        记录用户修改

        Args:
            file_path: 文件路径
            file_type: 文件类型
            original_code: 原始生成代码
            user_modified_code: 用户修改后的代码
            modification_type: 修改类型（可选）
        """
        self.profile.total_modifications += 1

        # 分析修改内容
        analysis = self._analyze_modification(
            original_code,
            user_modified_code,
            file_type
        )

        # 记录修改历史
        self._modification_history.append({
            "file_path": file_path,
            "file_type": file_type,
            "timestamp": datetime.now().isoformat(),
            "modification_type": modification_type or "unknown",
            "analysis": analysis
        })

        # 更新偏好画像
        self._update_preferences(analysis)

        # 限制历史记录大小
        if len(self._modification_history) > 1000:
            self._modification_history = self._modification_history[-1000:]

        self._save_preferences()

        logger.info(
            f"UserPreferenceLearner: 记录修改 file={file_path} "
            f"changes={len(analysis.get('changes', []))}"
        )

    def _analyze_modification(
        self,
        original: str,
        modified: str,
        file_type: str
    ) -> Dict[str, Any]:
        """分析修改内容"""
        analysis = {
            "file_type": file_type,
            "changes": [],
            "patterns": {}
        }

        original_lines = original.split('\n')
        modified_lines = modified.split('\n')

        # 简单的 diff 分析
        added_lines = set(modified_lines) - set(original_lines)
        removed_lines = set(original_lines) - set(modified_lines)

        # 分析命名风格变化
        naming_changes = self._analyze_naming_changes(added_lines, removed_lines)
        if naming_changes:
            analysis["changes"].append({
                "type": "naming_convention",
                "details": naming_changes
            })

        # 分析注释变化
        comment_changes = self._analyze_comment_changes(original, modified)
        if comment_changes:
            analysis["changes"].append({
                "type": "documentation",
                "details": comment_changes
            })

        # 分析结构变化
        structure_changes = self._analyze_structure_changes(original, modified)
        if structure_changes:
            analysis["changes"].append({
                "type": "structure",
                "details": structure_changes
            })

        # 分析技术选型变化
        tech_changes = self._analyze_tech_changes(original, modified)
        if tech_changes:
            analysis["changes"].append({
                "type": "technology",
                "details": tech_changes
            })

        return analysis

    def _analyze_naming_changes(
        self,
        added: set,
        removed: set
    ) -> Optional[Dict[str, Any]]:
        """分析命名风格变化"""
        snake_added = sum(1 for line in added if re.search(r'\b[a-z]+_[a-z]+\b', line))
        camel_added = sum(1 for line in added if re.search(r'\b[a-z]+[A-Z]\w+\b', line))

        snake_removed = sum(1 for line in removed if re.search(r'\b[a-z]+_[a-z]+\b', line))
        camel_removed = sum(1 for line in removed if re.search(r'\b[a-z]+[A-Z]\w+\b', line))

        if snake_added > camel_added and camel_removed > snake_removed:
            return {"trend": "toward_snake_case", "confidence": 0.7}
        elif camel_added > snake_added and snake_removed > camel_removed:
            return {"trend": "toward_camel_case", "confidence": 0.7}

        return None

    def _analyze_comment_changes(self, original: str, modified: str) -> Optional[Dict[str, Any]]:
        """分析注释变化"""
        original_comment_count = len(re.findall(r'(?:#|//|/\*|\*/)', original))
        modified_comment_count = len(re.findall(r'(?:#|//|/\*|\*/)', modified))

        diff = modified_comment_count - original_comment_count
        if diff > 5:
            return {"trend": "more_comments", "diff": diff}
        elif diff < -5:
            return {"trend": "fewer_comments", "diff": diff}

        return None

    def _analyze_structure_changes(
        self,
        original: str,
        modified: str
    ) -> Optional[Dict[str, Any]]:
        """分析结构变化"""
        original_funcs = len(re.findall(r'\bdef\b', original))
        original_classes = len(re.findall(r'\bclass\b', original))

        modified_funcs = len(re.findall(r'\bdef\b', modified))
        modified_classes = len(re.findall(r'\bclass\b', modified))

        if modified_funcs > original_funcs + 2:
            return {"trend": "more_functions", "confidence": 0.6}
        elif modified_classes > original_classes:
            return {"trend": "more_classes", "confidence": 0.6}

        return None

    def _analyze_tech_changes(
        self,
        original: str,
        modified: str
    ) -> Optional[Dict[str, Any]]:
        """分析技术选型变化"""
        # 检测框架/库的替换
        frameworks = {
            "flask": r'\bflask\b',
            "fastapi": r'\bfastapi\b',
            "django": r'\bdjango\b',
            "express": r'\bexpress\b',
            "vue": r'\bvue\b',
            "react": r'\breact\b',
        }

        changes = {}
        for name, pattern in frameworks.items():
            orig_match = re.search(pattern, original, re.IGNORECASE)
            mod_match = re.search(pattern, modified, re.IGNORECASE)

            if not orig_match and mod_match:
                changes[f"added_{name}"] = True
            elif orig_match and not mod_match:
                changes[f"removed_{name}"] = True

        return changes if changes else None

    def _update_preferences(self, analysis: Dict[str, Any]):
        """根据分析更新偏好"""
        for change in analysis.get("changes", []):
            change_type = change.get("type")
            details = change.get("details")

            if change_type == "naming_convention":
                trend = details.get("trend")
                if trend == "toward_snake_case":
                    self.profile.code_style.naming_convention = "snake_case"
                    self._update_confidence("naming_convention", 0.1)
                elif trend == "toward_camel_case":
                    self.profile.code_style.naming_convention = "camelCase"
                    self._update_confidence("naming_convention", 0.1)

            elif change_type == "documentation":
                diff = details.get("diff", 0)
                if diff > 10:
                    self.profile.documentation.comment_density = "verbose"
                elif diff > 0:
                    self.profile.documentation.comment_density = "moderate"
                elif diff < -10:
                    self.profile.documentation.comment_density = "minimal"

            elif change_type == "structure":
                trend = details.get("trend")
                if trend == "more_functions":
                    self.profile.code_style.paradigm = "functional"
                elif trend == "more_classes":
                    self.profile.code_style.paradigm = "object_oriented"

            elif change_type == "technology":
                for key, value in details.items():
                    if key.startswith("added_"):
                        framework = key.replace("added_", "")
                        category = self._infer_framework_category(framework)
                        self.profile.tech_stack.frameworks[category] = framework

    def _update_confidence(self, preference_key: str, delta: float):
        """更新偏好置信度"""
        current = self.profile.confidence_scores.get(preference_key, 0.5)
        new_confidence = min(1.0, current + delta)
        self.profile.confidence_scores[preference_key] = new_confidence

        # 更新偏好强度
        self.profile.preference_strength[preference_key] = new_confidence

    def _infer_framework_category(self, framework: str) -> str:
        """推断框架类别"""
        web_frameworks = ["flask", "fastapi", "django", "express"]
        frontend_frameworks = ["vue", "react", "angular", "svelte"]
        orm_frameworks = ["sqlalchemy", "typeorm", "prisma"]

        if framework in web_frameworks:
            return "web_backend"
        elif framework in frontend_frameworks:
            return "web_frontend"
        elif framework in orm_frameworks:
            return "orm"
        else:
            return "other"

    def get_preference_prompt(self) -> str:
        """
        生成用户偏好注入 Prompt

        返回一段描述用户偏好的文本，可注入到生成 Prompt 中。
        """
        parts = ["\n## 用户偏好（重要）"]

        # 代码风格
        style = self.profile.code_style
        if style.paradigm != "mixed":
            paradigm_cn = "函数式" if style.paradigm == "functional" else "面向对象"
            parts.append(f"- 代码风格：倾向于{paradigm_cn}风格")

        if style.naming_convention != "mixed":
            naming_cn = "下划线命名" if style.naming_convention == "snake_case" else "驼峰命名"
            parts.append(f"- 命名风格：使用{naming_cn}")

        # 文档注释
        doc = self.profile.documentation
        if doc.comment_density != "moderate":
            density_cn = {
                "minimal": "最少注释",
                "moderate": "适度注释",
                "verbose": "详细注释"
            }
            parts.append(f"- 注释偏好：{density_cn.get(doc.comment_density, '适度注释')}")

        if doc.type_annotations:
            parts.append("- 类型注解：使用类型注解")
        else:
            parts.append("- 类型注解：不使用类型注解")

        # 架构偏好
        arch = self.profile.architecture
        if arch.layer_separation != "moderate":
            sep_cn = {
                "strict": "严格分层",
                "moderate": "适度分层",
                "relaxed": "灵活分层"
            }
            parts.append(f"- 架构风格：{sep_cn.get(arch.layer_separation, '适度分层')}")

        # 技术栈
        if self.profile.tech_stack.frameworks:
            frameworks_str = ", ".join(
                f"{k}: {v}" for k, v in self.profile.tech_stack.frameworks.items()
            )
            parts.append(f"- 技术偏好：{frameworks_str}")

        # 置信度提示
        high_confidence = [
            k for k, v in self.profile.confidence_scores.items()
            if v >= 0.7
        ]
        if high_confidence:
            parts.append(f"\n> 以上偏好基于 {len(high_confidence)} 个高置信度的学习结果")

        return "\n".join(parts)

    def get_learning_stats(self) -> Dict[str, Any]:
        """获取学习统计"""
        return {
            "user_id": self.user_id,
            "total_modifications": self.profile.total_modifications,
            "preference_items": len(self.profile.confidence_scores),
            "high_confidence_preferences": sum(
                1 for v in self.profile.confidence_scores.values()
                if v >= 0.7
            ),
            "confidence_scores": self.profile.confidence_scores,
            "tech_stack": self.profile.tech_stack.frameworks,
            "code_style": asdict(self.profile.code_style),
            "documentation": asdict(self.profile.documentation)
        }


# 全局单例
_user_preference_learners: Dict[str, UserPreferenceLearner] = {}
_learner_lock = asyncio.Lock()


async def get_user_preference_learner(user_id: str = "default") -> UserPreferenceLearner:
    """获取 UserPreferenceLearner 单例（支持多用户）"""
    global _user_preference_learners

    if user_id not in _user_preference_learners:
        async with _learner_lock:
            if user_id not in _user_preference_learners:
                _user_preference_learners[user_id] = UserPreferenceLearner(user_id=user_id)

    return _user_preference_learners[user_id]
