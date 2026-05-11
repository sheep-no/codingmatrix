from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .. import models, schemas
from ..database import get_db

router = APIRouter(
    prefix="/games",
    tags=["games"],
    responses={404: {"description": "Not found"}},
)

# 创建新游戏
@router.post("/", response_model=schemas.Game, status_code=status.HTTP_201_CREATED)
def create_new_game(
    db: Session = Depends(get_db)
) -> schemas.Game:
    """创建一个新的五子棋游戏"""
    db_game = models.Game(is_active=True)
    db.add(db_game)
    db.commit()
    db.refresh(db_game)
    return db_game

# 移动棋子
@router.post("/{game_id}/move", response_model=schemas.Move)
def make_move(
    game_id: int,
    move: schemas.MoveBase,
    db: Session = Depends(get_db)
) -> schemas.Move:
    """在指定游戏上落子"""
    db_game = db.query(models.Game).filter(models.Game.id == game_id).first()
    if not db_game or not db_game.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Game not found or inactive"
        )
    
    # 检查位置是否有效
    if move.x < 0 or move.x >= 15 or move.y < 0 or move.y >= 15:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid board position"
        )
    
    # 创建并保存移动记录
    db_move = models.Move(
        game_id=game_id,
        x=move.x,
        y=move.y,
        player=move.player
    )
    db.add(db_move)
    db.commit()
    db.refresh(db_move)
    
    # 检查游戏是否结束
    if check_win(game_id, move.player):
        db_game.winner = move.player
        db_game.is_active = False
        db.commit()
    
    return db_move

# 获取游戏状态
@router.get("/{game_id}", response_model=schemas.GameDetail)
def get_game(game_id: int, db: Session = Depends(get_db)) -> schemas.GameDetail:
    """获取游戏的详细状态"""
    db_game = db.query(models.Game).filter(models.Game.id == game_id).first()
    if not db_game or not db_game.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Game not found or inactive"
        )
    
    # 获取所有移动记录
    db_moves = db.query(models.Move).filter(models.Move.game_id == game_id).all()
    moves = []
    for db_move in db_moves:
        moves.append({
            "id": db_move.id,
            "x": db_move.x,
            "y": db_move.y,
            "player": db_move.player,
            "timestamp": db_move.timestamp
        })
    
    return {
        "id": db_game.id,
        "is_active": db_game.is_active,
        "current_player": db_game.current_player,
        "winner": db_game.winner,
        "board": [{"x": m.x, "y": m.y, "player": m.player} for m in db_moves],
        "moves": moves
    }

# 获取游戏历史
@router.get("/{game_id}/history", response_model=schemas.GameHistory)
def get_game_history(
    game_id: int,
    db: Session = Depends(get_db)
) -> schemas.GameHistory:
    """获取游戏的历史记录"""
    db_game = db.query(models.Game).filter(models.Game.id == game_id).first()
    if not db_game or not db_game.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Game not found or inactive"
        )
    
    # 获取所有移动记录
    db_moves = db.query(models.Move).filter(models.Move.game_id == game_id).all()
    moves = []
    for db_move in db_moves:
        moves.append({
            "id": db_move.id,
            "x": db_move.x,
            "y": db_move.y,
            "player": db_move.player,
            "timestamp": db_move.timestamp
        })
    
    return {
        "game_id": db_game.id,
        "moves": moves
    }

# 检查胜负
def check_win(game_id: int, player: int) -> bool:
    """检查是否获胜"""
    db = next(get_db())
    db_game = db.query(models.Game).filter(models.Move.game_id == game_id).first()
    if not db_game:
        return False
    
    # 获取当前棋盘状态
    board = {}
    moves = db.query(models.Move).filter(models.Move.game_id == game_id).all()
    for move in moves:
        board[(move.x, move.y)] = move.player
    
    # 检查水平方向
    for y in range(15):
        for x in range(0, 11):
            if all(board.get((x+i, y), 0) == player for i in range(5)):
                return True
    
    # 检查垂直方向
    for x in range(15):
        for y in range(0, 11):
            if all(board.get((x, y+i), 0) == player for i in range(5)):
                return True
    
    # 检查对角线方向
    for y in range(0, 11):
        for x in range(0, 11):
            if all(board.get((x+i, y+i), 0) == player for i in range(5)):
                return True
    
    # 检查反对角线方向
    for y in range(4, 15):
        for x in range(0, 11):
            if all(board.get((x+i, y-i), 0) == player for i in range(5)):
                return True
    
    return False

# 游戏状态转换
def update_game_state(game_id: int, db: Session = Depends(get_db)):
    """更新游戏状态"""
    db_game = db.query(models.Game).filter(models.Game.id == game_id).first()
    if not db_game:
        return
    
    # 获取所有移动记录
    moves = db.query(models.Move).filter(models.Move.game_id == game_id).all()
    if not moves:
        db_game.current_player = 1
        db.commit()
        return
    
    # 确定当前玩家
    last_move = max(moves, key=lambda m: m.id)
    db_game.current_player = 3 - last_move.player  # 交替玩家
    db.commit()