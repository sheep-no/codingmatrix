#!/usr/bin/env python3
"""
提示词提取器 v5
自动扫描项目中的所有提示词并生成统一文档
支持用户自定义 skill
"""
import json
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# 项目根目录
WORKSPACE = Path("/workspace")

# 自定义 skill 存储目录
CUSTOM_SKILLS_DIR = WORKSPACE / "data" / "custom_skills"
CUSTOM_SKILLS_METADATA = CUSTOM_SKILLS_DIR / "_metadata.json"

# ============================================================================
# 提示词分类定义
# ============================================================================

PROMPT_CATEGORIES = {
    "orchestrator": {
        "name": "编排器角色提示词",
        "description": "项目生成流程中各角色的系统提示词",
        "icon": "🎯"
    },
    "reviewer": {
        "name": "审查角色提示词",
        "description": "代码审查和质量评估相关提示词",
        "icon": "🔍"
    },
    "spec": {
        "name": "规范生成提示词",
        "description": "API/类型/数据库/配置规范生成提示词",
        "icon": "📋"
    },
    "validation": {
        "name": "验证与修复提示词",
        "description": "代码验证、交叉评审、修复循环提示词",
        "icon": "✅"
    },
    "workflow": {
        "name": "工作流提示词",
        "description": "任务分解和工作流控制提示词",
        "icon": "⚙️"
    },
    "api": {
        "name": "API 层提示词",
        "description": "对外 API 接口使用的提示词模板",
        "icon": "🌐"
    },
    "tool": {
        "name": "工具提示词",
        "description": "内联的简短工具提示词",
        "icon": "🔧"
    },
    "other": {
        "name": "其他提示词",
        "description": "未分类的提示词",
        "icon": "📦"
    }
}

# ============================================================================
# .md 文件提示词提取
# ============================================================================

def extract_md_prompts() -> List[Dict]:
    """从 .md 文件提取提示词"""
    prompts = []
    
    # Orchestrator 角色提示词
    orchestrator_dir = WORKSPACE / ".claude/skills/orchestrator"
    if orchestrator_dir.exists():
        for md_file in orchestrator_dir.glob("*.md"):
            content = md_file.read_text(encoding="utf-8")
            name = md_file.stem
            
            # 判断类型
            if "enhanced_" in name:
                category = "orchestrator"
                desc = f"增强版{name.replace('enhanced_', '').replace('_', ' ').title()}提示词"
            elif "reviewer" in name and name != "code_reviewer_prompt":
                category = "reviewer"
                desc = f"{name.replace('_prompt', '').replace('_', ' ').title()}审查提示词"
            else:
                category = "orchestrator"
                desc = f"{name.replace('_prompt', '').replace('_', ' ').title()}角色提示词"
            
            prompts.append({
                "name": name,
                "category": category,
                "content": content,
                "description": desc,
                "source": str(md_file.relative_to(WORKSPACE)),
                "type": "md_file"
            })
    
    # 项目生成提示词
    project_gen_dir = WORKSPACE / ".claude/skills/project_generation"
    if project_gen_dir.exists():
        for md_file in project_gen_dir.glob("*.md"):
            content = md_file.read_text(encoding="utf-8")
            name = md_file.stem
            
            if "system" in name:
                category = "orchestrator"
                desc = "项目生成系统提示词"
            elif "resume" in name:
                category = "workflow"
                desc = "继续生成提示词"
            elif "directory" in name:
                category = "tool"
                desc = "目录状态提示词"
            else:
                category = "other"
                desc = f"项目生成{name.replace('_', ' ')}提示词"
            
            prompts.append({
                "name": name,
                "category": category,
                "content": content,
                "description": desc,
                "source": str(md_file.relative_to(WORKSPACE)),
                "type": "md_file"
            })
    
    # 验证与修复提示词
    validation_dir = WORKSPACE / ".claude/skills/validation"
    if validation_dir.exists():
        for md_file in validation_dir.glob("*.md"):
            content = md_file.read_text(encoding="utf-8")
            name = md_file.stem
            
            prompts.append({
                "name": name,
                "category": "validation",
                "content": content,
                "description": f"{name.replace('_prompt', '').replace('_', ' ').title()}验证提示词",
                "source": str(md_file.relative_to(WORKSPACE)),
                "type": "md_file"
            })
    
    # 认知技能提示词
    skills_dir = WORKSPACE / ".claude/skills/skills"
    if skills_dir.exists():
        for md_file in skills_dir.glob("*.md"):
            content = md_file.read_text(encoding="utf-8")
            name = md_file.stem
            
            prompts.append({
                "name": name,
                "category": "other",
                "content": content,
                "description": f"{name.replace('_', ' ').title()}技能提示词",
                "source": str(md_file.relative_to(WORKSPACE)),
                "type": "md_file"
            })
    
    # 工作流规划器提示词
    workflow_dir = WORKSPACE / "skills/workflow-planner"
    if workflow_dir.exists():
        for md_file in workflow_dir.glob("*.md"):
            if md_file.name == "SKILL.md":
                continue
            content = md_file.read_text(encoding="utf-8")
            name = md_file.stem
            
            prompts.append({
                "name": name,
                "category": "workflow",
                "content": content,
                "description": "工作流规划器系统提示词",
                "source": str(md_file.relative_to(WORKSPACE)),
                "type": "md_file"
            })
    
    # 自定义 skill 提示词
    custom_prompts = extract_custom_skills()
    prompts.extend(custom_prompts)
    
    return prompts


