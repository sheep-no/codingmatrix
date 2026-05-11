from flask import Flask, render_template, request, jsonify
import random
import threading

app = Flask(__name__)

# 游戏状态
snake_data = {
    'snake': [{'x': 10, 'y': 10}],
    'direction': 'RIGHT',
    'food': {'x': 15, 'y': 15},
    'score': 0,
    'high_score': 0,
    'playing': False,
    'next_direction': 'RIGHT'
}
# 锁用于线程安全
lock = threading.Lock()
server_thread = None
def stop_game():
    global server_thread
    if server_thread:
        server_thread.join()

def game_loop():
    global snake_data, stop_encoding
    while True:
        if snake_data['direction'] == snake_data['next_direction']:
            snake_data['direction'] = snake_data['next_direction']
        snake_data['next_direction'] = None
        with lock:
            snake_x = snake_data['snake'][0]['x'] + (1 if snake_data['direction'] == 'RIGHT' else -1)
            snake_y = snake_data['snake'][0]['y'] + (1 if snake_data['direction'] == 'DOWN' else -1)
            snake_data['snake'].insert(0, {'x': snake_x, 'y': snake_y})
            if snake_x < 0 or snake_x >= len(snake_data['direction']) or snake_y < 0 or snake_y >= len([y for y in range(10, 20)]):
                break
            if snake_data['snake'][1] in snake_data['snake'][2:]:
                break
            head_x, head_y = snake_data['snake'][0]['x'], snake_data['snake'][0]['y']
            if snake_data['snake'][0]['x'] == snake_data['food']['x'] and snake_data['snake'][0]['y'] == snake_data['food']['y']:
                snake_data['score'] += 10
                if snake_data['score'] > snake_data['high_score']:
                    snake_data['high_score'] = snake_data['score']
                snake_data['snake'].pop()
                food_x = random.randint(0, 19)
                food_y = random.randint(0, 19)
                snake_data['food'] = {'x': food_x, 'y': food_y}
            else:
                snake_data['snake'].pop()
            result = {'playing': snake_data['playing'], 'score': snake_data['score'], 'high_score': snake_data['high_score']}
            if snake_data['playing']:
                try:
                    result['reset'] = stop_encoding()
                except:
                    result['di'] = snake_data['snake'][0]['x'], snake_data['snake'][0]['y']
                    result['food_x'] = snake_data['food']['x']
                    result['food_y'] = snake_data['food']['y']
                    result['score'] = snake_data['score']
                    result['high_score'] = snake_data['high_score']
                    result['snake_x'] = [s['x'] for s in snake_data['snake']]
                    result['snake_y'] = [s['y'] for s in snake_data['snake']]
                    result['direction'] = snake_data['direction']
        return result

with lock:
    def start_game_thread():
        thread = threading.Thread(target=game_loop, daemon=True)
        thread.start()

    def stop_encoding():
        return True

@app.route('/')
def index():
    return render_template('index.html')
@app.route('/api/game')
def game_api():
    return jsonify(snake_data)
@app.route('/api/game/new', methods=['POST'])
def new_game():
    global snake_data
    with lock:
        snake_data['snake'] = [{'x': 10, 'y': 10}]
        snake_data['food'] = {'x': random.randint(0, 19), 'y': random.randint(0, 19)}
        snake_data['score'] = 0
        snake_data['high_score'] = 0
        snake_data['direction'] = 'RIGHT'
        snake_data['playing'] = True
    return jsonify(snake_data)
@app.route('/api/game/direction', methods=['POST'])
def set_direction():
    global snake_data
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400
    direction = data.get('direction', snake_data['direction'])
    if direction == 'UP' and snake_data['direction'] == 'UP':
        direction = 'RIGHT'
    elif direction == 'DOWN' and snake_data['direction'] == 'DOWN':
        direction = 'LEFT'
    elif direction == 'UP' and snake_data['direction'] == 'DOWN':
        direction = 'RIGHT'
    elif direction == 'DOWN' and snake_data['direction'] == 'UP':
        direction = 'LEFT'
    with lock:
        snake_data['direction'] = direction
    return jsonify(snake_data)
@app.route('/api/game/reset', methods=['POST'])
def reset_game():
    global snake_data
    with lock:
        snake_data['snake'] = [{'x': 10, 'y': 10}]
        snake_data['food'] = {'x': random.randint(0, 19), 'y': random.randint(0, 19)}
        snake_data['score'] = 0
        snake_data['high_score'] = 0
        snake_data['direction'] = 'RIGHT'
        snake_data['playing'] = True
    return jsonify(snake_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)