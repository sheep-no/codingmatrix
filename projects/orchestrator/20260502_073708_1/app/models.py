from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class Game(Base):
    __tablename__ = 'games'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    board_size = Column(Integer, default=15)
    created_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    winner = Column(String, nullable=True)
    
    # Relationships
    moves = relationship('Move', back_populates='game', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f"<Game(id={self.id}, board_size={self.board_size}, status={self.get_status()})>"
    
    def get_status(self):
        if self.ended_at:
            return "COMPLETED"
        return "IN_PROGRESS"

class Move(Base):
    __tablename__ = 'moves'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey('games.id'))
    player = Column(String, nullable=False)  # 'white' or 'black'
    row = Column(Integer, nullable=False)
    col = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    game = relationship('Game', back_populates='moves')
    
    def __repr__(self):
        return f"<Move(id={self.id}, game_id={self.game_id}, player={self.player}, position=({self.row},{self.col}))>"

class GameHistory(Base):
    __tablename__ = 'game_histories'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey('games.id'))
    player = Column(String, nullable=False)
    row = Column(Integer, nullable=False)
    col = Column(Integer, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    game = relationship('Game', back_populates='history')
    
    def __repr__(self):
        return f"<GameHistory(id={self.id}, game_id={self.game_id}, player={self.player}, position=({self.row},{self.col}))>"

class Player(Base):
    __tablename__ = 'players'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    color = Column(String, default='black')  # 'white' or 'black'
    
    def __repr__(self):
        return f"<Player(id={self.id}, name={self.name}, color={self.color})>"
    
    def toggle_color(self):
        if self.color == 'white':
            self.color = 'black'
        else:
            self.color = 'white'
        return self.color

class GameSettings(Base):
    __tablename__ = 'game_settings'
    
    id = Column(Integer, primary_key=True)
    board_size = Column(Integer, default=15)
    win_condition = Column(Integer, default=5)  # Number of consecutive stones to win
    
    def __repr__(self):
        return f"<GameSettings(id={self.id}, board_size={self.board_size}, win_condition={self.win_condition})>"