def extract_custom_skills() -> List[Dict]:
    """从用户自定义 skill 目录提取提示词"""
    prompts = []
    
    if not CUSTOM_SKILLS_DIR.exists():
        return prompts
    
    # 从元数据文件加载
    if CUSTOM_SKILLS_METADATA.exists():
        try:
            metadata = json.loads(CUSTOM_SKILLS_METADATA.read_text(encoding="utf-8"))
            skills = metadata.get("skills", [])
            
            for skill_info in skills:
                name = skill_info.get("name", "")
                category = skill_info.get("category", "other")
                file_path = CUSTOM_SKILLS_DIR / skill_info.get("file", "")
                description = skill_info.get("description", "")
                author = skill_info.get("author", "unknown")
                
                if file_path.exists():
                    content = file_path.read_text(encoding="utf-8")
                    prompts.append({
                        "name": f"custom_{name}",
                        "category": category,
                        "content": content,
                        "description": f"[自定义] {description}" if description else f"[自定义] {name}",
                        "source": f"data/custom_skills/{skill_info.get('file', '')}",
                        "type": "custom_skill",
                        "author": author,
                        "version": skill_info.get("version", 1)
                    })
            
            if skills:
                print(f"  从自定义 skill 目录提取了 {len(skills)} 个提示词")
        except Exception as e:
            print(f"  读取自定义 skill 元数据失败: {e}")
    
    return prompts

# ============================================================================
# Python 代码提示词提取
# ============================================================================

