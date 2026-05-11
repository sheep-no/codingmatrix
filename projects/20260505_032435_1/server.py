from flask import Flask, render_template_string

app = Flask(__name__)

html_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>贪吃蛇游戏</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background-color: #2c3e50;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            color: white;
        }
        .game-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 20px;
        }
        h1 {
            margin: 0;
            color: #ecf0f1;
            font-size: 2.5em;
        }
        #gameCanvas {
            border: 5px solid #34495e;
            background-color: #222;
        }
        .score-panel {
            background-color: #34495e;
            padding: 15px 30px;
            border-radius: 10px;
            color: white;
            font-size: 1.2em;
        }
        .score-panel span {
            color: #2ecc71;
            font-weight: bold;
        }
        .controls button {
            padding: 10px 25px;
            font-size: 14px;
            cursor: pointer;
            background-color: #34495e;
            color: white;
            border: 2px solid #7f8c8d;
            border-radius: 5px;
            margin: 0 10px;
            transition: background-color 0.3s;
        }
        .controls button:hover {
            background-color: #2ecc71;
        }
        .instructions {
            background-color: #34495e;
            padding: 15px;
            border-radius: 10px;
            text-align: center;
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <div class="game-container">
        <h1>🐍 贪吃蛇游戏</h1>
        <canvas id="gameCanvas" width="400" height="400"></canvas>
        <div class="score-panel">分数：<span id="score">0</span></div>
        <div class="controls">
            <button onclick="startGame()">开始游戏</button>
            <button onclick="resetGame()">重新开始</button>
        </div>
        <div class="instructions">
            使用方向键↑↓←→控制蛇移动<br/>空格键暂停游戏
        </div>
    </div>

    <script>
        const canvas = document.getElementById('gameCanvas');
        const ctx = canvas.getContext('2d');
        const scoreElement = document.getElementById('score');

        const gridSize = 20;
        const tileCount = canvas.width / gridSize;

        let snake = [];
        let food = null;
        let dx = 0;
        let dy = 0;
        let score = 0;
        let gameInterval = null;
        let speed = 150;
        let gameRunning = false;
        let isPaused = false;

        function initGame() {
            snake = [
                {x: 10 * gridSize, y: 10 * gridSize},
                {x: 9 * gridSize, y: 10 * gridSize},
                {x: 8 * gridSize, y: 10 * gridSize}
            ];
            food = randomFood();
            score = 0;
            dx = gridSize;
            dy = 0;
            scoreElement.textContent = score;
            document.getElementById('scores').textContent = score;
        }

        function randomFood() {
            let newFood;
            while (true) {
                newFood = {
                    x: Math.floor(Math.random() * tileCount) * gridSize,
                    y: Math.floor(Math.random() * tileCount) * gridSize
                };
                if (!snake.some(segment => segment.x === newFood.x && segment.y === newFood.y)) {
                    return newFood;
                }
            }
        }

        function draw() {
            // 绘制背景
            ctx.fillStyle = '#222';
            ctx.fillRect(0, 0, canvas.width, canvas.height);

            // 绘制蛇
            snake.forEach((segment, index) => {
                if (index === 0) {
                    ctx.fillStyle = '#2ecc71'; // 头部绿色
                } else {
                    ctx.fillStyle = '#1e8449'; // 身体深绿色
                }
                ctx.fillRect(segment.x, segment.y, gridSize - 2, gridSize - 2);
            });

            // 绘制食物
            ctx.fillStyle = '#e74c3c';
            ctx.fillRect(food.x, food.y, gridSize - 2, gridSize - 2);
        }

        function moveSnake() {
            const head = {x: snake[0].x + dx, y: snake[0].y + dy};
            snake.unshift(head);
            
            // 检查是否吃到食物
            if (head.x === food.x && head.y === food.y) {
                score += 10;
                scoreElement.textContent = score;
                food = randomFood();
            } else {
                snake.pop();
            }

            // 碰撞检测
            if (head.y < 0 || head.y >= canvas.height ||
                head.x < 0 || head.x >= canvas.width ||
                snake.some(segment => segment.x === head.x && segment.y === head.y)) {
                gameOver();
            }
        }

        function gameOver() {
            snake.forEach(segment => ctx.fillStyle = '#e74c3c');
            alert(`游戏结束！你的得分是 ${score}`);
            gameRunning = false;
            clearInterval(gameInterval);
            document.getElementById('pause-btn').disabled = false;
        }

        function startGame() {
            if (gameRunning) {
                resetGame();
                return;
            }
            gameRunning = true;
            isPaused = false;
            initGame();
            if (gameInterval) clearInterval(gameInterval);
            gameInterval = setInterval(gameLoop, speed);
            draw();
        }

        function resetGame() {
            gameRunning = false;
            clearInterval(gameInterval);
            isPaused = false;
            gameInterval = null;
        }

        function gameLoop() {
            moveSnake();
            draw();
        }

        document.addEventListener('keydown', function(event) {
            if (event.key === 'ArrowUp' && dy === 0) {
                dx = 0; dy = -gridSize;
            } else if (event.key === 'ArrowDown' && dy === 0) {
                dx = 0; dy = gridSize;
            } else if (event.key === 'ArrowLeft' && dx === 0) {
                dx = -gridSize; dy = 0;
            } else if (event.key === 'ArrowRight' && dx === 0) {
                dx = gridSize; dy = 0;
            } else if (event.key === 'Escape' && gameRunning) {
                isPaused = !isPaused;
            }
        });

        // 初始绘制
        initGame();
        draw();
    </script>
</body>
</html>
"""

@app.route('/')
def snake_game():
    return render_template_string(html_template)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
``