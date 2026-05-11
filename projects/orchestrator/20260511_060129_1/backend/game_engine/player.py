# backend/game_engine/player.py
import logging
from typing import Optional, Tuple, Dict, Any
from backend.game_engine.chess_board import ChessBoard
from backend.game_engine.game_logic import GameLogic
from backend.ai_module.minimax import minimax_move
from enum import Enum

# 配置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PlayerType(Enum):
    HUMAN = "human"
    AI = "ai"

class Player:
    def __init__(self, player_id: str, player_type: PlayerType, symbol: str):
        """
        初始化玩家对象
        
        Args:
            player_id: 玩家唯一标识
            player_type: 玩家类型（人类或AI）
            symbol: 玩家棋子符号（如'X'或'O'）
        """
        self.player_id = player_id
        self.player_type = player_type
        self.symbol = symbol
        self.board = ChessBoard()
        self.game_logic = GameLogic()
        
    def make_move(self, position: Tuple[int, int]) -> Dict[str, Any]:
        """
        玩家落子操作
        
        Args:
            position: 落子坐标 (行, 列)
            
        Returns:
            操作结果字典，包含成功状态和更新后的棋盘状态
            
        Raises:
            ValueError: 无效的坐标或非法操作
        """
        # 参数校验
        if not self._is_valid_position(position):
            logger.error(f"Invalid position {position} for player {self.player_id}")
            raise ValueError("无效的坐标：必须在棋盘范围内且为空位")
            
        # 记录移动历史
        self.board.record_move(position, self.symbol)
        
        # 检查胜负
        winner = self.game_logic.check_win(self.board.board_state, self.symbol)
        
        # 如果AI玩家，自动进行下一步
        if self.player_type == PlayerType.AI:
            ai_move = self._ai_play()
            if ai_move:
                self.board.record_move(ai_move, self.symbol)
                winner = self.game_logic.check_win(self.board.board_state, self.symbol)
                
        # 返回结果
        return {
            "success": True,
            "board": self.board.get_board_state(),
            "winner": winner,
            "current_player": self._get_next_player()
        }
    
    def _ai_play(self) -> Optional[Tuple[int, int]]:
        """
        AI玩家落子逻辑
        
        Returns:
            AI选择的坐标位置，或None表示游戏结束
        """
        try:
            # 调用AI策略获取最佳移动
            best_move = minimax_move(self.board.board_state, self.symbol)
            if best_move:
                return best_move
            return None
        except Exception as e:
            logger.error(f"AI play failed: {str(e)}")
            return None
    
    def _is_valid_position(self, position: Tuple[int, int]) -> bool:
        """
        验证坐标是否有效
        
        Args:
            position: 坐标位置
            
        Returns:
            是否有效
        """
        row, col = position
        return (0 <= row < 15 and 
                0 <= col < 15 and 
                self.board.is_empty_position(row, col))
    
    def _get_next_player(self) -> str:
        """
        获取下一个玩家的符号
        
        Returns:
            下一个玩家的棋子符号
        """
        # 简单交替逻辑（实际应由游戏逻辑管理）
        return 'O' if self.symbol == 'X' else 'X'
    
    def reset_game(self) -> Dict[str, Any]:
        """
        重置棋盘并返回初始状态
        
        Returns:
            重置后的棋盘状态
        """
        self.board = ChessBoard()
        return {
            "success": True,
            "board": self.board.get_board_state(),
            "message": "棋盘已重置"
        }