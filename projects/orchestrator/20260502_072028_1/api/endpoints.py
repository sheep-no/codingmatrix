from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import json
import uuid
import sqlite3
from typing import Dict, List, Optional, Tuple

app = FastAPI()

# 允许前端请求，解决跨域问题
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 棋盘大小
BOARD_SIZE = 15
# 棋子类型：0=空，1=黑棋，2=白棋
EMPTY = 0
BLACK = 1
WHITE = 2

# 存储活跃的游戏连接
active_games: Dict[str, Dict] = {}

class Game:
    def __init__(self, game_id: str):
        self.game_id = game_id
        self.board = [[EMPTY for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.current_player = BLACK
        self.game_over = False
        self.winner = None
        self.moves: List[Tuple[int, int]] = []
        self.player_connections: Dict[int, WebSocket] = {}  # 存储玩家ID和WebSocket连接

    def make_move(self, row: int, col: int) -> bool:
        """在棋盘上落子"""
        if self.game_over or self.board[row][col] != EMPTY:
            return False
        
        self.board[row][col] = self.current_player
        self.moves.append((row, col))
        
        # 检查是否获胜
        if self.check_win(row, col):
            self.game_over = True
            self.winner = self.current_player
            self.save_to_database()
            return True
        
        # 切换玩家
        self.current_player = WHITE if self.current_player == BLACK else BLACK
        return True

    def check_win(self, row: int, col: int) -> bool:
        """检查当前落子是否获胜"""
        directions = [
            [(0, 1), (0, -1)],  # 水平
            [(1, 0), (-1, 0)],  # 垂直
            [(1, 1), (-1, -1)],  # 对角线 ↘
            [(1, -1), (-1, 1)]   # 对角线 ↗
        ]
        
        player = self.board[row][col]
        
        for dir_pair in directions:
            count = 1  # 当前位置已经有一个棋子
            
            # 检查两个相反方向
            for dx, dy in dir_pair:
                r, c = row, col
                for _ in range(4):  # 最多检查4个连续位置
                    r += dx
                    c += dy
                    if (0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and 
                        self.board[r][c] == player):
                        count += 1
                    else:
                        break
            
            if count >= 5:
                return True
        
        return False

    def save_to_database(self):
        """保存游戏历史到SQLite数据库"""
        conn = sqlite3.connect('chess_games.db')
        cursor = conn.cursor()
        
        # 创建表如果不存在
        cursor.execute('''CREATE TABLE IF NOT EXISTS games (
            id TEXT PRIMARY KEY,
            black_player TEXT,
            white_player TEXT,
            winner INTEGER,
            moves TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        # 插入游戏记录
        moves_str = json.dumps(self.moves)
        cursor.execute('''INSERT INTO games (id, black_player, white_player, winner, moves)
                     VALUES (?, ?, ?, ?, ?)''', (
                         self.game_id,
                         "Player1",
                         "Player2",
                         self.winner,
                         moves_str
                     ))
        
        conn.commit()
        conn.close()

@app.websocket("/ws/game/{game_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: str):
    """WebSocket端点处理游戏连接"""
    await websocket.accept()
    
    # 初始化游戏
    if game_id not in active_games:
        active_games[game_id] = Game(game_id)
    
    game = active_games[game_id]
    
    # 存储连接
    player_id = len(game.player_connections) + 1
    game.player_connections[player_id] = websocket
    game.active_connections = {player_id: websocket}
    
    try:
        while True:
            # 接收消息
            data = await websocket.receive_json()
            
            # 处理消息
            if data.get("type") == "move":
                row = data.get("row")
                col = data.get("col")
                
                if row is not None and col is not None:
                    if game.make_move(row, col):
                        # 广播更新后的棋盘状态
                        await broadcast_game_state(game_id, game)
    
    except WebSocketDisconnect:
        # 客户端断开连接
        if game_id in active_games:
            del game.player_connections[player_id]
            
            # 如果所有玩家都断开连接，结束游戏
            if not game.player_connections:
                del active_games[game_id]
    except Exception as e:
        print(f"Error in websocket: {e}")
        # 发生错误，移除连接
        if player_id in game.player_connections:
            del game.player_connections[player_id]
            if not game.player_connections:
                del active_games[game_id]

async def broadcast_game_state(game_id: str, game: Game):
    """广播游戏状态给所有连接的玩家"""
    game_data = {
        "type": "update",
        "board": game.board,
        "current_player": game.current_player,
        "game_over": game.game_over,
        "winner": game.winner,
        "moves": game.moves
    }
    
    for player_id, websocket in game.player_connections.items():
        await websocket.send_json(game_data)

def initialize_database():
    """初始化数据库"""
    conn = sqlite3.connect('chess_games.db')
    cursor = conn.cursor()
    
    # 创建游戏表
    cursor.execute('''CREATE TABLE IF NOT EXISTS games (
        id TEXT PRIMARY KEY,
        black_player TEXT,
        white_player TEXT,
        winner INTEGER,
        moves TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # 创建玩家表
    cursor.execute('''CREATE TABLE IF NOT EXISTS players (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # 创建对局表
    cursor.execute('''CREATE TABLE IF NOT EXISTS game_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id TEXT,
        player1_id INTEGER,
        player2_id INTEGER,
        winner INTEGER,
        result TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (game_id) REFERENCES games(id)
    )''')
    
    conn.commit()
    conn.close()

# 在应用启动时初始化数据库
@app.on_event("startup")
async def on_startup():
    initialize_database()
    print("WebSocket server started on ws://localhost:8000/ws/game/{game_id}")