from typing import Dict, List, Optional, Set
import uuid
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime
from enum import Enum
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 定义游戏状态枚举
class GameState(Enum):
    WAITING = "waiting"
    PLAYING = "playing"
    GAME_OVER = "game_over"

# 定义棋盘大小
BOARD_SIZE = 15

# 定义棋子类型
class PieceType(Enum):
    EMPTY = 0
    BLACK = 1
    WHITE = 2

class RoomManager:
    """房间管理服务类，负责匹配玩家、维护房间状态"""
    
    def __init__(self):
        """初始化房间管理器"""
        self.rooms: Dict[str, Dict] = {}  # 存储所有房间信息
        self.connected_players: Dict[str, str] = {}  # 存储已连接玩家的房间ID
        self.logger = logger
    
    def create_room(self) -> str:
        """创建一个新的房间"""
        room_id = str(uuid.uuid4())
        self.rooms[room_id] = {
            "room_id": room_id,
            "players": {},
            "board": [[PieceType.EMPTY.value for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)],
            "current_player": None,
            "game_state": GameState.WAITING.value,
            "winner": None,
            "history": []
        }
        self.logger.info(f"创建新房间: {room_id}")
        return room_id
    
    def join_room(self, room_id: str, player_id: str, piece_type: PieceType) -> bool:
        """玩家加入房间"""
        if room_id not in self.rooms:
            self.logger.warning(f"房间 {room_id} 不存在")
            return False
        
        if player_id in self.connected_players.values():
            self.logger.warning(f"玩家 {player_id} 已加入其他房间")
            return False
        
        room = self.rooms[room_id]
        
        # 检查房间是否已满
        if len(room["players"]) >= 2:
            self.logger.warning(f"房间 {room_id} 已满，无法加入")
            return False
        
        # 检查玩家是否已加入其他房间
        if player_id in room["players"]:
            self.logger.warning(f"玩家 {player_id} 已在房间 {room_id} 中")
            return False
        
        # 检查房间状态是否允许加入
        if room["game_state"] == GameState.GAME_OVER.value and len(room["players"]) < 2:
            # 游戏结束但玩家数不足，允许新玩家加入
            room["game_state"] = GameState.WAITING.value
        
        # 添加玩家到房间
        room["players"][player_id] = {
            "player_id": player_id,
            "piece_type": piece_type.value,
            "score": 0
        }
        
        # 设置当前玩家（黑棋先行）
        if not room["current_player"]:
            room["current_player"] = player_id if piece_type == PieceType.BLACK else player_id
        
        # 更新房间状态
        room["game_state"] = GameState.PLAYING.value if len(room["players"]) == 2 else GameState.WAITING.value
        
        # 记录玩家连接
        self.connected_players[player_id] = room_id
        
        self.logger.info(f"玩家 {player_id} 加入房间 {room_id}，棋子类型: {piece_type.name}")
        return True
    
    def leave_room(self, player_id: str) -> bool:
        """玩家离开房间"""
        for room_id, room in list(self.rooms.items()):
            if player_id in room["players"]:
                del room["players"][player_id]
                player_room = self.connected_players.get(player_id)
                if player_room == room_id:
                    del self.connected_players[player_id]
                
                # 检查房间是否空了
                if not room["players"]:
                    self.rooms[room_id]["game_state"] = GameState.WAITING.value
                    self.logger.info(f"房间 {room_id} 已空置")
                
                self.logger.info(f"玩家 {player_id} 离开房间 {room_id}")
                return True
        return False
    
    def make_move(self, room_id: str, player_id: str, row: int, col: int) -> bool:
        """玩家落子"""
        if room_id not in self.rooms:
            self.logger.warning(f"房间 {room_id} 不存在")
            return False
        
        if player_id not in self.connected_players:
            self.logger.warning(f"玩家 {player_id} 未连接")
            return False
        
        if self.connected_players[player_id] != room_id:
            self.logger.warning(f"玩家 {player_id} 不在房间 {room_id}")
            return False
        
        room = self.rooms[room_id]
        player_piece = next((p["piece_type"] for p in room["players"].values() if p["player_id"] == player_id), None)
        
        if player_piece is None:
            self.logger.warning(f"玩家 {player_id} 在房间 {room_id} 中没有棋子类型")
            return False
        
        # 检查是否是当前玩家回合
        if room["current_player"] != player_id:
            self.logger.warning(f"不是玩家 {player_id} 的回合")
            return False
        
        # 检查落子位置是否有效
        if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
            self.logger.warning(f"无效的落子位置: ({row}, {col})")
            return False
        
        if room["board"][row][col] != PieceType.EMPTY.value:
            self.logger.warning(f"位置 ({row}, {col}) 已被占用")
            return False
        
        # 落子
        room["board"][row][col] = player_piece
        player_data = next((p for p in room["players"].values() if p["player_id"] == player_id), None)
        player_data["score"] += 1
        
        # 记录历史
        room["history"].append({
            "player_id": player_id,
            "piece_type": player_piece,
            "position": {"row": row, "col": col},
            "timestamp": datetime.now().isoformat()
        })
        
        # 检查胜负
        winner = self.check_win(room, row, col, player_piece)
        if winner:
            self.logger.info(f"玩家 {player_id} 获胜！")
            room["winner"] = player_id
            room["game_state"] = GameState.GAME_OVER.value
            return True
        
        # 切换玩家
        players = list(room["players"].keys())
        current_index = players.index(player_id)
        next_index = (current_index + 1) % len(players)
        room["current_player"] = players[next_index]
        
        self.logger.info(f"玩家 {player_id} 在 ({row}, {col}) 落子，轮到 {room['current_player']} 的回合")
        return True
    
    def check_win(self, room: dict, row: int, col: int, piece_type: int) -> bool:
        """检查是否获胜"""
        directions = [
            [(0, 1), (0, -1)],  # 水平
            [(1, 0), (-1, 0)],  # 垂直
            [(1, 1), (-1, -1)],  # 对角线 /
            [(1, -1), (-1, 1)]   # 对角线 \
        ]
        
        for direction_pair in directions:
            count = 1  # 当前位置已经有一个棋子
            
            # 检查两个相反方向
            for dx, dy in direction_pair:
                r, c = row, col
                while True:
                    r, c = r + dx, c + dy
                    if (0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE and 
                        room["board"][r][c] == piece_type):
                        count += 1
                    else:
                        break
            
            if count >= 5:
                return True
        
        return False
    
    def get_room_info(self, room_id: str) -> Optional[dict]:
        """获取房间信息"""
        if room_id not in self.rooms:
            return None
        
        room = self.rooms[room_id]
        return {
            "room_id": room_id,
            "players": {player_id: {"piece_type": room["players"][player_id]["piece_type"]} for player_id in room["players"]},
            "current_player": room["current_player"],
            "game_state": room["game_state"],
            "winner": room["winner"]
        }
    
    def get_player_room(self, player_id: str) -> Optional[str]:
        """获取玩家所在的房间"""
        return self.connected_players.get(player_id)
    
    def broadcast_move(self, room_id: str, player_id: str, row: int, col: int) -> None:
        """广播落子信息给房间内的其他玩家"""
        room = self.rooms[room_id]
        opponent_id = next(iter(set(room["players"].keys()) - {player_id}), None)
        
        if opponent_id and opponent_id in self.connected_players:
            # 通过WebSocket发送消息通知对手
            # 注意：实际实现需要WebSocket连接
            self.logger.info(f"向玩家 {opponent_id} 广播落子信息")
            # 这里应该发送WebSocket消息
    
    def broadcast_game_over(self, room_id: str, winner_id: str) -> None:
        """广播游戏结束信息"""
        room = self.rooms[room_id]
        self.logger.info(f"游戏结束，获胜者: {winner_id}")
        
        # 通知所有玩家游戏结束
        for player_id in room["players"]:
            # 这里应该发送WebSocket消息
            self.logger.info(f"向玩家 {player_id} 广播游戏结束")
            # 实际实现需要WebSocket连接
    
    def on_disconnect(self, player_id: str) -> None:
        """处理玩家断开连接"""
        self.leave_room(player_id)
        room_id = self.get_player_room(player_id)
        if room_id:
            # 检查房间是否空了
            if not self.rooms[room_id]["players"]:
                self.rooms[room_id]["game_state"] = GameState.WAITING.value
                self.logger.info(f"房间 {room_id} 因玩家断开而空置")
            else:
                # 如果还有玩家，将当前玩家设为断开玩家的对手
                players = list(self.rooms[room_id]["players"].keys())
                disconnected_index = players.index(player_id)
                next_index = (disconnected_index + 1) % len(players)
                self.rooms[room_id]["current_player"] = players[next_index]
                self.logger.info(f"房间 {room_id} 中玩家 {player_id} 断开，轮到 {self.rooms[room_id]['current_player']} 的回合")