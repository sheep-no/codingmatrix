# projects/orchestrator/20260511_072612_1/game_logic/chess_board.py

class ChessBoard:
    def __init__(self, size=15):
        self.size = size
        self.board = [[None for _ in range(size)] for _ in range(size)]
    
    def place_piece(self, x: int, y: int, player: str) -> bool:
        """在指定位置放置棋子并检查是否胜利"""
        if not (0 <= x < self.size and 0 <= y < self.size):
            raise ValueError("坐标超出棋盘范围")
        if self.board[x][y] is not None:
            raise ValueError("该位置已有棋子")
        
        self.board[x][y] = player
        return self.check_win(x, y, player)
    
    def check_win(self, x: int, y: int, player: str) -> bool:
        """检查是否形成五子连珠"""
        # 定义四个方向：水平、垂直、左上-右下、右上-左下
        directions = [(1, 0), (0, 1), (1, 1), (1, -1)]
        
        for dx, dy in directions:
            count = 1
            # 向一个方向延伸
            for i in range(1, 5):
                nx, ny = x + dx * i, y + dy * i
                if 0 <= nx < self.size and 0 <= ny < self.size and self.board[nx][ny] == player:
                    count += 1
                else:
                    break
            # 向相反方向延伸
            for i in range(1, 5):
                nx, ny = x - dx * i, y - dy * i
                if 0 <= nx < self.size and 0 <= ny < self.size and self.board[nx][ny] == player:
                    count += 1
                else:
                    break
            if count >= 5:
                return True
        
        return False
    
    def is_full(self) -> bool:
        """检查棋盘是否已满"""
        for row in self.board:
            if None in row:
                return False
        return True
    
    def get_board(self) -> list[list[str]]:
        """获取当前棋盘状态"""
        return [row[:] for row in self.board]
    
    def reset(self) -> None:
        """重置棋盘"""
        self.board = [[None for _ in range(self.size)] for _ in range(self.size)]