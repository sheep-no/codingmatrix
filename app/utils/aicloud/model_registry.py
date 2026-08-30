"""
AI Cloud 模型注册表

提供 SiliconFlow 内置模型目录；动态供应商的协议与路由能力由其他 Aicloud 模块提供。

当前内置模型共 18 个，完整字段以 MODEL_REGISTRY 为准。
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict


class ModelProvider(str, Enum):
    """模型提供商"""
    SILICONFLOW = "siliconflow"
    # 预留：未来可扩展
    # OPENAI = "openai"
    # ANTHROPIC = "anthropic"
    # DASHSCOPE = "dashscope"
    # OLLAMA = "ollama"


class ModelCapability(str, Enum):
    """模型能力"""
    TEXT = "text"                    # 文本生成
    VISION = "vision"                # 图片理解
    CODE = "code"                    # 代码生成
    REASONING = "reasoning"          # 深度推理
    FAST = "fast"                    # 快速响应


@dataclass
class ModelInfo:
    """模型信息"""
    id: str                                    # 简短 ID，用户选择用
    name: str                                  # 显示名称
    model_key: str                             # SiliconFlow API 模型名
    provider: ModelProvider                    # 提供商
    description: str                           # 描述
    max_tokens: int                            # 最大输出 token
    max_context: int                           # 最大上下文
    capabilities: List[ModelCapability]        # 能力列表
    is_default: bool = False                   # 是否默认
    is_free: bool = False                      # 是否免费
    cost_per_1m_input: float = 0.0            # 输入每百万 token 成本（元）
    cost_per_1m_output: float = 0.0           # 输出每百万 token 成本（元）
    tags: List[str] = field(default_factory=list)


# 当前硅基流动模型列表
MODEL_REGISTRY: Dict[str, ModelInfo] = {
    "deepseek-r1": ModelInfo(
        id="deepseek-r1",
        name="DeepSeek R1",
        model_key="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
        provider=ModelProvider.SILICONFLOW,
        description="DeepSeek 推理模型，逻辑推理和代码能力强",
        max_tokens=8192,
        max_context=131072,
        capabilities=[ModelCapability.TEXT, ModelCapability.CODE, ModelCapability.REASONING],
        is_default=True,
        cost_per_1m_input=1.0,
        cost_per_1m_output=4.0,
        tags=["推理", "代码", "主力"]
    ),
    "qwen2.5-7b": ModelInfo(
        id="qwen2.5-7b",
        name="Qwen2.5 7B",
        model_key="Qwen/Qwen2.5-7B-Instruct",
        provider=ModelProvider.SILICONFLOW,
        description="Qwen2.5 指令模型，代码生成能力优秀",
        max_tokens=8192,
        max_context=32768,
        capabilities=[ModelCapability.TEXT, ModelCapability.CODE],
        cost_per_1m_input=0.7,
        cost_per_1m_output=1.4,
        tags=["代码", "指令"]
    ),
    "qwen3-8b": ModelInfo(
        id="qwen3-8b",
        name="Qwen3 8B",
        model_key="Qwen/Qwen3-8B",
        provider=ModelProvider.SILICONFLOW,
        description="Qwen3 通用模型，综合能力均衡",
        max_tokens=8192,
        max_context=131072,
        capabilities=[ModelCapability.TEXT, ModelCapability.CODE],
        cost_per_1m_input=0.35,
        cost_per_1m_output=1.4,
        tags=["通用", "架构"]
    ),
    "qwen3.5-4b": ModelInfo(
        id="qwen3.5-4b",
        name="Qwen3.5 4B",
        model_key="Qwen/Qwen3.5-4B",
        provider=ModelProvider.SILICONFLOW,
        description="轻量快速模型，适合简单任务",
        max_tokens=4096,
        max_context=262144,
        capabilities=[ModelCapability.TEXT, ModelCapability.FAST],
        cost_per_1m_input=0.15,
        cost_per_1m_output=0.6,
        tags=["快速", "轻量"]
    ),
    "glm-z1-9b": ModelInfo(
        id="glm-z1-9b",
        name="GLM-Z1 9B",
        model_key="THUDM/GLM-Z1-9B-0414",
        provider=ModelProvider.SILICONFLOW,
        description="智谱 GLM 系列，适合评测和审查",
        max_tokens=8192,
        max_context=131072,
        capabilities=[ModelCapability.TEXT, ModelCapability.REASONING],
        cost_per_1m_input=0.5,
        cost_per_1m_output=2.0,
        tags=["评测", "审查"]
    ),
    "deepseek-ocr": ModelInfo(
        id="deepseek-ocr",
        name="DeepSeek OCR",
        model_key="deepseek-ai/DeepSeek-OCR",
        provider=ModelProvider.SILICONFLOW,
        description="DeepSeek OCR，图片文字识别",
        max_tokens=4096,
        max_context=8192,
        capabilities=[ModelCapability.VISION],
        cost_per_1m_input=1.0,
        cost_per_1m_output=4.0,
        tags=["OCR", "视觉"]
    ),
    "glm-4-9b": ModelInfo(
        id="glm-4-9b",
        name="GLM-4 9B",
        model_key="THUDM/GLM-4-9B-0414",
        provider=ModelProvider.SILICONFLOW,
        description="智谱 GLM-4 基础模型，通用对话能力强",
        max_tokens=8192,
        max_context=32768,
        capabilities=[ModelCapability.TEXT],
        cost_per_1m_input=0.5,
        cost_per_1m_output=2.0,
        tags=["通用", "对话"]
    ),
    "kolors": ModelInfo(
        id="kolors",
        name="Kolors",
        model_key="Kwai-Kolors/Kolors",
        provider=ModelProvider.SILICONFLOW,
        description="快手可图模型，AI 绘画生成",
        max_tokens=4096,
        max_context=8192,
        capabilities=[ModelCapability.VISION],
        cost_per_1m_input=1.0,
        cost_per_1m_output=4.0,
        tags=["绘画", "生成"]
    ),
    "paddleocr-vl-1.5": ModelInfo(
        id="paddleocr-vl-1.5",
        name="PaddleOCR VL 1.5",
        model_key="PaddlePaddle/PaddleOCR-VL-1.5",
        provider=ModelProvider.SILICONFLOW,
        description="PaddleOCR 多模态视觉模型，支持 OCR 与文档理解",
        max_tokens=4096,
        max_context=8192,
        capabilities=[ModelCapability.VISION, ModelCapability.TEXT],
        cost_per_1m_input=1.0,
        cost_per_1m_output=4.0,
        tags=["OCR", "视觉"]
    ),
    "xingchen-asr-v3.2-ultra": ModelInfo(
        id="xingchen-asr-v3.2-ultra",
        name="XingChen ASR V3.2 Ultra",
        model_key="XingChenAGI/XingChenASR-V3.2-Ultra",
        provider=ModelProvider.SILICONFLOW,
        description="XingChen 高性能语音识别模型",
        max_tokens=4096,
        max_context=8192,
        capabilities=[ModelCapability.TEXT],
        cost_per_1m_input=0.5,
        cost_per_1m_output=1.0,
        tags=["语音识别", "ASR"]
    ),
    "xingchen-gsr-v1": ModelInfo(
        id="xingchen-gsr-v1",
        name="XingChen GSR V1.0",
        model_key="XingChenAGI/XingChenGSR-V1.0",
        provider=ModelProvider.SILICONFLOW,
        description="XingChen 语音与说话人识别模型",
        max_tokens=4096,
        max_context=8192,
        capabilities=[ModelCapability.TEXT],
        cost_per_1m_input=0.5,
        cost_per_1m_output=1.0,
        tags=["语音", "说话人"]
    ),
    "xingchen-asr-diarize-v3": ModelInfo(
        id="xingchen-asr-diarize-v3",
        name="XingChen ASR Diarize V3.0",
        model_key="XingChenAGI/XingChenASR-Diarize-V3.0",
        provider=ModelProvider.SILICONFLOW,
        description="XingChen 语音识别与说话人分离模型",
        max_tokens=4096,
        max_context=8192,
        capabilities=[ModelCapability.TEXT],
        cost_per_1m_input=0.5,
        cost_per_1m_output=1.0,
        tags=["语音识别", "说话人分离"]
    ),
    "bge-m3": ModelInfo(
        id="bge-m3",
        name="BGE M3",
        model_key="BAAI/bge-m3",
        provider=ModelProvider.SILICONFLOW,
        description="智源 BGE M3 多语言嵌入模型，支持多种检索任务",
        max_tokens=512,
        max_context=8192,
        capabilities=[ModelCapability.TEXT],
        cost_per_1m_input=0.5,
        cost_per_1m_output=0.0,
        tags=["嵌入", "检索", "多语言"]
    ),
    "bge-reranker-v2-m3": ModelInfo(
        id="bge-reranker-v2-m3",
        name="BGE Reranker V2 M3",
        model_key="BAAI/bge-reranker-v2-m3",
        provider=ModelProvider.SILICONFLOW,
        description="智源 BGE 重排序模型，提升检索精度",
        max_tokens=512,
        max_context=8192,
        capabilities=[ModelCapability.TEXT],
        cost_per_1m_input=0.5,
        cost_per_1m_output=0.0,
        tags=["重排序", "检索"]
    ),
    "bge-large-zh": ModelInfo(
        id="bge-large-zh",
        name="BGE Large ZH",
        model_key="BAAI/bge-large-zh-v1.5",
        provider=ModelProvider.SILICONFLOW,
        description="智源中文向量模型，中文语义检索",
        max_tokens=512,
        max_context=512,
        capabilities=[ModelCapability.TEXT],
        cost_per_1m_input=0.5,
        cost_per_1m_output=0.0,
        tags=["嵌入", "中文", "检索"]
    ),
    "paddleocr-vl-1.5": ModelInfo(
        id="paddleocr-vl-1.5",
        name="PaddleOCR VL 1.5",
        model_key="PaddlePaddle/PaddleOCR-VL-1.5",
        provider=ModelProvider.SILICONFLOW,
        description="PaddleOCR 视觉文字识别模型",
        max_tokens=4096,
        max_context=8192,
        capabilities=[ModelCapability.VISION],
        cost_per_1m_input=0.0,
        cost_per_1m_output=0.0,
        tags=["OCR", "视觉"]
    ),
    "xingchen-asr-v3.2-ultra": ModelInfo(
        id="xingchen-asr-v3.2-ultra",
        name="XingChen ASR V3.2 Ultra",
        model_key="XingChenAGI/XingChenASR-V3.2-Ultra",
        provider=ModelProvider.SILICONFLOW,
        description="星尘语音识别模型",
        max_tokens=4096,
        max_context=4096,
        capabilities=[ModelCapability.TEXT],
        cost_per_1m_input=0.0,
        cost_per_1m_output=0.0,
        tags=["语音", "ASR"]
    ),
    "xingchen-gsr-v1": ModelInfo(
        id="xingchen-gsr-v1",
        name="XingChen GSR V1.0",
        model_key="XingChenAGI/XingChenGSR-V1.0",
        provider=ModelProvider.SILICONFLOW,
        description="星尘语音和说话人识别模型",
        max_tokens=4096,
        max_context=4096,
        capabilities=[ModelCapability.TEXT],
        cost_per_1m_input=0.0,
        cost_per_1m_output=0.0,
        tags=["语音", "说话人"]
    ),
    "xingchen-asr-diarize-v3": ModelInfo(
        id="xingchen-asr-diarize-v3",
        name="XingChen ASR Diarize V3.0",
        model_key="XingChenAGI/XingChenASR-Diarize-V3.0",
        provider=ModelProvider.SILICONFLOW,
        description="星尘语音识别和说话人分离模型",
        max_tokens=4096,
        max_context=4096,
        capabilities=[ModelCapability.TEXT],
        cost_per_1m_input=0.0,
        cost_per_1m_output=0.0,
        tags=["语音", "说话人分离"]
    ),
    "sense-voice": ModelInfo(
        id="sense-voice",
        name="SenseVoice Small",
        model_key="FunAudioLLM/SenseVoiceSmall",
        provider=ModelProvider.SILICONFLOW,
        description="阿里通义语音识别模型，多语言语音转文字",
        max_tokens=4096,
        max_context=4096,
        capabilities=[ModelCapability.TEXT],
        cost_per_1m_input=0.5,
        cost_per_1m_output=0.0,
        tags=["语音", "ASR", "多语言"]
    ),
    "telespeech-asr": ModelInfo(
        id="telespeech-asr",
        name="TeleSpeech ASR",
        model_key="TeleAI/TeleSpeechASR",
        provider=ModelProvider.SILICONFLOW,
        description="中国电信语音识别模型，中文语音转文字",
        max_tokens=4096,
        max_context=4096,
        capabilities=[ModelCapability.TEXT],
        cost_per_1m_input=0.5,
        cost_per_1m_output=0.0,
        tags=["语音", "ASR", "中文"]
    ),
    "hunyuan-mt": ModelInfo(
        id="hunyuan-mt",
        name="Hunyuan MT 7B",
        model_key="tencent/Hunyuan-MT-7B",
        provider=ModelProvider.SILICONFLOW,
        description="腾讯混元翻译模型，多语言翻译",
        max_tokens=4096,
        max_context=32768,
        capabilities=[ModelCapability.TEXT],
        cost_per_1m_input=0.5,
        cost_per_1m_output=1.0,
        tags=["翻译", "多语言"]
    ),
}


def get_model(model_id: str) -> Optional[ModelInfo]:
    """获取模型信息"""
    return MODEL_REGISTRY.get(model_id)


def get_default_model() -> ModelInfo:
    """获取默认模型"""
    for m in MODEL_REGISTRY.values():
        if m.is_default:
            return m
    return next(iter(MODEL_REGISTRY.values()))


def get_available_models(
    capability: Optional[ModelCapability] = None,
    free_only: bool = False
) -> List[ModelInfo]:
    """获取可用模型列表"""
    models = list(MODEL_REGISTRY.values())
    if capability:
        models = [m for m in models if capability in m.capabilities]
    if free_only:
        models = [m for m in models if m.is_free]
    models.sort(key=lambda m: (not m.is_default, m.id))
    return models


def get_provider_info() -> Dict:
    """获取当前供应商信息"""
    return {
        "provider": "siliconflow",
        "name": "硅基流动",
        "url": "https://siliconflow.cn",
        "models_count": len(MODEL_REGISTRY),
        "models": [
            {"id": m.id, "name": m.name, "tags": m.tags}
            for m in MODEL_REGISTRY.values()
        ]
    }
