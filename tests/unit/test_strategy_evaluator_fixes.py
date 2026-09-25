"""strategy_evaluator 状态卫生修复回归（SE4/SE6）。"""
import json

from app.agent.strategy_evaluator import StrategyEvaluator


def _temp_files(directory):
    return [p for p in directory.iterdir() if p.suffix == ".tmp"]


def test_default_file_is_absolute_and_cwd_independent(tmp_path, monkeypatch):
    """SE6: 默认策略库路径固定，不再随进程 CWD 漂移。"""
    monkeypatch.chdir(tmp_path)

    evaluator = StrategyEvaluator()

    assert evaluator.strategies_file.is_absolute()
    assert evaluator.strategies_file.parent.name == "data"


def test_save_is_atomic_and_leaves_no_temp(tmp_path):
    """原子写：落盘内容可解析，且不残留临时文件。"""
    strategies_file = tmp_path / "strategies.json"
    evaluator = StrategyEvaluator(strategies_file=strategies_file)

    evaluator.create_or_update_strategy("NameError", "fix it")

    assert strategies_file.exists()
    assert json.loads(strategies_file.read_text(encoding="utf-8"))
    assert _temp_files(tmp_path) == []


def test_save_failure_preserves_previous_file(tmp_path, monkeypatch, capsys):
    """写盘失败时保留上一版文件、清理临时文件、且不向 stdout 打印。"""
    strategies_file = tmp_path / "strategies.json"
    evaluator = StrategyEvaluator(strategies_file=strategies_file)
    evaluator.create_or_update_strategy("NameError", "first")
    before = strategies_file.read_text(encoding="utf-8")

    import app.agent.strategy_evaluator as mod

    def fail_replace(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(mod.os, "replace", fail_replace)
    evaluator.create_or_update_strategy("TypeError", "second")

    assert strategies_file.read_text(encoding="utf-8") == before
    assert _temp_files(tmp_path) == []
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_save_and_load_do_not_write_stdout(tmp_path, capsys):
    """SE4: 保存/加载走 logger，不再 print 污染 stdout（SSE 输出流）。"""
    strategies_file = tmp_path / "strategies.json"
    StrategyEvaluator(strategies_file=strategies_file).create_or_update_strategy(
        "NameError", "tpl"
    )
    # 从同一文件加载，覆盖 _load_strategies 成功路径
    StrategyEvaluator(strategies_file=strategies_file)
    # 损坏文件覆盖 _load_strategies 异常路径
    strategies_file.write_text("{ not json", encoding="utf-8")
    StrategyEvaluator(strategies_file=strategies_file)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
