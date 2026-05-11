from sqlalchemy import Column, Integer, String, ForeignKey, ARRAY, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
import enum
import datetime
import typing

Base = declarative_base()

class GameStatus(enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

class Player(Base):
    __tablename__ = "players"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    draws = Column(Integer, default=0)
    
    games_as_white = relationship("Game", foreign_keys="[Game.white_player_id]")
    games_as_black = relationship("Game", foreign_keys="[Game.black_player_id]")
    
    def __repr__(self):
        return f"<Player(id={self.id}, username='{self.username}')>"

class Game(Base):
    __tablename__ = "games"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    white_player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    black_player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    board_state = Column(ARRAY(Integer), default=[])  # Stores the current board state as a list of coordinates
    current_player = Column(Integer, default=1)  # 1 for black, 2 for white
    game_status = Column(String, default=GameStatus.IN_PROGRESS.value)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # Relationship to players
    white_player = relationship("Player", foreign_keys=[white_player_id])
    black_player = relationship("Player", foreign_keys=[black_player_id])
    
    # Relationship to game moves
    moves = relationship("GameMove", back_populates="game")
    
    def __repr__(self):
        return f"<Game(id={self.id}, white={self.white_player.username}, black={self.black_player.username}, status={self.game_status})>"
    
    def make_move(self, player_id: int, row: int, col: int) -> bool:
        """Make a move on the board and check for win condition"""
        # Validate player
        if player_id not in [self.white_player_id, self.black_player_id]:
            return False
        
        # Validate current player
        if (player_id == self.white_player_id and self.current_player != 2) or \
           (player_id == self.black_player_id and self.current_player != 1):
            return False
        
        # Validate move (within board and empty)
        if row < 0 or row >= 15 or col < 0 or col >= 15:
            return False
        
        # Check if position is already occupied
        if (row, col) in self.board_state:
            return False
        
        # Add move to board state
        self.board_state.append((row, col))
        
        # Update current player
        self.current_player = 3 - self.current_player  # Toggle between 1 and 2
        
        # Check for win condition
        if self.check_win(row, col):
            self.game_status = GameStatus.COMPLETED.value
            winner_id = self.white_player_id if self.current_player == 1 else self.black_player_id
            self.update_player_stats(winner_id)
        
        self.updated_at = datetime.datetime.utcnow()
        return True
    
    def check_win(self, row: int, col: int) -> bool:
        """Check if the last move resulted in a win"""
        player_piece = 1 if (self.white_player_id == self.current_player) else 2
        
        # Check horizontal
        if self.count_consecutive(row, col, 0, 1, player_piece, 4):
            return True
        
        # Check vertical
        if self.count_consecutive(row, col, 1, 0, player_piece, 4):
            return True
        
        # Check diagonal (top-left to bottom-right)
        if self.count_consecutive(row, col, -1, -1, player_piece, 4):
            return True
        
        # Check diagonal (top-right to bottom-left)
        if self.count_consecutive(row, col, -1, 1, player_piece, 4):
            return True
        
        return False
    
    def count_consecutive(self, row: int, col: int, delta_row: int, delta_col: int, player_piece: int, count: int) -> bool:
        """Count consecutive pieces in a given direction"""
        total = 1  # The move itself
        
        # Count in positive direction
        r, c = row + delta_row, col + delta_col
        while 0 <= r < 15 and 0 <= c < 15 and (r, c) in self.board_state and self.get_piece(r, c) == player_piece:
            total += 1
            r += delta_row
            c += delta_col
        
        # Count in negative direction
        r, c = row - delta_row, col - delta_col
        while 0 <= r < 15 and 0 <= c < 15 and (r, c) in self.board_state and self.get_piece(r, c) == player_piece:
            total += 1
            r -= delta_row
            c -= delta_col
        
        return total >= count
    
    def get_piece(self, row: int, col: int) -> int:
        """Get the piece value at a given position"""
        if (row, col) in self.board_state:
            return 1 if self.board_state[(row, col)] == (row, col) else 2
        return 0
    
    def update_player_stats(self, winner_id: int):
        """Update player statistics when a game is completed"""
        winner = Player.query.get(winner_id)
        loser = self.white_player if self.white_player_id != winner_id else self.black_player
        
        # Update winner stats
        winner.wins += 1
        winner.draws += 0
        
        # Update loser stats
        if self.white_player_id != winner_id and self.black_player_id != winner_id:
            # This should never happen in a normal game
            return
        
        # If it's a win for the winner, update loser's loss
        if self.white_player_id != winner_id:
            # Black won
            self.white_player.losses += 1
        else:
            # White won
            self.black_player.losses += 1
        
        # Save changes
        winner.save()
        self.white_player.save() if self.white_player_id != winner_id else self.black_player.save()

class GameMove(Base):
    __tablename__ = "game_moves"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    row = Column(Integer, nullable=False)
    col = Column(Integer, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationship to game and player
    game = relationship("Game", back_populates="moves")
    player = relationship("Player")
    
    def __repr__(self):
        return f"<GameMove(id={self.id}, game_id={self.game_id}, player_id={self.player_id}, row={self.row}, col={self.col})>"

class GameHistory(Base):
    __tablename__ = "game_histories"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey("games.id"), nullable=False)
    winner_id = Column(Integer, ForeignKey("players.id"), nullable=True)  # Only present if game completed
    board_state = Column(ARRAY(Integer), default=[])  # Final board state
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Relationship to game
    game = relationship("Game")
    
    def __repr__(self):
        return f"<GameHistory(id={self.id}, game_id={self.game_id}, winner_id={self.winner_id})>"

def init_db():
    """Initialize the database with required tables"""
    from sqlalchemy import create_engine
    from sqlalchemy_utils import create_database, database_exists
    
    # Create engine and connect to SQLite database
    engine = create_engine('sqlite:///chess.db')
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    # Verify database exists (SQLite)
    if not database_exists(engine.url):
        create_database(engine.url)
    
    print("Database initialized successfully")
    return engine

# Note: In a real application, you would use a dependency system to handle database connections
# This is just a conceptual implementation for demonstration purposes