import os
from dotenv import load_dotenv
from flask import Flask
from app import create_app

def main():
    # 加载环境变量
    load_dotenv()
    
    # 创建应用实例
    app = create_app()
    
    # 获取配置
    host = os.environ.get('APP_HOST', '0.0.0.0')
    port = int(os.environ.get('APP_PORT', 5000))
    
    # 启动应用
    try:
        app.run(
            host=host,
            port=port,
            debug=bool(os.environ.get('APP_DEBUG')),
            use_reloader=bool(os.environ.get('APP_RELOADER', True))
        )
    except Exception as e:
        print(f"应用启动失败: {str(e)}")
        exit(1)

if __name__ == '__main__':
    main()