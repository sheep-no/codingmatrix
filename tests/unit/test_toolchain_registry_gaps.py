"""Coverage gaps for toolchain contracts and interface registry."""

import asyncio
import os
import signal
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.agent.interface_registry import (
    InterfaceEntry,
    InterfaceRegistry,
    InterfaceSymbol,
    InterfaceVisibility,
    _coerce_entry,
    _coerce_parameters,
    _coerce_symbol,
)
from app.agent.toolchain import (
    CommandSpec,
    ToolchainAction,
    ToolchainProbePlan,
    ToolchainRunner,
    _append_command,
    _read_json_object,
    _read_toml_object,
    detect_toolchain,
)


# ---------------------------------------------------------------------------
# CommandSpec / ToolchainProbePlan
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "command",
    [(), ("",), ("npm", ""), ("npm", ">"), ("sh", "-c", "ls")],
)
def test_command_spec_rejects_invalid_parts(command):
    with pytest.raises(ValueError):
        CommandSpec(action=ToolchainAction.TEST, command=command)


def test_command_spec_missing_command_key_is_allowed_through_validator():
    spec = CommandSpec(action=ToolchainAction.TEST, command=("npm", "test"))
    with pytest.raises(ValidationError):
        spec.model_copy(update={}).model_validate(
            {"action": "test"}
        )


def test_toolchain_probe_plan_for_action_returns_none_when_missing():
    plan = ToolchainProbePlan(workspace="/tmp")
    assert plan.for_action(ToolchainAction.BUILD) is None


# ---------------------------------------------------------------------------
# ToolchainRunner
# ---------------------------------------------------------------------------

def test_runner_rejects_non_positive_output_limit():
    with pytest.raises(ValueError, match="output_limit"):
        ToolchainRunner(output_limit=0)


@pytest.mark.asyncio
async def test_runner_rejects_shell_spec(tmp_path):
    spec = CommandSpec(action=ToolchainAction.TEST, command=("npm", "test"))
    shell_spec = spec.model_copy(update={"shell": True})
    with pytest.raises(ValueError, match="shell=false"):
        await ToolchainRunner().run(shell_spec, tmp_path)


@pytest.mark.asyncio
async def test_runner_rejects_missing_workspace(tmp_path):
    spec = CommandSpec(action=ToolchainAction.TEST, command=("npm", "test"))
    with pytest.raises(ValueError, match="existing directory"):
        await ToolchainRunner().run(spec, tmp_path / "missing")


@pytest.mark.asyncio
async def test_runner_rejects_wrapper_outside_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = tmp_path / "mvnw"
    outside.write_text("#!/bin/sh\n", encoding="utf-8")
    (workspace / "mvnw").symlink_to(outside)

    spec = CommandSpec(action=ToolchainAction.BUILD, command=("./mvnw", "build"))
    with pytest.raises(ValueError, match="stay inside workspace"):
        await ToolchainRunner().run(spec, workspace)


@pytest.mark.asyncio
async def test_runner_executes_wrapper_file(tmp_path):
    wrapper = tmp_path / "mvnw"
    wrapper.write_text("#!/bin/sh\necho wrapper\n", encoding="utf-8")
    wrapper.chmod(0o755)
    spec = CommandSpec(
        action=ToolchainAction.BUILD,
        command=("./mvnw",),
        timeout_seconds=5,
    )

    returncode, stdout, _ = await ToolchainRunner().run(spec, tmp_path)

    assert returncode == 0
    assert "wrapper" in stdout


@pytest.mark.asyncio
async def test_runner_handles_cancellation(tmp_path, monkeypatch):
    spec = CommandSpec(
        action=ToolchainAction.INSPECT,
        command=("python3", "-c", "import time; time.sleep(30)"),
        timeout_seconds=30,
    )
    runner = ToolchainRunner()
    task = asyncio.create_task(runner.run(spec, tmp_path))
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_runner_returns_timeout_code(tmp_path):
    spec = CommandSpec(
        action=ToolchainAction.INSPECT,
        command=("python3", "-c", "import time; time.sleep(5)"),
        timeout_seconds=1,
    )

    result = await ToolchainRunner().run(spec, tmp_path)

    assert result == (124, "", "toolchain command timed out")


@pytest.mark.asyncio
async def test_read_limited_none_stream_returns_empty(tmp_path):
    runner = ToolchainRunner()
    assert await runner._read_limited(None) == b""


def test_kill_process_group_ignores_missing_process(monkeypatch):
    def boom(pid, sig):
        raise ProcessLookupError

    monkeypatch.setattr(os, "killpg", boom)
    ToolchainRunner._kill_process_group(SimpleNamespace(pid=123))


# ---------------------------------------------------------------------------
# detect_toolchain branches
# ---------------------------------------------------------------------------

def test_detect_toolchain_pyproject_with_ruff_and_mypy(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.ruff]\nline-length = 100\n[tool.mypy]\nstrict = true\n",
        encoding="utf-8",
    )

    plan = detect_toolchain(tmp_path)

    assert plan.for_action(ToolchainAction.LINT).command == (
        "python3", "-m", "ruff", "check", "."
    )
    assert plan.for_action(ToolchainAction.TYPECHECK).command == (
        "python3", "-m", "mypy", "."
    )


def test_detect_toolchain_package_scripts_non_mapping(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"scripts": "not-a-map"}', encoding="utf-8"
    )
    plan = detect_toolchain(tmp_path)
    assert plan.for_action(ToolchainAction.INSTALL).command == ("npm", "install")


def test_detect_toolchain_gradle_wrapper(tmp_path):
    (tmp_path / "settings.gradle.kts").write_text("", encoding="utf-8")
    (tmp_path / "gradlew").write_text("#!/bin/sh\n", encoding="utf-8")
    plan = detect_toolchain(tmp_path)
    assert plan.for_action(ToolchainAction.TEST).command == ("./gradlew", "test")


