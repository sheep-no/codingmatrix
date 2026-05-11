from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, List, Optional, Tuple
import uuid
import json
import sqlite3
from datetime import datetime
from enum import Enum
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 配置CORS
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 数据库初始化
def init_database():
    conn = sqlite3.connect('gobang.db')
    cursor = conn.cursor()
    
    # 创建房间表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS rooms (
        room_id TEXT PRIMARY KEY,
        max_players INTEGER DEFAULT 2,
        player1_id TEXT,
        player2_id TEXT,
        current_player TEXT,
        board_state TEXT,
        game_state TEXT DEFAULT 'active',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # 创建游戏记录表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS game_records (
        record_id TEXT PRIMARY KEY,
        room_id TEXT,
        move TEXT,
        player_id TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # 创建用户表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        is_bot BOOLEAN DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    conn.commit()
    conn.close()

# 初始化数据库
init_database()

# 房间管理状态
class RoomState(Enum):
    WAITING = "waiting"
    ACTIVE = "active"
    CLOSED = "closed"
    GAME_OVER = "game_over"

# 棋盘大小
BOARD_SIZE = 15

# 棋子类型
class PieceType(Enum):
    EMPTY = 0
    BLACK = 1
    WHITE = 2

# 方向
DIRECTIONS = [
    (1, 0),   # 水平
    (0, 1),   # 垂直
    (1, 1),   # 右下
    (1, -1)   # 左下
]

# 存储活动房间
active_rooms: Dict[str, Dict] = {}
# 存储房间连接
room_connections: Dict[str, List[WebSocket]] = {}

# 胜利方向计数
def count_directions(board: List[List], row: int, col: int, piece: int, direction: Tuple[int, int]) -> int:
    count = 1
    r, c = row, col
    
    # 向一个方向计数
    while True:
        r += direction[0]
        c += direction[1]
        if (0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and 
            board[r][c] == piece):
            count += 1
        else:
            break
            
    return count

# 检查是否获胜
def check_win(board: List[List], row: int, col: int, piece: int) -> bool:
    for direction in DIRECTIONS:
        if count_directions(board, row, col, piece, direction) >= 5:
            return True
    return False

# 创建新房间
async def create_room() -> str:
    room_id = str(uuid.uuid4())
    # 初始化空棋盘
    board_state = json.dumps([[PieceType.EMPTY.value for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)])
    active_rooms[room_id] = {
        "room_id": room_id,
        "max_players": 2,
        "player1_id": None,
        "player2_id": None,
        "current_player": None,
        "board_state": board_state,
        "game_state": RoomState.WAITING.value,
        "created_at": datetime.now().isoformat()
    }
    return room_id

