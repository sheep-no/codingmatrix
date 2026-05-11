from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
from . import models, schemas
from .database import get_db

router = APIRouter(prefix="/api", tags=["games"])

# 创建新游戏
@router.post("/games/", response_model=schemas.Game)
def create_game(
    board_size: int = 15,
    db: Session = Depends(get_db)
) -> schemas.Game:
    """创建一个新的五子棋游戏"""
    if board_size < 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="棋盘大小至少需要5x5"
        )
    
    db_game = models.Game(
        board_size=board_size,
        created_at=datetime.utcnow(),
        status="active"
    )
    db.add(db_game)
    db.commit()
    db.refresh(db_game)
    return db_game

# 获取游戏信息
@router.get("/games/{game_id}", response_model=schemas.Game)
def get_game(game_id: int, db: Session = Depends(get_db)) -> schemas.Game:
    """获取指定ID的游戏信息"""
    db_game = db.query(models.Game).filter(models.Game.id == game_id).first()
    if not db_game:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="游戏不存在"
        )
    return db_game

# 获取所有游戏列表
@router.get("/games/", response_model=list[schemas.Game])
def get_games(
    skip: int = 0,
    limit: int = 10,
    db: Session = Depends(get_db)
) -> List[schemas.Game]:
    """获取游戏列表"""
    games = db.query(models.Game).offset(skip).limit(limit).all()
    return games

# 落子
@router.put("/games/{game_id}/move/", response_model=schemas.Move)
def make_move(
    game_id: int,
    move: schemas.MoveRequest,
    db: Session = Depends(get_db)
) -> schemas.Move:
    """在指定游戏上落子"""
    # 检查游戏是否存在
    db_game = db.query(models.Game).filter(models.Game.id == game_id).first()
    if not db_game:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="游戏不存在"
        )
    
    # 检查游戏是否结束
    if db_game.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="游戏已结束"
        )
    
    # 检查落子位置是否有效
    if move.x < 1 or move.x > db_game.board_size or move.y < 1 or move.y > db_game.board_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="落子位置无效"
        )
    
    # 检查落子位置是否已有棋子
    db_position = db.query(models.Position).filter(
        models.Position.game_id == game_id,
        models.Position.x == move.x,
        models.Position.y == move.y
    ).first()
    if db_position:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该位置已有棋子"
        )
    
    # 检查是否轮到当前玩家
    if (db_game.current_player != "black" and move.player != "black") or \
        (db_game.current_player != "white" and move.player != "white"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不是当前玩家的回合"
        )
    
    # 创建新位置
    db_position = models.Position(
        game_id=game_id,
        x=move.x,
        y=move.y,
        player=move.player,
        created_at=datetime.utcnow()
    )
    db.add(db_position)
    db.commit()
    db.refresh(db_position)
    
    # 检查胜负
    if check_win(game_id, move.x, move.y, move.player, db):
        db_game.status = f"{move.player}_wins"
        db.commit()
        return db_position
    
    # 检查是否平局（棋盘已满）
    if db.query(models.Position).filter(models.Position.game_id == game_id).count() == db_game.board_size * db_game.board_size:
        db_game.status = "draw"
        db.commit()
    
    # 切换玩家
    db_game.current_player = "white" if db_game.current_player == "black" else "black"
    db.commit()
    
    return db_position

# 结束游戏
@router.put("/games/{game_id}/end/", response_model=schemas.Game)
def end_game(
    game_id: int,
    result: schemas.GameResult,
    db: Session = Depends(get_db)
) -> schemas.Game:
    """结束游戏"""
    db_game = db.query(models.Game).filter(models.Game.id == game_id).first()
    if not db_game:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="游戏不存在"
        )
    
    if db_game.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="游戏已结束"
        )
    
    db_game.status = "ended"
    db_game.end_time = datetime.utcnow()
    db_game.result = result.result
    
    db.commit()
    db.refresh(db_game)
    return db_game

# 获取历史记录
@router.get("/games/{game_id}/history/", response_model=List[schemas.Move])
def get_game_history(
    game_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
) -> List[schemas.Move]:
    """获取游戏历史记录"""
    db_game = db.query(models.Game).filter(models.Game.id == game_id).first()
    if not db_game:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="游戏不存在"
        )
    
    db_moves = db.query(models.Position).filter(
        models.Position.game_id == game_id
    ).order_by(
        models.Position.created_at
    ).offset(skip).limit(limit).all()
    
    return db_moves

# 检查胜负
def check_win(
    game_id: int,
    x: int,
    y: int,
    player: str,
    db: Session
) -> bool:
    """检查是否有五子连珠"""
    # 检查方向：水平、垂直、两个对角线
    directions = [
        [(0, 1), (0, -1)],   # 水平
        [(1, 0), (-1, 0)],   # 垂直
        [(1, 1), (-1, -1)],  # 对角线 /
        [(1, -1), (-1, 1)]   # 对角线 \
    ]
    
    for dir_pair in directions:
        count = 1  # 当前位置已经有一个棋子
        
        # 检查两个相反方向
        for dir in dir_pair:
            dx, dy = dir
            temp_x, temp_y = x, y
            
            # 沿着一个方向计数
            while True:
                temp_x += dx
                temp_y += dy
                if (1 <= temp_x <= db.query(models.Game).filter(models.Game.id == game_id).first().board_size and
                    1 <= temp_y <= db.query(models.Game).filter(models.Game.id == game_id).first().board_size):
                    # 检查这个位置是否有棋子
                    db_position = db.query(models.Position).filter(
                        models.Position.game_id == game_id,
                        models.Position.x == temp_x,
                        models.Position.y == temp_y
                    ).first()
                    
                    if db_position and db_position.player == player:
                        count += 1
                    else:
                        break
                else:
                    break
        
        if count >= 5:
            return True
    
    return False

# 获取统计信息
@router.get("/stats/", response_model=schemas.GameStats)
def get_stats(
    db: Session = Depends(get_db)
) -> schemas.GameStats:
    """获取游戏统计信息"""
    total_games = db.query(models.Game).count()
    active_games = db.query(models.Game).filter(models.Game.status == "active").count()
    completed_games = db.query(models.Game).filter(models.Game.status != "active").count()
    
    black_wins = db.query(models.Game).filter(models.Game.result == "black_wins").count()
    white_wins = db.query(models.Game).filter(models.Game.result == "white_wins").count()
    draws = db.query(models.Game).filter(models.Game.result == "draw").count()
    
    return {
        "total_games": total_games,
        "active_games": active_games,
        "completed_games": completed_games,
        "black_wins": black_wins,
        "white_wins": white_wins,
        "draws": draws
    }