#!/usr/bin/env python3
"""
使用多模型 Agent 生成小恐龙游戏
"""
import asyncio
import sys
import os
from pathlib import Path

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.agent import OrchestratorAgent


async def main():
    """使用 OrchestratorAgent 生成小恐龙游戏"""
    output_dir = Path("./projects/dino_game")
    output_dir.mkdir(parents=True, exist_ok=True)

    requirement = """
    创建一个Chrome浏览器风格的小恐龙跑步游戏，使用纯HTML+CSS+JavaScript实现。

    游戏要求：
    1. 一个绿色的小恐龙角色，可以跳跃（按空格键或点击屏幕）
    2. 随机生成的仙人掌障碍物，从右向左移动
    3. 计分系统，每通过一个障碍物加10分
    4. 碰到障碍物游戏结束，显示最终分数
    5. 按空格键或点击重新开始按钮可以重新开始
    6. 游戏速度随分数增加逐渐加快
    7. 添加简单的背景和地面效果
    8. 支持移动端触摸操作

    技术要求：
    - 单个HTML文件，包含所有CSS和JavaScript
    - 使用Canvas绘制游戏画面
    - 60fps流畅运行
    - 适配不同屏幕尺寸
    - 添加简单的音效（使用Web Audio API）
    """

    print("=" * 60)
    print("正在使用多模型 Agent 生成小恐龙游戏...")
    print("=" * 60)

    # 创建进度回调
    async def progress_callback(msg: str):
        print(f"[进度] {msg[:200]}")

    # 初始化 OrchestratorAgent
    agent = OrchestratorAgent(
        output_dir=str(output_dir),
        enable_review=True,
        enable_validation=True,
        enable_error_recovery=True,
        memory_enabled=False,  # 简单任务不需要记忆
        spec_first=True,
        dependency_graph=False,  # 单文件项目不需要依赖图
        callback=progress_callback,
        session_id="dino_game_session"
    )

    try:
        # 执行生成
        result = await agent.generate(requirement=requirement)

        print("\n" + "=" * 60)
        print("生成完成!")
        print("=" * 60)
        print(f"成功: {result.get('success', False)}")
        print(f"生成文件数: {result.get('total_files_created', 0)}")
        print(f"输出目录: {output_dir}")

        # 列出生成的文件
        if output_dir.exists():
            print("\n生成的文件:")
            for f in output_dir.rglob("*"):
                if f.is_file():
                    print(f"  - {f.relative_to(output_dir)}")

        return result

    except Exception as e:
        print(f"\n生成失败: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result and result.get("success") else 1)