def extract_python_prompts() -> List[Dict]:
    """从 Python 代码中提取提示词"""
    prompts = []
    
    # 定义要扫描的文件和对应的提取函数
    scan_targets = [
        ("app/agent/spec_first_generator.py", extract_spec_first_prompts),
        ("app/agent/refinement_loop.py", extract_refinement_prompts),
        ("app/agent/cross_validator.py", extract_cross_validator_prompts),
        ("app/agent/code_patcher.py", extract_code_patcher_prompts),
        ("app/agent/error_classifier.py", extract_error_classifier_prompts),
        ("app/agent/error_recovery.py", extract_error_recovery_prompts),
        ("app/agent/dependency_graph_validator.py", extract_dependency_graph_prompts),
        ("app/agent/orchestrator_files.py", extract_orchestrator_files_prompts),
        ("app/agent/orchestrator_generation/spec_first_generate.py", extract_spec_first_generate_prompts),
        ("app/agent/orchestrator_generation/incremental_modify.py", extract_incremental_modify_prompts),
        ("app/agent/ppt_agent.py", extract_ppt_agent_prompts),
        ("app/agent/multi_angle_review.py", extract_multi_angle_review_prompts),
        ("app/agent/agent_executor.py", extract_agent_executor_prompts),
        ("app/agent/react_engine.py", extract_react_engine_prompts),
        ("app/adapter/model_adapter.py", extract_model_adapter_prompts),
        ("app/api/v1/Aicode.py", extract_aicode_prompts),
        ("app/api/v1/aicloud.py", extract_aicloud_prompts),
        ("app/api/v1/GirlAi.py", extract_girlai_prompts),
        ("app/agent/orchestrator_requirements/llm_prompts.py", extract_orchestrator_requirements_prompts),
    ]
    
    for file_rel, extractor in scan_targets:
        file_path = WORKSPACE / file_rel
        if file_path.exists():
            try:
                content = file_path.read_text(encoding="utf-8")
                extracted = extractor(content, file_rel)
                prompts.extend(extracted)
                if extracted:
                    print(f"  从 {file_rel} 提取了 {len(extracted)} 个提示词")
            except Exception as e:
                print(f"  从 {file_rel} 提取失败: {e}")
    
    return prompts


def extract_spec_first_prompts(content: str, file_rel: str) -> List[Dict]:
    """提取 spec_first_generator.py 中的提示词"""
    prompts = []
    
    patterns = [
        (r'OPENAPI_SYSTEM_PROMPT\s*=\s*"""(.*?)"""', "spec", "API 架构师提示词"),
        (r'TYPES_SYSTEM_PROMPT\s*=\s*"""(.*?)"""', "spec", "类型系统设计师提示词"),
        (r'DB_SCHEMA_SYSTEM_PROMPT\s*=\s*"""(.*?)"""', "spec", "数据库设计师提示词"),
        (r'CONFIG_SYSTEM_PROMPT\s*=\s*"""(.*?)"""', "spec", "配置管理专家提示词"),
    ]
    
    for pattern, category, desc in patterns:
        match = re.search(pattern, content, re.DOTALL)
        if match:
            name = pattern.split('=')[0].strip().split('\\s')[0]
            prompts.append({
                "name": name,
                "category": category,
                "content": match.group(1).strip(),
                "description": desc,
                "source": file_rel,
                "type": "python_variable"
            })
    
    return prompts


def extract_refinement_prompts(content: str, file_rel: str) -> List[Dict]:
    """提取 refinement_loop.py 中的提示词"""
    prompts = []
    
    match = re.search(r'SYSTEM_PROMPT\s*=\s*"""(.*?)"""', content, re.DOTALL)
    if match:
        prompts.append({
            "name": "RefinementLoop.SYSTEM_PROMPT",
            "category": "validation",
            "content": match.group(1).strip(),
            "description": "代码修复专家提示词",
            "source": file_rel,
            "type": "python_variable"
        })
    
    return prompts


def extract_cross_validator_prompts(content: str, file_rel: str) -> List[Dict]:
    """提取 cross_validator.py 中的提示词"""
    prompts = []
    
    match = re.search(r'JUDGE_SYSTEM_PROMPT\s*=\s*"""(.*?)"""', content, re.DOTALL)
    if match:
        prompts.append({
            "name": "CrossValidator.JUDGE_SYSTEM_PROMPT",
            "category": "validation",
            "content": match.group(1).strip(),
            "description": "技术评审专家提示词",
            "source": file_rel,
            "type": "python_variable"
        })
    
    return prompts


