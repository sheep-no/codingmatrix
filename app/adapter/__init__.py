"""
Model Adapter - AI 模型适配器
"""
import sys
from pathlib import Path

# 确保可以导入 model_adapter
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from .model_adapter import ModelAdapter

__all__ = ['ModelAdapter']
