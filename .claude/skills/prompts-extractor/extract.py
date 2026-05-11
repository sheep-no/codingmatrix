#!/usr/bin/env python3
"""
提示词提取器 v3
自动扫描项目中的提示词定义并生成文档
"""
import os
import re
import json
from pathlib import Path
from datetime import datetime

# 项目根目录
WORKSPACE = Path("/workspace")


def extract_from_agent_core(file_path: Path) -> list:
    """提取 agent_core.py 中的提示词"""
    content = file_path.read_text(encoding="utf-8")
    prompts = []

    # 提取 system_prompt（f-string 格式）
    match = re.search(r'system_prompt\s*=\s*f"""(.*?)"""', content, re.DOTALL)
    if match:
        prompts.append({
            "name": "system_prompt",
            "type": "system",
            "content": match.group(1).strip(),
            "description": "项目生成 Agent 系统提示词（f-string，含动态工具描述）",
            "source": "app/utils/agent_core.py"
        })

    # 提取继续生成提示词
    match = re.search(r'resume_prompt\s*=\s*f?"""(.*?)"""', content, re.DOTALL)
    if match:
        prompts.append({
            "name": "resume_prompt",
            "type": "continue",
            "content": match.group(1).strip(),
            "description": "继续生成提示词（需求变更时使用）",
            "source": "app/utils/agent_core.py"
        })

    return prompts


def extract_from_girlai(file_path: Path) -> list:
    """提取 GirlAi.py 中的角色配置"""
    content = file_path.read_text(encoding="utf-8")
    prompts = []

    # 提取各个角色
    role_matches = re.finditer(r'"(\w+)":\s*\{(.*?)\n\s{4}\}', content, re.DOTALL)
    for role_match in role_matches:
        role_id = role_match.group(1)
        role_content = role_match.group(2)

        # 提取关键字段
        name = re.search(r'"name":\s*"([^"]+)"', role_content)
        desc = re.search(r'"description":\s*"([^"]+)"', role_content)
        personality = re.search(r'"personality":\s*"([^"]+)"', role_content)
        speaking = re.search(r'"speaking_style":\s*"([^"]+)"', role_content)

        role_info = {
            "name": name.group(1) if name else role_id,
            "description": desc.group(1) if desc else "",
            "personality": personality.group(1) if personality else "",
            "speaking_style": speaking.group(1) if speaking else "",
        }

        prompts.append({
            "name": f"CHARACTER_{role_id.upper()}",
            "type": "character",
            "content": json.dumps(role_info, ensure_ascii=False, indent=2),
            "description": f"角色: {role_info['name']}",
            "source": "app/api/v1/GirlAi.py"
        })

    return prompts


def extract_from_aicode(file_path: Path) -> list:
    """提取 Aicode.py 中的提示词"""
    content = file_path.read_text(encoding="utf-8")
    prompts = []

    # 提取 GENERAL_PROMPT
    match = re.search(r'GENERAL_PROMPT\s*=\s*"""(.*?)"""', content, re.DOTALL)
    if match:
        prompts.append({
            "name": "GENERAL_PROMPT",
            "type": "general",
            "content": match.group(1).strip(),
            "description": "通用问答提示词",
            "source": "app/api/v1/Aicode.py"
        })

    # 提取 CODE_PROMPT
    match = re.search(r'CODE_PROMPT\s*=\s*"""(.*?)"""', content, re.DOTALL)
    if match:
        prompts.append({
            "name": "CODE_PROMPT",
            "type": "code",
            "content": match.group(1).strip(),
            "description": "代码生成提示词",
            "source": "app/api/v1/Aicode.py"
        })

    # 提取 REASONING_PROMPT
    match = re.search(r'REASONING_PROMPT\s*=\s*"""(.*?)"""', content, re.DOTALL)
    if match:
        prompts.append({
            "name": "REASONING_PROMPT",
            "type": "reasoning",
            "content": match.group(1).strip(),
            "description": "推理增强提示词",
            "source": "app/api/v1/Aicode.py"
        })

    return prompts


