# config/settings.py
"""
存储并发测试的全局配置参数
包含并发数、执行时长等核心参数
支持通过环境变量覆盖默认值
"""

import os
from typing import Optional, Union

class Settings:
    """
    后端并发测试配置类
    
    可配置参数说明:
    - concurrency_level: 并发线程数，默认100
    - execution_duration: 执行时长（秒），默认60秒
    - task_type: 测试任务类型，支持 'load_test'（负载测试）、'stress_test'（压力测试）
    - result_storage: 结果存储路径或方式（可选）
    - enable_monitoring: 是否启用资源监控（可选）
    """
    
    concurrency_level: int = 100
    execution_duration: float = 60.0
    task_type: str = 'load_test'
    result_storage: Optional[Union[str, dict]] = None
    enable_monitoring: bool = False

    def __init__(self):
        """
        初始化配置并验证参数有效性
        """
        # 从环境变量中加载配置
        self._load_from_env()
        
        # 进行参数验证
        self._validate()

    def _load_from_env(self):
        """
        从环境变量加载配置参数
        """
        if env_value := os.getenv('CONCURRENCY_LEVEL'):
            self.concurrency_level = int(env_value)
        
        if env_value := os.getenv('EXECUTION_DURATION'):
            self.execution_duration = float(env_value)
        
        if env_value := os.getenv('TASK_TYPE'):
            self.task_type = env_value.lower()
        
        if env_value := os.getenv('RESULT_STORAGE'):
            try:
                self.result_storage = eval(env_value)  # 安全性注意：实际生产中应避免eval
            except:
                self.result_storage = env_value
        
        if env_value := os.getenv('ENABLE_MONITORING'):
            self.enable_monitoring = env_value.lower() in ('true', '1')

    def _validate(self):
        """
        验证配置参数有效性
        """
        if self.concurrency_level <= 0:
            raise ValueError("并发数必须大于0")
        
        if self.execution_duration <= 0:
            raise ValueError("执行时长必须大于0")
        
        if self.task_type not in ('load_test', 'stress_test'):
            raise ValueError(f"无效的任务类型: {self.task_type}。支持类型为: load_test, stress_test")
        
        if self.result_storage is not None and not isinstance(self.result_storage, (str, dict)):
            raise TypeError("结果存储参数类型错误，应为字符串或字典")

    @property
    def concurrency(self) -> int:
        """获取并发数参数"""
        return self.concurrency_level

    @property
    def duration(self) -> float:
        """获取执行时长参数（以秒为单位）"""
        return self.execution_duration

    @property
    def task_type(self) -> str:
        """获取任务类型"""
        return self.task_type

    @property
    def result_path(self) -> Optional[str]:
        """
        获取结果存储路径（如果配置为字符串）
        如果配置为字典，返回None
        """
        if isinstance(self.result_storage, str):
            return self.result_storage
        return None

    @property
    def result_config(self) -> Optional[dict]:
        """
        获取结果存储配置（如果配置为字典）
        如果配置为字符串，返回None
        """
        if isinstance(self.result_storage, dict):
            return self.result_storage
        return None