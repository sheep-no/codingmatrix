"""
测试重构后的 Aicode API

验证：
1. 代码生成 API 正常
2. 图片理解参数正确
3. 会话隔离机制
"""
import pytest
from typing import Dict, Any


class TestCodeRequestSchema:
 """测试 CodeRequest schema"""
 
 def test_basic_request(self):
 """基础代码生成请求"""
 from app.schema.codeRequest import CodeRequest
 
 req = CodeRequest(
 prompt="用 Python 写一个快速排序",
 model="Qwen/Qwen2.5-7B-Instruct",
 stream=False
 )
 
 assert req.prompt == "用 Python 写一个快速排序"
 assert req.stream == False
 assert req.enable_search == False
 assert req.enable_vision == False
 assert req.image_path is None
 
 def test_vision_request(self):
 """图片理解请求"""
 from app.schema.codeRequest import CodeRequest
 
 req = CodeRequest(
 prompt="根据这张 UI 图生成前端代码",
 enable_vision=True,
 image_path="uploads/2024/01/01/screenshot.png",
 image_analysis_prompt="请分析界面布局和技术实现建议"
 )
 
 assert req.enable_vision == True
 assert req.image_path == "uploads/2024/01/01/screenshot.png"
 assert "UI" in req.prompt
 
 def test_search_request(self):
 """联网搜索请求"""
 from app.schema.codeRequest import CodeRequest
 
 req = CodeRequest(
 prompt="写一个爬取最新新闻的脚本",
 enable_search=True,
 search_count=10,
 search_timelimit="week"
 )
 
 assert req.enable_search == True
 assert req.search_count == 10
 assert req.search_timelimit == "week"
 
 def test_combined_request(self):
 """图片 + 搜索混合请求"""
 from app.schema.codeRequest import CodeRequest
 
 req = CodeRequest(
 prompt="参考这个界面，实现类似功能",
 enable_vision=True,
 image_path="uploads/test.png",
 enable_search=True,
 use_reasoning=True,
 stream=True
 )
 
 assert req.enable_vision == True
 assert req.enable_search == True
 assert req.use_reasoning == True
 assert req.stream == True


class TestFileUploadSchema:
 """测试文件上传支持 conversation_id"""
 
 def test_upload_without_conversation_id(self):
 """不指定会话 ID 上传"""
 # 验证 file_upload.py 的 upload_file 函数接受 conversation_id 参数
 import inspect
 from app.api.v1.file_upload import upload_file
 
 sig = inspect.signature(upload_file)
 params = list(sig.parameters.keys())
 
 assert 'conversation_id' in params
 assert sig.parameters['conversation_id'].default is None
 
 def test_upload_with_conversation_id(self):
 """指定会话 ID 上传"""
 import inspect
 from app.api.v1.file_upload import upload_file
 
 sig = inspect.signature(upload_file)
 param = sig.parameters['conversation_id']
 
 # 验证是可选参数
 assert param.default is None


class TestAicodeAPI:
 """测试 Aicode API 端点"""
 
 def test_router_exists(self):
 """验证路由存在"""
 from app.api.v1.Aicode import router
 
 assert router is not None
 assert len(router.routes) > 0
 
 def test_generate_code_endpoint(self):
 """验证代码生成端点"""
 from app.api.v1.Aicode import router
 
 # 查找 /code 端点
 code_endpoint = None
 for route in router.routes:
 if hasattr(route, 'path') and route.path == '/code':
 code_endpoint = route
 break
 
 assert code_endpoint is not None
 assert code_endpoint.methods == {'POST'}


class TestVisionIntegration:
 """测试视觉功能集成"""
 
 def test_vision_is_internal_tool(self):
 """验证视觉功能是内部工具，不是独立 API"""
 import os
 from pathlib import Path
 
 vision_api_path = Path("/workspace/app/api/v1/vision_api.py")
 assert not vision_api_path.exists(), "vision_api.py 应该被删除"
 
 # 验证 vision.py 在 utils 中
 from app.utils import vision
 assert hasattr(vision, 'analyze_image')
 assert hasattr(vision, 'SUPPORTED_IMAGE_FORMATS')
 
 def test_aicode_uses_vision(self):
 """验证 Aicode 使用视觉工具（通过 get_or_parse_file）"""
 from app.api.v1.Aicode import get_or_parse_file
 import inspect
 
 # 验证函数存在
 assert callable(get_or_parse_file)
 
 # 验证函数签名
 sig = inspect.signature(get_or_parse_file)
 params = list(sig.parameters.keys())
 
 assert 'file_path' in params
 assert 'user_id' in params
 assert 'conversation_id' in params
 assert 'db' in params


class TestSessionIsolation:
 """测试会话隔离机制"""
 
 def test_file_model_has_conversation_id(self):
 """验证 File 模型添加了 conversation_id 字段"""
 from app.models.file import File
 from sqlalchemy import inspect
 
 mapper = inspect(File)
 column_names = [c.name for c in mapper.columns]
 
 assert 'conversation_id' in column_names
 
 def test_verify_file_access_function(self):
 """验证文件访问验证函数"""
 from app.api.v1.Aicode import verify_file_access
 import inspect
 
 sig = inspect.signature(verify_file_access)
 params = list(sig.parameters.keys())
 
 assert 'file_path' in params
 assert 'user_id' in params
 assert 'conversation_id' in params
 assert 'db' in params


if __name__ == "__main__":
 pytest.main([__file__, "-v", "--tb=short"])
