import sqlite3
import json
import uuid
from typing import List, Dict, Tuple, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

# 棋盘配置
BOARD_SIZE = 15
EMPTY = 0
BLACK = 1
WHITE = 2

# 棋局状态
class GameState:
    def __init__(self):
        self.board = [[EMPTY for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.current_player = BLACK
        self.game_id = str(uuid.uuid4())
        self.history = []
        self.winner = None

    def make_move(self, row: int, col: int) -> bool:
        """在指定位置落子"""
        if self.board[row][col] != EMPTY or self.winner is not None:
            return False
        
        self.board[row][col] = self.current_player
        self.history.append({
            'row': row,
            'col': col,
            'player': self.current_player
        })
        
        # 检查是否获胜
        if self.check_win(row, col):
            self.winner = self.current_player
            self.save_to_db()
            return True
        
        # 切换玩家
        self.current_player = WHITE if self.current_player == BLACK else BLACK
        self.save_to_db()
        return True

    def check_win(self, row: int, col: int) -> bool:
        """检查是否获胜"""
        directions = [
            [(0, 1), (0, -1)],  # 水平
            [(1, 0), (-1, 0)],  # 垂直
            [(1, 1), (-1, -1)],  # 对角线 /
            [(1, -1), (-1, 1)]   # 对角线 \
        ]
        
        player = self.board[row][col]
        
        for dx, dy in directions:
            count = 1  # 当前位置已经计数
            
            # 正向检查
            for dr, dc in dx:
                r, c = row + dr, col + dc
                while 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and self.board[r][c] == player:
                    count += 1
                    r += dr
                    c += dc
            
            # 反向检查
            for dr, dc in dy:
                r, c = row + dr, col + dc
                while 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and self.board[r][c] == player:
                    count += 1
                    r += dr
                    c += dc
            
            if count >= 5:
                return True
        
        return False

    def save_to_db(self):
        """保存棋局状态到数据库"""
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        
        # 创建表如果不存在
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS games (
                id TEXT PRIMARY KEY,
                board BLOB,
                current_player INTEGER,
                history BLOB,
                winner INTEGER
            )
        ''')
        
        # 保存棋局状态
        board_data = json.dumps(self.board)
        history_data = json.dumps(self.history)
        
        cursor.execute('''
            INSERT OR REPLACE INTO games 
            VALUES (?, ?, ?, ?, ?)
        ''', (
            self.game_id,
            board_data,
            self.current_player,
            history_data,
            self.winner
        ))
        
        conn.commit()
        conn.close()

    def load_from_db(game_id: str) -> 'GameState':
        """从数据库加载棋局状态"""
        conn = sqlite3.connect('game.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM games WHERE id = ?', (game_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        game_state = GameState()
        game_state.game_id = row[0]
        game_state.board = json.loads(row[1])
        game_state.current_player = row[2]
        game_state.history = json.loads(row[3])
        game_state.winner = row[4]
        
        conn.close()
        return game_state

# 数据库初始化
def init_db():
    """初始化数据库"""
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    
    # 创建游戏表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS games (
            id TEXT PRIMARY KEY,
            board BLOB,
            current_player INTEGER,
            history BLOB,
            winner INTEGER
        )
    ''')
    
    # 创建对局历史表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS game_histories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id TEXT,
            move TEXT,
            player INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

# API路由
@app.post("/start_game")
async def start_game():
    """开始新游戏"""
    game_state = GameState()
    game_state.save_to_db()
    return {"game_id": game_state.game_id}

@app.post("/make_move/{game_id}")
async def make_move(game_id: str, row: int, col: int):
    """落子"""
    game = GameState.load_from_db(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    
    if game.make_move(row, col):
        return {
            "game_id": game.game_id,
            "board": game.board,
            "current_player": game.current_player,
            "winner": game.winner
        }
    else:
        raise HTTPException(status_code=400, detail="Invalid move")

@app.get("/get_game/{game_id}")
async def get_game(game_id: str):
    """获取游戏状态"""
    game = GameState.load_from_db(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    
    return {
        "game_id": game.game_id,
        "board": game.board,
        "current_player": game.current_player,
        "winner": game.winner,
        "history": game.history
    }

@app.get("/list_games")
async def list_games():
    """列出所有正在进行的游戏"""
    conn = sqlite3.connect('game.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM games')
    games = [row[0] for row in cursor.fetchall()]
    
    conn.close()
    return {"games": games}

# 初始化数据库
init_db()