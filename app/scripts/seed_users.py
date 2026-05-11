"""
数据库种子脚本 - 创建测试用户

运行方式:
    python3 -m app.scripts.seed_users

功能:
    创建三个不同权限级别的测试用户:
    1. superadmin - mr_yang@example.com (超级管理员)
    2. admin - admin_test@example.com (管理员)
    3. normal - normal_user@example.com (普通用户)
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.models.user import User
from app.models.Permission import Permission
from app.utils.security import hash_password


# 测试用户配置
TEST_USERS = [
    {
        "username": "mr_yang",
        "email": "mr_yang@example.com",
        "password": "12345678",
        "permission_level": "superadmin",
        "description": "超级管理员 - 拥有所有系统管理权限"
    },
    {
        "username": "admin_test",
        "email": "admin_test@example.com",
        "password": "12345678",
        "permission_level": "admin",
        "description": "管理员 - 用户管理、系统监控、服务管理"
    },
    {
        "username": "normal_user",
        "email": "normal_user@example.com",
        "password": "12345678",
        "permission_level": "normal",
        "description": "普通用户 - 基础业务功能"
    }
]


async def seed_users(database_url: str):
    """创建测试用户"""
    print(f"连接到数据库: {database_url}")
    
    engine = create_async_engine(database_url)
    async_session = async_sessionmaker(engine)
    
    async with async_session() as session:
        for user_config in TEST_USERS:
            email = user_config["email"]
            
            # 检查用户是否已存在
            result = await session.execute(select(User).where(User.email == email))
            existing_user = result.scalar_one_or_none()
            
            if existing_user:
                # 更新现有用户的权限
                print(f"用户 {email} 已存在，更新权限为: {user_config['permission_level']}")
                
                # 更新权限
                perm_result = await session.execute(
                    select(Permission).where(Permission.user_id == existing_user.id)
                )
                existing_perm = perm_result.scalar_one_or_none()
                
                if existing_perm:
                    existing_perm.permission_level = user_config["permission_level"]
                else:
                    new_perm = Permission(
                        user_id=existing_user.id,
                        permission_level=user_config["permission_level"]
                    )
                    session.add(new_perm)
                
                # 更新密码（如果需要）
                existing_user.hashed_password = hash_password(user_config["password"])
                
            else:
                # 创建新用户
                print(f"创建用户: {user_config['username']} ({email}) - {user_config['permission_level']}")
                
                new_user = User(
                    username=user_config["username"],
                    email=email,
                    hashed_password=hash_password(user_config["password"])
                )
                session.add(new_user)
                await session.flush()
                
                new_perm = Permission(
                    user_id=new_user.id,
                    permission_level=user_config["permission_level"]
                )
                session.add(new_perm)
        
        await session.commit()
    
    await engine.dispose()
    print("\n种子用户创建完成!")
    print("\n测试账号列表:")
    print("-" * 60)
    for user_config in TEST_USERS:
        print(f"  {user_config['permission_level']:12} | {user_config['email']:30} | 密码: {user_config['password']}")
        print(f"  {'':12} | {user_config['description']}")
        print("-" * 60)


if __name__ == "__main__":
    # 从环境变量或配置文件获取数据库 URL
    from app.core.config import settings
    
    print("=" * 60)
    print("数据库种子脚本 - 创建测试用户")
    print("=" * 60)
    
    asyncio.run(seed_users(settings.DATABASE_URL))
