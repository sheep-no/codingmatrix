import logging
from typing import Tuple, Optional, Dict
from backend.game_engine.chess_board import ChessBoard

# 配置日志记录
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class GameLogic:
    def __init__(self):
        """初始化游戏逻辑，创建新棋盘并设置初始玩家"""
        self.board = ChessBoard()
        self.current_player = 'black'  # 默认先手为黑棋
        self.winner = None
        self.game_over = False
        
        # 记录游戏历史
        self.history = []
        
        logging.info("游戏逻辑初始化完成，棋盘已创建")

    def is_valid_move(self, position: Tuple[int, int]) -> bool:
        """
        验证落子位置是否有效
        
        参数:
            position (Tuple[int, int]): 落子坐标 (x, y)
            
        返回:
            bool: 是否为有效移动
        """
        x, y = position
        # 检查坐标是否在棋盘范围内
        if not (0 <= x < 15 and 0 <= y < 15):
            logging.warning("坐标越界: %s", position)
            return False
            
        # 检查该位置是否为空
        if self.board.get_position(x, y) != 'empty':
            logging.warning("位置已被占用: %s", position)
            return False
            
        return True

    def check_win(self, x: int, y: int) -> bool:
        """
        检查当前落子是否导致胜利
        
        参数:
            x (int): 落子的x坐标
            y (int): 落子的y坐标
            
        返回:
            bool: 是否有胜利者
        """
        # 获取当前玩家颜色
        player_color = self.current_player
        
        # 检查四个方向
        directions = [(1, 0), (0, 1), (1, 1), (1, -1)]
        for dx, dy in directions:
            count = 1
            # 向一个方向延伸
            for i in range(1, 5):
                nx, ny = x + dx*i, y + dy*i
                if 0 <= nx < 15 and 0 <= ny < 15:
                    if self.board.get_position(nx, ny) == player_color:
                        count += 1
                    else:
                        break
                else:
                    break
                    
            # 向相反方向延伸
            for i in range(1, 5):
                nx, ny = x - dx*i, y - dy*i
                if 0 <= nx < 15 and 0 <= ny < 15:
                    if self.board.get_position(nx, ny) == player_color:
                        count += 1
                    else:
                        break
                else:
                    break
                    
            if count >= 5:
                self.winner = player_color
                self.game_over = True
                logging.info(f"检测到胜利: 玩家 {player_color} 在方向 ({dx},{dy}) 形成五连珠")
                return True
                
        return False

    def check_draw(self) -> bool:
        """
        检查是否平局（棋盘已满但无人获胜）
        
        返回:
            bool: 是否为平局
        """
        if self.board.is_full():
            logging.info("棋盘已满，游戏结束")
            self.game_over = True
            return True
        return False

    def make_move(self, position: Tuple[int, int]) -> Dict[str, str]:
        """
        处理落子操作
        
        参数:
            position (Tuple[int, int]): 落子坐标
            
        返回:
            Dict[str, str]: 操作结果包括状态和获胜者
        """
        if not self.is_valid_move(position):
            logging.error("无效落子位置")
            raise ValueError("无效落子位置：请在有效范围内选择未被占用的位置")
            
        x, y = position
        self.board.place_stone(x, y, self.current_player)
        self.history.append(self.board.get_board_state())  # 记录棋盘状态
        
        # 检查胜利
        if self.check_win(x, y):
            return {"status": "win", "winner": self.winner}
            
        # 检查平局
        if self.check_draw():
            return {"status": "draw", "winner": "none"}
            
        # 切换玩家
        self.current_player = 'white' if self.current_player == 'black' else 'black'
        logging.info(f"玩家切换：当前为 {self.current_player} 的回合")
        return {"status": "continue", "current_player": self.current_player}

    def get_board_state(self) -> Dict[str, any]:
        """
        获取当前棋盘状态
        
        返回:
            Dict[str, any]: 包含棋盘数据、当前玩家和游戏状态
        """
        return {
            "board": self.board.get_board_state(),
            "current_player": self.current_player,
            "winner": self.winner,
            "game_over": self.game_over
        }

    def reset_game(self) -> Dict[str, str]:
        """
        重置游戏到初始状态
        
        返回:
            Dict[str, str]: 重置结果
        """
        self.board = ChessBoard()
        self.current_player = 'black'
        self.winner = None
        self.game_over = False
        logging.info("游戏已重置")
        return {"status": "reset", "message": "棋盘已重置"}