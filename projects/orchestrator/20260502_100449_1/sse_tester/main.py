# sse_tester/main.py
import logging
import socketserver
import http.server
import time
from threading import Thread
from typing import NoReturn, Optional

class SSEHandler(http.server.BaseHTTPRequestHandler):
    """
    自定义的SSE请求处理类，负责处理客户端连接并发送事件流。
    包含对客户端断开连接的检测和异常处理逻辑。
    """

    def do_GET(self) -> NoReturn:
        """
        处理GET请求，当路径为/sse时返回SSE事件流。
        负责维护连接并定期发送事件，同时检测客户端断开。
        """
        if self.path == "/sse":
            # 设置SSE响应头
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            # 初始化客户端连接标志
            is_connected = True

            try:
                while is_connected:
                    # 生成事件数据
                    event_data = self.generate_event()
                    # 检测客户端是否仍然连接
                    try:
                        self.wfile.write(event_data.encode("utf-8"))
                        self.wfile.write(b"\n\n")
                        time.sleep(1)  # 每秒发送一次事件
                    except (OSError, ConnectionResetError) as e:
                        # 客户端断开连接时捕获异常
                        logging.warning(f"客户端 {self.client_address} 断开连接: {e}")
                        is_connected = False
                    except Exception as e:
                        # 处理其他潜在异常
                        logging.error(f"SSE异常: {e}")
                        is_connected = False
            finally:
                # 最终确保连接关闭
                self.wfile.close()

        else:
            # 其他路径返回404错误
            self.send_error(404)

    def generate_event(self) -> str:
        """
        生成SSE事件内容，包含时间戳和随机数据。
        使用简单格式示例：data: <时间戳>\n\n
        """
        return f"data: {time.ctime()} | {self.random_data()}\n\n"

    def random_data(self) -> str:
        """
        生成随机测试数据，模拟实际事件流内容。
        示例数据包含时间戳和随机字符串。
        """
        import random
        return f"TEST_{random.randint(1000, 9999)}"

class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """
    支持多线程的HTTP服务器，每个客户端连接在一个独立线程中处理。
    便于支持多个并发的SSE连接。
    """

    def __init__(self, server_address: tuple, RequestHandlerClass: type) -> NoReturn:
        """
        初始化多线程服务器。
        
        Args:
            server_address: 服务器绑定地址和端口元组
            RequestHandlerClass: 请求处理类
        """
        super().__init__(server_address, RequestHandlerClass)

def run_server() -> NoReturn:
    """
    启动SSE测试服务器的入口函数。
    使用多线程支持并发连接，启动日志记录功能。
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    server_address = ("", 8000)  # 绑定到所有网络接口，端口8000
    httpd = ThreadedHTTPServer(server_address, SSEHandler)
    logging.info(f"SSE测试服务器启动，监听端口: {server_address[1]}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logging.info("服务器已停止。")
        httpd.server_close()

if __name__ == "__main__":
    run_server()