const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const CELL_SIZE = 20;
const CELL_COUNT = canvas.width / CELL_SIZE;
let snake = [x, y] = [], x = 5, y = 0;
let food = [x, y] = [], x = Math.floor(Math.random() * CELL_COUNT), y = Math.floor(Math.random() * CELL_COUNT);
let dx = 1, dy = 0;
let gameInterval = null;

function drawSnake() {
    ctx.fillStyle = 'green';
    for (let i = 0; i < snake.length; i++) {
        ctx.fillRect(snake[x][i] * CELL_SIZE, snake[y][i] * CELL_SIZE, CELL_SIZE - 1, CELL_SIZE - 1);
    }
}

function drawFood() {
    ctx.fillStyle = 'red';
    ctx.fillRect(food.x * CELL_SIZE, food.y * CELL_SIZE, CELL_SIZE - 1, CELL_SIZE - 1);
}

function score() {
    ctx.fillStyle = 'black';
    ctx.font = '20px Arial';
    ctx.fillText('得分: ' + score.value, 10, 30);
    ctx.fillText('最高分: ' + highScore.value, 10, 50);
}

function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    drawSnake();
    drawFood();
    drawGameInfo();
}

function drawGameInfo() {
    ctx.fillStyle = 'black';
    ctx.font = '20px Arial';
    ctx.fillText('得分: ' + score.value, 10, 30);
    ctx.fillText('最高分: ' + highScore.value, 10, 50);
}

function gameTick() {
    if (dx === 0 && dy === 0) return;
    let newHead = { x: x, y: y, x: snake[x] + dx * CELL_SIZE, y: snake[y] + dy * CELL_SIZE };
    snake.unshift(newHead[0], newHead[1]);
    snake.pop();
    if (newHead.x === food.x && newHead.y === food.y) {
        food.x = Math.floor(Math.random() * CELL_COUNT);
        food.y = Math.floor(Math.random() * CELL_COUNT);
        score.value++;
    }
    if (newHead.x < 0 || newHead.x >= CELL_COUNT || newHead.y < 0 || newHead.y >= CELL_COUNT || snake.some(s => s.x === newHead.x && s.y === newHead.y)) {
        clearInterval(gameInterval);
        gameInterval = null;
        requestAnimationFrame(draw); // 重新绘制游戏
    }
    requestAnimationFrame(draw);
}

function startGame() {
    document.getElementById('score').innerText = score.value;
    document.getElementById('high-score').innerText = highScore.value;
    gameInterval = setInterval(gameTick, 100);
}

function pauseGame() {
    clearInterval(gameInterval);
    gameInterval = null;
    document.getElementById('start-btn').innerText = '继续游戏';
}

function restartGame() {
    snake = [{ x: 5, y: 0 }];
    food.x = Math.floor(Math.random() * CELL_COUNT);
    food.y = Math.floor(Math.random() * CELL_COUNT);
    dx = 1; dy = 0;
    score.value = 0;
    highScore.value = 0;
    document.getElementById('score').innerText = score.value;
    document.getElementById('high-score').innerText = highScore.value;
    gameInterval = setInterval(gameTick, 100);
}

window.addEventListener('keydown', (event) => {
    switch (event.key) {
        case 'ArrowUp':
        case 'w':
        case 'W':
            dx = 0; dy = -1;
            break;
        case 'ArrowDown':
        case 's':
        case 'S':
            dx = 0; dy = 1;
            break;
        case 'ArrowLeft':
        case 'a':
        case 'A':
            dx = -1; dy = 0;
            break;
        case 'ArrowRight':
        case 'd':
        case 'D':
            dx = 1; dy = 0;
            break;
    }
});

// 按钮事件处理
document.getElementById('start-btn').addEventListener('click', startGame);
document.getElementById('pause-btn').addEventListener('click', pauseGame);
document.getElementById('restart-btn').addEventListener('click', restartGame);

// 初始化
draw();