def extract_code_patcher_prompts(content: str, file_rel: str) -> List[Dict]:
    """提取 code_patcher.py 中的提示词"""
    prompts = []
    
    # 查找函数内的 system_prompt
    match = re.search(r'system_prompt\s*=\s*f?"""(.*?)"""', content, re.DOTALL)
    if match:
        prompts.append({
            "name": "CodePatcher.system_prompt",
            "category": "validation",
            "content": match.group(1).strip(),
            "description": "代码补丁生成专家提示词",
            "source": file_rel,
            "type": "python_variable"
        })
    
    return prompts


def extract_error_classifier_prompts(content: str, file_rel: str) -> List[Dict]:
    """提取 error_classifier.py 中的提示词"""
    prompts = []
    
    match = re.search(r'system_prompt\s*=\s*f?"""(.*?)"""', content, re.DOTALL)
    if match:
        prompts.append({
            "name": "ErrorClassifier.system_prompt",
            "category": "validation",
            "content": match.group(1).strip(),
            "description": "错误分类专家提示词",
            "source": file_rel,
            "type": "python_variable"
        })
    
    return prompts


def extract_error_recovery_prompts(content: str, file_rel: str) -> List[Dict]:
    """提取 error_recovery.py 中的提示词"""
    prompts = []
    
    # 查找所有 system_prompt 定义
    matches = re.finditer(r'system_prompt\s*=\s*f?"""(.*?)"""', content, re.DOTALL)
    for i, match in enumerate(matches):
        prompts.append({
            "name": f"ErrorRecovery.system_prompt_{i+1}",
            "category": "validation",
            "content": match.group(1).strip(),
            "description": f"代码修复专家提示词（场景 {i+1}）",
            "source": file_rel,
            "type": "python_variable"
        })
    
    return prompts


def extract_dependency_graph_prompts(content: str, file_rel: str) -> List[Dict]:
    """提取 dependency_graph_validator.py 中的提示词"""
    prompts = []
    
    # 查找 _build_system_prompt 函数
    match = re.search(r'def _build_system_prompt\(.*?\).*?"""(.*?)"""', content, re.DOTALL)
    if match:
        prompts.append({
            "name": "DependencyGraphValidator._build_system_prompt",
            "category": "validation",
            "content": match.group(1).strip(),
            "description": "依赖图验证专家提示词",
            "source": file_rel,
            "type": "python_function"
        })
    
    return prompts


def extract_orchestrator_files_prompts(content: str, file_rel: str) -> List[Dict]:
    """提取 orchestrator_files.py 中的提示词"""
    prompts = []
    
    # 查找所有 system_prompt 定义
    matches = re.finditer(r'system_prompt\s*=\s*f?"""(.*?)"""', content, re.DOTALL)
    for i, match in enumerate(matches):
        prompts.append({
            "name": f"OrchestratorFiles.system_prompt_{i+1}",
            "category": "orchestrator",
            "content": match.group(1).strip(),
            "description": f"软件工程师提示词（文件生成 {i+1}）",
            "source": file_rel,
            "type": "python_variable"
        })
    
    return prompts


def extract_spec_first_generate_prompts(content: str, file_rel: str) -> List[Dict]:
    """提取 spec_first_generate.py 中的提示词"""
    prompts = []
    
    # 查找所有内联 system_prompt
    patterns = [
        (r'system_prompt\s*=\s*"""(你是一个代码文件类型推断器.*?)"""', "tool", "文件类型推断器"),
        (r'system_prompt\s*=\s*"""(你是一个代码语言检测器.*?)"""', "tool", "代码语言检测器"),
        (r'system_prompt\s*=\s*"""(你是一个代码重构专家.*?)"""', "tool", "代码重构专家"),
    ]
    
    for pattern, category, desc in patterns:
        match = re.search(pattern, content, re.DOTALL)
        if match:
            prompts.append({
                "name": f"SpecFirstGenerate.{desc}",
                "category": category,
                "content": match.group(1).strip(),
                "description": desc,
                "source": file_rel,
                "type": "python_variable"
            })
    
    return prompts


