"""
测试架构师 JSON 解析器的鲁棒性

模拟 LLM 模型可能产生的各种非标准 JSON 输出格式，
验证并增强 _safe_parse_json 的解析能力。
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import re
from app.agent.specialists import Architect


def create_architect():
    """创建架构师实例"""
    return Architect(
        role_name="Architect",
        model_name="Qwen/Qwen3-8B",
        task_type="generate"
    )


def test_parse(name: str, text: str, architect: Architect, expect_success: bool = True):
    """测试单个 JSON 解析案例"""
    try:
        result = architect._safe_parse_json(text)
        if expect_success:
            print(f"  [PASS] {name}: 解析成功, keys={list(result.keys())[:5]}...")
        else:
            print(f"  [UNEXPECTED] {name}: 本应失败但解析成功")
        return True
    except ValueError as e:
        if not expect_success:
            print(f"  [PASS] {name}: 预期失败: {e}")
        else:
            print(f"  [FAIL] {name}: 解析失败: {e}")
        return False


def main():
    architect = create_architect()
    passed = 0
    failed = 0
    total = 0

    def run_test(name, text, expect_success=True):
        nonlocal passed, failed, total
        total += 1
        if test_parse(name, text, architect, expect_success):
            if expect_success:
                passed += 1
            else:
                passed += 1
        else:
            failed += 1

    print("=" * 60)
    print("架构师 JSON 解析鲁棒性测试")
    print("=" * 60)

    # === 基础测试 ===
    print("\n--- 基础测试 ---")

    # 1. 标准 JSON
    run_test("标准JSON", '{"project_type": "full-stack", "file_plan": []}')

    # 2. 带 thinking tags
    run_test("带thinking标签",
             '<think>这是思考过程</think>\n{"project_type": "full-stack", "file_plan": []}')

    # 3. 带 markdown 代码块
    run_test("带markdown代码块",
             '```json\n{"project_type": "full-stack", "file_plan": []}\n```')

    # 4. 带文字说明 + JSON
    run_test("文字说明+JSON",
             '好的，我来设计架构。\n\n{"project_type": "full-stack", "file_plan": []}\n\n以上就是架构设计。')

    # === 实际失败案例 ===
    print("\n--- 实际失败案例 ---")

    # 5. 真实失败案例：JSON 中有 // 注释
    run_test("JSON中有//注释", '''
{
  "project_type": "full-stack",
  "db_schema": {
    "articles": {
      "columns": {
        "id": "INTEGER PRIMARY KEY",
        "status": "VARCHAR(20) DEFAULT '草稿'" // ("草稿)|(已发布)|(已归档)
      }
    }
  }
}
''')

    # 6. 带 /* */ 注释
    run_test("JSON中有/* */注释", '''
{
  "project_type": "full-stack",
  "db_schema": {
    "articles": {
      "columns": {
        "id": "INTEGER PRIMARY KEY" /* 主键 */
      }
    }
  }
}
''')

    # === 引号问题 ===
    print("\n--- 引号问题 ---")

    # 7. 字符串值中有未转义的反斜杠引号
    run_test("错误的反斜杠引号", '''
{
  "project_type": "full-stack",
  "db_schema": {
    "users": {
      "columns": {
        "id": "INTEGER PRIMARY KEY",
        "name": "VARCHAR(255)\\"
      }
    }
  }
}
''')

    # 8. 中文引号
    run_test("中文引号",
             '{"project_type": "full-stack", "说明": "这是一个项目"}')

    # 9. 单引号包裹的 JSON
    run_test("单引号JSON",
             "{'project_type': 'full-stack', 'file_plan': []}")

    # === 格式问题 ===
    print("\n--- 格式问题 ---")

    # 10. 尾随逗号
    run_test("尾随逗号", '''
{
  "project_type": "full-stack",
  "file_plan": [
    {"path": "main.py", "priority": 1},
  ],
}
''')

    # 11. 缺少逗号
    run_test("缺少逗号", '''
{
  "project_type": "full-stack"
  "file_plan": []
}
''')

    # 12. 键名未加引号
    run_test("键名未加引号", '''
{
  project_type: "full-stack",
  file_plan: []
}
''')

    # 13. 值中缺少引号（裸值）
    run_test("值中缺少引号", '''
{
  "project_type": full-stack,
  "file_plan": []
}
''')

    # 14. 多余的逗号（连续）
    run_test("连续逗号", '''
{
  "project_type": "full-stack",,
  "file_plan": [,,]
}
''')

    # === 复杂嵌套问题 ===
    print("\n--- 复杂嵌套问题 ---")

    # 15. api_spec 中嵌套对象数组
    run_test("复杂api_spec", '''
{
  "project_type": "full-stack",
  "api_spec": {
    "paths": {
      "/api/auth/login": {
        "post": {
          "summary": "登录",
          "responses": {
            "200": {
              "description": "登录成功"
            }
          }
        }
      }
    }
  },
  "file_plan": [
    {
      "path": "main.py",
      "description": "主入口文件"
    }
  ]
}
''')

    # 16. file_plan 中的依赖数组格式问题
    run_test("依赖数组格式", '''
{
  "project_type": "full-stack",
  "file_plan": [
    {
      "path": "frontend/src/App.vue",
      "description": "主应用组件",
      "priority": 1,
      "dependencies": ["utils.js", "store.js"]
    }
  ]
}
''')

    # 17. 超长真实案例（上次失败的完整 LLM 输出，含 // 注释）
    REAL_CASE = '''{
  "project_type": "full-stack",
  "tech_stack": ["vue3", "vite", "element-plus", "fastapi", "sqlalchemy", "jwt"],
  "file_plan": [
    {"path": "frontend/src/App.vue", "description": "主应用组件", "priority": 1},
    {"path": "backend/main.py", "description": "后端主入口", "priority": 1}
  ],
  "api_spec": {
    "paths": {
      "/api/auth/register": {"post": {"summary": "注册新用户", "responses": {"201": {"description": "注册成功"}}}},
      "/api/articles": {"get": {"summary": "文章列表", "parameters": [{"name": "page", "type": "integer", "in": "query"}], "responses": {"200": {"description": "文章列表"}}}}
    }
  },
  "db_schema": {
    "users": {
      "columns": {
        "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
        "email": "VARCHAR(255) UNIQUE NOT NULL"
      }
    },
    "articles": {
      "columns": {
        "id": "INTEGER PRIMARY KEY",
        "title": "VARCHAR(255) NOT NULL",
        "status": "VARCHAR(20) DEFAULT '草稿'" // ("草稿)|(已发布)|(已归档)
      }
    }
  }
}'''
    run_test("超长真实案例", REAL_CASE)

    # 18. 多个 JSON 块
    run_test("多个JSON块", '''
第一个方案：
{"project_type": "simple"}

或者第二个方案：
{"project_type": "full-stack"}
''')

    # 19. JSON 中有换行符未转义
    run_test("未转义换行符", '''
{
  "project_type": "full-stack",
  "description": "Line 1
Line 2"
}
''')

    # 20. 控制字符
    run_test("控制字符",
             '{"project_type": "full-stack", "note": "test\x00done"}')

    # === 边界情况 ===
    print("\n--- 边界情况 ---")

    # 21. 空输入
    run_test("空输入", "", expect_success=False)

    # 22. 纯文字
    run_test("纯文字", "这是一个项目架构设计，包含前后端分离", expect_success=False)

    # 23. 只有部分 JSON
    run_test("不完整JSON", '{"project_type": "full-stack"', expect_success=False)

    # === 结果 ===
    print(f"\n{'=' * 60}")
    print(f"测试结果: {passed}/{total} 通过, {failed} 失败")
    print(f"{'=' * 60}")

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
