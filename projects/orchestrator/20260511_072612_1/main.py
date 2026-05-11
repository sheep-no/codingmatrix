# main.py
import pygame
import sys
from game_logic.chess_board import ChessBoard
from game_logic.player import HumanPlayer, AIPlayer
from game_logic.game_engine import GameEngine
from pygame.locals import *

# 初始化Pygame
pygame.init()

# 屏幕设置
SCREEN_WIDTH = 600
SCREEN_HEIGHT = 600
CELL_SIZE = 600 // 15  # 15x15棋盘
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (128, 128, 128)
RED = (255, 0, 0)
BLUE = (0, 0, 255)

# 创建窗口
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("五子棋小游戏")

# 加载字体
font = pygame.font.Font(None, 36)

def draw_board(board):
    """绘制棋盘"""
    screen.fill(WHITE)
    for row in range(15):
        for col in range(15):
            x = col * CELL_SIZE
            y = row * CELL_SIZE
            if board[row][col] == 'B':
                pygame.draw.circle(screen, BLACK, (x + CELL_SIZE//2, y + CELL_SIZE//2), CELL_SIZE//2 - 2)
            elif board[row][col] == 'W':
                pygame.draw.circle(screen, WHITE, (x + CELL_SIZE//2, y + CELL_SIZE//2), CELL_SIZE//2 - 2)
            pygame.draw.rect(screen, GRAY, (x, y, CELL_SIZE, CELL_SIZE), 1)

def draw_status(text):
    """绘制状态信息"""
    status_text = font.render(text, True, BLACK)
    screen.blit(status_text, (10, SCREEN_HEIGHT - 40))

def main():
    # 创建棋盘
    board = ChessBoard()
    
    # 初始化玩家（人类玩家和AI玩家）
    players = [
        HumanPlayer("玩家", 'B'),
        AIPlayer("AI", 'W')
    ]
    
    # 创建游戏引擎
    game_engine = GameEngine(board, players)
    
    # 游戏主循环
    clock = pygame.time.Clock()
    current_player = 0  # 当前玩家索引
    game_over = False
    
    while not game_over:
        for event in pygame.event.get():
            if event.type == QUIT:
                pygame.quit()
                sys.exit()
            
            if event.type == MOUSEBUTTONDOWN and not game_over:
                # 处理玩家落子
                col = event.pos[0] // CELL_SIZE
                row = event.pos[1] // CELL_SIZE
                
                # 检查坐标有效性
                if 0 <= row < 15 and 0 <= col < 15:
                    try:
                        # 执行落子操作
                        game_engine.make_move(row, col)
                        
                        # 检查胜负
                        if game_engine.check_win(row, col):
                            winner = players[game_engine.current_player].name
                            draw_status(f"恭喜 {winner} 获胜！")
                            game_over = True
                            pygame.time.wait(3000)  # 显示3秒
                            break
                        
                        # 切换玩家
                        current_player = 1 - current_player
                        
                        # 如果AI回合，自动落子
                        if current_player == 1:
                            ai_move = game_engine.get_ai_move()
                            if ai_move:
                                game_engine.make_move(ai_move[0], ai_move[1])
                                if game_engine.check_win(ai_move[0], ai_move[1]):
                                    winner = players[1].name
                                    draw_status(f"恭喜 {winner} 获胜！")
                                    game_over = True
                                    pygame.time.wait(3000)
                                    break
                    except Exception as e:
                        # 错误处理
                        draw_status(f"错误：{str(e)}")
                        pygame.time.wait(2000)
                        continue
        
        # 渲染棋盘
        draw_board(board.board)
        draw_status(f"当前玩家：{players[current_player].name}")
        pygame.display.update()
        clock.tick(30)  # 限制帧率

if __name__ == "__main__":
    main()