"""
测试重构后的 PPTX 和 Kolors API

验证：
1. PPTX 会话历史支持
2. PPTX 素材文件权限验证
3. Kolors 图片缓存机制
4. Kolors 会话历史支持
5. AiProjectCode conversation_id 支持
"""
import pytest
import json


class TestPptxRefactor:
    """测试 PPTX 重构"""
    
    def test_ppt_request_has_conversation_id(self):
        """验证 PptRequest 添加 conversation_id"""
        from app.schema.ppxRequest import PptRequest
        
        req = PptRequest(
            prompt="生成一个产品介绍 PPT",
            model="THUDM/GLM-Z1-9B-0414",
            conversation_id=123,
            material_file_ids=[1, 2, 3]
        )
        
        assert req.conversation_id == 123
        assert req.material_file_ids == [1, 2, 3]
    
    def test_pptx_router_exists(self):
        """验证路由存在"""
        from app.api.v1.aiGeneratorPptx import router
        assert router is not None
    
    def test_compress_history_imported(self):
        """验证导入了 compress_conversation_history"""
        from app.api.v1.aiGeneratorPptx import compress_conversation_history
        assert callable(compress_conversation_history)
    
    def test_verify_file_access_imported(self):
        """验证导入了 verify_file_access"""
        from app.api.v1.aiGeneratorPptx import verify_file_access
        assert callable(verify_file_access)


class TestKolorsRefactor:
    """测试 Kolors 重构"""
    
    def test_text_to_image_request_has_conversation_id(self):
        """验证文生图请求添加 conversation_id"""
        from app.api.v1.kolors_api import TextToImageRequest
        
        req = TextToImageRequest(
            prompt="一个穿着汉服的女孩",
            conversation_id=123,
            seed=42
        )
        
        assert req.conversation_id == 123
        assert req.seed == 42
    
    def test_image_to_image_request_has_conversation_id(self):
        """验证图生图请求添加 conversation_id"""
        from app.api.v1.kolors_api import ImageToImageRequest
        
        req = ImageToImageRequest(
            prompt="让这个女孩笑起来",
            image_path="uploads/test.png",
            conversation_id=123
        )
        
        assert req.conversation_id == 123
        assert req.image_path == "uploads/test.png"
    
    def test_cache_functions_exist(self):
        """验证缓存函数存在"""
        from app.api.v1.kolors_api import get_cached_image, cache_image_to_history
        import inspect
        
        # get_cached_image
        sig = inspect.signature(get_cached_image)
        params = list(sig.parameters.keys())
        assert 'db' in params
        assert 'user_id' in params
        assert 'prompt' in params
        assert 'seed' in params
        
        # cache_image_to_history
        sig = inspect.signature(cache_image_to_history)
        params = list(sig.parameters.keys())
        assert 'db' in params
        assert 'conversation_id' in params
    
    def test_kolors_router_exists(self):
        """验证路由存在"""
        from app.api.v1.kolors_api import router
        assert router is not None
    
    def test_kolors_imports_compress_history(self):
        """验证导入了 compress_conversation_history"""
        from app.api.v1.kolors_api import compress_conversation_history
        assert callable(compress_conversation_history)


class TestAiProjectCode:
    """测试 AiProjectCode 更新"""
    
    def test_generate_request_has_conversation_id(self):
        """验证 GenerateRequest 添加 conversation_id"""
        from app.schema.codeRequest import GenerateRequest
        
        req = GenerateRequest(
            requirement="写一个 Todo 应用",
            session_id="sess_123",
            conversation_id=456
        )
        
        assert req.session_id == "sess_123"
        assert req.conversation_id == 456
    
    def test_session_id_still_exists(self):
        """验证 session_id 仍然存在（用于文件锁）"""
        from app.schema.codeRequest import GenerateRequest
        
        req = GenerateRequest(
            requirement="写一个博客系统",
            session_id="unique_session_789"
        )
        
        assert req.session_id == "unique_session_789"
        # conversation_id 是可选的
        assert req.conversation_id is None


class TestHistoryModel:
    """测试 History 模型 metadata_json"""
    
    def test_metadata_json_field_exists(self):
        """验证 metadata_json 字段存在"""
        from app.models.history import History
        from sqlalchemy import inspect
        
        mapper = inspect(History)
        column_names = [c.name for c in mapper.columns]
        
        assert 'metadata_json' in column_names


class TestIntegration:
    """集成测试"""
    
    def test_all_apis_use_same_compress_function(self):
        """验证所有 API 使用同一个 compress_conversation_history"""
        from app.api.v1.Aicode import compress_conversation_history as aicode_compress
        from app.api.v1.aiGeneratorPptx import compress_conversation_history as pptx_compress
        from app.api.v1.kolors_api import compress_conversation_history as kolors_compress
        
        # 应该是同一个函数
        assert aicode_compress is pptx_compress
        assert pptx_compress is kolors_compress
    
    def test_all_apis_use_same_verify_file_access(self):
        """验证所有 API 使用同一个 verify_file_access"""
        from app.api.v1.Aicode import verify_file_access as aicode_verify
        from app.api.v1.aiGeneratorPptx import verify_file_access as pptx_verify
        
        # 应该是同一个函数
        assert aicode_verify is pptx_verify


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
