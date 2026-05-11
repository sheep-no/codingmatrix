# projects/orchestrator/20260507_023146_1/main.py
from fastapi import FastAPI, HTTPException, Query
from typing import Dict, List, Optional
from board import Board
from game_manager import GameManager

app = FastAPI()

# 保存当前游戏实例，用于多请求之间的状态保持
current_game: Optional[GameManager] = None

@app.post("/api/v1/game")
async def create_game(size: int = Query(..., description="棋盘大小", required=True)) -> Dict[str, List[List[str]]]:
    """
    创建新游戏
    
    参数:
        size (int): 棋盘大小，必须大于等于5
        
    返回:
        board (List[List[str]]): 初始化后的棋盘状态
    """
    if size < 5:
        raise HTTPException(status_code=400, detail="棋盘大小至少为5")
    
    # 初始化游戏管理器，创建新的棋盘
    global current_game
    current_game = GameManager(size)
    
    # 返回当前棋盘状态
    return {"board": current_game.board.board}

@app.put("/api/v1/game")
async def make_move(x: int = Query(..., description="x坐标", required=True), 
                   y: int = Query(..., description="y坐标", required=True)) -> Dict[str, str]:
    """
    下棋操作
    
    参数:
        x (int): x坐标
        y (int): y坐标
        
    返回:
        status (str): 操作状态（success/error）
        winner (str): 获胜玩家（若存在）
        board (List[List[str]]): 更新后的棋盘状态
    """
    if current_game is None:
        raise HTTPException(status_code=404, detail="游戏未创建")
    
    # 调用游戏管理器进行落子操作
    result = current_game.make_move(x, y)
    
    # 如果操作失败，抛出HTTP异常
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    
    # 返回更新后的游戏状态
    return {
        "status": result["status"],
        "winner": result["winner"],
        "board": current_game.board.board
    }

@app.get("/api/v1/game")
async def get_game_status() -> Dict[str, List[List[str]]]:
    """
    获取当前游戏状态
    
    返回:
        board (List[List[str]]): 当前棋盘状态
    """
    if current_game is None:
        raise HTTPException(status_code=404, detail="游戏未创建")
    
    # 返回当前棋盘状态
    return {"board": current_game.board.board}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)