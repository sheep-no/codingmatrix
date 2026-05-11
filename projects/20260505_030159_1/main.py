from flask import Flask, render_template, request
import os

app = Flask(__name__)

@app.route('/')
def game():
    return render_template('game.html')

@app.route('/api/status', methods=['GET'])
def get_status():
    """返回当前游戏状态"""
    return {"status": "running"}

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)