"""防止宽泛异常处理继续扩散的棘轮测试。

存量 ``except Exception`` 按域逐步收敛，新增代码不得提高总数。
"""
from pathlib import Path

MAX_BROAD_EXCEPTIONS = 832


def test_broad_exception_handlers_do_not_grow():
    app_dir = Path(__file__).resolve().parents[2] / "app"
    total = sum(
        path.read_text(encoding="utf-8").count("except Exception")
        for path in app_dir.rglob("*.py")
    )

    assert total <= MAX_BROAD_EXCEPTIONS, (
        f"except Exception 数量从 {MAX_BROAD_EXCEPTIONS} 增长到 {total}；"
        "请改用具体异常类型或统一错误码"
    )
