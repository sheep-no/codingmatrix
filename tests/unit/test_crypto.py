"""
RSA 加密模块单元测试
"""
import pytest
import tempfile
from pathlib import Path
from app.utils.crypto import RSAKeyManager, get_rsa_key_manager, init_rsa_key_manager


class TestRSAKeyManager:
    """RSA 密钥管理器测试"""

    def test_key_generation(self, tmp_path):
        """测试密钥生成"""
        key_dir = tmp_path / "keys"
        manager = RSAKeyManager(key_dir=key_dir)
        assert (key_dir / "rsa_private.pem").exists()
        assert (key_dir / "rsa_public.pem").exists()

    def test_get_public_key_pem(self, tmp_path):
        """测试获取公钥 PEM"""
        key_dir = tmp_path / "keys"
        manager = RSAKeyManager(key_dir=key_dir)
        public_key = manager.get_public_key_pem()
        assert public_key.startswith("-----BEGIN PUBLIC KEY-----")
        assert "-----END PUBLIC KEY-----" in public_key

    def test_decrypt(self, tmp_path):
        """测试解密功能"""
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding, rsa
        import base64

        key_dir = tmp_path / "keys"
        manager = RSAKeyManager(key_dir=key_dir)
        original = "sk-test-key-12345"
        
        # 使用公钥加密
        public_key = manager.public_key
        encrypted = public_key.encrypt(
            original.encode("utf-8"),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        encrypted_base64 = base64.b64encode(encrypted).decode("utf-8")
        
        # 使用私钥解密
        decrypted = manager.decrypt(encrypted_base64)
        assert decrypted == original

    def test_decrypt_invalid_key(self, tmp_path):
        """测试解密无效密钥"""
        key_dir = tmp_path / "keys"
        manager = RSAKeyManager(key_dir=key_dir)
        
        with pytest.raises(Exception):
            manager.decrypt("invalid-base64-data!!!")

    def test_key_file_permissions(self, tmp_path):
        """测试私钥文件权限"""
        import os
        key_dir = tmp_path / "keys"
        RSAKeyManager(key_dir=key_dir)
        
        private_key_path = key_dir / "rsa_private.pem"
        # 检查权限是否为 0o600
        mode = oct(os.stat(private_key_path).st_mode)[-3:]
        assert mode == "600"

    def test_key_persistence(self, tmp_path):
        """测试密钥持久化"""
        key_dir = tmp_path / "keys"
        
        # 第一次创建
        manager1 = RSAKeyManager(key_dir=key_dir)
        public_key1 = manager1.get_public_key_pem()
        
        # 第二次加载（应该从文件加载）
        manager2 = RSAKeyManager(key_dir=key_dir)
        public_key2 = manager2.get_public_key_pem()
        
        # 应该相同
        assert public_key1 == public_key2

    def test_key_length(self, tmp_path):
        """测试密钥长度"""
        key_dir = tmp_path / "keys"
        manager = RSAKeyManager(key_dir=key_dir, key_size=2048)
        key = manager.get_public_key_pem()
        assert len(key) > 100


class TestGetRSAKeyManager:
    """获取 RSA 密钥管理器测试"""

    def test_get_instance(self):
        """测试获取实例"""
        manager = get_rsa_key_manager()
        assert isinstance(manager, RSAKeyManager)

    def test_returns_singleton(self):
        """测试返回单例"""
        manager1 = get_rsa_key_manager()
        manager2 = get_rsa_key_manager()
        assert manager1 is manager2


class TestInitRSAKeyManager:
    """初始化 RSA 密钥管理器测试"""

    def test_init_with_dir(self, tmp_path):
        """测试指定目录初始化"""
        key_dir = tmp_path / "test_keys"
        manager = init_rsa_key_manager(key_dir=key_dir)
        assert isinstance(manager, RSAKeyManager)
        assert (key_dir / "rsa_private.pem").exists()

    def test_reinit_replaces_singleton(self, tmp_path):
        """测试重新初始化替换单例"""
        key_dir = tmp_path / "test_keys2"
        old_manager = get_rsa_key_manager()
        new_manager = init_rsa_key_manager(key_dir=key_dir)
        assert new_manager is not old_manager
        assert get_rsa_key_manager() is new_manager


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
