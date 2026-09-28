"""`app.agent` 包内剩余 ASYNC 阻塞调用清理的回归。

覆盖 `layer1_cross_domain_template` 的领域模板读取、`scaffolding` /
`toolchain` / `framework_profiles` 里在协程中执行的 `resolve()` / `is_dir()`
等文件系统操作。用线程 id 断言这些操作发生在工作线程。
"""

import threading
from pathlib import Path

import pytest


def _spy(seen, attr):
    real = getattr(Path, attr)

    def spy(self, *args, **kwargs):
        seen.append(threading.get_ident())
        return real(self, *args, **kwargs)

    return spy


@pytest.mark.asyncio
async def test_layer1_template_reads_off_event_loop(tmp_path, monkeypatch):
    from app.agent.orchestrator_requirements import layer1_template

    (tmp_path / "banking.json").write_text(
        '{"domain": "banking", "core_modules": [{"name": "账户"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(layer1_template, "DOMAIN_TEMPLATES_DIR", tmp_path)

    main_thread = threading.get_ident()
    seen = []
    monkeypatch.setattr(Path, "read_text", _spy(seen, "read_text"))

    items = await layer1_template.layer1_cross_domain_template(
        "银行转账系统", ["banking"]
    )

    assert [item.content for item in items] == ["账户"]
    assert seen and seen[0] != main_thread, "领域模板读取仍在事件循环线程"


@pytest.mark.asyncio
async def test_toolchain_run_resolve_off_event_loop(tmp_path, monkeypatch):
    from app.agent.toolchain import CommandSpec, ToolchainAction, ToolchainRunner

    main_thread = threading.get_ident()
    seen = []
    monkeypatch.setattr(Path, "resolve", _spy(seen, "resolve"))

    runner = ToolchainRunner(allowed_executables=frozenset({"python3"}))
    spec = CommandSpec(
        action=ToolchainAction.INSPECT,
        command=("python3", "-c", "print('ok')"),
        timeout_seconds=30,
    )
    returncode, stdout, stderr = await runner.run(spec, tmp_path)

    assert returncode == 0 and stdout.strip() == "ok"
    assert seen and seen[0] != main_thread, "toolchain resolve 仍在事件循环线程"


@pytest.mark.asyncio
async def test_scaffolding_resolve_off_event_loop(tmp_path, monkeypatch):
    from app.agent.scaffolding import ScaffoldRequest, execute_official_scaffold

    main_thread = threading.get_ident()
    seen = []
    monkeypatch.setattr(Path, "resolve", _spy(seen, "resolve"))

    request = ScaffoldRequest(
        framework="express",
        language="javascript",
        target_dir="app",
        command=("npx", "--yes", "express-generator@4.16.1", "app", "--no-view"),
    )
    # 不存在的 workspace 在校验目录时即抛错，不会真的执行脚手架命令。
    with pytest.raises(ValueError, match="existing directory"):
        await execute_official_scaffold(tmp_path / "missing", request)

    assert seen and seen[0] != main_thread, "scaffold resolve 仍在事件循环线程"


@pytest.mark.asyncio
async def test_workspace_probe_resolve_off_event_loop(tmp_path, monkeypatch):
    from app.agent.framework_profiles.types import ProfileScope
    from app.agent.framework_profiles.workspace import probe_workspace_profile

    main_thread = threading.get_ident()
    seen = []
    monkeypatch.setattr(Path, "resolve", _spy(seen, "resolve"))

    profile = _workspace_profile(ProfileScope)
    with pytest.raises(ValueError, match="existing directory"):
        await probe_workspace_profile(tmp_path / "missing", profile)

    assert seen and seen[0] != main_thread, "workspace probe resolve 仍在事件循环线程"


def _workspace_profile(profile_scope):
    from app.agent.framework_profiles.types import FrameworkProfile, ProfileStatus

    # 只校验前置目录，用 model_construct 跳过与本用例无关的完整校验。
    return FrameworkProfile.model_construct(
        name="custom",
        language="python",
        version="1",
        status=ProfileStatus.CUSTOM_PENDING,
        capabilities=None,
        scope=profile_scope.WORKSPACE,
    )
