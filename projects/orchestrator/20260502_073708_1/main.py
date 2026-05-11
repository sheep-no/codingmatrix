#!/usr/bin/env python
# -*- coding: utf-8 -*-

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, Any
import uvicorn
import os
from datetime import datetime
import json
import chess
import chess.engine
import chess.pgn
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

# 创建 FastAPI 应用实例
app = FastAPI()

# 配置 CORS，允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 设置静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")

# 配置项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 棋盘状态管理
board_states = {}
game_history = []
current_game_id = 1

# 初始化棋盘状态
def init_board() -> chess.Board:
    """初始化五子棋棋盘"""
    return chess.Board()

# 创建新游戏
def start_new_game() -> int:
    """开始新游戏，返回游戏ID"""
    global current_game_id
    board_states[current_game_id] = init_board()
    game_history.append({
        "game_id": current_game_id,
        "moves": [],
        "result": None,
        "start_time": datetime.now().isoformat()
    })
    return current_game_id

# 处理玩家移动
def make_move(game_id: int, from_square: str, to_square: str) -> bool:
    """处理玩家移动"""
    if game_id not in board_states:
        return False
    
    board = board_states[game_id]
    
    # 检查移动是否合法
    if not board.is_valid_move(chess.parse_square(from_square), chess.parse_square(to_square)):
        return False
    
    # 检查游戏是否已结束
    if board.is_game_over():
        return False
    
    # 记录移动
    board.push(chess.Move.from_uci(f"{from_square}{to_square}"))
    
    # 检查是否获胜
    if board.is_checkmate() or board.is_stalemate():
        board_states[game_id] = board
        return True
    
    # 检查是否平局
    if board.is_draw():
        board_states[game_id] = board
        return True
    
    return True

# 获取游戏状态
def get_game_state(game_id: int) -> Dict[str, Any]:
    """获取游戏状态"""
    if game_id not in board_states:
        return None
    
    board = board_states[game_id]
    game_info = {
        "game_id": game_id,
        "board": board.fen(),
        "moves": list(board.move_stack),
        "current_player": "white" if board.turn == chess.WHITE else "black",
        "game_over": board.is_game_over(),
        "check": board.is_check(),
        "checkmate": board.is_checkmate(),
        "stalemate": board.is_stalemate(),
        "threefold": board.is_threefold_repetition(),
        "fifty": board.is_fivefold_repetition(),
        "elapsed_time": (datetime.now() - datetime.fromisoformat(game_history[-1]["start_time"])).total_seconds()
    }
    
    # 检查游戏是否结束
    if board.is_game_over():
        game_info["result"] = "checkmate" if board.is_checkmate() else "draw" if board.is_stalemate() else "threefold repetition" if board.is_threefold_repetition() else "fifty moves"
    
    return game_info

# 获取历史对局
def get_game_history() -> list:
    """获取历史对局"""
    return game_history

# 重置游戏
def reset_game(game_id: int) -> bool:
    """重置游戏"""
    if game_id in board_states:
        board_states[game_id] = init_board()
        game_history[-1]["moves"] = []
        game_history[-1]["result"] = None
        game_history[-1]["start_time"] = datetime.now().isoformat()
        return True
    return False

# 创建路由
@app.get("/")
async def read_root():
    """返回首页"""
    return {"message": "Welcome to Gomoku Game"}

@app.get("/api/games")
async def get_games():
    """获取所有游戏"""
    return {"games": list(board_states.keys())}

@app.post("/api/games/{game_id}/move")
async def make_move_api(game_id: int, request: Request):
    """处理玩家移动"""
    data = await request.json()
    from_square = data.get("from_square")
    to_square = data.get("to_square")
    
    if not from_square or not to_square:
        raise HTTPException(status_code=400, detail="Invalid move data")
    
    if not make_move(game_id, from_square, to_square):
        raise HTTPException(status_code=400, detail="Invalid move or game is over")
    
    return {"status": "success"}

@app.get("/api/games/{game_id}/status")
async def get_game_status_api(game_id: int):
    """获取游戏状态"""
    game_info = get_game_state(game_id)
    if not game_info:
        raise HTTPException(status_code=404, detail="Game not found")
    
    return game_info

@app.post("/api/games/{game_id}/reset")
async def reset_game_api(game_id: int):
    """重置游戏"""
    if not reset_game(game_id):
        raise HTTPException(status_code=404, detail="Game not found or invalid game ID")
    
    return {"status": "success"}

@app.get("/api/history")
async def get_game_history_api():
    """获取历史对局"""
    return {"history": get_game_history()}

@app.get("/game/{game_id}")
async def get_game_page(game_id: int):
    """返回游戏页面"""
    game_info = get_game_state(game_id)
    if not game_info:
        return {"error": "Game not found"}
    
    return {"game_id": game_id, "game_info": game_info}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        workers=1
    )