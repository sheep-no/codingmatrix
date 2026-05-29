#!/usr/bin/env python3
"""
多模型Agent流式生成测试脚本

功能：
1. 调用多模型Agent生成复杂项目
2. 实时显示生成进度
3. 文件预览功能
4. Diff对比功能
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
import difflib

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agent.orchestrator import OrchestratorAgent
from app.agent.session_manager import SessionManager
from app.agent.spec_cache import SpecCache
from app.agent.feedback_learner import FeedbackLearner


class ProjectGeneratorWithPreview:
    """带预览和Diff功能的项目生成器"""
    
    def __init__(self, output_dir: str = "./test_generated_project"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.generated_files: Dict[str, str] = {}  # 文件路径 -> 内容
        self.session_id = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
    async def stream_callback(self, msg: str):
        """流式回调函数，处理生成进度"""
        try:
            data = json.loads(msg)
            msg_type = data.get("type", "")
            
            if msg_type == "thinking":
                print(f"\n[思考] {data.get('content', '')[:200]}...")
                
            elif msg_type == "model_info":
                print(f"\n[模型] 使用模型: {data.get('model', 'unknown')}")
                
            elif msg_type == "file":
                file_path = data.get("path", "")
                content = data.get("content", "")
                action = data.get("action", "create")
                
                if action == "create":
                    print(f"\n[创建文件] {file_path}")
                    self.generated_files[file_path] = content
                    self._preview_file(file_path, content)
                    
                elif action == "modify":
                    print(f"\n[修改文件] {file_path}")
                    if file_path in self.generated_files:
                        old_content = self.generated_files[file_path]
                        self._show_diff(file_path, old_content, content)
                    self.generated_files[file_path] = content
                    
            elif msg_type == "file_diff":
                file_path = data.get("path", "")
                old_content = data.get("old_content", "")
                new_content = data.get("new_content", "")
                print(f"\n[Diff对比] {file_path}")
                self._show_diff(file_path, old_content, new_content)
                
            elif msg_type == "progress":
                progress_data = data.get("data", {})
                message = progress_data.get("message", "")
                step = progress_data.get("step", "")
                total = progress_data.get("total_steps", "")
                if message:
                    print(f"\n[进度] {message} {f'({step}/{total})' if step else ''}")
                    
            elif msg_type == "error":
                error_data = data.get("data", {})
                print(f"\n[错误] {error_data.get('error', '未知错误')}")
                
            elif msg_type == "done":
                result = data.get("data", {})
                print(f"\n[完成] 生成完成！")
                print(f"  - 创建文件数: {result.get('total_files_created', 0)}")
                print(f"  - 总文件数: {result.get('total_files', 0)}")
                
        except json.JSONDecodeError:
            print(f"[日志] {msg}")
    
    def _preview_file(self, file_path: str, content: str, max_lines: int = 30):
        """预览文件内容"""
        print(f"\n{'='*60}")
        print(f"文件预览: {file_path}")
        print(f"{'='*60}")
        
        lines = content.split('\n')
        total_lines = len(lines)
        
        if total_lines <= max_lines:
            print(content)
        else:
            # 显示前max_lines行
            for i, line in enumerate(lines[:max_lines]):
                print(f"{i+1:4d} | {line}")
            print(f"\n... 省略 {total_lines - max_lines} 行 ...")
            print(f"总行数: {total_lines}")
        
        print(f"{'='*60}\n")
    
    def _show_diff(self, file_path: str, old_content: str, new_content: str):
        """显示文件差异"""
        print(f"\n{'='*60}")
        print(f"Diff对比: {file_path}")
        print(f"{'='*60}")
        
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        
        diff = difflib.unified_diff(
            old_lines, 
            new_lines, 
            fromfile=f"原始/{file_path}",
            tofile=f"修改/{file_path}",
            lineterm=''
        )
        
        diff_output = list(diff)
        if diff_output:
            for line in diff_output[:100]:  # 限制显示行数
                if line.startswith('+'):
                    print(f"\033[32m{line}\033[0m")  # 绿色
                elif line.startswith('-'):
                    print(f"\033[31m{line}\033[0m")  # 红色
                elif line.startswith('@@'):
                    print(f"\033[36m{line}\033[0m")  # 青色
                else:
                    print(line)
                    
            if len(diff_output) > 100:
                print(f"\n... 省略 {len(diff_output) - 100} 行差异 ...")
        else:
            print("无差异")
        
        print(f"{'='*60}\n")
    
    async def generate_complex_project(self, requirement: str):
        """生成复杂项目"""
        print(f"\n{'='*80}")
        print(f"开始生成复杂项目")
        print(f"需求: {requirement[:200]}...")
        print(f"输出目录: {self.output_dir}")
        print(f"会话ID: {self.session_id}")
        print(f"{'='*80}\n")
        
        # 创建OrchestratorAgent
        orchestrator = OrchestratorAgent(
            output_dir=str(self.output_dir),
            enable_review=True,
            enable_validation=True,
            enable_error_recovery=True,
            memory_enabled=True,
            spec_first=True,
            dependency_graph=True,
            callback=self.stream_callback,
            session_id=self.session_id,
            incremental=False
        )
        
        try:
            # 开始生成
            result = await orchestrator.generate(requirement=requirement)
            
            print(f"\n{'='*80}")
            print(f"项目生成完成！")
            print(f"{'='*80}")
            print(f"生成结果:")
            print(f"  - 成功: {result.get('success', False)}")
            print(f"  - 创建文件数: {result.get('total_files_created', 0)}")
            print(f"  - 总文件数: {result.get('total_files', 0)}")
            print(f"  - 生成时间: {result.get('generation_time', 0):.2f} 秒")
            
            # 显示生成的文件列表
            print(f"\n生成的文件列表:")
            for file_path in sorted(self.generated_files.keys()):
                print(f"  - {file_path}")
            
            return result
            
        except Exception as e:
            print(f"\n[错误] 项目生成失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def incremental_modify(self, modification_request: str):
        """增量修改项目"""
        print(f"\n{'='*80}")
        print(f"开始增量修改")
        print(f"修改需求: {modification_request[:200]}...")
        print(f"{'='*80}\n")
        
        # 创建OrchestratorAgent（增量模式）
        orchestrator = OrchestratorAgent(
            output_dir=str(self.output_dir),
            enable_review=True,
            enable_validation=True,
            enable_error_recovery=True,
            memory_enabled=True,
            spec_first=True,
            dependency_graph=True,
            callback=self.stream_callback,
            session_id=self.session_id,
            incremental=True  # 启用增量模式
        )
        
        try:
            # 开始增量修改
            result = await orchestrator.generate(requirement=modification_request)
            
            print(f"\n{'='*80}")
            print(f"增量修改完成！")
            print(f"{'='*80}")
            print(f"修改结果:")
            print(f"  - 成功: {result.get('success', False)}")
            print(f"  - 修改文件数: {result.get('total_files_modified', 0)}")
            print(f"  - 新增文件数: {result.get('total_files_created', 0)}")
            
            return result
            
        except Exception as e:
            print(f"\n[错误] 增量修改失败: {e}")
            import traceback
            traceback.print_exc()
            return None


async def main():
    """主函数"""
    # 创建生成器
    generator = ProjectGeneratorWithPreview(
        output_dir="./test_complex_project"
    )
    
    # 复杂项目需求 - Ren'Py Galgame 学习游戏
    complex_requirement = """
    使用 Ren'Py 引擎开发一个 Galgame 风格的学习游戏，项目名称：StudyGal

    项目要求：

    1. 游戏设定：
       - 主题：高中校园恋爱 + 学习成长
       - 主角：普通高中生，需要提升成绩
       - 游戏时长：约30分钟完整剧情

    2. 可攻略角色（至少2个）：
       - 学姐「林雪」：学生会会长，学霸型，温柔耐心
         * 好感度事件：图书馆辅导、考试前鼓励
         * 结局：一起考上同一所大学
       - 同班同学「苏晴」：活泼开朗，体育特长生
         * 好感度事件：操场跑步、运动会备战
         * 结局：互相激励共同进步

    3. 场景设计（至少3个）：
       - 教室：日常上课、自习
       - 图书馆：学习、约会事件
       - 操场：体育活动、放松聊天

    4. 核心系统：
       - 对话系统：分支选项影响好感度
       - 好感度系统：隐藏数值，影响结局
       - 学习系统：数学、英语、编程三科目
       - 日程系统：周一到周五，每天选择活动
       - 存档/读档系统

    5. 美术资源：
       - 使用 Ren'Py 内置占位图
       - 背景：简单场景图
       - 角色：立绘占位符

    6. 技术要求：
       - 使用 Ren'Py 8.x 语法
       - 支持中文显示
       - 包含 script.rpy、screens.rpy、options.rpy
       - 包含完整的角色定义和剧情脚本

    请生成完整的 Ren'Py 项目，包含所有必要的 .rpy 文件和资源目录结构。
    """
    
    # 第一步：生成复杂项目
    print("\n" + "="*80)
    print("第一步：生成复杂项目")
    print("="*80)
    
    result = await generator.generate_complex_project(complex_requirement)
    
    if result and result.get('success'):
        print("\n项目生成完成！")
        
        # 第二步：增量修改
        print("\n" + "="*80)
        print("第二步：增量修改测试")
        print("="*80)
        
        modification_request = """
        对已生成的在线教育平台进行以下增量修改：
        
        1. 新增功能：
           - 添加直播课程功能
           - 支持屏幕共享和白板
           - 实时聊天和弹幕
        
        2. 优化改进：
           - 优化视频播放器，支持倍速播放
           - 添加课程推荐算法
           - 改进搜索功能，支持全文搜索
        
        3. Bug修复：
           - 修复支付回调处理问题
           - 修复视频进度同步问题
        
        请只修改需要变更的文件，不要重新生成整个项目。
        """
        
        modify_result = await generator.incremental_modify(modification_request)
        
        if modify_result:
            print("\n增量修改测试完成！")
        else:
            print("\n增量修改测试失败！")
    else:
        print("\n项目生成失败，无法进行增量修改测试！")


if __name__ == "__main__":
    # 运行测试
    asyncio.run(main())
