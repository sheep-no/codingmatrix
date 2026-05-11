"""
Agent 能力测试脚本

构造复杂项目需求，通过 API 调用 Orchestrator Agent，
验证 Spec-First、依赖图、并行生成、迭代修复等能力。
"""

import asyncio
import httpx
import json
import sys
from datetime import datetime, timedelta, timezone
from jose import jwt

# ============================================================
# 配置
# ============================================================

BASE_URL = "http://localhost:8080"
SECRET_KEY = "test-secret-key-for-development-only-12345"
ALGORITHM = "HS256"

# 复杂需求：一个带认证的待办事项管理系统
COMPLEX_REQUIREMENT = """
请生成一个完整的待办事项管理系统（Todo Management System），要求如下：

## 后端 (Python/FastAPI)
1. **用户认证系统**
   - 用户注册、登录、登出
   - JWT Token 认证
   - 密码加密存储（bcrypt）

2. **Todo CRUD API**
   - 创建、读取、更新、删除待办事项
   - 每个 Todo 包含：标题、描述、优先级(低/中/高)、截止日期、完成状态
   - 支持按优先级和截止日期排序
   - 支持按完成状态筛选
   - 每个用户只能管理自己的 Todo

3. **数据持久化**
   - 使用 SQLite + SQLAlchemy
   - 用户表和 Todo 表，外键关联
   - 自动创建 created_at 和 updated_at 字段

4. **API 规范**
   - RESTful 风格
   - 统一错误响应格式
   - 请求验证使用 Pydantic

## 前端 (Vue 3)
1. **页面**
   - 登陆/注册页面
   - Todo 列表页面（支持筛选、排序）
   - 添加/编辑 Todo 的表单组件

2. **功能**
   - 登陆状态持久化（localStorage）
   - 自动刷新 Token
   - 响应式布局
   - 操作成功/失败的 Toast 提示

## 项目结构
- 前后端分离
- 后端：app/main.py, app/models/, app/schemas/, app/api/, app/services/
- 前端：index.html, src/main.js, src/App.vue, src/components/
- 包含 requirements.txt 和 .env.example

请确保所有代码完整可运行，包含必要的注释和错误处理。
"""

# 中等需求：简单计算器 API
MEDIUM_REQUIREMENT = """
请生成一个简单的计算器 REST API 服务，要求：
1. FastAPI 框架
2. 支持加、减、乘、除四种运算
3. 除零时返回 400 错误
4. 请求和响应使用 Pydantic 模型
5. 包含 requirements.txt
"""

# 简单需求：Hello World
SIMPLE_REQUIREMENT = """
请生成一个简单的 Python 脚本，输出 "Hello, World!"
"""


def generate_test_token(user_id: str = "1", permission: str = "super") -> str:
    """生成测试 Token"""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=24)
    refresh_until = now + timedelta(days=5)
    
    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": now,
        "type": "access",
        "refresh_until": int(refresh_until.timestamp()),
        "permission_level": permission
    }
    
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token


async def test_orchestrate(requirement: str, test_name: str, output_dir: str = None):
    """测试 Orchestrator Agent"""
    print(f"\n{'='*60}")
    print(f"测试: {test_name}")
    print(f"需求长度: {len(requirement)} 字符")
    print(f"{'='*60}")
    
    token = generate_test_token()
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {
        "requirement": requirement,
        "enable_review": True,
        "enable_validation": True,
        "enable_error_recovery": True,
        "enable_memory": True,
    }
    if output_dir:
        payload["output_dir"] = output_dir
    
    start_time = asyncio.get_event_loop().time()
    
    async with httpx.AsyncClient(timeout=1200) as client:
        try:
            response = await client.post(
                f"{BASE_URL}/api/v1/agent/orchestrate",
                headers=headers,
                json=payload
            )
            
            elapsed = asyncio.get_event_loop().time() - start_time
            
            print(f"\nHTTP 状态码: {response.status_code}")
            print(f"响应时间: {elapsed:.2f}s")
            
            if response.status_code == 200:
                data = response.json()
                print(f"\n生成结果:")
                print(f"  成功: {data.get('success')}")
                print(f"  文件数: {data.get('total_files_created')}")
                print(f"  复杂度: {data.get('complexity')}")
                print(f"  错误数: {len(data.get('errors', []))}")
                print(f"  警告数: {len(data.get('warnings', []))}")
                print(f"  耗时: {data.get('elapsed_time', 0):.2f}s")
                
                if data.get('models_used'):
                    print(f"\n使用的模型:")
                    for role, model in data['models_used'].items():
                        print(f"  {role}: {model}")
                
                if data.get('files'):
                    print(f"\n生成的文件:")
                    for f in data['files']:
                        status = "✅" if f.get('success') else "❌"
                        print(f"  {status} {f['path']} ({f.get('size', 0)} bytes)")
                
                if data.get('errors'):
                    print(f"\n错误:")
                    for err in data['errors']:
                        print(f"  ❌ {err}")
                
                if data.get('warnings'):
                    print(f"\n警告:")
                    for warn in data['warnings'][:5]:  # 只显示前 5 个
                        print(f"  ⚠️ {warn}")
                
                return data
            else:
                print(f"\n错误响应: {response.text[:500]}")
                return None
                
        except httpx.ConnectError:
            print(f"\n无法连接到服务器: {BASE_URL}")
            print("请确保后端服务正在运行")
            return None
        except Exception as e:
            print(f"\n请求失败: {e}")
            return None


async def main():
    """运行所有测试"""
    print("Agent 能力测试")
    print(f"目标服务器: {BASE_URL}")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 跳过服务器检查
    print("服务器状态: 在线（跳过检查）")
    
    results = {}
    
    # 只测试复杂需求
    results['complex'] = await test_orchestrate(
        COMPLEX_REQUIREMENT,
        "复杂需求 - Todo 管理系统",
        "./test_output/complex"
    )
    
    # 汇总
    print(f"\n{'='*60}")
    print("测试汇总")
    print(f"{'='*60}")
    for name, result in results.items():
        if result:
            status = "✅ 通过" if result.get('success') else "⚠️ 部分成功"
            print(f"  {name}: {status} | 文件: {result.get('total_files_created')} | 耗时: {result.get('elapsed_time', 0):.1f}s")
        else:
            print(f"  {name}: ❌ 失败")


if __name__ == "__main__":
    asyncio.run(main())
