# backend/game_engine/player.py
import logging
from typing import Optional, Tuple
from backend.game_engine.chess_board import ChessBoard
from backend.game_engine.game_logic import GameLogic
from backend.ai_module.minimax import minimax_best_move  # 假设已实现AI算法

# 配置日志记录
logging.basicConfig(level=logging.INFO)

class Player:
    def __init__(self, board_size: int = 15):
        """初始化玩家和AI对战逻辑"""
        self.board = ChessBoard(board_size)
        self.game_logic = GameLogic(board_size)
        self.current_player = "human"  # "human" 或 "ai"
        self.winner = None
        self.game_over = False
        
    def switch_player(self) -> None:
        """切换当前玩家"""
        self.current_player = "ai" if self.current_player == "human" else "human"
        
    def make_move(self, position: Tuple[int, int]) -> dict:
        """
        处理玩家落子操作
        Args:
            position: 落子坐标 (x, y)
        Returns:
            包含操作结果的字典
        """
        if self.game_over:
            return {"error": "游戏已结束，无法继续操作"}
            
        if not self.game_logic.is_valid_move(position):
            return {"error": "非法落子位置，请选择有效坐标"}
            
        # 执行落子操作
        self.board.place_piece(position, self.current_player)
        
        # 检查胜负
        result = self.game_logic.check_winner(position)
        if result:
            self.winner = result
            self.game_over = True
            return {"status": "game_over", "winner": self.winner}
            
        # 如果游戏未结束，切换玩家
        if not self.game_over:
            self.switch_player()
            
            # AI下棋
            ai_move = self.ai_play()
            if ai_move:
                self.board.place_piece(ai_move, self.current_player)
                
                # 检查胜负
                result = self.game_logic.check_winner(ai_move)
                if result:
                    self.winner = result
                    self.game_over = True
                    return {"status": "game_over", "winner": self.winner}
                    
                # 切换回玩家
                self.switch_player()
                
        return {"status": "success", "board": self.board.get_board_state()}
    
    def ai_play(self) -> Optional[Tuple[int, int]]:
        """
        AI下棋逻辑
        Returns:
            AI落子坐标，若AI未找到有效移动则返回None
        """
        if self.game_over:
            return None
            
        # 获取所有有效移动位置
        valid_moves = self.game_logic.get_valid_moves()
        if not valid_moves:
            return None
            
        # 使用minimax算法寻找最佳落子位置
        try:
            best_move = minimax_best_move(self.board, self.current_player)
            if best_move in valid_moves:
                return best_move
            return None
        except Exception as e:
            logging.error(f"AI下棋出错: {str(e)}")
            return None
    
    def get_board_state(self) -> dict:
        """获取当前棋盘状态"""
        return {
            "board": self.board.get_board_state(),
            "current_player": self.current_player,
            "winner": self.winner,
            "game_over": self.game_over
        }
    
    def reset_game(self) -> dict:
        """重置棋盘"""
        self.board = ChessBoard(15)
        self.game_logic = GameLogic(15)
        self.current_player = "human"
        self.winner = None
        self.game_over = False
        return {"status": "success", "message": "棋盘已重置"}