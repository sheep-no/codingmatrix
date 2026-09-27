"""`agent_core.CodeValidator._validate_security` 危险函数误报回归。

原实现把 `open` 列入危险函数，导致任何使用文件读写（极常见）的生成代码
都会被追加「使用了潜在危险函数: open」警告，噪声淹没真正的危险调用。
修复后 `open` 不再触发该警告，`eval`/`exec`/`os.system` 等仍然告警。
"""
import pytest

from app.utils.agent_core import CodeValidator


def _validator() -> CodeValidator:
    # _validate_security 只用 file_path，绕过 __init__ 的 pip 探测
    return object.__new__(CodeValidator)


@pytest.mark.asyncio
async def test_open_is_not_reported_as_dangerous(tmp_path):
    src = tmp_path / "reader.py"
    src.write_text("with open('a.txt') as f:\n    print(f.read())\n", encoding="utf-8")

    result = await _validator()._validate_security(src)

    assert all("open" not in w for w in result.warnings)


@pytest.mark.asyncio
async def test_eval_is_still_reported_as_dangerous(tmp_path):
    src = tmp_path / "danger.py"
    src.write_text("eval('1 + 1')\n", encoding="utf-8")

    result = await _validator()._validate_security(src)

    assert any("eval" in w for w in result.warnings)
