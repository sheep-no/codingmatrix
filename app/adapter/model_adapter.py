"""
Model Adapter - AI 模型适配器实现
"""
import json
import logging
import re
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class ModelAdapterConfig:
    """模型适配器配置"""
    def __init__(self, model_name: str):
        self.require_strict_json = True
        self.enable_few_shot = True
        self.default_temperature = 0.7
        self.default_max_tokens = 4096


class ModelAdapter:
    """
    AI 模型适配器
    
    用于适配不同的 AI 模型，提供统一的调用接口
    """
    
    def __init__(self, model_name: str):
        """
        初始化模型适配器

        Args:
            model_name: 模型名称，如 'Qwen/Qwen3-8B'
        """
        self.model_name = model_name
        self.model_config = self._load_model_config(model_name)
        self.config = ModelAdapterConfig(model_name)
        logger.info(f"ModelAdapter 初始化：{model_name}")

    @property
    def require_strict_json(self) -> bool:
        return self.config.require_strict_json

    @property
    def enable_few_shot(self) -> bool:
        return self.config.enable_few_shot
    
    def _load_model_config(self, model_name: str) -> Dict[str, Any]:
        """
        加载模型配置

        Args:
            model_name: 模型名称

        Returns:
            模型配置字典
        """
        # 默认配置
        default_config = {
            'model_name': model_name,
            'max_tokens': 4096,
            'temperature': 0.7,
            'thinking_budget': 4096,
        }

        # 根据模型名称返回特定配置
        model_configs = {
            # Qwen 系列
            'Qwen/Qwen3.5-4B': {
                'max_tokens': 4096,
                'temperature': 0.7,
                'thinking_budget': 4096,
            },
            'Qwen/Qwen3-8B': {
                'max_tokens': 4096,
                'temperature': 0.7,
                'thinking_budget': 4096,
            },
            'Qwen/Qwen2.5-7B-Instruct': {
                'max_tokens': 4096,
                'temperature': 0.7,
                'thinking_budget': 4096,
            },
            # DeepSeek 系列
            'deepseek-ai/DeepSeek-R1-0528-Qwen3-8B': {
                'max_tokens': 8192,
                'temperature': 0.6,
                'thinking_budget': 8192,
            },
            'deepseek-ai/DeepSeek-OCR': {
                'max_tokens': 2048,
                'temperature': 0.5,
                'thinking_budget': 2048,
            },
            # Qwen 视觉模型
            'Qwen/Qwen3.5-4B': {
                'max_tokens': 4096,
                'temperature': 0.7,
                'thinking_budget': 4096,
            },
            # Kolors
            'Kwai-Kolors/Kolors': {
                'max_tokens': 512,
                'temperature': 0.8,
                'thinking_budget': 0,
            },
        }

        config = default_config.copy()
        if model_name in model_configs:
            config.update(model_configs[model_name])

        return config
    
    async def chat(self, prompt: str, **kwargs) -> str:
        """
        聊天接口（兼容旧版本）
        
        Args:
            prompt: 提示词
            **kwargs: 其他参数
            
        Returns:
            AI 回复的文本
        """
        # 实际上这个类主要是配置管理
        # 实际调用由 utils/AiCodeUtil.py 中的 call_siliconflow 处理
        logger.warning("ModelAdapter.chat() 已废弃，请使用 call_siliconflow()")
        return ""

    def build_system_prompt(self, tools_schema: List[Dict[str, Any]] = None) -> str:
        """
        构建系统提示词

        Args:
            tools_schema: 工具 schema 列表

        Returns:
            格式化的系统提示词
        """
        base_prompt = """你是一个专业的 AI 编程助手。

你可以通过工具调用来完成任务。当需要执行操作时，请在响应中包含 JSON 格式的工具调用。

## 工具调用格式
```json
{
    "tool_calls": [
        {
            "id": "call_unique_id",
            "function": {
                "name": "tool_name",
                "arguments": {"param1": "value1", "param2": "value2"}
            }
        }
    ]
}
```

## 可用工具
"""

        if tools_schema:
            tools_text = self._format_tools_schema(tools_schema)
            base_prompt += f"\n{tools_text}\n"
        else:
            base_prompt += "\n暂无预定义工具。\n"

        return base_prompt

    def _format_tools_schema(self, tools_schema: List[Dict[str, Any]]) -> str:
        """
        格式化工具 schema 为可读文本

        Args:
            tools_schema: 工具 schema 列表

        Returns:
            格式化的工具描述文本
        """
        result = []
        for tool in tools_schema:
            name = tool.get("name", "unknown")
            description = tool.get("description", "无描述")
            params = tool.get("parameters", {})

            result.append(f"### {name}")
            result.append(f"描述：{description}")

            if "properties" in params:
                result.append("参数：")
                for param_name, param_info in params["properties"].items():
                    param_type = param_info.get("type", "any")
                    param_desc = param_info.get("description", "")
                    required = param_name in params.get("required", [])
                    req标记 = "(必需)" if required else "(可选)"
                    result.append(f"  - {param_name}: {param_type} {req标记} - {param_desc}")

            result.append("")

        return "\n".join(result)

    def parse_response(self, response_text: str) -> tuple:
        """
        解析模型响应，提取工具调用

        Args:
            response_text: 模型响应文本

        Returns:
            (tool_calls, text_content, success) 元组
        """
        tool_calls = []
        text_content = ""

        if not response_text or not response_text.strip():
            return [], "", False

        text_content = self._extract_text_content(response_text)
        tool_calls = self._extract_tool_calls(response_text)

        has_tool_calls = len(tool_calls) > 0
        return tool_calls, text_content, has_tool_calls

    def _extract_text_content(self, text: str) -> str:
        """从响应中提取纯文本内容"""
        result = text
        json_match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', text)
        if json_match:
            json_str = json_match.group(1)
            try:
                data = json.loads(json_str)
                if "tool_calls" in data:
                    result = text.replace(json_match.group(0), "").strip()
            except json.JSONDecodeError:
                pass
        return result.strip()

    def _extract_tool_calls(self, text: str) -> List[Dict[str, Any]]:
        """从响应中提取工具调用"""
        tool_calls = []

        patterns = [
            r'```(?:json)?\s*(\{[\s\S]*?\})\s*```',
            r'"tool_calls"\s*:\s*\[([\s\S]*?)\]',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                try:
                    if match.startswith('{'):
                        data = json.loads(match)
                    else:
                        data = json.loads(f'[{match}]')

                    if isinstance(data, dict) and "tool_calls" in data:
                        tool_calls.extend(data["tool_calls"])
                    elif isinstance(data, list):
                        tool_calls.extend(data)
                except json.JSONDecodeError:
                    continue

        seen_ids = set()
        unique_calls = []
        for call in tool_calls:
            call_id = call.get("id", "")
            if call_id and call_id not in seen_ids:
                seen_ids.add(call_id)
                unique_calls.append(call)

        return unique_calls

    def get_config(self, key: str, default: Any = None) -> Any:
        """
        获取模型配置
        
        Args:
            key: 配置键
            default: 默认值
            
        Returns:
            配置值
        """
        return self.model_config.get(key, default)
    
    def __repr__(self) -> str:
        return f"ModelAdapter(model_name='{self.model_name}')"
