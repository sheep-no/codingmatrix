from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from typing import List, Optional
from app.database import Base

class Player(Base):
    __tablename__ = 'players'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    win_count = Column(Integer, default=0)
    loss_count = Column(Integer, default=0)
    draw_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    games_as_first_player = relationship(
        "GomokuGame", 
        foreignkey="GomokuGame.first_player_id",
        back_populates="first_player"
    )
    
    games_as_second_player = relationship(
        "GomokuGame", 
        foreignkey="GomokuGame.second_player_id",
        back_populates="second_player"
    )
    
    def __repr__(self):
        return f"<Player {self.username}>"
    
    def get_stats(self):
        return {
            "wins": self.win_count,
            "losses": self.loss_count,
            "draws": self.draw_count,
            "win_rate": f"{self.win_count/(self.win_count+self.loss_count*2)*100:.1f}%"
        }

class GomokuGame(Base):
    __tablename__ = 'gomoku_games'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    first_player_id = Column(Integer, ForeignKey('players.id'))
    second_player_id = Column(Integer, ForeignKey('players.id'))
    game_board = Column(String(255))  # JSON string of board state
    game_status = Column(Integer, default=0)  # 0=ongoing, 1=first win, 2=second win, 3=draw
    created_at = Column(DateTime, default=datetime.utcnow)
    winner_id = Column(Integer, ForeignKey('players.id'), nullable=True)
    
    first_player = relationship("Player", foreignkey="GomokuGame.first_player_id")
    second_player = relationship("Player", foreignkey="GomokuGame.second_player_id")
    winner = relationship("Player", foreignkey="GomokuGame.winner_id")
    moves = relationship("Move", back_populates="game")
    
    def __repr__(self):
        return f"<Game {id} between {self.first_player.username} and {self.second_player.username}>"
    
    def get_winner(self):
        if self.game_status == 1:
            return self.first_player
        elif self.game_status == 2:
            return self.second_player
        return None
    
    def update_win_stats(self):
        if self.game_status == 1:
            self.first_player.win_count += 1
            self.second_player.loss_count += 1
        elif self.game_status == 2:
            self.first_player.loss_count += 1
            self.second_player.win_count += 1
        elif self.game_status == 3:
            self.first_player.draw_count += 1
            self.second_player.draw_count += 1
        self.first_player.save()
        self.second_player.save()
    
    def is_valid_move(self, row: int, col: int) -> bool:
        # Check if move is within board and position is empty
        if not (0 <= row < 15 and 0 <= col < 15):
            return False
        board = eval(self.game_board) if self.game_board else None
        if board is None or board[row][col] != '.':
            return False
        return True
    
    def make_move(self, row: int, col: int, player_id: int) -> bool:
        if self.is_valid_move(row, col):
            # Update board state
            board = eval(self.game_board) if self.game_board else [['.' for _ in range(15)] for _ in range(15)]
            board[row][col] = 'X' if player_id == self.first_player_id else 'O'
            self.game_board = str(board)
            
            # Check for win
            if self.check_win(row, col):
                self.game_status = 1 if player_id == self.first_player_id else 2
                self.winner_id = self.first_player_id if player_id == self.second_player_id else self.second_player_id
                self.update_win_stats()
            
            # Check for draw
            elif all(cell != '.' for row in board for cell in row):
                self.game_status = 3
            
            self.save()
            return True
        return False
    
    def check_win(self, row: int, col: int) -> bool:
        board = eval(self.game_board) if self.game_board else None
        if board is None:
            return False
            
        # Directions: horizontal, vertical, diagonal, anti-diagonal
        directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
        player = 'X' if self.first_player_id == self.winner_id else 'O'
        
        for dr, dc in directions:
            count = 1  # Current position
            
            # Check forward
            r, c = row + dr, col + dc
            while 0 <= r < 15 and 0 <= c < 15 and board[r][c] == player:
                count += 1
                r += dr
                c += dc
            
            # Check backward
            r, c = row - dr, col - dc
            while 0 <= r < 15 and 0 <= c < 15 and board[r][c] == player:
                count += 1
                r -= dr
                c -= dc
            
            if count >= 5:
                return True
        
        return False

class Move(Base):
    __tablename__ = 'moves'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey('gomoku_games.id'))
    player_id = Column(Integer, ForeignKey('players.id'))
    row = Column(Integer)
    col = Column(Integer)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    game = relationship("GomokuGame", back_populates="moves")
    player = relationship("Player")
    
    def __repr__(self):
        return f"<Move {id} at {row},{col} by {player.username}>"