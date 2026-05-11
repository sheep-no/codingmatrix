from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base

class Game(Base):
    __tablename__ = 'games'

    id = Column(Integer, primary_key=True, index=True)
    player1_id = Column(String, nullable=True)
    player2_id = Column(String, nullable=True)
    board_size = Column(Integer, default=15)
    current_player = Column(Integer, default=1)  # 1 for black, 2 for white
    created_at = Column(DateTime, default=datetime.utcnow)
    moves = relationship("Move", back_populates="game", order_by="Move.id")
    winner_id = Column(Integer, nullable=True)

    def __repr__(self):
        return f"Game(id={self.id}, player1={self.player1_id}, player2={self.player2_id})"

class Move(Base):
    __tablename__ = 'moves'

    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey('games.id'))
    player_id = Column(String)
    row = Column(Integer)
    col = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

    game = relationship("Game", back_populates="moves")

    def __repr__(self):
        return f"Move(id={self.id}, game_id={self.game_id}, player={self.player_id}, position=({self.row},{self.col}))"