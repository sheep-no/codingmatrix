# src/generator.py
from typing import Optional, Dict, Any
import uuid
import time
from sqlalchemy.exc import IntegrityError, OperationalError
from datetime import datetime
from ..db_config import db  # 假设db_config.py已配置数据库实例

class GenerationTaskException(Exception):
    """生成任务相关异常基类"""
    pass

class GenerationTask:
    """管理增量生成任务的核心类"""
    
    def __init__(self, task_id: str, data_type: str, batch_size: int):
        self.task_id = task_id
        self.data_type = data_type
        self.batch_size = batch_size
        self.status = "running"  # 状态初始化为running
        self.started_at = datetime.now()
        self.completed_at: Optional[datetime] = None

    def generate(self) -> None:
        """
        执行增量数据生成逻辑
        根据数据类型模拟生成过程，并在完成时更新任务状态
        """
        try:
            # 模拟生成数据的耗时过程
            for i in range(self.batch_size):
                self._generate_batch_item(i)
                time.sleep(0.1)  # 模拟生成耗时
                
            # 生成完成后更新状态
            self.status = "completed"
            self.completed_at = datetime.now()
            db.session.commit()
            
        except OperationalError as e:
            # 数据库操作异常处理
            db.session.rollback()
            raise GenerationTaskException(f"数据库操作失败: {str(e)}")
        except Exception as e:
            # 其他异常处理
            db.session.rollback()
            raise GenerationTaskException(f"生成过程发生错误: {str(e)}")

    def _generate_batch_item(self, item_index: int) -> None:
        """
        模拟单个数据项的生成逻辑
        Args:
            item_index: 当前生成的项的索引
        """
        # 这里可以替换为实际的数据生成逻辑
        # 示例：生成包含ID和时间戳的模拟数据
        if self.data_type == "user":
            data = {
                "user_id": f"USER_{item_index}",
                "timestamp": datetime.now().isoformat()
            }
        elif self.data_type == "product":
            data = {
                "product_id": f"PRODUCT_{item_index}",
                "name": f"Item {item_index}",
                "created_at": datetime.now().isoformat()
            }
        else:
            raise GenerationTaskException(f"不支持的数据类型: {self.data_type}")
            
        # 模拟将数据存入数据库或外部系统
        # 实际实现中可以替换为真实的数据存储逻辑
        print(f"[生成任务 {self.task_id}] 生成数据项 {item_index} - {data}")

class GenerationTaskManager:
    """管理生成任务的工具类"""
    
    @staticmethod
    def create_task(data_type: str, batch_size: int) -> str:
        """
        创建新的生成任务
        Args:
            data_type: 数据类型，如 'user' 或 'product'
            batch_size: 批量大小
        Returns:
            新创建任务的ID
        Raises:
            GenerationTaskException: 参数无效或数据库操作失败时抛出
        """
        if not data_type or not isinstance(data_type, str):
            raise GenerationTaskException("data_type 必须为非空字符串")
            
        if not isinstance(batch_size, int) or batch_size <= 0:
            raise GenerationTaskException("batch_size 必须为正整数")
            
        # 创建唯一任务ID
        task_id = str(uuid.uuid4())
        
        try:
            task = GenerationTask(task_id=task_id, data_type=data_type, batch_size=batch_size)
            db.session.add(task)
            db.session.commit()
            return task_id
        except IntegrityError as e:
            db.session.rollback()
            raise GenerationTaskException("任务创建失败：数据库完整性约束冲突")
        except Exception as e:
            db.session.rollback()
            raise GenerationTaskException(f"任务创建失败: {str(e)}")

    @staticmethod
    def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
        """
        查询指定ID的任务状态
        Args:
            task_id: 任务ID
        Returns:
            包含任务信息的字典，或 None 如果任务不存在
        """
        task = GenerationTask.query.get(task_id)
        if not task:
            return None
            
        return {
            "task_id": task.task_id,
            "data_type": task.data_type,
            "batch_size": task.batch_size,
            "status": task.status,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None
        }

    @staticmethod
    def update_task_status(task_id: str, new_status: str) -> None:
        """
        更新指定任务的状态
        Args:
            task_id: 任务ID
            new_status: 新状态（如 'running', 'completed', 'failed'）
        Raises:
            GenerationTaskException: 任务不存在或状态更新失败时抛出
        """
        task = GenerationTask.query.get(task_id)
        if not task:
            raise GenerationTaskException("任务不存在")
            
        if new_status not in ["running", "completed", "failed"]:
            raise GenerationTaskException("无效的状态值")
            
        task.status = new_status
        db.session.commit()