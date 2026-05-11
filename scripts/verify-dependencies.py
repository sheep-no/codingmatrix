#!/usr/bin/env python3
"""
验证所有项目依赖是否正确安装
使用方法：python verify_dependencies.py
"""

import sys
import importlib

REQUIRED_PACKAGES = {
    # 核心框架
    'fastapi': '0.136.0',
    'uvicorn': '0.44.0',
    'starlette': '0.41.0',
    
    # 数据库
    'sqlalchemy': '2.0.49',
    'alembic': '1.18.4',
    'aiosqlite': '0.19.0',
    'aiomysql': '0.2.0',
    
    # Pydantic
    'pydantic': '2.13.3',
    'pydantic_settings': '2.14.0',
    
    # 认证安全
    'jose': '3.5.0',  # python-jose
    'passlib': '1.7.4',
    'bcrypt': '4.0.1',
    
    # HTTP & Files
    'httpx': '0.28.1',
    'aiofiles': '25.1.0',
    'PIL': '12.2.0',  # Pillow
    
    # Parsing
    'bs4': '4.12.3',  # beautifulsoup4
    
    # AI
    'tiktoken': '0.12.0',
    
    # Logging
    'structlog': '23.2.0',
    'pythonjsonlogger': '4.1.0',  # python-json-logger
    'psutil': '7.2.2',
    
    # Rate Limiting
    'slowapi': '0.1.9',
    
    # Scheduling
    'apscheduler': '3.11.2',
    
    # Caching
    'redis': '7.4.0',
    
    # WebSocket
    'websockets': '12.0',
    
    # Utilities
    'dotenv': '1.2.2',  # python-dotenv
    'anyio': '4.13.0',
    'tenacity': '9.1.4',
    'pptx': '1.0.2',  # python-pptx
}

def check_package(name, expected_version=None):
    """检查包是否安装及版本是否匹配"""
    try:
        module = importlib.import_module(name)
        version = getattr(module, '__version__', 'unknown')
        
        if expected_version and version != 'unknown':
            if version.startswith(expected_version):
                status = '✅'
            else:
                status = '⚠️ '
        else:
            status = '✅'
        
        return True, version, status
    except ImportError as e:
        return False, str(e), '❌'

def main():
    print("=" * 70)
    print("  项目依赖验证")
    print("=" * 70)
    print()
    
    results = []
    
    # 检查每个包
    for package, expected_version in REQUIRED_PACKAGES.items():
        installed, version, status = check_package(package, expected_version)
        results.append((package, expected_version, version, status, installed))
    
    # 打印结果
    max_pkg_len = max(len(pkg) for pkg in REQUIRED_PACKAGES.keys())
    
    for package, expected, actual, status, installed in sorted(results, key=lambda x: x[0]):
        if installed:
            if actual == 'unknown':
                print(f"{status} {package:<{max_pkg_len}} (installed, version unknown)")
            elif actual.startswith(expected):
                print(f"{status} {package:<{max_pkg_len}} {actual}")
            else:
                print(f"{status} {package:<{max_pkg_len}} {actual} (expected {expected})")
        else:
            print(f"{status} {package:<{max_pkg_len}} NOT INSTALLED - {actual}")
    
    print()
    print("=" * 70)
    
    # 统计
    total = len(results)
    installed = sum(1 for r in results if r[4])
    missing = total - installed
    
    print(f"总计：{total} 个包")
    print(f"已安装：{installed} 个")
    print(f"缺失：{missing} 个")
    
    if missing == 0:
        print("\n✅ 所有依赖包已正确安装！")
        return 0
    else:
        print(f"\n❌ 缺少 {missing} 个依赖包，请运行以下命令安装：")
        print("\n   pip install -r requirements.txt\n")
        return 1

if __name__ == '__main__':
    sys.exit(main())
