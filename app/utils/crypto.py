"""
RSA 加密工具模块

用于 API Key 安全传输：
- 前端使用公钥加密 API Key
- 后端使用私钥解密
- 密钥对在应用启动时生成或加载
"""
import os
import base64
import logging
from pathlib import Path
from typing import Optional, Tuple
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)


class RSAKeyManager:
    """RSA 密钥管理器"""
    
    def __init__(self, key_dir: Optional[Path] = None, key_size: int = 2048):
        self.key_size = key_size
        self.key_dir = key_dir or Path("keys")
        self.private_key_path = self.key_dir / "rsa_private.pem"
        self.public_key_path = self.key_dir / "rsa_public.pem"
        
        self._private_key: Optional[rsa.RSAPrivateKey] = None
        self._public_key: Optional[rsa.RSAPublicKey] = None
        
        # 初始化：加载或生成密钥对
        self._initialize_keys()
    
    def _initialize_keys(self):
        """加载或生成密钥对"""
        if self.private_key_path.exists() and self.public_key_path.exists():
            self._load_keys()
            logger.info("RSA 密钥对已从文件加载")
        else:
            self._generate_keys()
            self._save_keys()
            logger.info("RSA 密钥对已生成并保存")
    
    def _generate_keys(self):
        """生成新的 RSA 密钥对"""
        self._private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=self.key_size,
            backend=default_backend()
        )
        self._public_key = self._private_key.public_key()
        logger.info(f"生成 {self.key_size}-bit RSA 密钥对")
    
    def _load_keys(self):
        """从文件加载密钥对"""
        try:
            with open(self.private_key_path, "rb") as f:
                self._private_key = serialization.load_pem_private_key(
                    f.read(),
                    password=None,
                    backend=default_backend()
                )
            
            with open(self.public_key_path, "rb") as f:
                self._public_key = serialization.load_pem_public_key(
                    f.read(),
                    backend=default_backend()
                )
        except Exception as e:
            logger.error(f"加载 RSA 密钥失败：{e}")
            # 如果加载失败，重新生成
            self._generate_keys()
            self._save_keys()
    
    def _save_keys(self):
        """保存密钥对到文件"""
        self.key_dir.mkdir(parents=True, exist_ok=True)
        
        private_pem = self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        with open(self.private_key_path, "wb") as f:
            f.write(private_pem)
        
        public_pem = self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        with open(self.public_key_path, "wb") as f:
            f.write(public_pem)
        
        # 设置私钥文件权限（仅所有者可读）
        os.chmod(self.private_key_path, 0o600)
        logger.info("RSA 密钥对已保存到文件")
    
    def decrypt(self, encrypted_base64: str) -> str:
        """
        RSA 解密
        
        Args:
            encrypted_base64: Base64 编码的加密数据
            
        Returns:
            解密后的明文
        """
        if self._private_key is None:
            raise RuntimeError("私钥未初始化")
        
        encrypted_data = base64.b64decode(encrypted_base64)
        
        decrypted = self._private_key.decrypt(
            encrypted_data,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        
        return decrypted.decode("utf-8")
    
    def get_public_key_pem(self) -> str:
        """
        获取 PEM 格式的公钥
        
        Returns:
            PEM 格式的公钥字符串
        """
        if self._public_key is None:
            raise RuntimeError("公钥未初始化")
        
        return self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode("utf-8")
    
    @property
    def private_key(self) -> Optional[rsa.RSAPrivateKey]:
        return self._private_key
    
    @property
    def public_key(self) -> Optional[rsa.RSAPublicKey]:
        return self._public_key


# 全局单例
_rsa_key_manager: Optional[RSAKeyManager] = None


def get_rsa_key_manager() -> RSAKeyManager:
    """获取全局 RSAKeyManager 实例"""
    global _rsa_key_manager
    if _rsa_key_manager is None:
        _rsa_key_manager = RSAKeyManager()
    return _rsa_key_manager


def init_rsa_key_manager(key_dir: Optional[Path] = None, key_size: int = 2048) -> RSAKeyManager:
    """初始化全局 RSAKeyManager 实例（应用启动时调用）"""
    global _rsa_key_manager
    _rsa_key_manager = RSAKeyManager(key_dir=key_dir, key_size=key_size)
    return _rsa_key_manager
