"""RSA 密钥生命周期回归测试。

覆盖 docs/evolution/modules/crypto_encryption.md 中核实的缺陷：
- CRY1：密钥加载失败静默重生成并覆盖共用密钥文件
- CRY2：encryption.py 私钥落盘未收紧权限、未建目录
- CRY3：默认密钥路径为相对路径，随 CWD 漂移
- CRY6：crypto.py 单例无锁
- CRY7：encryption.py 只传一个路径时静默生成内存密钥
"""
import os
import threading
from pathlib import Path

import pytest

import app.utils.crypto as crypto_module
import app.utils.encryption as encryption_module
from app.utils.crypto import RSAKeyManager as CryptoKeyManager
from app.utils.crypto import get_rsa_key_manager
from app.utils.encryption import RSAKeyManager as EncryptionKeyManager


def _write(path: Path, content: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


class TestCryptoKeyManager:
    """crypto.RSAKeyManager 密钥加载与路径"""

    def test_corrupt_private_key_not_overwritten(self, tmp_path):
        key_dir = tmp_path / "keys"
        private_path = key_dir / "rsa_private.pem"
        public_path = key_dir / "rsa_public.pem"
        _write(private_path, b"not a valid pem")
        _write(public_path, b"not a valid pem")

        with pytest.raises(RuntimeError):
            CryptoKeyManager(key_dir=key_dir)

        assert private_path.read_bytes() == b"not a valid pem"
        assert public_path.read_bytes() == b"not a valid pem"

    def test_missing_public_key_rebuilt_without_rotating_private(self, tmp_path):
        source_dir = tmp_path / "source"
        CryptoKeyManager(key_dir=source_dir)
        original_private = (source_dir / "rsa_private.pem").read_bytes()

        # 只提供私钥文件，模拟公钥文件丢失
        target_dir = tmp_path / "target"
        _write(target_dir / "rsa_private.pem", original_private)

        manager = CryptoKeyManager(key_dir=target_dir)

        assert (target_dir / "rsa_private.pem").read_bytes() == original_private
        assert (target_dir / "rsa_public.pem").exists()
        assert manager.get_public_key_pem().count("BEGIN PUBLIC KEY") == 1

    def test_default_key_dir_is_absolute_and_cwd_independent(self, tmp_path, monkeypatch):
        first = crypto_module._default_key_dir()
        assert first.is_absolute()

        monkeypatch.chdir(tmp_path)
        assert crypto_module._default_key_dir() == first

    def test_default_key_dir_honors_env(self, tmp_path, monkeypatch):
        target = tmp_path / "custom-keys"
        monkeypatch.setenv(crypto_module.KEY_DIR_ENV, str(target))
        assert crypto_module._default_key_dir() == target.resolve()

    def test_singleton_lock_is_reentrant_safe(self, tmp_path, monkeypatch):
        """并发首次获取单例不应产生多个实例"""
        monkeypatch.setattr(crypto_module, "_rsa_key_manager", None)
        manager = CryptoKeyManager(key_dir=tmp_path / "keys")
        results = []
        barrier = threading.Barrier(4)

        def _grab():
            barrier.wait()
            results.append(get_rsa_key_manager())

        with monkeypatch.context() as m:
            m.setattr(crypto_module, "RSAKeyManager", lambda *a, **k: manager)
            threads = [threading.Thread(target=_grab) for _ in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        assert len(results) == 4
        assert all(item is manager for item in results)


class TestEncryptionKeyManager:
    """encryption.RSAKeyManager 权限与配置校验"""

    def test_private_key_permissions_are_tightened(self, tmp_path):
        key_dir = tmp_path / "keys"
        EncryptionKeyManager(
            str(key_dir / "rsa_private.pem"), str(key_dir / "rsa_public.pem")
        )

        private_mode = oct(os.stat(key_dir / "rsa_private.pem").st_mode)[-3:]
        assert private_mode == "600"
        assert (key_dir / "rsa_public.pem").exists()

    def test_key_dir_is_created_for_nested_paths(self, tmp_path):
        nested = tmp_path / "a" / "b" / "keys"
        EncryptionKeyManager(
            str(nested / "rsa_private.pem"), str(nested / "rsa_public.pem")
        )
        assert (nested / "rsa_public.pem").exists()

    def test_partial_paths_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            EncryptionKeyManager(str(tmp_path / "rsa_private.pem"), None)

    def test_corrupt_private_key_not_overwritten(self, tmp_path):
        key_dir = tmp_path / "keys"
        private_path = key_dir / "rsa_private.pem"
        _write(private_path, b"garbage")
        _write(key_dir / "rsa_public.pem", b"garbage")

        with pytest.raises(RuntimeError):
            EncryptionKeyManager(str(private_path), str(key_dir / "rsa_public.pem"))

        assert private_path.read_bytes() == b"garbage"

    def test_missing_public_key_rebuilt_without_rotating_private(self, tmp_path):
        source = tmp_path / "source"
        EncryptionKeyManager(
            str(source / "rsa_private.pem"), str(source / "rsa_public.pem")
        )
        original_private = (source / "rsa_private.pem").read_bytes()

        target = tmp_path / "target"
        _write(target / "rsa_private.pem", original_private)

        EncryptionKeyManager(str(target / "rsa_private.pem"), str(target / "rsa_public.pem"))

        assert (target / "rsa_private.pem").read_bytes() == original_private
        assert (target / "rsa_public.pem").exists()


class TestSharedKeyFile:
    """双模块共用同一密钥文件时应能互相解密"""

    def test_encryption_manager_decrypts_data_encrypted_by_crypto_public_key(self, tmp_path):
        import base64

        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        key_dir = tmp_path / "keys"
        crypto_manager = CryptoKeyManager(key_dir=key_dir)
        encryption_manager = EncryptionKeyManager(
            str(key_dir / "rsa_private.pem"), str(key_dir / "rsa_public.pem")
        )

        payload = "sk-shared-secret"
        encrypted = crypto_manager.public_key.encrypt(
            payload.encode("utf-8"),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        decrypted = encryption_manager.private_key.decrypt(
            encrypted,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        assert decrypted.decode("utf-8") == payload
        assert base64.b64encode(decrypted).decode("utf-8")