# 加入房间
def join_room(room_id: str, user_id: str) -> dict:
    if room_id not in active_rooms:
        raise HTTPException(status_code=404, detail="Room not found")
    
    room = active_rooms[room_id]
    
    if room["game_state"] != RoomState.WAITING.value:
        raise HTTPException(status_code=400, detail="Room is not in waiting state")
        
    if room["player1_id"] is None:
        room["player1_id"] = user_id
        room["current_player"] = "player1"
    elif room["player2_id"] is None:
        room["player2_id"] = user_id
        room["current_player"] = "player2"
    else:
        raise HTTPException(status_code=400, detail="Room is full")
        
    # 更新房间状态
    active_rooms[room_id] = room
    
    # 创建用户记录（如果不存在）
    conn = sqlite3.connect('gobang.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, is_bot) VALUES (?, ?)", (user_id, False))
    conn.commit()
    conn.close()
    
    return {
        "room_id": room_id,
        "user_id": user_id,
        "player_id": "player1" if room["player1_id"] == user_id else "player2",
        "players": {
            "player1": room["player1_id"],
            "player2": room["player2_id"]
        }
    }

# 发送消息到房间
async def send_message_to_room(room_id: str, message: dict) -> None:
    if room_id in room_connections:
        for connection in room_connections[room_id]:
            await connection.send_json(message)

# 处理落子
def make_move(room_id: str, user_id: str, row: int, col: int) -> dict:
    if room_id not in active_rooms:
        raise HTTPAPIException(status_code=404, detail="Room not found")
    
    room = active_rooms[room_id]
    
    if room["game_state"] != RoomState.ACTIVE.value:
        raise HTTPAPIException(status_code=400, detail="Game not active")
        
    # 检查玩家是否是当前玩家
    current_player_id = "player1" if room["current_player"] == "player1" else "player2"
    if user_id != room["player1_id"] and user_id != room["player2_id"]:
        raise HTTPAPIException(status_code=403, detail="Not a player in this room")
    if user_id != current_player_id:
        raise HTTPAPIException(status_code=403, detail="Not your turn")
        
    # 检查位置是否有效
    board = json.loads(room["board_state"])
    if board[row][col] != PieceType.EMPTY.value:
        raise HTTPAPIException(status_code=400, detail="Invalid position")
        
    # 更新棋盘状态
    board[row][col] = 1 if user_id == room["player1_id"] else 2
    new_board_state = json.dumps(board)
    
    # 检查是否获胜
    if check_win(board, row, col, 1 if user_id == room["player1_id"] else 2):
        # 记录游戏结束
        record_id = str(uuid.uuid4())
        conn = sqlite3.connect('gobang.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO game_records (record_id, room_id, move, player_id) VALUES (?, ?, ?, ?)",
                      (record_id, room_id, json.dumps({"row": row, "col": col}), user_id))
        cursor.execute("INSERT INTO game_records (record_id, room_id, move, player_id) VALUES (?, ?, ?, ?)",
                      (str(uuid.uuid4()), room_id, "game_over", "system"))
        conn.commit()
        conn.close()
        
        # 更新房间状态
        room["game_state"] = RoomState.GAME_OVER.value
        winner = "player1" if user_id == room["player1_id"] else "player2"
        active_rooms[room_id] = room
        
        # 发送游戏结束消息
        await send_message_to_room(room_id, {
            "type": "game_over",
            "winner": winner,
            "board": board
        })
        
        return {
            "message": "Game over - win!",
            "board": board,
            "winner": winner
        }
    
    # 切换玩家
    room["current_player"] = "player2" if room["current_player"] == "player1" else "player1"
    new_board_state = json.dumps(board)
    room["board_state"] = new_board_state
    
    # 更新房间状态
    active_rooms[room_id] = room
    
    # 记录移动
    record_id = str(uuid.uuid4())
    conn = sqlite3.connect('gobang.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO game_records (record_id, room_id, move, player_id) VALUES (?, ?, ?, ?)",
                  (record_id, room_id, json.dumps({"row": row, "col": col}), user_id))
    conn.commit()
    conn.close()
    
    return {
        "message": "Move successful",
        "board": board,
        "current_player": room["current_player"]
    }

# 房间管理器WebSocket连接
@app.websocket("/room/{room_id}/ws")
async def room_manager(websocket: WebSocket, room_id: str):
    await websocket.accept()
    
    if room_id not in active_rooms:
        await websocket.close(code=4001, reason="Invalid room ID")
        return
        
    if room_id not in room_connections:
        room_connections[room_id] = []
        
    room_connections[room_id].append(websocket)
    
    # 发送房间状态
    await send_message_to_room(room_id, {
        "type": "room_state",
        "room": active_rooms[room_id],
        "board": json.loads(active_rooms[room_id]["board_state"])
    })
    
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "join":
                # 处理加入房间
                user_id = data.get("user_id")
                try:
                    join_result = join_room(room_id, user_id)
                    await send_message_to_room(room_id, {
                        "type": "join_success",
                        "player_id": join_result["player_id"],
                        "players": join_result["players"],
                        "room": active_rooms[room_id]
                    })
                except HTTPException as e:
                    await send_message_to_room(room_id, {
                        "type": "error",
                        "message": str(e.detail)
                    })
                    
            elif data.get("type") == "move":
                # 处理落子
                try:
                    row = data.get("row")
                    col = data.get("col")
                    move_result = make_move(room_id, user_id, row, col)
                    await send_message_to_room(room_id, {
                        "type": "move",
                        "board": move_result["board"],
                        "current_player": move_result["current_player"]
                    })
                except HTTPException as e:
                    await send_message_to_room(room_id, {
                        "type": "error",
                        "message": str(e.detail)
                    })
                    
            elif data.get("type") == "leave":
                # 处理离开房间
                room_connections[room_id].remove(websocket)
                if not room_connections[room_id]:
                    del room_connections[room_id]
                    
                # 更新房间状态
                room = active_rooms[room_id]
                if room["player1_id"] == user_id or room["player2_id"] == user_id:
                    if room["game_state"] == RoomState.ACTIVE.value:
                        # 切换到等待状态
                        room["game_state"] = RoomState.WAITING.value
                        room["current_player"] = None
                        active_rooms[room_id] = room
                        
                        # 通知所有连接的客户端
                        await send_message_to_room(room_id, {
                            "type": "room_state",
                            "room": room,
                            "board": json.loads(room["board_state"])
                        })
                    break
                    
    except WebSocketDisconnect as e:
        logger.info(f"Client disconnected from room {room_id}: {e}")
        if room_id in room_connections:
            if websocket in room_connections[room_id]:
                room_connections[room_id].remove(websocket)
                if not room_connections[room_id]:
                    del room_connections[room_id]
                    
                # 更新房间状态
                room = active_rooms[room_id]
                if room["player1_id"] == user_id or room["player2_id"] == user_id:
                    if room["game_state"] == RoomState.ACTIVE.value:
                        # 切换到等待状态
                        room["game_state"] = RoomState.WAITING.value
                        room["current_player"] = None
                        active_rooms[room_id] = room
                        
                        # 通知所有连接的客户端
                        await send_message_to_room(room_id, {
                            "type": "room_state",
                            "room": room,
                            "board": json.loads(room["board_state"])
                        })
    except Exception as e:
        logger.error(f"Error in room {room_id}: {str(e)}")
        if room_id in room_connections and websocket in room_connections[room_id]:
            room_connections[room_id].remove(websocket)
            if not room_connections[room_id]:
                del room_connections[room_id]
                
            # 更新房间状态
            room = active_rooms[room_id]
            if room["player1_id"] == user_id or room["player2_id"] == user_id:
                if room["game_state"] == RoomState.ACTIVE.value:
                    # 切换到等待状态
                    room["game_state"] = RoomState.WAITING.value
                    room["current_player"] = None
                    active_rooms[room_id] = room
                    
                    # 通知所有连接的客户端
                    await send_message_to_room(room_id, {
                        "type": "room_state",
                        "room": room,
                        "board": json.loads(room["board_state"])
                    })
                    
    finally:
        if room_id in room_connections and websocket in room_connections[room_id]:
            room_connections[room_id].remove(websocket)
            if not room_connections[room_id]:
                del room_connections[room_id]
                
            # 更新房间状态
            room = active_rooms[room_id]
            if room["player1_id"] == user_id or room["player2_id"] == user_id:
                if room["game_state"] == RoomState.ACTIVE.value:
                    # 切换到等待状态
                    room["game_state"] = RoomState.WAITING.value
                    room["current_player"] = None
                    active_rooms[room_id] = room
                    
                    # 通知所有连接的客户端
                    await send_message_to_room(room_id, {
                        "type": "room_state",
                        "room": room,
                        "board": json.loads(room["board_state"])
                    })