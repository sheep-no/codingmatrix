"""`app.utils.agent_core` 验证链路的文件读取必须离开事件循环。

`CodeValidator` 的语法/导入/安全校验、`ProjectValidator` 的依赖清单与入口点
检查都在 async 方法里同步 `open()` / `read_text()`。项目级校验会对每个 .py
文件并发调用这些方法，读文件阻塞会拖住事件循环。这里用线程 id 断言读取发生在
工作线程。
"""

import threading
from pathlib import Path

import pytest

from app.utils.agent_core import CodeValidator, ProjectValidator
from app.schema.codeRequest import AgentConfig


def _read_text_spy(seen):
    real = Path.read_text

    def spy(self, *args, **kwargs):
        seen.append(threading.get_ident())
        return real(self, *args, **kwargs)

    return spy


@pytest.mark.asyncio
async def test_validate_syntax_reads_off_event_loop(tmp_path, monkeypatch):
    target = tmp_path / "a.py"
    target.write_text("x = 1\n", encoding="utf-8")
    validator = CodeValidator(tmp_path, AgentConfig())
    main_thread = threading.get_ident()
    seen = []
    monkeypatch.setattr(Path, "read_text", _read_text_spy(seen))

    result = await validator._validate_syntax(target)

    assert result.success is True
    assert seen and seen[0] != main_thread, "语法校验读取仍在事件循环线程"


@pytest.mark.asyncio
async def test_validate_imports_reads_off_event_loop(tmp_path, monkeypatch):
    target = tmp_path / "a.py"
    target.write_text("x = 1\n", encoding="utf-8")
    validator = CodeValidator(tmp_path, AgentConfig())
    main_thread = threading.get_ident()
    seen = []
    monkeypatch.setattr(Path, "read_text", _read_text_spy(seen))

    await validator._validate_imports(target)

    assert seen and seen[0] != main_thread, "导入校验读取仍在事件循环线程"


@pytest.mark.asyncio
async def test_validate_security_reads_off_event_loop(tmp_path, monkeypatch):
    target = tmp_path / "a.py"
    target.write_text("x = 1\n", encoding="utf-8")
    validator = CodeValidator(tmp_path, AgentConfig())
    main_thread = threading.get_ident()
    seen = []
    monkeypatch.setattr(Path, "read_text", _read_text_spy(seen))

    await validator._validate_security(target)

    assert seen and seen[0] != main_thread, "安全校验读取仍在事件循环线程"


@pytest.mark.asyncio
async def test_check_dependencies_reads_off_event_loop(tmp_path, monkeypatch):
    (tmp_path / "requirements.txt").write_text("requests==2.0\n# comment\n", encoding="utf-8")
    validator = ProjectValidator(tmp_path, AgentConfig())
    main_thread = threading.get_ident()
    seen = []
    monkeypatch.setattr(Path, "read_text", _read_text_spy(seen))

    results = await validator._check_dependencies()

    assert results["has_requirements"] is True
    assert seen and seen[0] != main_thread, "依赖清单读取仍在事件循环线程"


@pytest.mark.asyncio
async def test_check_entrypoint_reads_off_event_loop(tmp_path, monkeypatch):
    (tmp_path / "main.py").write_text(
        "#!/usr/bin/env python\nprint('hi')\n", encoding="utf-8"
    )
    validator = ProjectValidator(tmp_path, AgentConfig())
    main_thread = threading.get_ident()
    seen = []
    monkeypatch.setattr(Path, "read_text", _read_text_spy(seen))

    results = await validator._check_entrypoint()

    assert results["entrypoint_file"] == "main.py"
    assert results["executable"] is True
    assert seen and seen[0] != main_thread, "入口点读取仍在事件循环线程"


def test_list_relative_files_returns_relative_paths(tmp_path):
    from app.utils.agent_core import _list_relative_files

    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("hi\n", encoding="utf-8")

    files = sorted(_list_relative_files(tmp_path))

    assert files == ["README.md", str(Path("pkg") / "mod.py")]
    assert _list_relative_files(tmp_path / "missing") == []
