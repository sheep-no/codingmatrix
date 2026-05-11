# game_logic/game_engine.py
import logging
from typing import Tuple, Optional, List
from game_logic.chess_board import ChessBoard
from game_logic.player import Player

logger = logging.getLogger(__name__)

class GameEngine:
    def __init__(self, board_size: int = 15):
        """
        初始化五子棋游戏引擎
        
        Args:
            board_size: 棋盘大小，默认为15x15标准棋盘
        """
        self.board_size = board_size
        self.board = ChessBoard(board_size)
        self.current_player = Player.BLACK
        self.game_over = False
        
        # 配置日志记录
        logging.basicConfig(level=logging.INFO)
    
    def make_move(self, position: Tuple[int, int]) -> Optional[str]:
        """
        处理玩家落子操作
        
        Args:
            position: 落子坐标 (x, y)
            
        Returns:
            None: 移动成功
            str: 错误信息（如无效位置、重复落子等）
        """
        # 参数校验
        if not self._is_valid_position(position):
            logger.error("无效的落子位置")
            return "无效的落子位置，请输入在棋盘范围内的坐标"
        
        x, y = position
        
        # 检查该位置是否已被占用
        if self.board.get_piece(x, y) != Player.NONE:
            logger.error("该位置已落子")
            return "该位置已落子，请选择空白位置"
        
        # 执行落子
        self.board.set_piece(x, y, self.current_player)
        
        # 检查胜负
        winner = self.check_winner(x, y)
        if winner:
            self.game_over = True
            logger.info(f"玩家 {winner} 获胜")
            return f"玩家 {winner} 获胜！游戏结束"
        
        # 检查平局
        if self.board.is_full():
            self.game_over = True
            logger.info("棋盘已满，平局")
            return "棋盘已满，游戏结束，双方平局"
        
        # 切换玩家
        self.current_player = Player.WHITE if self.current_player == Player.BLACK else Player.BLACK
        logger.info(f"当前玩家切换为 {self.current_player}")
        return "落子成功，游戏继续"
    
    def _is_valid_position(self, position: Tuple[int, int]) -> bool:
        """
        检查坐标是否在棋盘范围内
        
        Args:
            position: 坐标 (x, y)
            
        Returns:
            bool: 是否有效
        """
        x, y = position
        return 0 <= x < self.board_size and 0 <= y < self.board_size
    
    def check_winner(self, x: int, y: int) -> Optional[Player]:
        """
        检查是否形成五连
        
        Args:
            x: 落子的x坐标
            y: 落子的y坐标
            
        Returns:
            Player: 获胜的玩家（如果有的话）
            None: 游戏未结束
        """
        directions = [
            (1, 0),   # 横向
            (0, 1),   # 纵向
            (1, 1),   # 左上到右下
            (1, -1)   # 右上到左下
        ]
        
        for dx, dy in directions:
            count = 1
            # 向一个方向延伸
            for i in range(1, 5):
                nx, ny = x + dx * i, y + dy * i
                if 0 <= nx < self.board_size and 0 <= ny < self.board_size:
                    if self.board.get_piece(nx, ny) == self.current_player:
                        count += 1
                    else:
                        break
                else:
                    break
            
            # 向相反方向延伸
            for i in range(1, 5):
                nx, ny = x - dx * i, y - dy * i
                if 0 <= nx < self.board_size and 0 <= ny < self.board_size:
                    if self.board.get_piece(nx, ny) == self.current_player:
                        count += 1
                    else:
                        break
                else:
                    break
            
            if count >= 5:
                return self.current_player
        
        return None
    
    def get_board_state(self) -> List[List[int]]:
        """
        获取当前棋盘状态
        
        Returns:
            二维列表表示棋盘状态（0: 空，1: 黑棋，2: 白棋）
        """
        return self.board.get_state()
    
    def get_current_player(self) -> Player:
        """
        获取当前玩家
        
        Returns:
            当前玩家对象
        """
        return self.current_player
    
    def reset_game(self) -> None:
        """
        重置游戏状态
        """
        self.board = ChessBoard(self.board_size)
        self.current_player = Player.BLACK
        self.game_over = False
        logger.info("游戏已重置")