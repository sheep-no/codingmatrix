"""
sse_tester/disconnect_tester.py
测试SSE断开功能的脚本，包含断开检测和异常处理逻辑
"""

import socketserver
import http.server
import time
from http import HTTPStatus
from typing import Optional

class SSEHandler(http.server.BaseHTTPRequestHandler):
    """
    SSE事件流处理类，实现客户端断开检测和异常处理
    """

    def do_GET(self) -> None:
        """
        处理GET请求，建立SSE连接并发送事件流
        """
        try:
            # 设置SSE响应头
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.end_headers()
            
            # 记录活跃连接状态
            self.connection_active = True
            print("SSE连接已建立")

            # 模拟持续发送事件流
            for event_id in range(1, 11):
                if not self.connection_active:
                    # 检测到客户端已断开，终止事件发送
                    print("检测到客户端已断开，停止发送事件")
                    break
                
                # 构造事件数据（示例格式）
                event_data = f"id: {event_id}\n" \
                             f"data: 事件 {event_id} 已发送\n\n"
                
                # 发送事件数据
                self.wfile.write(event_data.encode('utf-8'))
                self.wfile.flush()
                
                # 模拟事件间隔时间
                time.sleep(1)
                
        except BrokenPipeError:
            # 客户端主动断开连接时的异常处理
            print("客户端断开连接，已捕获BrokenPipeError异常")
            self.connection_active = False
        except Exception as e:
            # 处理其他异常，防止服务器崩溃
            error_message = f"发生未处理的异常: {str(e)}"
            print(error_message)
            self.connection_active = False
            self.wfile.write(error_message.encode('utf-8'))
            self.wfile.flush()
        finally:
            # 确保连接正确关闭
            if self.connection_active:
                print("连接正常关闭")
            else:
                print("连接异常终止，已进行资源清理")

    def handle(self) -> None:
        """
        重写handle方法以增强异常处理能力
        """
        try:
            super().handle()
        except Exception as e:
            # 处理潜在的连接异常
            print(f"处理请求时发生异常: {str(e)}")
            self.connection_active = False


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """
    支持多线程的HTTP服务器
    使用ThreadingMixIn来处理多个并发连接
    """
    pass


def run_disconnect_test_server() -> None:
    """
    启动SSE断开检测测试服务器
    """
    try:
        # 定义服务器地址和端口
        server_address = ('localhost', 8000)
        
        # 创建服务器实例
        httpd = ThreadedHTTPServer(server_address, SSEHandler)
        
        # 启动服务器
        print(f"启动SSE断开检测测试服务器，在 {server_address} 处监听...")    
        httpd.serve_forever()
        
    except Exception as e:
        # 处理服务器启动异常
        print(f"服务器启动失败: {str(e)}")
        raise


if __name__ == '__main__':
    """
    入口点：当直接运行此脚本时启动测试服务器
    """
    run_disconnect_test_server()