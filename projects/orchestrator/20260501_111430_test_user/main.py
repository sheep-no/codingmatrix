from flask import Flask, jsonify
from datetime import datetime

app = Flask(__name__)

# Hello World API endpoint
@app.route('/')
def hello_world():
    """
    Returns a greeting message with current timestamp
    """
    response = jsonify({
        "message": "Hello, World!",
        "status": "success",
        "timestamp": datetime.utcnow().isoformat()
    })
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response

if __name__ == '__main__':
    """
    Main entry point for development server
    """
    # Run with debug mode enabled for development
    app.run(host='0.0.0.0', port=5000, debug=True)