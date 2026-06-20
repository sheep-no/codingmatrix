"""
自定义 Skill 管理 API
允许用户上传、管理和使用自定义提示词 skill
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

from app.services.custom_skill_manager import get_skill_manager, VALID_CATEGORIES

router = APIRouter(prefix="/skills", tags=["Skills"])


# ============================================================================
# 数据模型
# ============================================================================

class SkillUploadRequest(BaseModel):
    """Skill 上传请求"""
    name: str = Field(..., description="Skill 名称（只允许字母、数字、下划线、连字符）")
    category: str = Field(..., description=f"分类，支持: {', '.join(VALID_CATEGORIES)}")
    content: str = Field(..., description="Skill 内容（Markdown 格式）")
    description: str = Field("", description="Skill 描述")


class SkillUpdateRequest(BaseModel):
    """Skill 更新请求"""
    content: str = Field(..., description="Skill 内容（Markdown 格式）")
    description: Optional[str] = Field(None, description="Skill 描述")


class SkillInfo(BaseModel):
    """Skill 信息"""
    name: str
    category: str
    file: str
    description: str
    author: str
    created_at: str
    updated_at: str
    version: int


class SkillDetail(SkillInfo):
    """Skill 详细信息（包含内容）"""
    content: str


# ============================================================================
# API 端点
# ============================================================================

@router.post("/upload", response_model=SkillInfo, summary="上传自定义 Skill")
async def upload_skill(request: SkillUploadRequest):
    """
    上传自定义 Skill
    
    - **name**: Skill 名称，只允许字母、数字、下划线、连字符，以字母开头
    - **category**: 分类，支持 orchestrator/reviewer/validation/workflow/api/tool/other
    - **content**: Skill 内容，Markdown 格式
    - **description**: 描述信息
    """
    manager = get_skill_manager()
    success, message, skill_info = manager.upload_skill(
        name=request.name,
        category=request.category,
        content=request.content,
        description=request.description,
        author="api_user"  # TODO: 从认证信息获取
    )
    
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    return skill_info


@router.get("/list", response_model=List[SkillInfo], summary="列出所有自定义 Skill")
async def list_skills(
    category: Optional[str] = None,
    author: Optional[str] = None
):
    """
    列出所有自定义 Skill
    
    - **category**: 按分类过滤（可选）
    - **author**: 按作者过滤（可选）
    """
    manager = get_skill_manager()
    skills = manager.list_skills(category=category, author=author)
    return skills


@router.get("/categories", summary="获取支持的分类列表")
async def get_categories():
    """获取支持的 Skill 分类列表"""
    return {
        "categories": VALID_CATEGORIES,
        "descriptions": {
            "orchestrator": "编排器角色提示词",
            "reviewer": "审查角色提示词",
            "validation": "验证与修复提示词",
            "workflow": "工作流提示词",
            "api": "API 层提示词",
            "tool": "工具提示词",
            "other": "其他提示词"
        }
    }


@router.get("/{name}", response_model=SkillDetail, summary="获取 Skill 详情")
async def get_skill(name: str):
    """
    获取指定 Skill 的详细信息和内容
    
    - **name**: Skill 名称
    """
    manager = get_skill_manager()
    skill = manager.get_skill(name)
    
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' 不存在")
    
    return skill


@router.put("/{name}", response_model=SkillInfo, summary="更新 Skill")
async def update_skill(name: str, request: SkillUpdateRequest):
    """
    更新 Skill 内容
    
    - **name**: Skill 名称
    - **content**: 新的 Skill 内容
    - **description**: 新的描述（可选）
    """
    manager = get_skill_manager()
    success, message, skill_info = manager.update_skill(
        name=name,
        content=request.content,
        description=request.description
    )
    
    if not success:
        if "不存在" in message:
            raise HTTPException(status_code=404, detail=message)
        raise HTTPException(status_code=400, detail=message)
    
    return skill_info


@router.delete("/{name}", summary="删除 Skill")
async def delete_skill(name: str):
    """
    删除指定 Skill
    
    - **name**: Skill 名称
    """
    manager = get_skill_manager()
    success, message = manager.delete_skill(name)
    
    if not success:
        if "不存在" in message:
            raise HTTPException(status_code=404, detail=message)
        raise HTTPException(status_code=400, detail=message)
    
    return {"message": message}


@router.post("/upload-file", response_model=SkillInfo, summary="通过文件上传 Skill")
async def upload_skill_file(
    file: UploadFile = File(...),
    name: str = Form(...),
    category: str = Form(...),
    description: str = Form("")
):
    """
    通过文件上传 Skill
    
    - **file**: Markdown 文件
    - **name**: Skill 名称
    - **category**: 分类
    - **description**: 描述
    """
    # 验证文件类型
    if not file.filename.endswith('.md'):
        raise HTTPException(status_code=400, detail="只支持 .md 文件")
    
    # 读取文件内容
    content = await file.read()
    try:
        content_str = content.decode('utf-8')
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="文件编码错误，请使用 UTF-8 编码")
    
    # 上传
    manager = get_skill_manager()
    success, message, skill_info = manager.upload_skill(
        name=name,
        category=category,
        content=content_str,
        description=description,
        author="api_user"
    )
    
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    return skill_info


@router.post("/reload", summary="重新扫描并更新提示词文档")
async def reload_prompts():
    """
    重新扫描所有 skill（包括自定义 skill）并更新 PROMPTS.md 文档
    """
    import subprocess
    
    try:
        result = subprocess.run(
            ['python3', '/workspace/.claude/skills/prompts-extractor/extract.py'],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"提取失败: {result.stderr}"
            )
        
        return {
            "message": "提示词文档已更新",
            "output": result.stdout
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="提取超时")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
