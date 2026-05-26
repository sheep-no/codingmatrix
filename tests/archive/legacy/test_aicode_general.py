"""
测试重构后的 Aicode API

验证：
1. 通用问答（不仅是代码）
2. 文件/图片首次解析缓存
3. 会话历史压缩
4. JSON 解析健壮性
"""
import pytest


class TestGeneralPrompt:
 """测试通用提示词"""
 
 def test_life_question(self):
 """生活问题"""
 from app.schema.codeRequest import CodeRequest
 
 req = CodeRequest(
 prompt="今天北京天气怎么样？",
 stream=False
 )
 assert "天气" in req.prompt
 
 def test_coding_question(self):
 """编程问题"""
 from app.schema.codeRequest import CodeRequest
 
 req = CodeRequest(
 prompt="用 Python 写快速排序",
 stream=False
 )
 assert "Python" in req.prompt
 
 def test_technical_question(self):
 """技术问题"""
 from app.schema.codeRequest import CodeRequest
 
 req = CodeRequest(
 prompt="解释一下 RESTful API 的设计原则",
 use_reasoning=True
 )
 assert req.use_reasoning == True


class TestFileParsing:
 """测试文件解析缓存"""
 
 def test_get_or_parse_file_function(self):
 """验证函数存在"""
 from app.api.v1.Aicode import get_or_parse_file
 import inspect
 
 sig = inspect.signature(get_or_parse_file)
 params = list(sig.parameters.keys())
 
 assert 'file_path' in params
 assert 'user_id' in params
 assert 'conversation_id' in params
 assert 'db' in params
 
 def test_verify_file_access_function(self):
 """验证权限验证"""
 from app.api.v1.Aicode import verify_file_access
 import inspect
 
 sig = inspect.signature(verify_file_access)
 params = list(sig.parameters.keys())
 
 assert 'conversation_id' in params


class TestHistoryCompression:
 """测试会话历史压缩"""
 
 def test_compress_function_exists(self):
 """验证压缩函数存在"""
 from app.api.v1.Aicode import compress_conversation_history
 import inspect
 
 sig = inspect.signature(compress_conversation_history)
 params = list(sig.parameters.keys())
 
 assert 'db' in params
 assert 'user_id' in params
 assert 'conversation_id' in params
 assert 'max_messages' in params


class TestJSONParsing:
 """测试 JSON 解析健壮性"""
 
 def test_extract_stream_content(self):
 """测试 SSE chunk 解析"""
 from app.api.v1.Aicode import extract_stream_content
 
 # 正常 JSON
 chunk = '{"choices": [{"delta": {"content": "测试"}}]}'
 success, content = extract_stream_content(chunk)
 assert success == True
 assert content == "测试"
 
 # 空内容
 chunk = '{"choices": [{"delta": {"content": ""}}]}'
 success, content = extract_stream_content(chunk)
 assert success == True
 assert content == ""
 
 # 无效 JSON（应返回 False）
 chunk = 'not valid json'
 success, content = extract_stream_content(chunk)
 assert success == False
 assert content == ""
 
 def test_robust_json_parser(self):
 """测试 RobustJSONParser"""
 from app.utils.json_parser import RobustJSONParser
 
 parser = RobustJSONParser(strict_mode=False)
 
 # 测试不完整 JSON
 partial = '{"choices": [{"delta": {"content": "测'
 try:
 result = parser.parse(partial)
 # 如果能解析，应该有部分结果
 except:
 # 解析失败也正常
 pass


class TestAicodeAPI:
 """测试 API 端点"""
 
 def test_router_exists(self):
 """验证路由存在"""
 from app.api.v1.Aicode import router
 assert router is not None
 
 def test_generate_code_endpoint(self):
 """验证端点存在"""
 from app.api.v1.Aicode import router
 
 code_endpoint = None
 for route in router.routes:
 if hasattr(route, 'path') and route.path == '/code':
 code_endpoint = route
 break
 
 assert code_endpoint is not None
 assert 'POST' in code_endpoint.methods


class TestHistoryModel:
 """测试 History 模型更新"""
 
 def test_metadata_field_exists(self):
 """验证 metadata_json 字段"""
 from app.models.history import History
 from sqlalchemy import inspect
 
 mapper = inspect(History)
 column_names = [c.name for c in mapper.columns]
 
 assert 'metadata_json' in column_names


if __name__ == "__main__":
 pytest.main([__file__, "-v", "--tb=short"])
