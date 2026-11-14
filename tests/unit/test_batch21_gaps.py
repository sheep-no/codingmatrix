"""Coverage gaps for orchestration transitions, crypto, adapters, and validation."""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent.orchestration import (
    InvalidOrchestrationTransition,
    OrchestrationStage,
    OrchestrationState,
    OrchestrationStatus,
    advance_state,
    terminate_state,
)


def _state() -> OrchestrationState:
    return OrchestrationState(
        task_id="t",
        session_id="s",
        engine_version="core-v1",
        mode="traditional",
    )


# ------------------------------------------------------- state machine


def test_advance_state_rejects_empty_event_id():
    with pytest.raises(ValueError, match="event_id must be non-empty"):
        advance_state(
            _state(),
            OrchestrationStage.PLANNING,
            event_id="",
            expected_revision=0,
        )


def test_terminate_state_requires_terminal_status():
    with pytest.raises(InvalidOrchestrationTransition, match="terminal status"):
        terminate_state(
            _state(),
            OrchestrationStatus.RUNNING,
            event_id="e1",
            expected_revision=0,
        )


# ------------------------------------------------------- retrieval models


def test_retrieval_models_to_dict_round_trip():
    from app.agent.retrieval.models import RetrievalChunk, RetrievalResult

    chunk = RetrievalChunk(content="hello", source_type="memory", source_id="m1", score=0.5)
    assert chunk.to_dict()["content_hash"]
    result = RetrievalResult(chunks=[chunk], degraded=True, fallback_mode="keyword")
    payload = result.to_dict()
    assert payload["degraded"] is True
    assert payload["fallback_mode"] == "keyword"
    assert payload["chunks"][0]["content"] == "hello"


# ------------------------------------------------------- rust adapter


def test_rust_adapter_helpers_and_import_resolution():
    from app.agent.adapters.rust import RustLanguageAdapter
    from app.agent.adapters.language_adapter import ImportInfo

    adapter = RustLanguageAdapter()
    assert adapter.parse_imports("pub mod util;")[0].module == "util"
    assert adapter.resolve_import_to_file(
        ImportInfo(module="std::io", is_relative=False, raw_line="use std::io;"), "src/a.rs"
    ) == []
    resolved = adapter.resolve_import_to_file(
        ImportInfo(module="crate::models::User", is_relative=True, raw_line="use crate::models::User;"),
        "src/a.rs",
    )
    assert resolved[0].endswith("src/models.rs")
    assert adapter.get_package_init_file("pkg/") == "pkg/mod.rs"
    assert adapter.is_project_module("crate::x") is True
    assert adapter.is_project_module("serde") is False


# ------------------------------------------------- single file generation


def test_resource_limits_sets_rlimits(monkeypatch):
    from app.api.v1.ai_agent import single_file_generation as module

    calls = []
    monkeypatch.setattr(module.resource, "setrlimit", lambda kind, limits: calls.append((kind, limits)))
    module._resource_limits()
    assert len(calls) == 3


def test_run_generated_file_javascript_uses_node(tmp_path, monkeypatch):
    from app.api.v1.ai_agent import single_file_generation as module

    file_path = tmp_path / "app.js"
    file_path.write_text("console.log(1)", encoding="utf-8")
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    result = module._run_generated_file(file_path, "javascript")
    assert result["ran"] is True
    assert seen["command"] == ["node", "app.js"]


# ------------------------------------------------------- crypto


def test_crypto_uninitialised_state_guards(tmp_path):
    from app.utils.crypto import RSAKeyManager, init_rsa_key_manager

    manager = init_rsa_key_manager(key_dir=tmp_path / "keys", key_size=2048)
    manager._private_key = None
    manager._public_key = None
    with pytest.raises(RuntimeError, match="私钥未初始化"):
        manager.decrypt("abc")
    with pytest.raises(RuntimeError, match="公钥未初始化"):
        manager.get_public_key_pem()


def test_crypto_reports_unreadable_private_key(tmp_path):
    from app.utils.crypto import RSAKeyManager

    key_dir = tmp_path / "keys"
    key_dir.mkdir()
    (key_dir / "rsa_private.pem").mkdir()
    with pytest.raises(RuntimeError, match="读取 RSA 私钥失败"):
        RSAKeyManager(key_dir=key_dir)


def test_crypto_warns_when_permission_tighten_fails(tmp_path, monkeypatch):
    import app.utils.crypto as module

    calls = {"n": 0}
    real_chmod = os.chmod

    def flaky_chmod(path, mode):
        calls["n"] += 1
        if calls["n"] == 1:
            return real_chmod(path, mode)
        raise OSError("chmod denied")

    monkeypatch.setattr(module.os, "chmod", flaky_chmod)
    manager = module.RSAKeyManager(key_dir=tmp_path / "keys")
    assert manager.private_key is not None


