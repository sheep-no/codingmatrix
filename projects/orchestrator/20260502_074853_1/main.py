import asyncio
from datetime import datetime
from typing import Optional, Dict, List, Set
import random

class GomokuGame:
    def __init__(self, game_id: str):
        self.id = game_id
        self.board = [[None for _ in range(15)] for _ in range(15)]
        self.current_player = 1
        self.game_over = False
        self.winner = None
        self.history = []  # Store move history
        self.start_time = datetime.now()
        self.end_time = None
        self.player1_name = "Player 1"
        self.player2_name = "Player 2"

    def make_move(self, row: int, col: int) -> bool:
        """Make a move on the board if valid"""
        if self.game_over or row < 0 or row >= 15 or col < 0 or col >= 15:
            return False
            
        if self.board[row][col] is not None:
            return False
            
        # Record the move
        self.board[row][col] = self.current_player
        self.history.append((row, col, self.current_player))
        
        # Check for win
        if self.check_win(row, col):
            self.game_over = True
            self.winner = self.current_player
            self.end_time = datetime.now()
            return True
            
        # Check for draw
        if self.is_board_full():
            self.game_over = True
            self.winner = None
            self.end_time = datetime.now()
            return True
            
        # Switch player
        self.current_player = 3 - self.current_player  # 1->2, 2->1
        return True

    def check_win(self, row: int, col: int) -> bool:
        """Check if the last move resulted in a win"""
        player = self.board[row][col]
        if not player:
            return False
            
        # Check horizontal
        if self.count_line(row, col, 0, 1) >= 4:
            return True
            
        # Check vertical
        if self.count_line(row, col, 1, 0) >= 4:
            return True
            
        # Check diagonal (top-left to bottom-right)
        if self.count_line(row, col, 1, 1) >= 4:
            return True
            
        # Check diagonal (top-right to bottom-left)
        if self.count_line(row, col, 1, -1) >= 4:
            return True
            
        return False

    def count_line(self, row: int, col: int, delta_row: int, delta_col: int) -> int:
        """Count consecutive pieces in a line in all four directions"""
        player = self.board[row][col]
        if not player:
            return 0
            
        count = 1  # Starting with the current cell
        
        # Positive direction
        r, c = row + delta_row, col + delta_col
        while 0 <= r < 15 and 0 <= c < 15 and self.board[r][c] == player:
            count += 1
            r += delta_row
            c += delta_col
            
        # Negative direction
        r, c = row - delta_row, col - delta_col
        while 0 <= r < 15 and 0 <= c < 15 and self.board[r][c] == player:
            count += 1
            r -= delta_row
            c -= delta_col
            
        return count

    def is_board_full(self) -> bool:
        """Check if the board is completely filled"""
        for row in self.board:
            for cell in row:
                if cell is None:
                    return False
        return True

    def get_board_state(self) -> Dict:
        """Return the current state of the game"""
        return {
            "id": self.id,
            "currentPlayer": self.current_player,
            "gameOver": self.game_over,
            "winner": self.winner,
            "board": self.board,
            "history": self.history,
            "startTime": self.start_time.isoformat() if self.start_time else None,
            "endTime": self.end_time.isoformat() if self.end_time else None
        }

    def reset_game(self):
        """Reset the game state"""
        self.board = [[None for _ in range(15)] for _ in range(15)]
        self.current_player = 1
        self.game_over = False
        self.winner = None
        self.history = []
        self.start_time = datetime.now()
        self.end_time = None

# Game manager to track all active games
class GameManager:
    def __init__(self):
        self.games: Dict[str, GomokuGame] = {}
        self.next_game_id = 1

    def create_game(self) -> str:
        """Create a new game and return its ID"""
        game_id = f"game_{self.next_game_id}"
        self.games[game_id] = GomokuGame(game_id)
        self.next_game_id += 1
        return game_id

    def get_game(self, game_id: str) -> Optional[GomokuGame]:
        """Get a game by its ID"""
        return self.games.get(game_id)

    def remove_game(self, game_id: str) -> bool:
        """Remove a game"""
        if game_id in self.games:
            del self.games[game_id]
            return True
        return False

    def list_games(self) -> List[str]:
        """List all active game IDs"""
        return list(self.games.keys())

# Create a game manager instance
game_manager = GameManager()

# Example usage (would typically be in an async task or similar)
async def example_usage():
    # Create a new game
    game_id = game_manager.create_game()
    print(f"Created game: {game_id}")
    
    # Make some moves
    game = game_manager.get_game(game_id)
    if game:
        # Player 1's turn
        game.make_move(7, 7)
        game.make_move(7, 8)
        
        # Player 2's turn
        game.make_move(6, 7)
        game.make_move(8, 7)
        
        # Print board state
        print("Board state after moves:")
        for row in game.board:
            print(row)
            
        # Get game state
        game_state = game.get_board_state()
        print("\nGame state:")
        print(game_state)
        
        # Check if game is over
        print(f"\nGame over: {game.game_over}, Winner: {game.winner}")
        
        # Reset the game
        game.reset_game()
        print("\nGame reset")
        print(game.get_board_state())

# Run the example
if __name__ == "__main__":
    asyncio.run(example_usage())