"""RSA 私钥口令加密（RSA_KEY_PASSPHRASE）回归测试：默认明文落盘，配置口令后加密并兼容明文升级。"""
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization

import app.utils.crypto as crypto_module
import app.utils.encryption as encryption_module
from app.utils.crypto import RSAKeyManager as CryptoKeyManager
from app.utils.encryption import RSAKeyManager as EncryptionKeyManager

PASSPHRASE = "unit-passphrase"


def _load_raw(path: Path, password=None):
    return serialization.load_pem_private_key(path.read_bytes(), password=password)


class TestCryptoKeyPassphrase:
    def test_default_remains_plaintext(self, tmp_path, monkeypatch):
        monkeypatch.delenv(crypto_module.KEY_PASSPHRASE_ENV, raising=False)
        key_dir = tmp_path / "keys"
        CryptoKeyManager(key_dir=key_dir)
        assert _load_raw(key_dir / "rsa_private.pem") is not None

    def test_passphrase_encrypts_new_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv(crypto_module.KEY_PASSPHRASE_ENV, PASSPHRASE)
        key_dir = tmp_path / "keys"
        CryptoKeyManager(key_dir=key_dir)
        with pytest.raises(TypeError):
            _load_raw(key_dir / "rsa_private.pem")
        assert _load_raw(key_dir / "rsa_private.pem", PASSPHRASE.encode()) is not None

    def test_plaintext_key_upgraded_to_encrypted(self, tmp_path, monkeypatch):
        monkeypatch.delenv(crypto_module.KEY_PASSPHRASE_ENV, raising=False)
        key_dir = tmp_path / "keys"
        plain_manager = CryptoKeyManager(key_dir=key_dir)
        public_before = plain_manager.get_public_key_pem()

        monkeypatch.setenv(crypto_module.KEY_PASSPHRASE_ENV, PASSPHRASE)
        upgraded = CryptoKeyManager(key_dir=key_dir)

        with pytest.raises(TypeError):
            _load_raw(key_dir / "rsa_private.pem")
        encrypted_key = _load_raw(key_dir / "rsa_private.pem", PASSPHRASE.encode())
        assert encrypted_key is not None
        assert upgraded.get_public_key_pem() == public_before

    def test_wrong_passphrase_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setenv(crypto_module.KEY_PASSPHRASE_ENV, PASSPHRASE)
        key_dir = tmp_path / "keys"
        CryptoKeyManager(key_dir=key_dir)

        monkeypatch.setenv(crypto_module.KEY_PASSPHRASE_ENV, "wrong-passphrase")
        with pytest.raises(RuntimeError):
            CryptoKeyManager(key_dir=key_dir)

    def test_encrypted_key_without_env_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv(crypto_module.KEY_PASSPHRASE_ENV, PASSPHRASE)
        key_dir = tmp_path / "keys"
        CryptoKeyManager(key_dir=key_dir)

        monkeypatch.delenv(crypto_module.KEY_PASSPHRASE_ENV, raising=False)
        with pytest.raises(RuntimeError):
            CryptoKeyManager(key_dir=key_dir)


class TestEncryptionKeyPassphrase:
    @staticmethod
    def _make(key_dir: Path, monkeypatch, passphrase):
        if passphrase is None:
            monkeypatch.delenv(encryption_module.KEY_PASSPHRASE_ENV, raising=False)
        else:
            monkeypatch.setenv(encryption_module.KEY_PASSPHRASE_ENV, passphrase)
        return EncryptionKeyManager(
            str(key_dir / "rsa_private.pem"), str(key_dir / "rsa_public.pem")
        )

    def test_passphrase_encrypts_new_key(self, tmp_path, monkeypatch):
        key_dir = tmp_path / "keys"
        self._make(key_dir, monkeypatch, PASSPHRASE)
        with pytest.raises(TypeError):
            _load_raw(key_dir / "rsa_private.pem")
        assert _load_raw(key_dir / "rsa_private.pem", PASSPHRASE.encode()) is not None

    def test_plaintext_key_upgraded_to_encrypted(self, tmp_path, monkeypatch):
        key_dir = tmp_path / "keys"
        self._make(key_dir, monkeypatch, None)
        self._make(key_dir, monkeypatch, PASSPHRASE)
        with pytest.raises(TypeError):
            _load_raw(key_dir / "rsa_private.pem")
        assert _load_raw(key_dir / "rsa_private.pem", PASSPHRASE.encode()) is not None