def extract_incremental_modify_prompts(content: str, file_rel: str) -> List[Dict]:
    """提取 incremental_modify.py 中的提示词"""
    prompts = []
    
    match = re.search(r'system_prompt\s*=\s*"""(.*?)"""', content, re.DOTALL)
    if match:
        prompts.append({
            "name": "IncrementalModify.system_prompt",
            "category": "orchestrator",
            "content": match.group(1).strip(),
            "description": "增量修改架构师提示词",
            "source": file_rel,
            "type": "python_variable"
        })
    
    return prompts


def extract_ppt_agent_prompts(content: str, file_rel: str) -> List[Dict]:
    """提取 ppt_agent.py 中的提示词"""
    prompts = []
    
    patterns = [
        (r'system_prompt\s*=\s*"""(你是 PPT 制作助手.*?)"""', "tool", "PPT 制作助手"),
        (r'system_prompt\s*=\s*"""(你是一个 JSON 修复助手.*?)"""', "tool", "JSON 修复助手"),
        (r'system_prompt\s*=\s*"""(你是 PPT 修改助手.*?)"""', "tool", "PPT 修改助手"),
    ]
    
    for pattern, category, desc in patterns:
        match = re.search(pattern, content, re.DOTALL)
        if match:
            prompts.append({
                "name": f"PPTAgent.{desc}",
                "category": category,
                "content": match.group(1).strip(),
                "description": desc,
                "source": file_rel,
                "type": "python_variable"
            })
    
    return prompts


def extract_multi_angle_review_prompts(content: str, file_rel: str) -> List[Dict]:
    """提取 multi_angle_review.py 中的提示词"""
    prompts = []
    
    # 这些是从 .md 文件加载的，但我们可以提取变量定义
    matches = re.finditer(r'(\w+_SYS_PROMPT)\s*=\s*"""(.*?)"""', content, re.DOTALL)
    for match in matches:
        name = match.group(1)
        prompts.append({
            "name": f"MultiAngleReview.{name}",
            "category": "reviewer",
            "content": match.group(2).strip(),
            "description": f"多角度审查{name.replace('SYS_PROMPT', '').replace('_', ' ').title()}提示词",
            "source": file_rel,
            "type": "python_variable"
        })
    
    return prompts


def extract_agent_executor_prompts(content: str, file_rel: str) -> List[Dict]:
    """提取 agent_executor.py 中的提示词"""
    prompts = []
    
    match = re.search(r'_ANALYSIS_SYSTEM_PROMPT\s*=\s*"""(.*?)"""', content, re.DOTALL)
    if match:
        prompts.append({
            "name": "AgentExecutor._ANALYSIS_SYSTEM_PROMPT",
            "category": "tool",
            "content": match.group(1).strip(),
            "description": "代码分析专家提示词",
            "source": file_rel,
            "type": "python_variable"
        })
    
    return prompts


def extract_react_engine_prompts(content: str, file_rel: str) -> List[Dict]:
    """提取 react_engine.py 中的提示词"""
    prompts = []
    
    # 查找 _build_system_prompt 函数
    match = re.search(r'def _build_system_prompt\(.*?\).*?"""(.*?)"""', content, re.DOTALL)
    if match:
        prompts.append({
            "name": "ReActEngine._build_system_prompt",
            "category": "orchestrator",
            "content": match.group(1).strip(),
            "description": "ReAct 引擎系统提示词构建器",
            "source": file_rel,
            "type": "python_function"
        })
    
    return prompts


def extract_model_adapter_prompts(content: str, file_rel: str) -> List[Dict]:
    """提取 model_adapter.py 中的提示词"""
    prompts = []
    
    match = re.search(r'def build_system_prompt\(.*?\).*?"""(.*?)"""', content, re.DOTALL)
    if match:
        prompts.append({
            "name": "ModelAdapter.build_system_prompt",
            "category": "orchestrator",
            "content": match.group(1).strip(),
            "description": "AI 编程助手提示词",
            "source": file_rel,
            "type": "python_function"
        })
    
    return prompts


