# incremental_generator/generator.py
# 核心增量生成逻辑实现
# 该模块提供一个用于生成递增序列的工具类，支持按步长生成数据并管理状态

from typing import Generator, Optional, Tuple
import uuid
import time

class IncrementalGenerator:
    """
    实现递增序列生成的核心类
    
    功能特点:
    1. 支持从指定起始值开始生成
    2. 可配置生成步长
    3. 支持唯一标识生成
    4. 提供状态控制方法
    5. 包含异常处理机制
    
    使用示例:
    >>> gen = IncrementalGenerator(start_value=100, step=5)
    >>> next(gen.generate())
    100
    >>> next(gen.generate())
    105
    """
    
    def __init__(self, start_value: int = 0, step: int = 1):
        """
        初始化增量生成器
        
        参数:
        start_value: 起始值（默认0）
        step: 步长（默认1）
        
        异常:
        ValueError: 当起始值为负数或步长小于等于0时抛出
        """
        if start_value < 0:
            raise ValueError("起始值必须为非负整数")
        if step <= 0:
            raise ValueError("步长必须为正整数")
        
        # 基础属性
        self.start_value = start_value
        self.step = step
        self._current_value = start_value
        self._sequence_id = str(uuid.uuid4())  # 唯一序列标识
        self._generation_time = time.time()  # 记录生成起始时间
        
    def generate(self) -> Generator[Tuple[int, str, float], None, None]:
        """
        生成增量数据
        
        返回:
        生成器，每次生成包含以下元素的元组：
        - 当前数值值（int）
        - 唯一序列标识（str）
        - 生成时间戳（float）
        
        异常:
        RuntimeError: 当生成器处于异常状态时抛出
        """
        if self._current_value < self.start_value:
            raise RuntimeError("生成器状态异常，当前值小于起始值")
        
        try:
            while True:
                # 生成数据并更新状态
                yield (
                    self._current_value,
                    self._sequence_id,
                    time.time()  # 生成时间戳
                )
                self._current_value += self.step
                
        except Exception as e:
            # 记录异常并重新抛出
            self._current_value = self.start_value  # 重置状态
            self._generation_time = time.time()
            raise

    def reset(self, start_value: Optional[int] = None) -> None:
        """
        重置生成器状态
        
        参数:
        start_value: 新的起始值（默认使用初始起始值）
        
        异常:
        ValueError: 当提供负数起始值时抛出
        """
        if start_value is not None:
            if start_value < 0:
                raise ValueError("重置起始值必须为非负整数")
            self._current_value = start_value
        else:
            self._current_value = self.start_value
            
        self._generation_time = time.time()

    def get_status(self) -> Tuple[int, int, str]:
        """
        获取生成器状态信息
        
        返回:
        (当前值, 步长, 序列标识)
        """
        return (self._current_value, self.step, self._sequence_id)