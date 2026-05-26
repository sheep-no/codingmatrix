"""
KV Cache 优化 - 提示词构建器

将调用结构从 "一个完整大提示词" 重构为:
  [稳定的静态前缀] + [变化的任务指令]

目标: 缓存命中率从 ~0% 提升到 75-97%
"""
import json
import logging
import hashlib
import re
from typing import Optional, Dict, List, Any
from collections import OrderedDict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PromptContext:
    """提示词上下文 - 包含静态前缀和动态后缀"""
    # === 静态前缀（所有调用共享，用于 KV Cache） ===
    system_instructions: str = ""  # 系统指令（身份设定、行为规范）
    tool_definitions: str = ""     # 工具定义（函数名、参数说明）
    spec_cache_content: str = ""   # 规范文件内容
    project_context: str = ""      # 项目上下文（路径、技术栈等）
    
    # === 动态后缀（每次调用变化） ===
    task_instruction: str = ""     # 即时任务指令
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    session_state: Dict[str, Any] = field(default_factory=dict)  # 会话级状态


class PromptBuilder:
    """
    KV Cache 友好的提示词构建器
    
    核心原则:
    1. 静态前缀固化（不变的部分放在 system 消息）
    2. 动态后缀隔离（变化的部分放在 user 消息）
    3. 无意义动态变量清理（移除时间戳/UUID/请求ID）
    4. JSON 键顺序固定化
    5. 历史不可变（仅追加，不修改）
    """
    
    # 需要移除的无意义动态变量模式
    DYNAMIC_PATTERN = re.compile(
        r'(?:timestamp|request_id|uuid|session_id|trace_id)'
        r'[s:：]*\s*[0-9a-f-]{8,}',
        re.IGNORECASE
    )
    
    def __init__(self):
        self._static_prefix_cache: Optional[str] = None
        self._static_prefix_hash: Optional[str] = None
    
    def build_messages(
        self,
        context: PromptContext,
        force_rebuild_prefix: bool = False
    ) -> List[Dict[str, str]]:
        """
        构建符合 KV Cache 规则的 messages 列表
        
        结构:
        [
            {"role": "system", "content": "[静态前缀]"},  # 缓存命中关键
            {"role": "assistant", "content": history[0]},  # 仅追加
            {"role": "user", "content": history[1]},       # 仅追加
            ...
            {"role": "user", "content": "[动态后缀]"}       # 当前请求
        ]
        
        Args:
            context: 提示词上下文
            force_rebuild_prefix: 是否强制重建静态前缀
        
        Returns:
            OpenAI 兼容的 messages 列表
        """
        messages = []
        
        # 1. 构建静态前缀（system 消息）
        static_prefix = self._build_static_prefix(context, force_rebuild_prefix)
        messages.append({
            "role": "system",
            "content": static_prefix
        })
        logger.debug(
            f"静态前缀构建完成，长度: {len(static_prefix)} 字符, "
            f"hash: {self._static_prefix_hash}"
        )
        
        # 2. 追加对话历史（仅追加，不修改）
        for msg in context.conversation_history:
            # 清理动态变量
            cleaned_content = self._clean_dynamic_variables(msg.get("content", ""))
            messages.append({
                "role": msg.get("role", "user"),
                "content": cleaned_content
            })
        
        # 3. 构建动态后缀（当前任务指令）
        dynamic_suffix = self._build_dynamic_suffix(context)
        if dynamic_suffix:
            messages.append({
                "role": "user",
                "content": dynamic_suffix
            })
        
        return messages
    
    def _build_static_prefix(
        self,
        context: PromptContext,
        force_rebuild: bool = False
    ) -> str:
        """构建静态前缀（带缓存）"""
        # 计算缓存键
        cache_key = self._compute_prefix_hash(context)
        
        if not force_rebuild and self._static_prefix_hash == cache_key and self._static_prefix_cache:
            logger.debug("使用缓存的静态前缀")
            return self._static_prefix_cache
        
        # 构建新前缀
        parts = []
        
        if context.system_instructions:
            parts.append(context.system_instructions)
        
        if context.tool_definitions:
            parts.append(f"## 可用工具\n\n{context.tool_definitions}")
        
        if context.spec_cache_content:
            parts.append(f"## 项目规范\n\n{context.spec_cache_content}")
        
        if context.project_context:
            parts.append(f"## 项目上下文\n\n{context.project_context}")
        
        prefix = "\n\n---\n\n".join(parts)
        
        # 更新缓存
        self._static_prefix_cache = prefix
        self._static_prefix_hash = cache_key
        
        return prefix
    
    def _build_dynamic_suffix(self, context: PromptContext) -> str:
        """构建动态后缀"""
        parts = []
        
        # 会话级状态（保留在动态后缀）
        if context.session_state:
            # JSON 键顺序固定化
            state_str = json.dumps(
                context.session_state,
                sort_keys=True,
                ensure_ascii=False,
                indent=2
            )
            parts.append(f"## 当前会话状态\n\n```\n{state_str}\n```")
        
        # 即时任务指令
        if context.task_instruction:
            cleaned = self._clean_dynamic_variables(context.task_instruction)
            parts.append(f"## 当前任务\n\n{cleaned}")
        
        return "\n\n---\n\n".join(parts) if parts else ""
    
    def _clean_dynamic_variables(self, content: str) -> str:
        """清理无意义动态变量"""
        # 移除时间戳、UUID 等
        cleaned = self.DYNAMIC_PATTERN.sub("", content)
        return cleaned.strip()
    
    def _compute_prefix_hash(self, context: PromptContext) -> str:
        """计算静态前缀哈希"""
        content = (
            context.system_instructions +
            context.tool_definitions +
            context.spec_cache_content +
            context.project_context
        )
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    
    def append_history(
        self,
        context: PromptContext,
        role: str,
        content: str
    ) -> None:
        """
        追加对话历史（仅追加，不修改）
        
        这是唯一允许修改 conversation_history 的方法
        """
        # 清理动态变量
        cleaned = self._clean_dynamic_variables(content)
        context.conversation_history.append({
            "role": role,
            "content": cleaned
        })
    
    def clear_cache(self) -> None:
        """清除静态前缀缓存"""
        self._static_prefix_cache = None
        self._static_prefix_hash = None


# --- 有序 JSON 序列化 ---

def ordered_json_dumps(obj: Any) -> str:
    """
    将对象序列化为 JSON，确保键顺序一致
    
    用于确保不同调用生成的 JSON 字符串完全相同，
    避免因序列化差异导致 KV Cache 失效
    """
    def _order(d):
        if isinstance(d, dict):
            return OrderedDict(sorted((k, _order(v)) for k, v in d.items()))
        elif isinstance(d, list):
            return [_order(item) for item in d]
        return d
    
    return json.dumps(_order(obj), ensure_ascii=False, indent=2, sort_keys=True)


# --- 全局单例 ---

_prompt_builder: Optional[PromptBuilder] = None


def get_prompt_builder() -> PromptBuilder:
    """获取全局 PromptBuilder 实例"""
    global _prompt_builder
    if _prompt_builder is None:
        _prompt_builder = PromptBuilder()
    return _prompt_builder