def extract_aicode_prompts(content: str, file_rel: str) -> List[Dict]:
    """提取 Aicode.py 中的提示词"""
    prompts = []
    
    patterns = [
        (r'GENERAL_PROMPT\s*=\s*"""(.*?)"""', "api", "通用问答提示词模板"),
        (r'CODE_PROMPT\s*=\s*"""(.*?)"""', "api", "代码专用提示词模板"),
        (r'REASONING_PROMPT\s*=\s*"""(.*?)"""', "api", "推理增强提示词模板"),
    ]
    
    for pattern, category, desc in patterns:
        match = re.search(pattern, content, re.DOTALL)
        if match:
            name = pattern.split('=')[0].strip().split('\\s')[0]
            prompts.append({
                "name": name,
                "category": category,
                "content": match.group(1).strip(),
                "description": desc,
                "source": file_rel,
                "type": "python_variable"
            })
    
    return prompts


def extract_aicloud_prompts(content: str, file_rel: str) -> List[Dict]:
    """提取 aicloud.py 中的提示词"""
    prompts = []
    
    # 查找函数内的 system_prompt
    matches = re.finditer(r'system_prompt\s*=\s*"""(.*?)"""', content, re.DOTALL)
    for i, match in enumerate(matches):
        prompts.append({
            "name": f"AICloud.system_prompt_{i+1}",
            "category": "api",
            "content": match.group(1).strip(),
            "description": f"AICloud 智能助手提示词（版本 {i+1}）",
            "source": file_rel,
            "type": "python_variable"
        })
    
    return prompts


def extract_girlai_prompts(content: str, file_rel: str) -> List[Dict]:
    """提取 GirlAi.py 中的角色配置"""
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
        
        import json
        prompts.append({
            "name": f"CHARACTER_{role_id.upper()}",
            "category": "api",
            "content": json.dumps(role_info, ensure_ascii=False, indent=2),
            "description": f"角色: {role_info['name']}",
            "source": file_rel,
            "type": "python_variable"
        })
    
    return prompts


def extract_orchestrator_requirements_prompts(content: str, file_rel: str) -> List[Dict]:
    """提取 orchestrator_requirements/llm_prompts.py 中的提示词"""
    prompts = []
    
    match = re.search(r'def llm_system_prompt\(.*?\).*?"""(.*?)"""', content, re.DOTALL)
    if match:
        prompts.append({
            "name": "OrchestratorRequirements.llm_system_prompt",
            "category": "orchestrator",
            "content": match.group(1).strip(),
            "description": "全栈架构顾问提示词",
            "source": file_rel,
            "type": "python_function"
        })
    
    return prompts

# ============================================================================
# 文档生成
# ============================================================================