def extract_from_aicloud(file_path: Path) -> list:
    """提取 aicloud.py 中的提示词"""
    content = file_path.read_text(encoding="utf-8")
    prompts = []

    # 提取 aicloud system_prompt（函数内定义）
    match = re.search(r'system_prompt\s*=\s*"""(.*?)"""', content, re.DOTALL)
    if match:
        prompts.append({
            "name": "aicloud_system_prompt",
            "type": "aicloud",
            "content": match.group(1).strip(),
            "description": "AI Cloud 智能助手系统提示词",
            "source": "app/api/v1/aicloud.py"
        })

    return prompts


def extract_from_task_decomposer(file_path: Path) -> list:
    """提取 task_decomposer.py 中的提示词"""
    content = file_path.read_text(encoding="utf-8")
    prompts = []

    # 提取 SYSTEM_PROMPT
    match = re.search(r'SYSTEM_PROMPT\s*=\s*"""(.*?)"""', content, re.DOTALL)
    if match:
        prompts.append({
            "name": "TaskDecomposer.SYSTEM_PROMPT",
            "type": "workflow",
            "content": match.group(1).strip(),
            "description": "任务规划专家 - 将自然语言请求分解为结构化任务图",
            "source": "app/utils/workflow/task_decomposer.py"
        })

    return prompts


def extract_from_cross_validator(file_path: Path) -> list:
    """提取 cross_validator.py 中的提示词"""
    content = file_path.read_text(encoding="utf-8")
    prompts = []

    match = re.search(r'JUDGE_SYSTEM_PROMPT\s*=\s*"""(.*?)"""', content, re.DOTALL)
    if match:
        prompts.append({
            "name": "CrossValidator.JUDGE_SYSTEM_PROMPT",
            "type": "validation",
            "content": match.group(1).strip(),
            "description": "技术评审专家 - 代码交叉评估和质量选择",
            "source": "app/agent/cross_validator.py"
        })

    return prompts


def extract_from_refinement_loop(file_path: Path) -> list:
    """提取 refinement_loop.py 中的提示词"""
    content = file_path.read_text(encoding="utf-8")
    prompts = []

    match = re.search(r'SYSTEM_PROMPT\s*=\s*"""(.*?)"""', content, re.DOTALL)
    if match:
        prompts.append({
            "name": "RefinementLoop.SYSTEM_PROMPT",
            "type": "refinement",
            "content": match.group(1).strip(),
            "description": "代码修复专家 - 根据错误信息修复代码",
            "source": "app/agent/refinement_loop.py"
        })

    return prompts


def extract_from_orchestrator(file_path: Path) -> list:
    """提取 orchestrator.py 中的 Specialist 提示词"""
    content = file_path.read_text(encoding="utf-8")
    prompts = []

    # 查找所有 class xxx(Specialist) 及其 SYSTEM_PROMPT
    class_pattern = r'class\s+(\w+)\(Specialist\):.*?"""(.*?)""".*?SYSTEM_PROMPT\s*=\s*"""(.*?)"""'
    for match in re.finditer(class_pattern, content, re.DOTALL):
        class_name = match.group(1)
        class_doc = match.group(2).strip()
        system_prompt = match.group(3).strip()
        
        type_map = {
            "Architect": "architecture",
            "FrontendEngineer": "frontend",
            "BackendEngineer": "backend",
            "CodeReviewer": "review",
        }
        
        prompts.append({
            "name": f"{class_name}.SYSTEM_PROMPT",
            "type": type_map.get(class_name, "specialist"),
            "content": system_prompt,
            "description": class_doc.split('\n')[0],
            "source": "app/agent/orchestrator.py"
        })

    return prompts


def extract_from_spec_first_generator(file_path: Path) -> list:
    """提取 spec_first_generator.py 中的提示词"""
    content = file_path.read_text(encoding="utf-8")
    prompts = []

    prompt_names = [
        ("OPENAPI_SYSTEM_PROMPT", "spec", "API 架构师 - OpenAPI 3.0 规范生成"),
        ("TYPES_SYSTEM_PROMPT", "spec", "类型系统设计师 - Pydantic/TypeScript 类型定义"),
        ("DB_SCHEMA_SYSTEM_PROMPT", "spec", "数据库设计师 - SQLAlchemy ORM 建模"),
        ("CONFIG_SYSTEM_PROMPT", "spec", "配置管理专家 - 环境变量和配置文件"),
    ]

    for prompt_name, ptype, desc in prompt_names:
        match = re.search(rf'{prompt_name}\s*=\s*"""(.*?)"""', content, re.DOTALL)
        if match:
            prompts.append({
                "name": f"SpecFirstGenerator.{prompt_name}",
                "type": ptype,
                "content": match.group(1).strip(),
                "description": desc,
                "source": "app/agent/spec_first_generator.py"
            })

    return prompts


