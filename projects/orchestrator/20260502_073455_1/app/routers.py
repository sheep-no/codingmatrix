from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
from . import models, database
from .models import Game, Move, Player, Board

# 创建路由对象
router = APIRouter(
    prefix="/api",
    tags=["game"],
    responses={404: {"description": "Not found"}}
)

# 获取数据库会话的依赖
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 创建新游戏
@router.post("/games/", response_model=dict)
def create_game(db: Session = Depends(get_db)) -> dict:
    """创建一个新的五子棋游戏实例"""
    try:
        # 创建游戏实例
        new_game = Game(
            board_size=15,
            created_at=datetime.now(),
            status="ongoing",
            current_player=Player.BLACK.value
        )
        
        # 保存到数据库
        db.add(new_game)
        db.commit()
        db.refresh(new_game)
        
        return {"game_id": new_game.game_id, "status": "Game created successfully"}
    
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

# 下一步棋
@router.post("/games/{game_id}/move", response_model=dict)
def make_move(
    game_id: int,
    move: dict,
    db: Session = Depends(get_db)
) -> dict:
    """在指定游戏ID的游戏中下棋"""
    try:
        # 检查游戏是否存在
        game = db.query(Game).filter(Game.game_id == game_id).first()
        if not game:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Game not found"
            )
        
        # 验证移动参数
        if "row" not in move or "col" not in move:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Row and column are required"
            )
        
        row = move["row"]
        col = move["col"]
        
        # 检查移动是否有效
        if not (0 <= row < game.board_size and 0 <= col < game.board_size):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid row or column"
            )
        
        # 获取棋盘状态
        board = game.board
        if board[row][col] != 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cell already occupied"
            )
        
        # 确定玩家
        player = Player.BLACK if game.current_player == Player.BLACK.value else Player.WHITE.value
        
        # 记录移动
        new_move = Move(
            game_id=game_id,
            player=player.value,
            row=row,
            col=col,
            timestamp=datetime.now()
        )
        db.add(new_move)
        
        # 更新棋盘
        board[row][col] = player.value
        
        # 检查胜利条件
        winner = check_win(game, row, col, player)
        if winner:
            game.status = "completed"
            if winner == player:
                game.winner = player.value
            else:
                game.winner = None
        
        # 切换玩家
        game.current_player = Player.WHITE.value if game.current_player == Player.BLACK.value else Player.BLACK.value
        
        # 保存更新
        db.commit()
        db.refresh(game)
        
        return {
            "game_id": game.game_id,
            "status": game.status,
            "current_player": game.current_player,
            "board": game.board
        }
    
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

# 获取游戏状态
@router.get("/games/{game_id}/status", response_model=dict)
def get_game_status(game_id: int, db: Session = Depends(get_db)) -> dict:
    """获取游戏状态"""
    try:
        game = db.query(Game).filter(Game.game_id == game_id).first()
        if not game:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Game not found"
            )
        
        return {
            "game_id": game.game_id,
            "status": game.status,
            "current_player": game.current_player,
            "board": game.board,
            "winner": game.winner
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

# 获取历史记录
@router.get("/games/{game_id}/history", response_model=List[dict])
def get_game_history(game_id: int, db: Session = Depends(get_db)) -> List[dict]:
    """获取游戏历史记录"""
    try:
        game = db.query(Game).filter(Game.game_id == game_id).first()
        if not game:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Game not found"
            )
        
        # 获取所有移动记录
        moves = db.query(Move).filter(Move.game_id == game_id).all()
        history = []
        
        for move in moves:
            history.append({
                "row": move.row,
                "col": move.col,
                "player": move.player,
                "timestamp": move.timestamp.isoformat()
            })
        
        return history
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

# 辅助函数：检查胜利条件
def check_win(game: Game, row: int, col: int, player: int) -> int:
    """检查是否有玩家获胜"""
    # 定义四个方向：水平、垂直、两个对角线
    directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
    
    for dr, dc in directions:
        count = 1  # 当前位置已经有一个棋子
        
        # 正向检查
        r, c = row + dr, col + dc
        while 0 <= r < game.board_size and 0 <= c < game.board_size and game.board[r][c] == player:
            count += 1
            r += dr
            c += dc
        
        # 反向检查
        r, c = row - dr, col - dc
        while 0 <= r < game.board_size and 0 <= c < game.board_size and game.board[r][c] == player:
            count += 1
            r -= dr
            c -= dc
        
        # 如果有5个连续的棋子，则获胜
        if count >= 5:
            return player
    
    return None

# 模型枚举
class Player:
    BLACK = 1
    WHITE = 2

# 模型定义
class Game(Base):
    __tablename__ = "games"
    game_id = Column(Integer, primary_key=True, index=True)
    board_size = Column(Integer, default=15)
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String(20), default="ongoing")
    current_player = Column(Integer, default=1)  # 1 for black, 2 for white
    winner = Column(Integer, nullable=True)
    board = Column(JSON, default=lambda: [[0 for _ in range(15)] for _ in range(15)])

class Move(Base):
    __tablename__ = "moves"
    move_id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("games.game_id"))
    player = Column(Integer)
    row = Column(Integer)
    col = Column(Integer)
    timestamp = Column(DateTime, default=datetime.utcnow)

# 数据库模型
Base.metadata.create_all(bind=engine)