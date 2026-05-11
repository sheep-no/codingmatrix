import asyncio
import uuid
import datetime
from typing import Optional, Dict, Any, List

import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from databases import Database
from sqlalchemy import create_engine, Column, String, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, declarative_base, sessionmaker

# 配置CORS
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 数据库配置
DATABASE_URL = "sqlite:///gomoku.db"
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=Database)

# 创建数据库引擎
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
database = Database(DATABASE_URL)

# 定义数据模型
class Player(Base):
    __tablename__ = "players"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, index=True)
    color = Column(String, default="black")
    is_ai = Column(Boolean, default=False)
    rating = Column(Integer, default=1000)

class Game(Base):
    __tablename__ = "games"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    status = Column(String, default="active")
    current_player = Column(String, ForeignKey("players.id"))
    board_size = Column(Integer, default=15)

class Move(Base):
    __tablename__ = "moves"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    game_id = Column(String, ForeignKey("games.id"))
    player_id = Column(String, ForeignKey("players.id"))
    row = Column(Integer)
    col = Column(Integer)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# 创建表
async def create_tables():
    async with database:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

# 初始化数据库
@app.on_event("startup")
async def startup():
    await database.connect()
    await create_tables()

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

# 创建数据库会话
def get_db():
    async def get_db(request: Request):
        db = SessionLocal()
        try:
            yield db
        finally:
            await db.close()
    return get_db

# 检查胜利条件
def check_win(board: List[List[str]], row: int, col: int, player_id: str) -> bool:
    # 检查方向: 水平, 垂直, 对角线, 反对角线
    directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
    
    for dr, dc in directions:
        count = 1  # 当前位置已经有一个棋子
        
        # 正向检查
        r, c = row + dr, col + dc
        while 0 <= r < len(board) and 0 <= c < len(board[0]) and board[r][c] == player_id:
            count += 1
            r += dr
            c += dc
        
        # 反向检查
        r, c = row - dr, col - dc
        while 0 <= r < len(board) and 0 <= c < len(board[0]) and board[r][c] == player_id:
            count += 1
            r -= dr
            c -= dc
        
        if count >= 5:
            return True
    
    return False

# 创建新游戏
@app.post("/games/", response_model=dict)
async def create_game(db: SessionLocal = Depends(get_db)):
    game_id = str(uuid.uuid4())
    board_size = 15
    
    # 初始化空棋盘
    board = [['' for _ in range(board_size)] for _ in range(board_size)]
    
    new_game = Game(
        id=game_id,
        name=f"Gomoku Game {game_id[:8]}",
        board_size=board_size
    )
    
    db.add(new_game)
    await db.commit()
    await db.refresh(new_game)
    
    return {"game_id": game_id, "board_size": board_size}

# 落子
@app.post("/games/{game_id}/move/", response_model=dict)
async def make_move(game_id: str, row: int, col: int, player_id: str = None, db: SessionLocal = Depends(get_db)):
    # 检查游戏是否存在
    game = await db.get(Game, game_id)
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")
    
    # 获取当前玩家
    if game.current_player is None:
        # 第一手棋，创建玩家
        player = Player(id=player_id, name="Player 1")
        db.add(player)
        await db.commit()
        
        # 设置当前玩家
        game.current_player = player_id
    else:
        # 检查玩家是否是当前玩家
        if player_id != game.current_player:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your turn")
    
    # 检查落子位置是否有效
    if row < 0 or row >= game.board_size or col < 0 or col >= game.board_size:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid board position")
    
    # 检查位置是否为空
    board = game.board or [['' for _ in range(game.board_size)] for _ in range(game.board_size)]
    if board[row][col] != '':
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Position already occupied")
    
    # 创建棋盘状态表示
    board_state = []
    for i in range(game.board_size):
        row_data = []
        for j in range(game.board_size):
            if i == row and j == col:
                row_data.append(player_id)
            else:
                row_data.append(board[i][j])
        board_state.append(row_data)
    
    # 检查胜利条件
    if check_win(board_state, row, col, player_id):
        # 更新游戏状态为胜利
        game.status = "completed"
        winner = await db.get(Player, player_id)
        if winner:
            winner.rating += 100
            await db.commit()
        else:
            # 创建玩家
            winner = Player(id=player_id, name="AI" if player_id == "ai" else "Player", rating=1000)
            db.add(winner)
            await db.commit()
    
    # 检查平局（棋盘已满）
    board_full = all(board[i][j] != '' for i in range(game.board_size) for j in range(game.board_size))
    if board_full and not check_win(board_state, row, col, player_id):
        game.status = "draw"
    
    # 创建移动记录
    move = Move(
        game_id=game_id,
        player_id=player_id,
        row=row,
        col=col
    )
    
    db.add(move)
    game.board = board_state  # 更新棋盘状态
    
    await db.commit()
    await db.refresh(game)
    await db.refresh(move)
    
    # 切换玩家
    if game.status != "completed" and not board_full:
        players = await db.query(Player).filter(Player.id != player_id).limit(2).all()
        if players:
            game.current_player = players[0].id
    
    return {
        "game_id": game_id,
        "board": board_state,
        "current_player": game.current_player,
        "status": game.status
    }

# 获取游戏历史
@app.get("/games/{game_id}/history/", response_model=dict)
async def get_game_history(game_id: str, db: SessionLocal = Depends(get_db)):
    game = await db.get(Game, game_id)
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")
    
    moves = await db.query(Move).filter(Move.game_id == game_id).order_by(Move.created_at).all()
    players = {move.player_id: await db.get(Player, move.player_id) for move in moves}
    
    result = {
        "game_id": game_id,
        "status": game.status,
        "moves": []
    }
    
    for move in moves:
        player = players[move.player_id]
        result["moves"].append({
            "move_id": move.id,
            "player": player.name,
            "color": player.color,
            "rating": player.rating,
            "position": {"row": move.row, "col": move.col},
            "created_at": move.created_at.isoformat()
        })
    
    return result

# 获取玩家列表
@app.get("/players/", response_model=dict)
async def get_players(skip: int = 0, limit: int = 10, db: SessionLocal = Depends(get_db)):
    players = await db.query(Player).offset(skip).limit(limit).all()
    return {"players": [p.dict() for p in players]}

# 获取游戏列表
@app.get("/games/", response_model=dict)
async def get_games(skip: int = 0, limit: int = 10, db: SessionLocal = Depends(get_db)):
    games = await db.query(Game).offset(skip).limit(limit).all()
    return {"games": [g.dict() for g in games]}

# 运行应用
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)