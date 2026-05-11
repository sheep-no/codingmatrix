# backend/game_engine/chess_board.py
import logging
import json
from typing import List, Dict, Tuple, Optional

# 配置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
chess_logger = logging.getLogger(__name__)

class ChessBoard:
    """五子棋棋盘类，负责棋盘状态的表示和基本操作"""
    
    def __init__(self, size: int = 15):
        """初始化棋盘"""
        self.size = size
        self.board: List[List[int]] = [[0 for _ in range(size)] for _ in range(size)]
        self.last_move: Optional[Tuple[int, int]] = None
        chess_logger.info(f"创建 {size}x{size} 棋盘")
    
    def get_board_state(self) -> Dict[str, any]:
        """获取当前棋盘状态"""
        state = {
            "size": self.size,
            "board": self.board,
            "last_move": self.last_move
        }
        chess_logger.debug("获取棋盘状态: %s", json.dumps(state, ensure_ascii=False))
        return state
    
    def check_valid_position(self, position: Tuple[int, int]) -> bool:
        """检查落子位置是否有效"""
        x, y = position
        if not (0 <= x < self.size and 0 <= y < self.size):
            chess_logger.warning("无效坐标: %s", position)
            return False
        if self.board[x][y] != 0:
            chess_logger.warning("坐标已被占用: %s", position)
            return False
        return True
    
    def place_stone(self, position: Tuple[int, int], player: int) -> bool:
        """在指定位置放置棋子"""
        if not self.check_valid_position(position):
            return False
            
        x, y = position
        self.board[x][y] = player
        self.last_move = position
        chess_logger.info("玩家 %d 在位置 %s 落子", player, position)
        return True
    
    def reset(self) -> None:
        """重置棋盘到初始状态"""
        self.board = [[0 for _ in range(self.size)] for _ in range(self.size)]
        self.last_move = None
        chess_logger.info("棋盘已重置")
    
    def to_string(self) -> str:
        """将棋盘状态转换为可存储的字符串格式"""
        return json.dumps(self.board, ensure_ascii=False)
    
    @classmethod
    def from_string(cls, board_str: str, size: int = 15) -> 'ChessBoard':
        """从字符串恢复棋盘状态"""
        board = json.loads(board_str)
        if len(board) != size or any(len(row) != size for row in board):
            raise ValueError("棋盘字符串格式不正确")
        instance = cls(size)
        instance.board = board
        return instance