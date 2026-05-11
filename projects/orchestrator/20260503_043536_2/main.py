from flask import Flask, jsonify, request

app = Flask(__name__)

# 计数器状态（简单实现，实际应用中应使用数据库）
counter_state = {
    "count": 0,
    "last_reset": None,
    "max_value": 100
}

@app.route('/counter', methods=['GET'])
def get_counter():
    """获取当前计数器状态"""
    return jsonify({
        "count": counter_state["count"],
        "max_value": counter_state["max_value"],
        "last_reset": counter_state["last_reset"]
    })

@app.route('/counter', methods=['POST'])
def increment_counter():
    """增加计数器值"""
    if counter_state["count"] >= counter_state["max_value"]:
        return jsonify({"error": "Counter has reached its maximum value"}), 400
        
    counter_state["count"] += 1
    
    # 如果达到最大值，重置计数器
    if counter_state["count"] >= counter_state["max_value"]:
        counter_state["count"] = 0
        counter_state["last_reset"] = "2023-05-01T00:00:00"
    
    return jsonify({
        "count": counter_state["count"],
        "message": "Counter incremented successfully"
    })

@app.route('/counter/reset', methods=['POST'])
def reset_counter():
    """重置计数器"""
    counter_state["count"] = 0
    counter_state["last_reset"] = "2023-05-01T00:00:00"
    return jsonify({
        "count": counter_state["count"],
        "message": "Counter has been reset",
        "last_reset": counter_state["last_reset"]
    })

@app.route('/counter/set_max', methods=['POST'])
def set_max_value():
    """设置计数器最大值"""
    try:
        new_max = int(request.form.get("max_value", 0))
        if new_max <= 0:
            return jsonify({"error": "Max value must be positive"}), 400
            
        counter_state["max_value"] = new_max
        
        if counter_state["count"] >= counter_state["max_value"]:
            counter_state["count"] = 0
            counter_state["last_reset"] = "2023-05-01T00:00:00"
            
        return jsonify({
            "max_value": counter_state["max_value"],
            "message": "Max value updated successfully"
        })
    except ValueError:
        return jsonify({"error": "Invalid max value format"}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)