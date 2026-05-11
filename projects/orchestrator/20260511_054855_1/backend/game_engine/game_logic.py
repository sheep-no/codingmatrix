# backend/game_engine/game_logic.py
"""
五子棋胜负判断与游戏规则实现
"""

from typing import List, Tuple, Optional
from backend.game_engine.chess_board import ChessBoard

def check_winner(board: ChessBoard, position: Tuple[int, int]) -> Optional[str]:
    """
    判断落子后是否形成五子连珠
    
    Args:
        board: 当前棋盘对象
        position: 落子坐标 (x, y)
        
    Returns:
        胜利玩家标识（'X'或'O'）或None（无胜利者）
    """
    if not board.is_valid_position(position):
        raise ValueError("无效的落子坐标")
        
    x, y = position
    player = board.get_player_at(position)
    
    # 检查四个方向：水平、垂直、主对角线、副对角线
    directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
    for dx, dy in directions:
        count = 1
        # 向一个方向延伸
        for i in range(1, 5):
            nx, ny = x + dx*i, y + dy*i
            if board.is_valid_position((nx, ny)) and board.get_player_at((nx, ny)) == player:
                count += 1
            else:
                break
        # 向相反方向延伸
        for i in range(1, 5):
            nx, ny = x - dx*i, y - dy*i
            if board.is_valid_position((nx, ny)) and board.get_player_at((nx, ny)) == player:
                count += 1
            else:
                break
                
        if count >= 5:
            return player
            
    return None

def is_game_over(board: ChessBoard) -> Tuple[bool, Optional[str]]:
    """
    判断游戏是否结束
    
    Args:
        board: 当前棋盘对象
        
    Returns:
        (是否结束, 胜利者标识) 元组
    """
    # 检查是否有玩家胜利
    winner = check_winner(board, board.get_last_move())
    if winner:
        return True, winner
    
    # 检查是否棋盘已满
    if board.is_full():
        return True, "draw"
    
    return False, None

def get_valid_moves(board: ChessBoard) -> List[Tuple[int, int]]:
    """
    获取所有有效的落子位置
    
    Args:
        board: 当前棋盘对象
        
    Returns:
        有效坐标列表
    """
    return [(x, y) for x in range(board.size) 
            for y in range(board.size) 
            if board.is_empty((x, y))]

def is_valid_move(board: ChessBoard, position: Tuple[int, int]) -> bool:
    """
    验证落子位置是否有效
    
    Args:
        board: 当前棋盘对象
        position: 落子坐标 (x, y)
        
    Returns:
        是否有效
    """
    if not board.is_valid_position(position):
        return False
    return board.is_empty(position)