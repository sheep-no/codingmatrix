"""
RSA + AES 混合加密模块

用于敏感数据（如登录密码）的安全传输

加密流程：
1. 前端生成随机 AES 密钥
2. 使用 AES 加密敏感数据
3. 使用 RSA 公钥加密 AES 密钥
4. 发送：加密数据 + 加密的 AES 密钥

解密流程：
1. 使用 RSA 私钥解密 AES 密钥
2. 使用 AES 密钥解密数据
"""

import asyncio
import base64
import json
import hashlib
from typing import Optional, Dict, Any
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding as sym_padding
import os
import logging

logger = logging.getLogger(__name__)


class RSAKeyManager:
    """RSA 密钥对管理器"""
    
    def __init__(self, private_key_path: str = None, public_key_path: str = None):
        self.private_key = None
        self.public_key = None
        self.private_key_path = private_key_path
        self.public_key_path = public_key_path
        
        # 如果没有提供路径，使用内存中的密钥
        if not private_key_path or not public_key_path:
            self._generate_keys()
        else:
            self._load_keys()
    
    def _generate_keys(self):
        """生成新的 RSA 密钥对"""
        # 生成 2048 位 RSA 密钥对
        self.private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        self.public_key = self.private_key.public_key()
        logger.info("已生成新的 RSA 密钥对（2048 位）")
    
    def _load_keys(self):
        """从文件加载密钥对"""
        try:
            # 加载私钥
            with open(self.private_key_path, "rb") as f:
                self.private_key = serialization.load_pem_private_key(
                    f.read(),
                    password=None,
                    backend=default_backend()
                )
            
            # 加载公钥
            with open(self.public_key_path, "rb") as f:
                self.public_key = serialization.load_pem_public_key(
                    f.read(),
                    backend=default_backend()
                )
            
            logger.info(f"已从文件加载 RSA 密钥对")
        except FileNotFoundError:
            logger.warning("密钥文件不存在，生成新的密钥对")
            self._generate_keys()
            self.save_keys()
        except Exception as e:
            logger.error(f"加载密钥失败：{e}")
            self._generate_keys()
    
    def save_keys(self):
        """保存密钥到文件"""
        if not self.private_key_path or not self.public_key_path:
            return
        
        # 保存私钥
        with open(self.private_key_path, "wb") as f:
            f.write(self.private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ))
        
        # 保存公钥
        with open(self.public_key_path, "wb") as f:
            f.write(self.public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            ))
        
        logger.info(f"密钥已保存到：{self.private_key_path}, {self.public_key_path}")
    
    def get_public_key_pem(self) -> str:
        """获取 PEM 格式的公钥"""
        if not self.public_key:
            return ""
        
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')
    
    def decrypt_aes_key(self, encrypted_aes_key: bytes) -> bytes:
        """使用 RSA 私钥解密 AES 密钥"""
        if not self.private_key:
            raise ValueError("私钥未加载")
        
        try:
            aes_key = self.private_key.decrypt(
                encrypted_aes_key,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            return aes_key
        except Exception as e:
            logger.error(f"解密 AES 密钥失败：{e}")
            raise ValueError("解密失败")
    
    def decrypt_data(self, encrypted_data: bytes, aes_key: bytes) -> Dict[str, Any]:
        """使用 AES 密钥解密数据"""
        try:
            # 提取 IV 和密文
            iv = encrypted_data[:16]
            ciphertext = encrypted_data[16:]
            
            # AES 解密
            cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv), backend=default_backend())
            decryptor = cipher.decryptor()
            decrypted = decryptor.update(ciphertext) + decryptor.finalize()
            
            # 去除填充
            unpadder = sym_padding.PKCS7(128).unpadder()
            unpadded_data = unpadder.update(decrypted) + unpadder.finalize()
            
            # 解析 JSON
            data = json.loads(unpadded_data.decode('utf-8'))
            return data
        except Exception as e:
            logger.error(f"解密数据失败：{e}")
            raise ValueError("数据解密失败")
    
    def decrypt_login_data(self, encrypted_payload: Dict[str, str]) -> Dict[str, Any]:
        """
        解密登录数据（完整流程）
        
        Args:
            encrypted_payload: {
                "encrypted_data": base64 加密数据,
                "encrypted_key": base64 加密的 AES 密钥
            }
        
        Returns:
            解密后的数据：{
                "email": "...",
                "password": "..."
            }
        """
        try:
            # 解码 base64
            encrypted_data = base64.b64decode(encrypted_payload["encrypted_data"])
            encrypted_aes_key = base64.b64decode(encrypted_payload["encrypted_key"])
            
            # RSA 解密 AES 密钥
            aes_key = self.decrypt_aes_key(encrypted_aes_key)
            
            # AES 解密数据
            data = self.decrypt_data(encrypted_data, aes_key)
            
            # 验证必要字段
            if "email" not in data or "password" not in data:
                raise ValueError("缺少必要字段")
            
            return data
        except Exception as e:
            logger.error(f"解密登录数据失败：{e}")
            raise ValueError(f"数据解密失败：{str(e)}")


# 全局密钥管理器实例
_key_manager: Optional[RSAKeyManager] = None
_key_lock = asyncio.Lock()


async def get_key_manager(private_key_path: str = "keys/rsa_private.pem",
                          public_key_path: str = "keys/rsa_public.pem") -> RSAKeyManager:
    """获取密钥管理器单例"""
    global _key_manager

    if _key_manager is None:
        async with _key_lock:
            if _key_manager is None:
                _key_manager = RSAKeyManager(private_key_path, public_key_path)

    return _key_manager


async def init_encryption(private_key_path: str = "keys/rsa_private.pem",
                   public_key_path: str = "keys/rsa_public.pem"):
    """
    初始化加密模块

    在应用启动时调用
    """
    key_manager = await get_key_manager(private_key_path, public_key_path)
    logger.info("加密模块初始化完成")
    return key_manager


async def get_public_key_for_client() -> str:
    """获取公钥（发送给前端）"""
    return (await get_key_manager()).get_public_key_pem()


async def decrypt_sensitive_data(encrypted_payload: Dict[str, str]) -> Dict[str, Any]:
    """解密敏感数据（用于登录等场景）"""
    return (await get_key_manager()).decrypt_login_data(encrypted_payload)
