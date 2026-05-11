# game_logic/player.py
import pygame
import logging
from typing import Optional, Tuple
from game_logic.chess_board import ChessBoard

class Player:
    """五子棋玩家行为逻辑类"""
    
    def __init__(self, player_id: str, symbol: str, board: ChessBoard):
        """
        初始化玩家
        
        Args:
            player_id: 玩家唯一标识
            symbol: 玩家棋子符号（'X'或'O'）
            board: 棋盘对象
        """
        self.player_id = player_id
        self.symbol = symbol
        self.board = board
        self.logging = logging.getLogger(f"Player.{player_id}")
        
    def make_move(self, position: Tuple[int, int]) -> bool:
        """
        玩家落子操作
        
        Args:
            position: 下棋坐标 (x, y)
            
        Returns:
            bool: 是否落子成功
            
        Raises:
            ValueError: 无效的坐标或位置已占用
        """
        # 参数校验
        if not self._validate_position(position):
            self.logging.error(f"无效坐标 {position}，超出棋盘范围")
            raise ValueError("坐标超出棋盘范围或位置已占用")
            
        x, y = position
        if self.board.get_cell(x, y) is not None:
            self.logging.error(f"位置 ({x}, {y}) 已被占用")
            raise ValueError("位置已被占用")
            
        # 执行落子操作
        if self.board.place_piece(x, y, self.symbol):
            self.logging.info(f"玩家 {self.player_id} 在 ({x}, {y}) 成功落子")
            return True
        return False
    
    def _validate_position(self, position: Tuple[int, int]) -> bool:
        """
        验证坐标有效性
        
        Args:
            position: 坐标元组 (x, y)
            
        Returns:
            bool: 坐标是否有效
        """
        x, y = position
        return (0 <= x < self.board.size and 
                0 <= y < self.board.size and 
                self.board.get_cell(x, y) is None)
    
    def check_win(self) -> Optional[str]:
        """
        检查是否胜利
        
        Returns:
            str: 胜利信息，若未胜利返回 None
        """
        winning_line = self.board.find_winning_line()
        if winning_line:
            self.logging.info(f"玩家 {self.player_id} 在位置 {winning_line} 获胜")
            return f"玩家 {self.player_id} 获胜！在位置 {winning_line} 形成五子连珠"
        self.logging.debug(f"玩家 {self.player_id} 未获胜")
        return None
    
    def is_valid_move(self, position: Tuple[int, int]) -> bool:
        """
        检查移动是否合法
        
        Args:
            position: 坐标元组 (x, y)
            
        Returns:
            bool: 移动是否合法
        """
        return self._validate_position(position) and self.board.is_position_valid(position)
    
    def get_available_moves(self) -> list:
        """获取所有可用落子位置"""
        return self.board.get_empty_cells()
    
    def switch_player(self) -> None:
        """切换玩家回合"""
        self.board.switch_player()
    
    def get_player_symbol(self) -> str:
        """获取玩家棋子符号"""
        return self.symbol
    
    def get_player_id(self) -> str:
        """获取玩家ID"""
        return self.player_id