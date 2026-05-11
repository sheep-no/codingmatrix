# main.py
import os
import sys
from typing import Optional, Dict, List, Any

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse

# 添加项目目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 创建FastAPI应用
app = FastAPI()

# 配置CORS，允许前端域名访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")

# 主路由，返回前端页面
@app.get("/", response_class=HTMLResponse)
async def read_root():
    return """
    <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>五子棋游戏</title>
            <link rel="stylesheet" href="/static/style.css">
        </head>
        <body>
            <div class="container">
                <h1>五子棋游戏</h1>
                <div id="game-container"></div>
                <script src="/static/app.js"></script>
            </div>
        </body>
    </html>
    """

# 模拟游戏状态
class GameState:
    def __init__(self):
        self.board = [['' for _ in range(15)] for _ in range(15)]
        self.current_player = 'black'
        self.game_over = False
        self.winner = None
        self.move_history = []

game_state = GameState()

# 获取游戏状态API
@app.get("/game/status")
async def get_game_status():
    return {
        "board": game_state.board,
        "current_player": game_state.current_player,
        "game_over": game_state.game_over,
        "winner": game_state.winner,
        "move_history": game_state.move_history
    }

# 落子API
@app.post("/game/move")
async def make_move(row: int, col: int):
    if game_state.game_over:
        raise HTTPException(status_code=400, detail="游戏已结束")

    if not (0 <= row < 15 and 0 <= col < 15):
        raise HTTPException(status_code=400, detail="无效的行列位置")

    if game_state.board[row][col] != '':
        raise HTTPException(status_code=400, detail="该位置已有棋子")

    # 放置棋子
    game_state.board[row][col] = game_state.current_player
    game_state.move_history.append({"row": row, "col": col, "player": game_state.current_player})

    # 检查胜利条件
    if check_win(row, col, game_state.current_player):
        game_state.game_over = True
        game_state.winner = game_state.current_player
        return {"status": "win", "winner": game_state.current_player}

    # 检查平局条件（棋盘已满）
    if all(cell != '' for row in game_state.board for cell in row):
        game_state.game_over = True
        return {"status": "draw"}

    # 切换玩家
    game_state.current_player = 'white' if game_state.current_player == 'black' else 'black'

    return {"status": "move_made", "current_player": game_state.current_player}

# 重置游戏API
@app.post("/game/reset")
async def reset_game():
    global game_state
    game_state = GameState()
    return {"status": "reset"}

# 检查胜利条件
def check_win(row: int, col: int, player: str) -> bool:
    # 检查方向: 水平、垂直、两个对角线
    directions = [
        [(0, 1), (0, -1)],   # 水平
        [(1, 0), (-1, 0)],   # 垂直
        [(1, 1), (-1, -1)],  # 主对角线
        [(1, -1), (-1, 1)]   # 副对角线
    ]

    for dir_pair in directions:
        count = 1  # 当前位置已有一个棋子

        # 检查每个方向对
        for dir in dir_pair:
            dr, dc = dir
            r, c = row + dr, col + dc
            while 0 <= r < 15 and 0 <= c < 15 and game_state.board[r][c] == player:
                count += 1
                r += dr
                c += dc

        if count >= 5:
            return True

    return False

# 运行FastAPI应用
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)