def test_detect_toolchain_pom_uses_wrapper(tmp_path):
    (tmp_path / "pom.xml").write_text("", encoding="utf-8")
    (tmp_path / "mvnw").write_text("#!/bin/sh\n", encoding="utf-8")
    plan = detect_toolchain(tmp_path)
    assert plan.for_action(ToolchainAction.INSTALL).command == (
        "./mvnw", "dependency:go-offline"
    )


def test_append_command_skips_duplicate_action():
    commands = []
    _append_command(commands, ToolchainAction.TEST, ("npm", "test"))
    _append_command(commands, ToolchainAction.TEST, ("npm", "run", "test"))
    assert len(commands) == 1


def test_read_json_object_rejects_invalid_json(tmp_path):
    path = tmp_path / "package.json"
    path.write_text("{oops", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON manifest"):
        _read_json_object(path)


def test_read_toml_object_rejects_invalid_toml(tmp_path):
    path = tmp_path / "pyproject.toml"
    path.write_text("not = [valid", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid TOML manifest"):
        _read_toml_object(path)


# ---------------------------------------------------------------------------
# InterfaceRegistry
# ---------------------------------------------------------------------------

def test_registry_rejects_digest_mismatch():
    with pytest.raises(ValidationError, match="digest"):
        InterfaceRegistry(version=1, entries=(), digest="0" * 64)


def test_registry_build_accepts_none_and_string_entries():
    assert InterfaceRegistry.build(None).entries == ()
    assert InterfaceRegistry.build("ignored").entries == ()


def test_registry_build_accepts_single_mapping():
    registry = InterfaceRegistry.build(
        {"module": "mod", "owner": "alice", "symbols": ["run"]}
    )
    assert registry.entries[0].module == "mod"
    assert registry.entries[0].symbols[0].name == "run"


def test_registry_symbol_owner_returns_none_for_ambiguous_symbol():
    registry = InterfaceRegistry.build(
        [
            {
                "module": "a",
                "owner": "alice",
                "symbols": [
                    {"name": "shared", "visibility": InterfaceVisibility.PRIVATE.value}
                ],
            },
            {
                "module": "b",
                "owner": "bob",
                "symbols": [
                    {"name": "shared", "visibility": InterfaceVisibility.PRIVATE.value}
                ],
            },
        ]
    )
    assert registry.symbol_owner("shared") is None


def test_registry_symbol_owner_returns_unique_owner():
    registry = InterfaceRegistry.build(
        [{"module": "a", "owner": "alice", "symbols": ["run"]}]
    )
    assert registry.symbol_owner("run") == "alice"
    assert registry.symbol_owner("missing") is None


def test_registry_symbols_for_module():
    registry = InterfaceRegistry.build(
        [{"module": "a", "owner": "alice", "symbols": ["run", "stop"]}]
    )
    assert [s.name for s in registry.symbols_for("a")] == ["run", "stop"]
    assert registry.symbols_for("other") == ()


def test_registry_build_merges_duplicate_module_entries():
    registry = InterfaceRegistry.build(
        [
            {"module": "a", "owner": "alice", "symbols": ["run"]},
            {"module": "a", "owner": "bob", "symbols": ["run", "stop"]},
        ]
    )
    assert len(registry.entries) == 1
    assert registry.entries[0].owner == "alice"
    assert [s.name for s in registry.entries[0].symbols] == ["run", "stop"]


def test_registry_rejects_conflicting_public_symbol_owners():
    with pytest.raises(ValueError, match="multiple owners"):
        InterfaceRegistry.build(
            [
                {"module": "a", "owner": "alice", "symbols": ["run"]},
                {"module": "b", "owner": "bob", "symbols": ["run"]},
            ]
        )


def test_coerce_entry_accepts_instance():
    entry = InterfaceEntry(module="a", owner="alice")
    assert _coerce_entry(entry) is entry


def test_coerce_entry_string_symbols_and_path_defaults():
    entry = _coerce_entry({"path": "pkg/mod.py", "exports": "run"})
    assert entry.module == "pkg/mod.py"
    assert entry.owner == "pkg/mod.py"
    assert entry.symbols[0].name == "run"


def test_coerce_symbol_accepts_instance_and_scalars():
    symbol = InterfaceSymbol(name="run")
    assert _coerce_symbol(symbol) is symbol
    assert _coerce_symbol("plain").name == "plain"


def test_coerce_symbol_drops_descriptive_fields():
    symbol = _coerce_symbol(
        {
            "name": "run",
            "parameters": "uid",
            "return_type": "int",
            "description": "ignored",
            "signature": "run(uid)",
        }
    )
    assert symbol.parameters == ("uid",)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ()),
        ("", ()),
        ("uid", ("uid",)),
        ({"uid": "int", "name": None}, ("uid: int", "name")),
        (42, ("42",)),
    ],
)
def test_coerce_parameters_variants(value, expected):
    assert _coerce_parameters(value) == expected


def test_coerce_parameters_handles_mapping_items_in_list():
    assert _coerce_parameters([{"name": "uid", "type": "int"}, "raw"]) == (
        "uid: int",
        "raw",
    )


def test_registry_private_symbols_do_not_conflict():
    registry = InterfaceRegistry.build(
        [
            {
                "module": "a",
                "owner": "alice",
                "symbols": [
                    {"name": "run", "visibility": InterfaceVisibility.PRIVATE.value}
                ],
            },
            {
                "module": "b",
                "owner": "bob",
                "symbols": [
                    {"name": "run", "visibility": InterfaceVisibility.PRIVATE.value}
                ],
            },
        ]
    )
    assert len(registry.entries) == 2
