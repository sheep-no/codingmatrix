#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
贪吃蛇游戏服务器
自动启动一个 HTTP 服务器来运行贪吃蛇游戏
默认端口：8000
用法：python main.py [端口号]
"""

import os
import sys
import argparse
from http.server import HTTPServer, SimpleHTTPRequestHandler

class StaticGameHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            root_path = os.path.dirname(os.path.abspath('index.html'))
            print(f"正在加载 game.html from: {root_path}", flush=True)
            f = open(os.path.join(root_path, 'index.html'), 'r', encoding='utf-8')
            self.wfile.write(f.read().encode('utf-8'))
            f.close()
        else:
            self.send_response(200)
            self.end_headers()
            if os.path.exists(self.path):
                return self.send_file()
            else:
                self.send_error(404, 'Not Found')

    def send_file(self):
        try:
            self._send_response()
            with open(self.path, 'rb') as f:
                self.wfile.write(f.read())
        except IOError:
            self.send_error(404, 'Not Found')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000, help='服务器端口')
    args = parser.parse_args()
    
    port = args.port
    print(f"Starting Python HTTP Server on port {port}...", flush=True)
    server = HTTPServer(('localhost', port), StaticGameHandler)
    print("服务器已启动！访问 http://localhost:8000 运行游戏", flush=True)
    try:
        server.serve()
    except KeyboardInterrupt:
        print("\n服务器已停止")
