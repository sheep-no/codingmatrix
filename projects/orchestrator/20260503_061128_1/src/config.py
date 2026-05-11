# src/config.py
"""
配置文件，存储增量生成测试所需的参数和设置
包含数据生成规则、批次配置、调试模式等关键参数
"""

from typing import Dict, List, Optional
from enum import Enum
from pydantic import BaseModel, validator
import os
import json


class GenerationType(Enum):
    """增量生成类型枚举"""
    INTEGER = "integer"
    STRING = "string"
    DATE = "date"
    BOOLEAN = "boolean"
    FLOAT = "float"


class Config(BaseModel):
    """测试增量生成的配置类"""
    generation_type: GenerationType = GenerationType.INTEGER
    """生成数据类型，可选: integer, string, date, boolean, float"""
    
    batch_size: int = 100
    """每次生成的数据批次大小，默认100条记录"""
    
    increment_step: int = 10
    """增量步长，控制每次生成的数据范围增量"""
    
    max_records: int = 1000
    """最大生成记录数，防止无限生成"""
    
    enable_debug: bool = False
    """是否启用调试模式，开启后会输出详细日志"""
    
    output_format: str = "json"
    """输出格式，可选: 'json' 或 'csv'"""
    
    seed_value: Optional[int] = None
    """随机数种子，用于生成可重复的数据"""
    
    @validator('batch_size')
    def validate_batch_size(cls, value):
        """验证批次大小是否为正整数"""
        if value <= 0:
            raise ValueError('batch_size 必须是大于0的整数')
        return value
    
    @validator('increment_step')
    def validate_increment_step(cls, value):
        """验证增量步长是否为正整数"""
        if value <= 0:
            raise ValueError('increment_step 必须是大于0的整数')
        return value
    
    @validator('max_records')
    def validate_max_records(cls, value):
        """验证最大记录数是否为正整数"""
        if value <= 0:
            raise ValueError('max_records 必须是大于0的整数')
        return value
    
    @validator('output_format')
    def validate_output_format(cls, value):
        """验证输出格式是否有效"""
        valid_formats = ["json", "csv"]
        if value not in valid_formats:
            raise ValueError(f'output_format 必须是 {valid_formats} 中的一种')
        return value


# 初始化配置实例
config = Config()

# 配置文件路径
CONFIG_FILE_PATH = os.path.join(os.path.dirname(__file__), "config.json")

# 用于测试的示例配置（可选）
EXAMPLE_CONFIG = {
    "generation_type": "integer",
    "batch_size": 50,
    "increment_step": 5,
    "max_records": 200,
    "enable_debug": True,
    "output_format": "json",
    "seed_value": 42
}

# 从文件加载配置的函数（可选）
def load_config_from_file() -> Dict:
    """从文件加载配置参数"""
    try:
        with open(CONFIG_FILE_PATH, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"警告: 配置文件 {CONFIG_FILE_PATH} 未找到，使用默认配置")
        return EXAMPLE_CONFIG
    except json.JSONDecodeError:
        print(f"错误: 配置文件 {CONFIG_FILE_PATH} 格式错误")
        raise
    except Exception as e:
        print(f"加载配置时发生未知错误: {str(e)}")
        raise