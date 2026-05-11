import logging
import json
from typing import Dict, List, Tuple, Optional
import numpy as np

# 配置日志记录
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChessBoard:
    """五子棋棋盘类，处理棋盘状态存储和基本操作"""
    
    def __init__(self, size: int = 19):
        """
        初始化棋盘
        
        Args:
            size: 棋盘大小（默认19x19）
        """
        self.size = size
        self.board: List[List[str]] = [['' for _ in range(size)] for _ in range(size)]
        self.move_history: List[Tuple[int, int, str]] = []
        
        # 初始化日志记录
        logger.info(f"创建 {size}x{size} 的五子棋棋盘")
    
    def get_board_state(self) -> Dict[str, List[List[str]]]:
        """
        获取当前棋盘状态
        
        Returns:
            包含棋盘状态的字典
        """
        return {
            "board": self.board,
            "size": self.size
        }
    
    def make_move(self, position: str, player: str) -> Dict[str, bool]:
        """
        在指定位置落子
        
        Args:
            position: 坐标字符串（如 "A1"）
            player: 玩家标识（"B" 或 "W"）
            
        Returns:
            操作结果字典
        """
        try:
            # 参数校验
            if not position or len(position) < 2:
                logger.error("无效的坐标格式")
                return {"success": False, "error": "坐标格式错误，应为类似 'A1' 的字符串"}
                
            col = position[0].upper()
            row = position[1:]
            
            # 转换为数值坐标
            try:
                col_idx = ord(col) - ord('A')
                row_idx = int(row) - 1
            except (ValueError, IndexError):
                logger.error("坐标转换失败")
                return {"success": False, "error": "坐标转换失败，列应为大写字母，行应为数字"}
                
            # 检查坐标有效性
            if not (0 <= col_idx < self.size and 0 <= row_idx < self.size):
                logger.error(f"坐标越界：{position}")
                return {"success": False, "error": "坐标越界"}
                
            # 检查是否已有棋子
            if self.board[row_idx][col_idx]:
                logger.warning(f"位置 {position} 已有棋子")
                return {"success": False, "error": "该位置已有棋子"}
                
            # 执行落子操作
            self.board[row_idx][col_idx] = player
            self.move_history.append((row_idx, col_idx, player))
            
            logger.info(f"玩家 {player} 在位置 {position} 落子成功")
            return {"success": True, "message": "落子成功"}
            
        except Exception as e:
            logger.error(f"落子操作发生错误: {str(e)}")
            return {"success": False, "error": "内部服务器错误"}
    
    def reset_board(self) -> Dict[str, bool]:
        """
        重置棋盘
        
        Returns:
            重置结果字典
        """
        try:
            # 保存当前状态到历史记录（可选）
            # 可以选择是否将当前状态存入数据库，此处暂不实现
            
            # 重置棋盘
            self.board = [['' for _ in range(self.size)] for _ in range(self.size)]
            self.move_history = []
            
            logger.info("棋盘已重置")
            return {"success": True, "message": "棋盘重置成功"}
            
        except Exception as e:
            logger.error(f"棋盘重置发生错误: {str(e)}")
            return {"success": False, "error": "内部服务器错误"}
    
    def get_move_history(self) -> List[Tuple[int, int, str]]:
        """获取落子历史记录"""
        return self.move_history
    
    def is_valid_position(self, position: str) -> bool:
        """验证坐标有效性"""
        if not position or len(position) < 2:
            return False
            
        col = position[0].upper()
        row = position[1:]
        
        try:
            col_idx = ord(col) - ord('A')
            row_idx = int(row) - 1
            return 0 <= col_idx < self.size and 0 <= row_idx < self.size
        except:
            return False
    
    def to_dict(self) -> Dict[str, List[List[str]]]:
        """将棋盘状态转换为字典格式"""
        return {
            "board": [row.copy() for row in self.board],
            "size": self.size,
            "move_history": self.move_history
        }
    
    def from_dict(self, data: Dict[str, List[List[str]]]) -> None:
        """从字典恢复棋盘状态"""
        if not data or "board" not in data or "size" not in data:
            logger.warning("无效的棋盘状态数据")
            return
            
        self.size = data["size"]
        self.board = [row.copy() for row in data["board"]]
        self.move_history = data.get("move_history", [])
        
        logger.info("棋盘状态已恢复")