"""Branch coverage for app/utils/encryption.py."""

import base64
import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding as sym_padding

import app.utils.encryption as enc
from app.utils.encryption import (
    RSAKeyManager,
    decrypt_sensitive_data,
    get_key_manager,
    get_public_key_for_client,
    init_encryption,
)


def _encrypt_payload(manager: RSAKeyManager, data: dict) -> dict:
    aes_key = os.urandom(32)
    iv = os.urandom(16)
    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(json.dumps(data).encode()) + padder.finalize()
    encryptor = Cipher(algorithms.AES(aes_key), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    encrypted_aes = manager.public_key.encrypt(
        aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return {
        "encrypted_data": base64.b64encode(iv + ciphertext).decode(),
        "encrypted_key": base64.b64encode(encrypted_aes).decode(),
    }


def _make_file_manager(tmp_path, monkeypatch, passphrase=None):
    if passphrase is None:
        monkeypatch.delenv(enc.KEY_PASSPHRASE_ENV, raising=False)
    else:
        monkeypatch.setenv(enc.KEY_PASSPHRASE_ENV, passphrase)
    private = tmp_path / "keys" / "rsa_private.pem"
    public = tmp_path / "keys" / "rsa_public.pem"
    return RSAKeyManager(str(private), str(public))


class TestDefaultPaths:
    def test_uses_env_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv(enc.KEY_DIR_ENV, str(tmp_path / "k"))
        private, public = enc._default_key_paths()
        assert private == str((tmp_path / "k").resolve() / "rsa_private.pem")
        assert public == str((tmp_path / "k").resolve() / "rsa_public.pem")

    def test_uses_repo_keys_without_env(self, monkeypatch):
        monkeypatch.delenv(enc.KEY_DIR_ENV, raising=False)
        private, public = enc._default_key_paths()
        assert private.endswith("rsa_private.pem")
        assert Path(private).is_absolute()


class TestConstruction:
    def test_memory_manager_generates_keys(self):
        manager = RSAKeyManager()
        assert manager.private_key is not None
        assert manager.get_public_key_pem().startswith("-----BEGIN PUBLIC KEY-----")

    def test_single_path_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            RSAKeyManager(str(tmp_path / "x.pem"), None)

    def test_missing_key_files_generated_and_saved(self, tmp_path, monkeypatch):
        manager = _make_file_manager(tmp_path, monkeypatch)
        assert (tmp_path / "keys" / "rsa_private.pem").exists()
        assert (tmp_path / "keys" / "rsa_public.pem").exists()
        assert manager.private_key is not None

    def test_oserror_on_private_read(self, tmp_path, monkeypatch):
        monkeypatch.setattr(enc.Path, "read_bytes", MagicMock(side_effect=OSError("denied")))
        with pytest.raises(RuntimeError):
            RSAKeyManager(str(tmp_path / "p.pem"), str(tmp_path / "pub.pem"))

    def test_encrypted_key_without_env_raises(self, tmp_path, monkeypatch):
        _make_file_manager(tmp_path, monkeypatch, passphrase="secret")
        monkeypatch.delenv(enc.KEY_PASSPHRASE_ENV, raising=False)
        with pytest.raises(RuntimeError):
            RSAKeyManager(
                str(tmp_path / "keys" / "rsa_private.pem"),
                str(tmp_path / "keys" / "rsa_public.pem"),
            )

    def test_wrong_passphrase_raises(self, tmp_path, monkeypatch):
        _make_file_manager(tmp_path, monkeypatch, passphrase="secret")
        monkeypatch.setenv(enc.KEY_PASSPHRASE_ENV, "wrong")
        with pytest.raises(RuntimeError):
            RSAKeyManager(
                str(tmp_path / "keys" / "rsa_private.pem"),
                str(tmp_path / "keys" / "rsa_public.pem"),
            )

    def test_corrupt_private_key_raises(self, tmp_path, monkeypatch):
        private = tmp_path / "keys" / "rsa_private.pem"
        private.parent.mkdir(parents=True)
        private.write_bytes(b"garbage")
        (tmp_path / "keys" / "rsa_public.pem").write_bytes(b"garbage")
        with pytest.raises(RuntimeError):
            RSAKeyManager(str(private), str(tmp_path / "keys" / "rsa_public.pem"))

    def test_mismatched_public_key_rebuilt(self, tmp_path, monkeypatch):
        manager = _make_file_manager(tmp_path, monkeypatch)
        original_private = (tmp_path / "keys" / "rsa_private.pem").read_bytes()
        # Replace public key with one from a different pair.
        other = RSAKeyManager()
        (tmp_path / "keys" / "rsa_public.pem").write_bytes(
            other.get_public_key_pem().encode()
        )

        reloaded = RSAKeyManager(
            str(tmp_path / "keys" / "rsa_private.pem"),
            str(tmp_path / "keys" / "rsa_public.pem"),
        )

        assert (tmp_path / "keys" / "rsa_private.pem").read_bytes() == original_private
        assert reloaded.get_public_key_pem() == manager.get_public_key_pem()

    def test_missing_public_key_rebuilt(self, tmp_path, monkeypatch):
        _make_file_manager(tmp_path, monkeypatch)
        (tmp_path / "keys" / "rsa_public.pem").unlink()
        assert (tmp_path / "keys" / "rsa_public.pem").exists() is False
        manager = RSAKeyManager(
            str(tmp_path / "keys" / "rsa_private.pem"),
            str(tmp_path / "keys" / "rsa_public.pem"),
        )
        assert (tmp_path / "keys" / "rsa_public.pem").exists()
        assert manager.public_key is not None

    def test_chmod_failure_logs_warning(self, tmp_path, monkeypatch):
        manager = RSAKeyManager()
        manager.private_key_path = str(tmp_path / "p.pem")
        manager.public_key_path = str(tmp_path / "pub.pem")
        import app.utils.encryption as module

        fake_logger = MagicMock()
        monkeypatch.setattr(module, "logger", fake_logger)
        def _chmod(path, mode):
            if not path.endswith(".tmp"):
                raise OSError("no")

        monkeypatch.setattr(module.os, "chmod", _chmod)
        manager.save_keys()
        assert fake_logger.warning.called

    def test_save_keys_without_paths_is_noop(self):
        RSAKeyManager().save_keys()


class TestDecryption:
    def test_get_public_key_pem_without_key(self):
        manager = RSAKeyManager()
        manager.public_key = None
        assert manager.get_public_key_pem() == ""

    def test_decrypt_aes_key_requires_private_key(self):
        manager = RSAKeyManager()
        manager.private_key = None
        with pytest.raises(ValueError):
            manager.decrypt_aes_key(b"x")

    def test_decrypt_aes_key_invalid_ciphertext(self):
        with pytest.raises(ValueError, match="解密失败"):
            RSAKeyManager().decrypt_aes_key(b"not-encrypted")

    def test_decrypt_data_invalid_input(self):
        with pytest.raises(ValueError, match="数据解密失败"):
            RSAKeyManager().decrypt_data(b"short", b"0" * 32)

    def test_login_roundtrip(self):
        manager = RSAKeyManager()
        payload = _encrypt_payload(manager, {"email": "a@b.c", "password": "pw"})
        assert manager.decrypt_login_data(payload) == {
            "email": "a@b.c",
            "password": "pw",
        }

    def test_login_missing_fields(self):
        manager = RSAKeyManager()
        payload = _encrypt_payload(manager, {"email": "a@b.c"})
        with pytest.raises(ValueError, match="数据解密失败"):
            manager.decrypt_login_data(payload)

    def test_login_bad_base64(self):
        manager = RSAKeyManager()
        with pytest.raises(ValueError, match="数据解密失败"):
            manager.decrypt_login_data({"encrypted_data": "!!", "encrypted_key": "!!"})


class TestGlobalHelpers:
    @pytest.fixture(autouse=True)
    def _reset(self, monkeypatch):
        monkeypatch.setattr(enc, "_key_manager", None)
        yield
        enc._key_manager = None

    @pytest.mark.asyncio
    async def test_key_manager_default_paths(self, tmp_path, monkeypatch):
        monkeypatch.setenv(enc.KEY_DIR_ENV, str(tmp_path / "keys"))
        manager = await get_key_manager()
        assert manager.private_key is not None

    @pytest.mark.asyncio
    async def test_key_manager_singleton(self):
        first = await get_key_manager(str(Path("/tmp/opencode/k1.pem")), str(Path("/tmp/opencode/k1pub.pem")))
        second = await get_key_manager()
        assert first is second

    @pytest.mark.asyncio
    async def test_key_manager_explicit_paths(self, tmp_path, monkeypatch):
        monkeypatch.delenv(enc.KEY_PASSPHRASE_ENV, raising=False)
        manager = await get_key_manager(
            str(tmp_path / "k" / "p.pem"), str(tmp_path / "k" / "pub.pem")
        )
        assert manager.private_key is not None

    @pytest.mark.asyncio
    async def test_init_encryption(self, tmp_path, monkeypatch):
        monkeypatch.delenv(enc.KEY_PASSPHRASE_ENV, raising=False)
        manager = await init_encryption(
            str(tmp_path / "k" / "p.pem"), str(tmp_path / "k" / "pub.pem")
        )
        assert manager is await get_key_manager()

    @pytest.mark.asyncio
    async def test_public_key_and_decrypt_sensitive(self):
        manager = await get_key_manager()
        pem = await get_public_key_for_client()
        assert pem == manager.get_public_key_pem()

        payload = _encrypt_payload(manager, {"email": "e", "password": "p"})
        assert await decrypt_sensitive_data(payload) == {"email": "e", "password": "p"}


def test_plaintext_key_upgraded_when_passphrase_configured(tmp_path, monkeypatch):
    manager = _make_file_manager(tmp_path, monkeypatch, passphrase=None)
    original_public = manager.get_public_key_pem()
    monkeypatch.setenv(enc.KEY_PASSPHRASE_ENV, "secret")

    upgraded = RSAKeyManager(
        str(tmp_path / "keys" / "rsa_private.pem"),
        str(tmp_path / "keys" / "rsa_public.pem"),
    )

    assert upgraded.get_public_key_pem() == original_public
    with pytest.raises(TypeError):
        serialization.load_pem_private_key(
            (tmp_path / "keys" / "rsa_private.pem").read_bytes(),
            password=None,
        )


@pytest.mark.asyncio
async def test_get_key_manager_double_check_race(monkeypatch):
    existing = RSAKeyManager()

    class _Lock:
        async def __aenter__(self):
            monkeypatch.setattr(enc, "_key_manager", existing)
            return self

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(enc, "_key_manager", None)
    monkeypatch.setattr(enc, "_key_lock", _Lock())

    assert await get_key_manager() is existing
