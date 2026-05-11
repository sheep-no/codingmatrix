# backend/game_engine/board.py
from typing import List, Tuple, Optional, Dict
import json

class Board:
    """
    五子棋棋盘逻辑实现
    
    特性:
    - 15x15标准棋盘
    - 支持黑白双方落子
    - 包含胜利条件检测逻辑
    - 坐标验证和错误处理
    """
    
    def __init__(self, size: int = 15):
        """
        初始化棋盘
        
        参数:
        size: 棋盘边长（默认15）
        """
        self.size = size
        self.grid: List[List[str]] = [['' for _ in range(size)] for _ in range(size)]
        self.last_move: Optional[Tuple[int, int]] = None
        
    def place_move(self, x: int, y: int, player: str) -> Dict[str, any]:
        """
        在指定位置落子
        
        参数:
        x: x坐标（0-based）
        y: y坐标（0-based）
        player: 玩家标识（'Black' 或 'White'）
        
        返回:
        操作结果字典包含状态和棋盘状态
        """
        # 验证坐标有效性
        if not self._is_valid_coordinate(x, y):
            raise ValueError("坐标超出棋盘范围，有效范围为0 <= x < 15, 0 <= y < 15")
            
        # 验证位置是否为空
        if self.grid[y][x] != '':
            raise ValueError("该位置已存在棋子")
            
        # 落子操作
        self.grid[y][x] = player
        self.last_move = (x, y)
        
        # 检查胜利条件
        winner = self._check_winner(x, y)
        
        # 构造响应
        return {
            'status': 'success' if winner is None else 'game_over',
            'winner': winner,
            'board': self._get_board_state()
        }
    
    def _is_valid_coordinate(self, x: int, y: int) -> bool:
        """
        验证坐标是否在有效范围内
        
        参数:
        x: x坐标
        y: y坐标
        
        返回:
        布尔值表示坐标有效性
        """
        return 0 <= x < self.size and 0 <= y < self.size
    
    def _get_board_state(self) -> List[List[str]]:
        """
        获取当前棋盘状态
        
        返回:
        二维列表表示的棋盘状态
        """
        return [row.copy() for row in self.grid]
    
    def _check_winner(self, x: int, y: int) -> Optional[str]:
        """
        检查落子位置是否形成五连
        
        参数:
        x: 最后落子的x坐标
        y: 最后落子的y坐标
        
        返回:
        获胜玩家（'Black' 或 'White'）或 None（无胜者）
        """
        # 检查四个方向：水平、垂直、主对角线、副对角线
        directions = [
            (0, 1),    # 水平向右
            (1, 0),    # 垂直向下
            (1, 1),    # 主对角线（从左上到右下）
            (1, -1)    # 副对角线（从右上到左下）
        ]
        
        for dx, dy in directions:
            count = 1
            # 向一个方向延伸
            for i in range(1, 5):
                nx, ny = x + dx*i, y + dy*i
                if self._is_valid_coordinate(nx, ny) and self.grid[ny][nx] == self.grid[y][x]:
                    count += 1
                else:
                    break
            
            # 向相反方向延伸
            for i in range(1, 5):
                nx, ny = x - dx*i, y - dy*i
                if self._is_valid_coordinate(nx, ny) and self.grid[ny][nx] == self.grid[y][x]:
                    count += 1
                else:
                    break
            
            # 判断是否形成五连
            if count >= 5:
                return self.grid[y][x]
        
        # 检查棋盘是否已满（平局）
        if all(cell != '' for row in self.grid for cell in row):
            return 'Draw'
            
        return None
    
    def get_board(self) -> List[List[str]]:
        """
        获取当前棋盘状态（用于API响应）
        
        返回:
        二维列表表示的棋盘状态
        """
        return self._get_board_state()