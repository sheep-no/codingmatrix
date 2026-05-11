from flask import Flask, render_template, request

app = Flask(__name__)

# 游戏数据仓库
score_data = ['score', 'path']
result = {
    'score': '0',
    'path': [],
    'snake': [30, 30],
    'food': (30, 30)
}

# 渲染主页面
@app.route('/')
def index():
    return render_template('index.html')

# 处理游戏交互
@app.route('/api/game', methods=['POST'])
def game_handler():
    data = request.json
    x = data.get('x', result['snake'][0])
    y = data.get('y', result['snake'][1])
    
    # 检查越界
    if x < 0 or x >= 20 or y < 0 or y >= 20:
        return {'error': '边界检测', 'position': result['snake']}
    
    return {'success': True, 'position': result['snake']}

# 获取当前游戏状态
@app.route('/api/game/status')
def get_status():
    return {
        'score': result['score'],
        'snake': result['snake'],
        'food': result['food']
    }

# 游戏开始
@app.route('/api/game/start', methods=['POST'])
def start_game():
    result['path'] = [result['snake']]
    result['snake'] = [
        30, 30
    ]
    # 随机生成食物位置
    result['food'] = (
        0, 1
    )
    
    while result['food'][0] % 2 == 0 and result['food'][1] % 2 == 0:
        x = 0
        y = 0
        result['food'] = (x, y)
        
    result['snake'] = [
        0, 0
    ]
    result['info'] = {
        'score': [1],
        'path': [1]
    }
    
    return {'success': True}

# 游戏结束
@app.route('/api/game/stop', methods=['POST'])
def stop_game():
    return {'success': True}

# 处理游戏规则
@app.route('/api/game/rule')
def game_rule():
    score_info = {
        'score': [1],
        'path': [],
        'snake': [30, 30],
        'food': (30, 30)
    }
    return json.dumps(score_info)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