def extract_all_prompts() -> list:
    """提取所有提示词"""
    all_prompts = []

    extractors = {
        "app/utils/agent_core.py": extract_from_agent_core,
        "app/api/v1/GirlAi.py": extract_from_girlai,
        "app/api/v1/Aicode.py": extract_from_aicode,
        "app/api/v1/aicloud.py": extract_from_aicloud,
        "app/utils/workflow/task_decomposer.py": extract_from_task_decomposer,
        "app/agent/cross_validator.py": extract_from_cross_validator,
        "app/agent/refinement_loop.py": extract_from_refinement_loop,
        "app/agent/orchestrator.py": extract_from_orchestrator,
        "app/agent/spec_first_generator.py": extract_from_spec_first_generator,
    }

    for file_rel, extractor in extractors.items():
        file_path = WORKSPACE / file_rel
        if file_path.exists():
            prompts = extractor(file_path)
            all_prompts.extend(prompts)
            print(f"  从 {file_rel} 提取了 {len(prompts)} 个提示词")

    return all_prompts


def generate_markdown(prompts: list) -> str:
    """生成 Markdown 格式的提示词文档"""

    # 按类型分组
    by_type = {}
    for p in prompts:
        ptype = p["type"]
        if ptype not in by_type:
            by_type[ptype] = []
        by_type[ptype].append(p)

    type_names = {
        "system": ("系统提示词", "Agent 系统级提示词"),
        "continue": ("继续生成提示词", "暂停后继续生成的提示词"),
        "character": ("角色提示词", "虚拟角色配置"),
        "general": ("通用提示词", "通用问答"),
        "code": ("代码提示词", "代码生成相关"),
        "reasoning": ("推理提示词", "深度推理"),
        "aicloud": ("AI Cloud 提示词", "AI Cloud 智能助手相关"),
        "workflow": ("工作流提示词", "任务分解和工作流控制"),
        "validation": ("验证提示词", "代码交叉验证和评审"),
        "refinement": ("迭代提示词", "代码修复和优化循环"),
        "architecture": ("架构提示词", "项目架构设计"),
        "frontend": ("前端提示词", "前端代码生成"),
        "backend": ("后端提示词", "后端代码生成"),
        "review": ("审查提示词", "代码质量审查"),
        "spec": ("规范提示词", "API/类型/数据库/配置规范生成"),
    }

    lines = [
        "# AI 提示词文档",
        "",
        f"**更新时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"**总计**: {len(prompts)} 个提示词",
        "",
        "---",
        "",
        "## 目录",
        "",
    ]

    for ptype, (name, desc) in type_names.items():
        if ptype in by_type:
            lines.append(f"- [{name}](#{ptype}) - {desc} ({len(by_type[ptype])}个)")

    lines.append("")
    lines.append("---")
    lines.append("")

    for ptype, (name, desc) in type_names.items():
        if ptype not in by_type:
            continue

        lines.append(f"## {name}")
        lines.append("")
        lines.append(f"{desc}")
        lines.append("")

        for prompt in by_type[ptype]:
            lines.append(f"### {prompt['name']}")
            lines.append("")
            lines.append(f"**来源文件**: `{prompt.get('source', 'unknown')}`")
            if prompt.get('description'):
                lines.append(f"**用途**: {prompt['description']}")
            lines.append("")
            lines.append("```")
            lines.append(prompt['content'])
            lines.append("```")
            lines.append("")

    return "\n".join(lines)


def main():
    print("=" * 50)
    print("提示词提取器 v3")
    print("=" * 50)
    print()

    prompts = extract_all_prompts()

    print()
    print(f"共提取 {len(prompts)} 个提示词")
    print()

    # 生成文档
    md_content = generate_markdown(prompts)

    # 保存到文件
    output_file = WORKSPACE / "PROMPTS.md"
    output_file.write_text(md_content, encoding="utf-8")
    print(f"提示词文档已保存到: {output_file}")
    print()


if __name__ == "__main__":
    main()