def test_crypto_rebuilds_mismatched_public_key(tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from app.utils.crypto import RSAKeyManager

    key_dir = tmp_path / "keys"
    manager = RSAKeyManager(key_dir=key_dir)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    mismatched = other.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    (key_dir / "rsa_public.pem").write_bytes(mismatched)

    reloaded = RSAKeyManager(key_dir=key_dir)
    assert reloaded.public_key.public_numbers() == reloaded.private_key.public_key().public_numbers()


def test_rsa_singleton_double_checked_lock(tmp_path, monkeypatch):
    import app.utils.crypto as module

    monkeypatch.setattr(module, "_rsa_key_manager", None)
    first = module.get_rsa_key_manager()
    assert module.get_rsa_key_manager() is first


# ------------------------------------------------------- complexity


def test_complexity_large_and_llm_alias():
    from app.agent.complexity import ComplexityAnalyzer, ProjectComplexity

    analysis = ComplexityAnalyzer.analyze("前端 后端 数据库 登录 微服务")
    assert analysis.level is ProjectComplexity.LARGE
    assert 20 < analysis.estimated_files <= 50
    assert asyncio_run(ComplexityAnalyzer.analyze_with_llm("前端 后端")) is not None


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)


# ------------------------------------------------------- input validator


@pytest.mark.asyncio
async def test_read_body_safe_stops_on_disconnect():
    from app.middleware.input_validator import _read_body_safe

    async def receive():
        return {"type": "http.disconnect"}

    assert await _read_body_safe(receive, 100) == b""


@pytest.mark.asyncio
async def test_input_validator_rejects_declared_invalid_json():
    import json as jsonlib

    from app.middleware.input_validator import InputValidatorMiddleware

    messages = []
    reached = False

    async def app(scope, receive, send):
        nonlocal reached
        reached = True

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/users",
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", b"4"),
        ],
    }

    async def receive():
        return {"type": "http.request", "body": b"{bad", "more_body": False}

    await InputValidatorMiddleware(app)(scope, receive, send)
    assert reached is False
    assert jsonlib.loads(messages[1]["body"])["code"] == "INVALID_JSON"


@pytest.mark.asyncio
async def test_input_validator_handles_recursion_in_scan(monkeypatch):
    import app.middleware.input_validator as module

    def boom(_value):
        raise RecursionError("deep")

    monkeypatch.setattr(module, "_scan_value", boom)
    messages = []

    async def app(scope, receive, send):
        raise AssertionError("must not reach app")

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/users",
        "headers": [(b"content-type", b"application/json")],
    }

    async def receive():
        return {"type": "http.request", "body": b'{"a": 1}', "more_body": False}

    await module.InputValidatorMiddleware(app)(scope, receive, send)
    assert messages[0]["status"] == 400


# ------------------------------------------------------- pptx scenario


def test_scenario_keywords_falls_back_for_unknown():
    from app.utils.pptx.scenario import SCENARIO_PROFILES, scenario_keywords

    assert tuple(scenario_keywords("unknown")) == tuple(SCENARIO_PROFILES["general"][1])


def test_retrieval_chunk_keeps_explicit_hash():
    from app.agent.retrieval.models import RetrievalChunk

    chunk = RetrievalChunk(
        content="x", source_type="rag", source_id="r", content_hash="fixed"
    )
    assert chunk.to_dict()["content_hash"] == "fixed"


def test_rust_adapter_unmatched_lines_fall_through():
    from app.agent.adapters.rust import RustLanguageAdapter

    adapter = RustLanguageAdapter()
    imports = adapter.parse_imports("// plain comment\nlet x = 1;\n")
    assert imports == []
    definitions = adapter.extract_definitions("// comment\nstruct A;\n")
    assert set(definitions) == {"A"}


def test_rsa_singleton_inner_check_when_initialised_concurrently(tmp_path, monkeypatch):
    import app.utils.crypto as module

    existing = module.RSAKeyManager(key_dir=tmp_path / "keys")
    monkeypatch.setattr(module, "_rsa_key_manager", None)

    class FakeLock:
        def __enter__(self):
            module._rsa_key_manager = existing
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(module, "_rsa_key_manager_lock", FakeLock())
    assert module.get_rsa_key_manager() is existing


@pytest.mark.asyncio
async def test_read_body_safe_ignores_unknown_messages():
    from app.middleware.input_validator import _read_body_safe

    events = iter([
        {"type": "other"},
        {"type": "http.request", "body": b"hi", "more_body": False},
    ])

    async def receive():
        return next(events)

    assert await _read_body_safe(receive, 100) == b"hi"