def generate_markdown(md_prompts: List[Dict], python_prompts: List[Dict]) -> str:
    """生成 Markdown 格式的提示词文档"""
    
    all_prompts = md_prompts + python_prompts
    
    # 按分类分组
    by_category: Dict[str, List[Dict]] = {}
    for p in all_prompts:
        cat = p["category"]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(p)
    
    lines = [
        "# AI 提示词文档",
        "",
        f"**更新时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"**总计**: {len(all_prompts)} 个提示词",
        "",
        "---",
        "",
        "## 目录",
        "",
    ]
    
    # 生成目录
    for cat_key, cat_info in PROMPT_CATEGORIES.items():
        if cat_key in by_category:
            count = len(by_category[cat_key])
            lines.append(f"- [{cat_info['icon']} {cat_info['name']}](#{cat_key}) - {cat_info['description']} ({count}个)")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # 生成各分类内容
    for cat_key, cat_info in PROMPT_CATEGORIES.items():
        if cat_key not in by_category:
            continue
        
        prompts = by_category[cat_key]
        
        lines.append(f"## {cat_info['icon']} {cat_info['name']}")
        lines.append("")
        lines.append(f"{cat_info['description']}")
        lines.append("")
        
        # 按来源分组
        by_source: Dict[str, List[Dict]] = {}
        for p in prompts:
            source = p.get("source", "unknown")
            if source not in by_source:
                by_source[source] = []
            by_source[source].append(p)
        
        for source, source_prompts in by_source.items():
            lines.append(f"### 来源: `{source}`")
            lines.append("")
            
            for prompt in source_prompts:
                lines.append(f"#### {prompt['name']}")
                lines.append("")
                if prompt.get('description'):
                    lines.append(f"**用途**: {prompt['description']}")
                if prompt.get('author'):
                    lines.append(f"**作者**: {prompt['author']}")
                if prompt.get('version'):
                    lines.append(f"**版本**: v{prompt['version']}")
                lines.append("")
                
                # 根据内容长度决定展示方式
                content = prompt['content']
                if len(content) > 2000:
                    lines.append("<details>")
                    lines.append(f"<summary>点击展开完整内容 ({len(content)} 字符)</summary>")
                    lines.append("")
                    lines.append("```")
                    lines.append(content)
                    lines.append("```")
                    lines.append("")
                    lines.append("</details>")
                else:
                    lines.append("```")
                    lines.append(content)
                    lines.append("```")
                lines.append("")
    
    # 添加提示词架构说明
    lines.extend([
        "---",
        "",
        "## 提示词架构",
        "",
        "本项目采用**分层加载**架构管理提示词：",
        "",
        "1. **.md 文件层** (`.claude/skills/orchestrator/*.md`) - 提示词的权威来源",
        "2. **加载器层** (`app/utils/prompt_loader.py`) - 提供 `load_xxx_prompt()` 函数",
        "3. **Agent 层** (`app/agent/*.py`) - 通过 `SYSTEM_PROMPT` property 调用加载器",
        "4. **内联层** - 简短的工具提示词直接以字符串字面量写在代码中",
        "",
        "### 提示词加载流程",
        "",
        "```",
        "Agent 初始化",
        "  ↓",
        "访问 self.SYSTEM_PROMPT (property)",
        "  ↓",
        "调用 load_xxx_prompt() 函数",
        "  ↓",
        "读取 .md 文件内容",
        "  ↓",
        "失败时使用 _fallback_prompt() 兜底",
        "```",
        "",
    ])
    
    return "\n".join(lines)

# ============================================================================
# 主函数
# ============================================================================

def main():
    print("=" * 60)
    print("提示词提取器 v5 (支持自定义 Skill)")
    print("=" * 60)
    print()
    
    # 1. 提取 .md 文件提示词（包含自定义 skill）
    print("【1/3】扫描 .md 文件提示词...")
    md_prompts = extract_md_prompts()
    custom_count = len([p for p in md_prompts if p.get("type") == "custom_skill"])
    builtin_count = len(md_prompts) - custom_count
    print(f"  共提取 {builtin_count} 个内置 .md 文件提示词")
    if custom_count > 0:
        print(f"  共提取 {custom_count} 个用户自定义 skill")
    print()
    
    # 2. 提取 Python 代码提示词
    print("【2/3】扫描 Python 代码提示词...")
    python_prompts = extract_python_prompts()
    print(f"  共提取 {len(python_prompts)} 个 Python 代码提示词")
    print()
    
    # 3. 生成文档
    print("【3/3】生成提示词文档...")
    md_content = generate_markdown(md_prompts, python_prompts)
    
    # 保存到文件
    output_file = WORKSPACE / "PROMPTS.md"
    output_file.write_text(md_content, encoding="utf-8")
    print(f"  提示词文档已保存到: {output_file}")
    print()
    
    # 统计信息
    total = len(md_prompts) + len(python_prompts)
    print("=" * 60)
    print(f"提取完成！共 {total} 个提示词")
    print("=" * 60)


if __name__ == "__main__":
    main()
