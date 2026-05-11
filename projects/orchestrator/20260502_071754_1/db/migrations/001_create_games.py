# db/migrations/001_create_games.py
import sqlite3
import os
from datetime import datetime

def create_games_table():
    """Create the games table in the database"""
    try:
        conn = sqlite3.connect('chess_game.db')
        cursor = conn.cursor()
        
        # Create games table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                board_state TEXT NOT NULL,
                current_player TEXT NOT NULL,
                game_status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create game moves table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS game_moves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL,
                player TEXT NOT NULL,
                position TEXT NOT NULL,
                move_number INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (game_id) REFERENCES games (id)
            )
        ''')
        
        # Create game history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS game_histories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL,
                winner TEXT NOT NULL,
                result TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (game_id) REFERENCES games (id)
            )
        ''')
        
        conn.commit()
        conn.close()
        print(f"Database migration completed successfully at {datetime.now()}")
        return True
    except sqlite3.Error as e:
        print(f"Database migration error: {str(e)}")
        return False
    except Exception as e:
        print(f"Unexpected error during migration: {str(e)}")
        return False

if __name__ == "__main__":
    create_games_table()